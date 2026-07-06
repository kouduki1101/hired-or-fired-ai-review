from aios_common.config import Settings
from aios_common.errors import NoDeleteError, PhaseLockedError


def test_settings_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.default_ema_alpha == 0.1
    assert s.default_cycle_interval_seconds == 300


def test_error_catalog_codes() -> None:
    assert PhaseLockedError().code == "phase_locked"
    assert PhaseLockedError().status == 409
    assert NoDeleteError().status == 405
