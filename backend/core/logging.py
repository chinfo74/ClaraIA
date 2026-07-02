"""
Structured (JSON) logging for Clara.

Every event is written as one JSON object per line to `log_file`, and also to
stderr for local development. The back-office reads these lines back to display
the activity log.

PII rule: log *counts and statuses only* — never the sensitive content itself.
Use `log_event(logger, "pii.scrubbed", count=3)`, never the matched strings.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        data = getattr(record, "data", None)
        if isinstance(data, dict):
            payload.update(data)
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    settings = get_settings()
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("clara")
    root.setLevel(logging.INFO)
    root.propagate = False

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(_JsonFormatter())
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    )
    root.addHandler(stream_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(f"clara.{name}")


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **data: Any) -> None:
    """Emit a structured event. `data` must contain counts/ids/statuses only."""
    logger.log(level, event, extra={"data": data})


def read_logs(limit: int = 200) -> list[dict[str, Any]]:
    """Return the most recent structured log records (newest first) for the back-office."""
    settings = get_settings()
    path = Path(settings.log_file)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"event": line, "level": "RAW"})
    records.reverse()
    return records
