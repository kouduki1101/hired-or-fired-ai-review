"""構造化 JSON ログ(NFR-OP-01)。

- 1 行 1 JSON。ts / level / logger / event + 任意フィールド。
- OpenTelemetry の現在スパンがあれば trace_id / span_id を自動付与し、
  ログとトレースを相関できるようにする。
- 依存追加なし(標準 logging + json)。

使い方:
    from aios_api.logging_config import log_event
    log_event("cycle.completed", cohort_id=cid, step_no=42, health="STABLE")
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import IO, Any

from opentelemetry import trace

_LOGGER_NAME = "aios"
log = logging.getLogger(_LOGGER_NAME)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        extra = getattr(record, "aios_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx is not None and ctx.is_valid:
            payload["trace_id"] = format(ctx.trace_id, "032x")
            payload["span_id"] = format(ctx.span_id, "016x")

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", stream: IO[str] | None = None) -> logging.Logger:
    """`aios` ロガーに JSON ハンドラを設定する(冪等)。"""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    log.handlers = [handler]
    log.setLevel(level)
    log.propagate = False
    return log


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """構造化イベントを1件出力する。"""
    log.log(level, event, extra={"aios_fields": fields})
