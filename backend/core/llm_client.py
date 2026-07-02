from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from .config import Settings, get_settings
from .logging import get_logger

logger = get_logger("llm")

_mistral_singleton: Any = None


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for chunk in content:
        text = getattr(chunk, "text", None)
        if text is None and isinstance(chunk, dict):
            text = chunk.get("text")
        if text:
            parts.append(text)
    return "".join(parts)


def _get_mistral(settings: Settings) -> Any:
    global _mistral_singleton
    if _mistral_singleton is None:
        from mistralai.client import Mistral

        if not settings.mistral_api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY manquante. Ajoutez-la dans backend/.env "
                "(voir backend/.env.example)."
            )
        _mistral_singleton = Mistral(api_key=settings.mistral_api_key)
    return _mistral_singleton


class LLMClient(ABC):
    @abstractmethod
    def complete_text(
        self, system: str, messages: list[dict[str, str]], max_tokens: int = 1024
    ) -> str:
        ...

    @abstractmethod
    def complete_json(
        self, system: str, user: str, schema: dict, schema_name: str = "output"
    ) -> dict:
        ...


class MistralLLMClient(LLMClient):
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = _get_mistral(self._settings)
        self._model = self._settings.mistral_model

    def complete_text(
        self, system: str, messages: list[dict[str, str]], max_tokens: int = 1024
    ) -> str:
        full = [{"role": "system", "content": system}, *messages]
        resp = self._client.chat.complete(
            model=self._model, messages=full, max_tokens=max_tokens
        )
        return _content_to_text(resp.choices[0].message.content).strip()

    def complete_json(
        self, system: str, user: str, schema: dict, schema_name: str = "output"
    ) -> dict:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            resp = self._client.chat.complete(
                model=self._model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "schema": schema,
                        "strict": True,
                    },
                },
            )
            return json.loads(_content_to_text(resp.choices[0].message.content))
        except Exception as exc:  # noqa: BLE001
            logger.warning("json_schema indisponible (%s), repli sur json_object", type(exc).__name__)
            guided_system = (
                system
                + "\n\nRéponds UNIQUEMENT avec un objet JSON valide respectant ce schéma "
                + "(pas de texte autour) :\n"
                + json.dumps(schema, ensure_ascii=False)
            )
            resp = self._client.chat.complete(
                model=self._model,
                messages=[
                    {"role": "system", "content": guided_system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
            )
            return json.loads(_content_to_text(resp.choices[0].message.content))


class OllamaLLMClient(LLMClient):
    def __init__(self) -> None:
        self._settings = get_settings()
        self._base = self._settings.ollama_base_url.rstrip("/")
        self._model = self._settings.ollama_model

    def _chat(self, messages: list[dict[str, str]], fmt: Any = None, num_predict: int | None = None) -> str:
        import httpx

        payload: dict[str, Any] = {"model": self._model, "messages": messages, "stream": False}
        if fmt is not None:
            payload["format"] = fmt
        if num_predict is not None:
            payload["options"] = {"num_predict": num_predict}
        with httpx.Client(timeout=300.0) as http:
            resp = http.post(f"{self._base}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    def complete_text(
        self, system: str, messages: list[dict[str, str]], max_tokens: int = 1024
    ) -> str:
        full = [{"role": "system", "content": system}, *messages]
        return self._chat(full, num_predict=max_tokens).strip()

    def complete_json(
        self, system: str, user: str, schema: dict, schema_name: str = "output"
    ) -> dict:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            return json.loads(self._chat(messages, fmt=schema))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama format=schema indisponible (%s), repli sur format=json", type(exc).__name__)
            guided = (
                system
                + "\n\nRéponds UNIQUEMENT avec un objet JSON valide respectant ce schéma "
                + "(aucun texte autour) :\n"
                + json.dumps(schema, ensure_ascii=False)
            )
            content = self._chat(
                [{"role": "system", "content": guided}, {"role": "user", "content": user}],
                fmt="json",
            )
            return json.loads(content)


def get_llm_client() -> LLMClient:
    provider = get_settings().llm_provider.lower()
    if provider == "mistral":
        return MistralLLMClient()
    if provider == "ollama":
        return OllamaLLMClient()
    raise ValueError(
        f"LLM_PROVIDER='{provider}' non supporté (mistral | ollama). Implémentez une "
        "sous-classe de LLMClient et ajoutez-la ici."
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    settings = get_settings()
    provider = settings.embed_provider.lower()
    if provider == "mistral":
        return _mistral_embed(texts, settings)
    if provider == "ollama":
        return _ollama_embed(texts, settings)
    raise ValueError(f"EMBED_PROVIDER='{provider}' non supporté (mistral | ollama).")


def _mistral_embed(texts: list[str], settings: Settings) -> list[list[float]]:
    client = _get_mistral(settings)
    resp = client.embeddings.create(model=settings.mistral_embed_model, inputs=texts)
    return [d.embedding for d in resp.data]


def _ollama_embed(texts: list[str], settings: Settings) -> list[list[float]]:
    import httpx

    vectors: list[list[float]] = []
    with httpx.Client(timeout=60.0) as http:
        for text in texts:
            resp = http.post(
                f"{settings.ollama_base_url}/api/embeddings",
                json={"model": settings.ollama_embed_model, "prompt": text},
            )
            resp.raise_for_status()
            vectors.append(resp.json()["embedding"])
    return vectors
