"""AIOS 高水準クライアント(同期API)。

- 認証: X-API-Key ヘッダ(FR-TN-02)
- エラー: 非2xxは AiosApiError(status, aios_code, detail)
- transport 注入可(テスト・ASGI直結用)
"""

from __future__ import annotations

from typing import Any

import httpx

DEFAULT_TIMEOUT = 30.0


class AiosApiError(Exception):
    def __init__(self, status: int, detail: str, aios_code: str | None = None) -> None:
        super().__init__(f"[{status}] {aios_code or 'error'}: {detail}")
        self.status = status
        self.detail = detail
        self.aios_code = aios_code


class Client:
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"X-API-Key": api_key} if api_key else {}
        self._http = httpx.Client(
            base_url=base_url, headers=headers, timeout=timeout, transport=transport
        )
        self.cohorts = _Cohorts(self)
        self.lineage = _Lineage(self)
        self.approvals = _Approvals(self)
        self.proposals = _Proposals(self)
        self.admin = _Admin(self)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- 低水準 ---
    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        res = self._http.request(method, path, **kwargs)
        if res.status_code >= 400:
            code, detail = None, res.text
            try:
                body = res.json()
                code = body.get("aios_code")
                detail = body.get("detail", detail)
            except ValueError:
                pass
            raise AiosApiError(res.status_code, str(detail), code)
        if res.headers.get("content-type", "").startswith("application/x-ndjson"):
            return res.text
        return res.json() if res.content else None

    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self.request("POST", path, **kw)


class CohortHandle:
    """単一コホートに対する操作(docs/05 §4 の `cohort.` 名前空間)。"""

    def __init__(self, client: Client, cohort_id: str) -> None:
        self._c = client
        self.cohort_id = cohort_id
        self.tasks = _Tasks(client, cohort_id)

    def get(self) -> dict[str, Any]:
        return self._c.get(f"/v1/cohorts/{self.cohort_id}")

    # --- 指標・制御ループ ---
    def metrics(self) -> dict[str, Any]:
        return self._c.get(f"/v1/cohorts/{self.cohort_id}/metrics/current")

    def metrics_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._c.get(
            f"/v1/cohorts/{self.cohort_id}/metrics/history", params={"limit": limit}
        )

    def run_cycle(self, dry_run: bool = False) -> dict[str, Any]:
        return self._c.post(
            f"/v1/cohorts/{self.cohort_id}/cycles/run", params={"dry_run": dry_run}
        )

    def pause(self) -> dict[str, Any]:
        return self._c.post(f"/v1/cohorts/{self.cohort_id}/loop", json={"action": "pause"})

    def resume(self) -> dict[str, Any]:
        return self._c.post(f"/v1/cohorts/{self.cohort_id}/loop", json={"action": "resume"})

    # --- スロット操作 ---
    def set_slot_lock(self, slot_id: str, locked: bool) -> dict[str, Any]:
        return self._c.request(
            "PUT",
            f"/v1/cohorts/{self.cohort_id}/slots/{slot_id}/lock",
            json={"rehatch_lock": locked},
        )

    def quarantine(self, slot_id: str) -> dict[str, Any]:
        return self._c.post(f"/v1/cohorts/{self.cohort_id}/slots/{slot_id}/quarantine")

    def restore(self, slot_id: str) -> dict[str, Any]:
        return self._c.post(f"/v1/cohorts/{self.cohort_id}/slots/{slot_id}/restore")

    # --- 安全境界(FR-SF) ---
    def register_negative_centroid(
        self,
        label: str,
        *,
        examples: list[list[float]] | None = None,
        vector: list[float] | None = None,
        threshold: float = 0.85,
    ) -> dict[str, Any]:
        return self._c.post(
            f"/v1/cohorts/{self.cohort_id}/safety/negative-centroids",
            json={
                "label": label,
                "examples": examples,
                "vector": vector,
                "threshold": threshold,
            },
        )

    # --- 次元拡張(請求項9) ---
    def expand_dimension(self, added_dims: int, axis_labels: list[str]) -> dict[str, Any]:
        return self._c.post(
            f"/v1/cohorts/{self.cohort_id}/scaling/expand",
            json={"added_dims": added_dims, "axis_labels": axis_labels},
        )

    # --- 監査エクスポート(FR-GV-03) ---
    def export_audit(self) -> str:
        """全運用履歴のNDJSON(各行にprev_hash/hash)。"""
        return self._c.get(f"/v1/lineage/export/{self.cohort_id}")

    def export_manifest(self) -> dict[str, Any]:
        return self._c.get(f"/v1/lineage/export/{self.cohort_id}/manifest")


