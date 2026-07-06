"""アプリケーション設定(pydantic-settings)。

環境変数プレフィクス AIOS_。docker-compose / Helm values から注入する。
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIOS_", env_file=".env", extra="ignore")

    env: str = "dev"  # dev / staging / prod
    database_url: str = "postgresql+asyncpg://aios:aios@localhost:5432/aios"
    redis_url: str = "redis://localhost:6379/0"
    object_store_endpoint: str = "http://localhost:9000"
    object_store_bucket: str = "aios"

    # 認証(P0: 静的APIキー。P4でOIDC/SSOへ拡張)
    api_keys: list[str] = []

    # 制御ループ既定値(コホート個別設定で上書き可)
    default_cycle_interval_seconds: int = 300
    default_ema_alpha: float = 0.1


def get_settings() -> Settings:
    return Settings()
