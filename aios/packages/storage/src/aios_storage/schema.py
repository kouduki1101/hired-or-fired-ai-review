"""スキーマ初期化。

P1: create_all(開発・テスト用)。本番マイグレーションはAlembic導入(P2)で置換し、
その際も本モジュールのメタデータを単一の真実源とする。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from aios_storage.models import Base


async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
