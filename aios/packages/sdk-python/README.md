# aios-sdk

Python client SDK for **AIOS** — the multi-agent population long-term operations
platform (patent 特願2026-000860). Talks to the AIOS Control Plane API over HTTP;
it shares only the HTTP contract and has no dependency on the server internals.

Typed (PEP 561), synchronous, dependency-light (only `httpx`).

## Install

```bash
pip install aios-sdk
# or
uv add aios-sdk
```

## Quickstart

```python
from aios_sdk import Client

aios = Client(base_url="https://api.aios.example", api_key="...")

# Create a cohort of 20 slots and route a task to it
cohort = aios.cohorts.create(name="support", slot_count=20)
result = cohort.tasks.run(
    messages=[{"role": "user", "content": "How do I reset my password?"}],
    importance="high",
)
print(result["routed_to"]["display_id"], result["output"])

# Disclosure-request response (開示請求応答): who handled it, which generation, why
print(aios.lineage.task(result["task_id"])["explanation"])
```

## Authentication

- **API key**: `Client(base_url=..., api_key="key1")` sends `X-API-Key`.
  API keys are service-account principals (ADMIN role).
- **OIDC bearer**: pass a pre-obtained token via a custom header/transport, or
  front the SDK with your IdP. Roles (viewer/operator/admin) are enforced
  server-side per the token claims.

## Capabilities

| Namespace | Operations |
|---|---|
| `aios.cohorts` | `create`, `list`, `get` |
| `cohort.tasks` | `run` (route + execute) |
| `cohort` | `metrics`, `metrics_history`, `run_cycle`, `pause`, `resume`, `set_slot_lock`, `quarantine`, `restore`, `register_negative_centroid`, `train_rehatch`, `advance_training`, `expand_dimension`, `export_audit`, `export_manifest` |
| `aios.lineage` | `task` (disclosure response), `slot_history` |
| `aios.approvals` | `list`, `approve`, `reject` |
| `aios.proposals` | `submit` (agent autonomous proposal) |
| `aios.admin` | `register_webhook`, `usage` |

## Errors

Non-2xx responses raise `AiosApiError(status, detail, aios_code)`:

```python
from aios_sdk import AiosApiError

try:
    aios.cohorts.list()
except AiosApiError as e:
    print(e.status, e.aios_code, e.detail)   # e.g. 401 unauthorized ...
```

## Versioning

Semantic versioning. See [CHANGELOG.md](CHANGELOG.md). The SDK's minor version
tracks the Control Plane API `/v1` contract; breaking API changes bump the major.

## License

Proprietary. All rights reserved. Contact the AIOS team for licensing terms.
