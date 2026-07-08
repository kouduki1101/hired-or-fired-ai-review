"""学習系 Rehatch API(P5)の結合テスト。"""

from __future__ import annotations

from aios_api.main import create_app
from aios_api.store import STORE
from fastapi.testclient import TestClient


def _client() -> TestClient:
    STORE.clear_memory()
    return TestClient(create_app())


def test_submit_and_advance_to_commit() -> None:
    client = _client()
    cohort = client.post("/v1/cohorts", json={"name": "train", "slot_count": 4}).json()
    cid = cohort["cohort_id"]
    slot_id = cohort["slots"][0]["slot_id"]
    gen0 = cohort["slots"][0]["generation"]

    submit = client.post(
        f"/v1/cohorts/{cid}/slots/{slot_id}/rehatch/train",
        json={"strategy": "distillation", "max_steps": 3},
    )
    assert submit.status_code == 202
    job_id = submit.json()["job_id"]
    assert submit.json()["status"] in ("pending", "running")

    # 進捗しながら適用まで進める(冪等に advance を叩く)
    last = None
    for _ in range(10):
        last = client.post(
            f"/v1/cohorts/{cid}/slots/{slot_id}/rehatch/train/{job_id}/advance"
        ).json()
        if last["applied"]:
            break
    assert last is not None and last["applied"] is True
    assert last["committed"] is True
    assert last["generation"] == gen0 + 1

    # スロットの世代が上がっている(Rehatch-in-Place)
    slot = next(
        s for s in client.get(f"/v1/cohorts/{cid}").json()["slots"] if s["slot_id"] == slot_id
    )
    assert slot["generation"] == gen0 + 1


def test_duplicate_active_job_is_409() -> None:
    client = _client()
    cohort = client.post("/v1/cohorts", json={"name": "train2", "slot_count": 3}).json()
    cid = cohort["cohort_id"]
    slot_id = cohort["slots"][0]["slot_id"]
    first = client.post(
        f"/v1/cohorts/{cid}/slots/{slot_id}/rehatch/train", json={"max_steps": 5}
    )
    assert first.status_code == 202
    dup = client.post(
        f"/v1/cohorts/{cid}/slots/{slot_id}/rehatch/train", json={"max_steps": 5}
    )
    assert dup.status_code == 409


def test_train_unknown_slot_is_404() -> None:
    client = _client()
    cohort = client.post("/v1/cohorts", json={"name": "train3", "slot_count": 3}).json()
    cid = cohort["cohort_id"]
    res = client.post(f"/v1/cohorts/{cid}/slots/nope/rehatch/train", json={})
    assert res.status_code == 404
