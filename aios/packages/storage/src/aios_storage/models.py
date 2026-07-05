"""SQLAlchemyモデル(docs/04_data_model.md のDDLに対応)。

- ベクトル列は VectorColumn 型: PostgreSQLでは pgvector、その他(テスト用SQLite)ではJSON
- slots への削除操作はリポジトリ層に存在しない(No-Delete by Design)。
  PostgreSQL本番ではさらに REVOKE DELETE / FK RESTRICT を適用する(infra側)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class VectorColumn(TypeDecorator):
    """PostgreSQL: pgvector / その他: JSON(list[float])。

    アプリ層とは常に list[float] で受け渡す(NumPy変換はリポジトリの外)。
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector  # optional dependency

            return dialect.type_descriptor(Vector())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return [float(x) for x in value]


# SQLiteは INTEGER PRIMARY KEY のみ自動採番のため方言バリアントを使う
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class CohortRow(Base):
    __tablename__ = "cohorts"

    cohort_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phase: Mapped[str] = mapped_column(String(20), default="INITIALIZING")
    slot_count: Mapped[int] = mapped_column(Integer)
    tv_dimension: Mapped[int] = mapped_column(Integer, default=1536)
    ema_alpha: Mapped[float] = mapped_column(Float, default=0.1)
    loop_state: Mapped[str] = mapped_column(String(20), default="RUNNING")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SlotRow(Base):
    """スロット投影(明細書 図7)。正はslot_events(イベントソーシング)。"""

    __tablename__ = "slots"
    __table_args__ = (UniqueConstraint("cohort_id", "display_id"),)

    slot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    cohort_id: Mapped[str] = mapped_column(
        ForeignKey("cohorts.cohort_id", ondelete="RESTRICT"), index=True
    )
    display_id: Mapped[str] = mapped_column(String(10))
    generation: Mapped[int] = mapped_column(Integer, default=0)
    adapter_kind: Mapped[str] = mapped_column(String(50))
    current_snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    rehatch_lock: Mapped[bool] = mapped_column(Boolean, default=False)
    role_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    maturity: Mapped[int] = mapped_column(BigInteger, default=0)
    fitness: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_rehatch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SlotEventRow(Base):
    """追記専用イベントストア(ハッシュチェーン)。UPDATE/DELETEは発行しない。"""

    __tablename__ = "slot_events"

    event_id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    slot_id: Mapped[str] = mapped_column(
        ForeignKey("slots.slot_id", ondelete="RESTRICT"), index=True
    )
    cohort_id: Mapped[str] = mapped_column(String(36), index=True)
    cycle_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40))
    generation: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TeacherVectorRow(Base):
    """第1の指標の時系列(追記のみ)。"""

    __tablename__ = "teacher_vectors"

    tv_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cohort_id: Mapped[str] = mapped_column(String(36), index=True)
    cycle_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    dimension: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list] = mapped_column(VectorColumn)
    nl_directive: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40))  # ema_update / initial / dimension_expansion
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CohortCycleRow(Base):
    """制御サイクル結果(明細書 図8 指標管理データ)。"""

    __tablename__ = "cohort_cycles"
    __table_args__ = (UniqueConstraint("cohort_id", "step_no"),)

    cycle_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cohort_id: Mapped[str] = mapped_column(String(36), index=True)
    step_no: Mapped[int] = mapped_column(BigInteger)
    tv_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    dissipation: Mapped[float | None] = mapped_column(Float, nullable=True)
    dissipation_algo: Mapped[str] = mapped_column(String(40), default="output_embedding")
    health: Mapped[str] = mapped_column(String(10))
    lr_correction: Mapped[float] = mapped_column(Float, default=1.0)
    noise_amount: Mapped[float] = mapped_column(Float, default=0.0)
    fitness_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    rehatch_count: Mapped[int] = mapped_column(Integer, default=0)
    probe_missing: Mapped[int] = mapped_column(Integer, default=0)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    decisions: Mapped[dict] = mapped_column(JSON, default=dict)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ModelSnapshotRow(Base):
    """世代ごとの構成スナップショット(ロールバック・リネージ用)。"""

    __tablename__ = "model_snapshots"
    __table_args__ = (UniqueConstraint("slot_id", "generation"),)

    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slot_id: Mapped[str] = mapped_column(String(36), index=True)
    generation: Mapped[int] = mapped_column(Integer)
    adapter_kind: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict] = mapped_column(JSON)  # ModelConfig(広義の内部パラメータ)
    params_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(60))  # hatchery / rehatch:<strategy> / rollback
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KnowledgeArchiveRow(Base):
    """知識継承用データ(明細書 図9)。削除せずstorage_tierで退避。"""

    __tablename__ = "knowledge_archives"

    archive_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cohort_id: Mapped[str] = mapped_column(String(36), index=True)
    # elite_model / trend_mean / stabilization_snapshot
    kind: Mapped[str] = mapped_column(String(40))
    source_slot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tv_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    params_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    distill_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    storage_tier: Mapped[str] = mapped_column(String(10), default="hot")
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TaskRecordRow(Base):
    """タスクとリネージ(担当時点の世代・TVを固定記録)。"""

    __tablename__ = "task_records"
    __table_args__ = (UniqueConstraint("cohort_id", "idempotency_key"),)

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    cohort_id: Mapped[str] = mapped_column(String(36), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    task_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    slot_id: Mapped[str] = mapped_column(String(36), index=True)
    generation: Mapped[int] = mapped_column(Integer)  # ★担当時点の世代(リネージの要)
    tv_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cycle_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    routing_reason: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
