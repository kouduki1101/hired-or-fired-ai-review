"""P1デモストア: CohortRuntime(インメモリ)+FakeAdapterで制御ループ一式をAPIから体験できる。

P2でpackages/storage(PostgreSQL)ベースの実装に置換する。境界:
- get_cohort / create_cohort / list_cohorts のシグネチャを維持する
- ルータはCohortRuntimeの内部構造に触れず、この層の関数を経由する
"""

from __future__ import annotations

import numpy as np
from aios_adapters.fake import FakeAgentAdapter
from aios_adapters.spi import ModelConfig
from aios_adapters.training_fake import FakeTrainer
from aios_core.types import HealthThresholds
from aios_orchestrator.cycle import CycleResult
from aios_orchestrator.persistence import load_cohort, save_cohort
from aios_orchestrator.runtime import CohortRuntime, hatch_cohort
from aios_orchestrator.training import TrainingCoordinator
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aios_api.auth import current_tenant
from aios_api.notify import Notifier

DEMO_DIM = 16
DEMO_THRESHOLDS = HealthThresholds(lower=0.05, upper=1.2, hysteresis_cycles=2)


def _restore_fake_adapter(index: int, config: ModelConfig) -> FakeAgentAdapter:
    """rehydrate: スナップショットのcontext_vector(挙動)からFakeAdapterを再構成。"""
    assert config.context_vector is not None
    return FakeAgentAdapter(behavior=np.asarray(config.context_vector), seed=index)


