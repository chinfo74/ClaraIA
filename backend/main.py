from __future__ import annotations

import secrets
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .core.config import ADMIN_DIR, WIDGET_DIR, get_settings
from .core.logging import get_logger, log_event, read_logs
from .rag.ingestion import IngestResult, get_document, ingest_file, list_documents
from .rag.vectorstore import get_vectorstore, search
from .session.store import get_session_store
from .agents.manager import handle as handle_chat

logger = get_logger("api")
settings = get_settings()

app = FastAPI(title="Clara API", version="6.0.0-step1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

templates = Jinja2Templates(directory=str(ADMIN_DIR / "templates"))
app.mount("/admin/static", StaticFiles(directory=str(ADMIN_DIR / "static")), name="admin-static")
app.mount("/widget", StaticFiles(directory=str(WIDGET_DIR), html=True), name="widget")

ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}

_security = HTTPBasic(auto_error=True)


def require_admin(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Back-office non configuré : définissez ADMIN_PASSWORD dans backend/.env.",
        )
    ok_user = secrets.compare_digest(credentials.username, settings.admin_user)
    ok_pass = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté ({suffix}). Acceptés : PDF, DOCX, TXT.",
        )
    dest = Path(settings.uploads_dir) / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(upload.file.read())
    return dest


def _ingest_upload(file: UploadFile) -> IngestResult:
    saved = _save_upload(file)
    try:
        return ingest_file(saved, file.filename or saved.name)
    finally:
        if not settings.keep_uploads:
            saved.unlink(missing_ok=True)
            log_event(logger, "upload.discarded", filename=file.filename)


@app.post("/api/ingest", dependencies=[Depends(require_admin)])
async def api_ingest(file: UploadFile = File(...)) -> JSONResponse:
    result = _ingest_upload(file)
    status_code = 200 if result.status == "success" else 422
    return JSONResponse(result.to_dict(), status_code=status_code)


@app.get("/api/documents", dependencies=[Depends(require_admin)])
async def api_documents() -> list[dict]:
    return list_documents()


@app.get("/api/documents/{document_id}/markdown", dependencies=[Depends(require_admin)])
async def api_document_markdown(document_id: str) -> dict:
    doc = get_document(document_id)
    if not doc or not doc.get("md_path") or not Path(doc["md_path"]).exists():
        raise HTTPException(status_code=404, detail="Document ou .md introuvable.")
    return {"document_id": document_id, "markdown": Path(doc["md_path"]).read_text(encoding="utf-8")}


@app.get("/api/search", dependencies=[Depends(require_admin)])
async def api_search(q: str, k: int = 5) -> dict:
    hits = search(q, n_results=k)
    return {
        "query": q,
        "results": [
            {"text": h.text, "score": h.score, "metadata": h.metadata} for h in hits
        ],
    }


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    actions: list[dict] = []
    sources: list[str] = []
    suggestions: list[str] = []


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    store = get_session_store()
    session = store.get_or_create(req.session_id)
    store.append(session.session_id, "user", req.message)
    try:
        result = handle_chat(req.message, session)
    except Exception:  # noqa: BLE001
        logger.exception("Erreur de traitement du chat")
        result = {
            "response": "Désolée, je rencontre un problème technique. Réessayez dans un instant, "
            "ou écrivez à service.client@voyagedo.fr.",
            "sources": [],
            "actions": [],
        }
    store.append(session.session_id, "assistant", result["response"])
    log_event(logger, "chat.reply", session_id=session.session_id, section=result.get("section"))
    return ChatResponse(
        response=result["response"],
        session_id=session.session_id,
        sources=result.get("sources", []),
        actions=result.get("actions", []),
        suggestions=result.get("suggestions", []),
    )


@app.get("/api/logs", dependencies=[Depends(require_admin)])
async def api_logs(limit: int = 200) -> list[dict]:
    return read_logs(limit=limit)


@app.get("/health")
async def health() -> dict:
    info: dict = {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "embed_provider": settings.embed_provider,
    }
    try:
        info["docs_indexed"] = get_vectorstore().count()
    except Exception as exc:  # noqa: BLE001
        info["status"] = "degraded"
        info["error"] = str(exc)
    return info


@app.get("/")
async def root() -> dict:
    return {"message": "Clara API (étape 1 — ingestion RAG)", "back_office": "/admin", "docs": "/docs"}


@app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def admin_home(request: Request) -> HTMLResponse:
    try:
        total = get_vectorstore().count()
    except Exception:  # noqa: BLE001
        total = None
    return templates.TemplateResponse(
        request,
        "documents.html",
        {"documents": list_documents(), "total_chunks": total},
    )


@app.post("/admin/upload", dependencies=[Depends(require_admin)])
async def admin_upload(file: UploadFile = File(...)) -> RedirectResponse:
    result = _ingest_upload(file)
    return RedirectResponse(url=f"/admin/document/{result.document_id}", status_code=303)


@app.get("/admin/document/{document_id}", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def admin_document(request: Request, document_id: str) -> HTMLResponse:
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable.")
    markdown = ""
    md_path = doc.get("md_path")
    if md_path and Path(md_path).exists():
        markdown = Path(md_path).read_text(encoding="utf-8")
    return templates.TemplateResponse(
        request, "document_detail.html", {"doc": doc, "markdown": markdown}
    )


@app.get("/admin/logs", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def admin_logs(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "logs.html", {"logs": read_logs(limit=300)}
    )
