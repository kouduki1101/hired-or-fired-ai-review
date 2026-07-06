"""特許請求項の実施をAPI契約レベルで恒常保証するテスト(CI必須ゲート)。

- 請求項2: スロットは削除が許容されない管理単位 → DELETEルートの不存在
- 請求項10: 定常運用フェーズでの追加生成なし → スロット追加ルートの不存在
"""

from aios_api.main import create_app
from fastapi.routing import APIRoute


def _routes() -> list[APIRoute]:
    return [r for r in create_app().routes if isinstance(r, APIRoute)]


class TestNoDeleteByDesign:
    def test_no_delete_route_touches_slots_or_cohorts(self) -> None:
        """スロット・コホートに対するDELETEエンドポイントが存在しないこと。"""
        offenders = [
            r.path
            for r in _routes()
            if "DELETE" in r.methods and ("slot" in r.path or "cohort" in r.path)
        ]
        assert offenders == [], f"No-Delete違反ルート: {offenders}"

    def test_no_slot_creation_route(self) -> None:
        """スロットの追加生成ルートが存在しない(卵層=コホート作成時のみ、請求項10)。"""
        offenders = [
            r.path
            for r in _routes()
            if "POST" in r.methods and r.path.rstrip("/").endswith("/slots")
        ]
        assert offenders == [], f"卵層非再入違反ルート: {offenders}"


class TestCohortLifecycle:
    def test_create_cohort_generates_fixed_slots(self) -> None:
        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        res = client.post("/v1/cohorts", json={"name": "test", "slot_count": 5})
        assert res.status_code == 201
        body = res.json()
        assert body["phase"] == "OPERATING"
        assert len(body["slots"]) == 5
        # 表示IDは001からの固定連番
        assert [s["display_id"] for s in body["slots"]] == ["001", "002", "003", "004", "005"]

    def test_slot_count_bounds(self) -> None:
        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        assert client.post("/v1/cohorts", json={"name": "x", "slot_count": 1}).status_code == 422
        assert client.post("/v1/cohorts", json={"name": "x", "slot_count": 1001}).status_code == 422

    def test_rehatch_lock_toggle(self) -> None:
        """削除保護フラグ(図7)の設定契約。"""
        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        cohort = client.post("/v1/cohorts", json={"name": "t", "slot_count": 2}).json()
        slot = cohort["slots"][0]
        res = client.put(
            f"/v1/cohorts/{cohort['cohort_id']}/slots/{slot['slot_id']}/lock",
            json={"rehatch_lock": True},
        )
        assert res.status_code == 200
        assert res.json()["rehatch_lock"] is True