class DemoStore:
    def __init__(self) -> None:
        self._cohorts: dict[str, CohortRuntime] = {}
        self._names: dict[str, str] = {}  # cohort_id -> 表示名
        self._task_counts: dict[str, dict[str, int]] = {}  # cohort_id -> slot_id -> count
        self._last_cycle: dict[str, CycleResult] = {}
        self._task_records: dict[str, dict] = {}  # task_id -> リネージ記録(FR-GV-01)
        self._loop_states: dict[str, str] = {}  # cohort_id -> RUNNING/PAUSED/DRY_RUN
        self._cycle_history: dict[str, list[dict]] = {}  # cohort_id -> サイクル時系列
        self.notifier = Notifier()  # Webhook配送(FR-EX-01)
        self._sessionmaker: async_sessionmaker | None = None  # DB配線(任意)
        self._tenants: dict[str, str] = {}  # cohort_id -> tenant(FR-TN-01)
        self._approvals: dict[str, dict] = {}  # 承認キュー(FR-GV-05)
        self._usage: dict[str, dict[str, int]] = {}  # 使用量カウンタ(FR-TN-03)
        # 学習系Rehatch調停(P5)。ジョブ状態はプロセス内(再起動で中断中ジョブは破棄)。
        # 既定はFakeTrainer。本番はTrainer Protocolを満たす実蒸留/LoRAへ差替。
        self.training = TrainingCoordinator(FakeTrainer())

    # --- 永続化配線(AIOS_DATABASE_URL設定時のみ有効) ---
    def attach_db(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    def clear_memory(self) -> None:
        """テスト・再起動シミュレーション用: インメモリ状態のみ破棄(DBは保持)。"""
        self._cohorts.clear()
        self._names.clear()
        self._task_counts.clear()
        self._last_cycle.clear()
        self._task_records.clear()
        self._loop_states.clear()
        self._cycle_history.clear()
        self._tenants.clear()
        self._approvals.clear()
        self._usage.clear()
        self.training = TrainingCoordinator(FakeTrainer())

    async def persist(self, cohort_id: str) -> None:
        """コホート状態をDBへ保存(未配線時はno-op)。"""
        if self._sessionmaker is None:
            return
        cohort = self.get_cohort(cohort_id)
        async with self._sessionmaker() as session, session.begin():
            await save_cohort(
                session,
                cohort,
                tenant_id=self.tenant_of(cohort_id),
                display_name=self._names.get(cohort_id),
            )

    async def rehydrate_all(self) -> int:
        """DBに保存済みの全コホートを復元する(起動時)。"""
        if self._sessionmaker is None:
            return 0
        from aios_storage.models import CohortRow

        restored = 0
        async with self._sessionmaker() as session:
            rows = (await session.scalars(select(CohortRow))).all()
            for row in rows:
                if row.cohort_id in self._cohorts:
                    continue
                cohort = await load_cohort(
                    session, row.cohort_id, _restore_fake_adapter, tenant_id=row.tenant_id
                )
                self._cohorts[cohort.cohort_id] = cohort
                self._tenants[cohort.cohort_id] = row.tenant_id
                self._names[cohort.cohort_id] = row.name
                self._task_counts[cohort.cohort_id] = {s.slot_id: 0 for s in cohort.slots}
                restored += 1
        return restored

    # --- 表示名 ---
    def set_name(self, cohort_id: str, name: str) -> None:
        self._names[cohort_id] = name

    def name(self, cohort_id: str) -> str:
        return self._names.get(cohort_id, "")

    # --- 承認キュー(FR-GV-05) ---
    def add_approval(self, *, cohort_id: str, action_type: str, payload: dict) -> str:
        import uuid
        from datetime import UTC, datetime

        # 同一アクションの保留が既にあれば重複登録しない(サイクル毎の再選定対策)
        for existing in self._approvals.values():
            if (
                existing["status"] == "pending"
                and existing["cohort_id"] == cohort_id
                and existing["action_type"] == action_type
                and existing["payload"] == payload
            ):
                return existing["approval_id"]

        approval_id = str(uuid.uuid4())
        self._approvals[approval_id] = {
            "approval_id": approval_id,
            "tenant": self.tenant_of(cohort_id),
            "cohort_id": cohort_id,
            "action_type": action_type,  # 'rehatch' | 'dimension_expansion'
            "payload": payload,
            "status": "pending",
            "requested_at": datetime.now(UTC).isoformat(),
            "decided_at": None,
        }
        return approval_id

    def get_approval(self, approval_id: str) -> dict:
        approval = self._approvals.get(approval_id)
        if approval is None or approval.get("tenant", "default") != current_tenant.get():
            raise HTTPException(status_code=404, detail="approval not found")
        return approval

    def list_approvals(self, status: str | None = None) -> list[dict]:
        tenant = current_tenant.get()
        return [
            a for a in self._approvals.values()
            if a.get("tenant", "default") == tenant
            and (status is None or a["status"] == status)
        ]

    # --- 使用量メータリング(FR-TN-03) ---
    def bump_usage(self, cohort_id: str, key: str, amount: int = 1) -> None:
        counters = self._usage.setdefault(cohort_id, {})
        counters[key] = counters.get(key, 0) + amount

    def usage(self) -> list[dict]:
        out = []
        tenant = current_tenant.get()
        for cohort_id, cohort in self._cohorts.items():
            if self.tenant_of(cohort_id) != tenant:
                continue
            counters = self._usage.get(cohort_id, {})
            out.append(
                {
                    "cohort_id": cohort_id,
                    "name": self.name(cohort_id),
                    "slot_count": len(cohort.slots),
                    "cycles_run": counters.get("cycles_run", 0),
                    "tasks_processed": counters.get("tasks_processed", 0),
                    "probes_executed": counters.get("probes_executed", 0),
                    "rehatches_committed": counters.get("rehatches_committed", 0),
                }
            )
        return out

    def create_cohort(self, *, name: str, slot_count: int, ema_alpha: float) -> CohortRuntime:
        rng = np.random.default_rng(abs(hash(name)) % (2**32))
        t0 = rng.normal(size=DEMO_DIM)
        cohort = hatch_cohort(
            adapter_factory=lambda i, seed_vec: FakeAgentAdapter(behavior=seed_vec, seed=i),
            slot_count=slot_count,
            initial_tv=t0,
            thresholds=DEMO_THRESHOLDS,
            diversity=0.4,
            seed=42,
            ema_alpha=ema_alpha,
        )
        self._cohorts[cohort.cohort_id] = cohort
        self._tenants[cohort.cohort_id] = current_tenant.get()
        self._task_counts[cohort.cohort_id] = {s.slot_id: 0 for s in cohort.slots}
        return cohort

    def tenant_of(self, cohort_id: str) -> str:
        return self._tenants.get(cohort_id, "default")

    def get_cohort(self, cohort_id: str) -> CohortRuntime:
        cohort = self._cohorts.get(cohort_id)
        # 他テナントのリソースは「存在しない」扱い(情報漏えい防止、NFR-SE-02)
        if cohort is None or self.tenant_of(cohort_id) != current_tenant.get():
            raise HTTPException(status_code=404, detail="cohort not found")
        return cohort

    def list_cohorts(self) -> list[CohortRuntime]:
        tenant = current_tenant.get()
        return [c for cid, c in self._cohorts.items() if self.tenant_of(cid) == tenant]

    # --- タスク割当シェア(支配的モデル検出の入力) ---
    def record_assignment(self, cohort_id: str, slot_id: str) -> None:
        counts = self._task_counts[cohort_id]
        counts[slot_id] = counts.get(slot_id, 0) + 1
        total = sum(counts.values())
        for s in self.get_cohort(cohort_id).slots:
            s.assign_share = counts.get(s.slot_id, 0) / total if total else 0.0

    # --- 制御サイクル結果(最新+履歴。履歴はダッシュボードのトレンド入力) ---
    def set_last_cycle(self, cohort_id: str, result: CycleResult) -> None:
        self._last_cycle[cohort_id] = result
        cohort = self.get_cohort(cohort_id)
        history = self._cycle_history.setdefault(cohort_id, [])
        history.append(
            {
                "step_no": result.step_no,
                "health": str(result.health),
                "dissipation": None if result.dissipation != result.dissipation
                else result.dissipation,  # NaN→None
                "fitness_mean": None if result.fitness_mean != result.fitness_mean
                else result.fitness_mean,
                "lr_correction": result.lr_correction,
                "noise_amount": result.noise_amount,
                "rehatched": [
                    {"slot_id": o.slot_id, "reason": o.reason, "committed": o.committed}
                    for o in result.rehatched
                ],
                "quarantined": [
                    {"slot_id": q.slot_id, "label": q.label} for q in result.quarantined
                ],
                "slots": [
                    {"display_id": s.display_id, "fitness": s.fitness_hat}
                    for s in cohort.slots
                ],
            }
        )
        del history[:-200]  # 直近200サイクルのみ保持(P2のPostgreSQL化で全履歴へ)

    def last_cycle(self, cohort_id: str) -> CycleResult | None:
        return self._last_cycle.get(cohort_id)

    def cycle_history(self, cohort_id: str) -> list[dict]:
        return self._cycle_history.get(cohort_id, [])

    # --- タスクリネージ記録(FR-GV-01: 担当時点の世代・判断・制御値を固定) ---
    def record_task(self, task_id: str, record: dict) -> None:
        self._task_records[task_id] = record

    def get_task(self, task_id: str) -> dict:
        record = self._task_records.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task not found")
        return record

    # --- ループ制御(FR-LC-03) ---
    def loop_state(self, cohort_id: str) -> str:
        return self._loop_states.get(cohort_id, "RUNNING")

    def set_loop_state(self, cohort_id: str, state: str) -> None:
        self._loop_states[cohort_id] = state

    def find_cohort_by_slot(self, slot_id: str) -> CohortRuntime:
        tenant = current_tenant.get()
        for cid, cohort in self._cohorts.items():
            if self.tenant_of(cid) == tenant and any(
                s.slot_id == slot_id for s in cohort.slots
            ):
                return cohort
        raise HTTPException(status_code=404, detail="slot not found")


STORE = DemoStore()