class _Cohorts:
    def __init__(self, client: Client) -> None:
        self._c = client

    def create(
        self,
        name: str,
        slot_count: int,
        *,
        approval_mode: str = "auto",
        ema_alpha: float = 0.1,
    ) -> CohortHandle:
        body = self._c.post(
            "/v1/cohorts",
            json={
                "name": name,
                "slot_count": slot_count,
                "approval_mode": approval_mode,
                "ema_alpha": ema_alpha,
            },
        )
        return CohortHandle(self._c, body["cohort_id"])

    def list(self) -> list[dict[str, Any]]:
        return self._c.get("/v1/cohorts")

    def get(self, cohort_id: str) -> CohortHandle:
        return CohortHandle(self._c, cohort_id)


class _Tasks:
    def __init__(self, client: Client, cohort_id: str) -> None:
        self._c = client
        self._cohort_id = cohort_id

    def run(
        self,
        *,
        messages: list[dict[str, Any]] | None = None,
        input: dict[str, Any] | None = None,
        importance: str = "normal",
        difficulty: str = "normal",
        category: str | None = None,
    ) -> dict[str, Any]:
        payload = input if input is not None else {"messages": messages or []}
        return self._c.post(
            f"/v1/cohorts/{self._cohort_id}/tasks",
            json={
                "input": payload,
                "metadata": {
                    "importance": importance,
                    "difficulty": difficulty,
                    "category": category,
                },
            },
        )


class _Lineage:
    def __init__(self, client: Client) -> None:
        self._c = client

    def task(self, task_id: str) -> dict[str, Any]:
        """開示請求応答(¶0224-0226): 担当スロット・世代・由来+説明文。"""
        return self._c.get(f"/v1/lineage/tasks/{task_id}")

    def slot_history(self, slot_id: str) -> dict[str, Any]:
        return self._c.get(f"/v1/lineage/slots/{slot_id}/history")


class _Approvals:
    def __init__(self, client: Client) -> None:
        self._c = client

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        params = {"status": status} if status else {}
        return self._c.get("/v1/approvals", params=params)

    def approve(self, approval_id: str, comment: str = "") -> dict[str, Any]:
        return self._c.post(f"/v1/approvals/{approval_id}/approve", json={"comment": comment})

    def reject(self, approval_id: str, comment: str = "") -> dict[str, Any]:
        return self._c.post(f"/v1/approvals/{approval_id}/reject", json={"comment": comment})


class _Proposals:
    def __init__(self, client: Client) -> None:
        self._c = client

    def submit(
        self, slot_id: str, kind: str, rationale: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """エージェント自律提案(FR-GV-04)。kind: rehatch_request | role_change"""
        return self._c.post(
            "/v1/proposals",
            json={"slot_id": slot_id, "kind": kind, "rationale": rationale or {}},
        )


class _Admin:
    def __init__(self, client: Client) -> None:
        self._c = client

    def register_webhook(
        self, url: str, secret: str, events: list[str] | None = None
    ) -> dict[str, Any]:
        return self._c.post(
            "/v1/admin/webhooks", json={"url": url, "secret": secret, "events": events}
        )

    def usage(self) -> dict[str, Any]:
        return self._c.get("/v1/admin/usage")
