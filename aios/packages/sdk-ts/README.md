# aios-sdk (TypeScript)

TypeScript client SDK for **AIOS** — the multi-agent population long-term operations
platform. Mirrors the Python SDK's high-level API over the same `/v1` HTTP contract;
no dependency on server internals.

Zero runtime dependencies (built on `fetch`) — works on Node 18+, browsers, and
edge runtimes. Fully typed, strict-mode TypeScript.

## Install

```bash
npm install aios-sdk
```

## Quickstart

```ts
import { Client } from "aios-sdk";

const aios = new Client({ baseUrl: "https://api.aios.example", apiKey: "..." });

// Create a cohort of 20 slots and route a task to it
const cohort = await aios.cohorts.create("support", 20);
const result = await cohort.tasks.run({
  messages: [{ role: "user", content: "How do I reset my password?" }],
  importance: "high",
});
console.log(result.routed_to, result.output);

// Disclosure-request response (開示請求応答)
console.log(await aios.lineage.task(result.task_id as string));
```

## Authentication

- **API key**: `new Client({ apiKey: "key1" })` sends `X-API-Key` (service-account
  principal, ADMIN role).
- **OIDC bearer**: `new Client({ authToken: "<jwt>" })` sends `Authorization: Bearer`.
  Roles (viewer/operator/admin) are enforced server-side from token claims.

## Capabilities

| Namespace | Operations |
|---|---|
| `aios.cohorts` | `create`, `list`, `get` |
| `cohort.tasks` | `run` |
| `cohort` | `metrics`, `metricsHistory`, `runCycle`, `pause`, `resume`, `autopilotOn`, `autopilotOff`, `setSlotLock`, `quarantine`, `restore`, `registerNegativeCentroid`, `trainRehatch`, `advanceTraining`, `expandDimension`, `exportAudit`, `exportManifest` |
| `aios.lineage` | `task`, `slotHistory` |
| `aios.approvals` | `list`, `approve`, `reject` |
| `aios.proposals` | `submit` |
| `aios.admin` | `registerWebhook`, `usage` |

## Errors

Non-2xx responses throw `AiosApiError` with `status`, `detail`, and `aiosCode`:

```ts
import { AiosApiError } from "aios-sdk";

try {
  await aios.cohorts.list();
} catch (e) {
  if (e instanceof AiosApiError) console.log(e.status, e.aiosCode, e.detail);
}
```

## Testing

`fetch` is injectable for hermetic tests:

```ts
const client = new Client({ fetch: myMockFetch });
```

```bash
npm test   # tsc (strict) + node --test
```

## License

Proprietary. All rights reserved. Contact the AIOS team for licensing terms.
