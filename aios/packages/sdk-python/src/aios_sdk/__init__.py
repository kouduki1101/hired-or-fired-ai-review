"""AIOS Python SDK(docs/05 §4 の高水準API)。

使用例:
    from aios_sdk import Client

    aios = Client(base_url="https://api.aios.example", api_key="...")
    cohort = aios.cohorts.create(name="support", slot_count=20)
    result = cohort.tasks.run(messages=[{"role": "user", "content": "..."}],
                              importance="high")
    print(result["routed_to"]["display_id"], result["output"])
    print(aios.lineage.task(result["task_id"])["explanation"])   # 開示請求応答

本体サービスへ依存しない(HTTP契約のみ共有、NFR-MT-03)。
"""

from aios_sdk.client import AiosApiError, Client, CohortHandle

__all__ = ["AiosApiError", "Client", "CohortHandle"]
__version__ = "0.1.0"
