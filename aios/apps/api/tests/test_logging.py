"""構造化 JSON ログ(NFR-OP-01)の検証。"""

from __future__ import annotations

import io
import json

from aios_api.logging_config import configure_logging, log_event


def test_log_event_is_json_with_fields() -> None:
    buf = io.StringIO()
    configure_logging("INFO", stream=buf)
    log_event("cycle.completed", cohort_id="c1", step_no=7, health="STABLE")

    line = buf.getvalue().strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["event"] == "cycle.completed"
    assert rec["level"] == "INFO"
    assert rec["logger"] == "aios"
    assert rec["cohort_id"] == "c1"
    assert rec["step_no"] == 7
    assert rec["health"] == "STABLE"
    assert "ts" in rec


def test_debug_suppressed_at_info_level() -> None:
    import logging

    buf = io.StringIO()
    configure_logging("INFO", stream=buf)
    log_event("verbose.detail", level=logging.DEBUG, x=1)
    assert buf.getvalue().strip() == ""
