/**
 * SDK 単体テスト(hermetic): fetch を注入し、HTTP 契約(URL/メソッド/ヘッダ/本文)と
 * エラー写像(AiosApiError)を検証する。実サーバ結合は Python 側 SDK e2e が担う。
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { AiosApiError, Client, type Json } from "../src/index.js";

interface Captured {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

function mockClient(
  responder: (req: Captured) => { status?: number; body?: unknown; contentType?: string } = () => ({}),
): { client: Client; requests: Captured[] } {
  const requests: Captured[] = [];
  const client = new Client({
    baseUrl: "http://api.test",
    apiKey: "key-1",
    fetch: async (url, init) => {
      const req: Captured = {
        url,
        method: init?.method ?? "GET",
        headers: (init?.headers ?? {}) as Record<string, string>,
        body: init?.body ? JSON.parse(init.body as string) : undefined,
      };
      requests.push(req);
      const r = responder(req);
      const contentType = r.contentType ?? "application/json";
      const payload =
        typeof r.body === "string" ? r.body : JSON.stringify(r.body ?? {});
      return new Response(payload, {
        status: r.status ?? 200,
        headers: { "content-type": contentType },
      });
    },
  });
  return { client, requests };
}

test("create cohort posts contract body and returns handle", async () => {
  const { client, requests } = mockClient(() => ({ body: { cohort_id: "c-1" } }));
  const cohort = await client.cohorts.create("support", 20, { approvalMode: "manual" });

  assert.equal(cohort.cohortId, "c-1");
  const req = requests[0]!;
  assert.equal(req.url, "http://api.test/v1/cohorts");
  assert.equal(req.method, "POST");
  assert.equal(req.headers["X-API-Key"], "key-1");
  assert.deepEqual(req.body, {
    name: "support",
    slot_count: 20,
    approval_mode: "manual",
    ema_alpha: 0.1,
  });
});

test("task run wraps messages and metadata", async () => {
  const { client, requests } = mockClient(() => ({ body: { task_id: "t-1" } }));
  await client.cohorts.get("c-9").tasks.run({
    messages: [{ role: "user", content: "hi" }],
    importance: "high",
  });

  const req = requests[0]!;
  assert.equal(req.url, "http://api.test/v1/cohorts/c-9/tasks");
  const body = req.body as Json;
  assert.deepEqual(body["input"], { messages: [{ role: "user", content: "hi" }] });
  assert.deepEqual(body["metadata"], {
    importance: "high",
    difficulty: "normal",
    category: null,
  });
});

test("query parameters are encoded (runCycle dry_run, history limit)", async () => {
  const { client, requests } = mockClient(() => ({ body: {} }));
  const cohort = client.cohorts.get("c-2");
  await cohort.runCycle(true);
  await cohort.metricsHistory(50);

  assert.equal(requests[0]!.url, "http://api.test/v1/cohorts/c-2/cycles/run?dry_run=true");
  assert.equal(
    requests[1]!.url,
    "http://api.test/v1/cohorts/c-2/metrics/history?limit=50",
  );
});

test("training endpoints follow the async-job contract", async () => {
  const { client, requests } = mockClient(() => ({ body: { job_id: "job-1" } }));
  const cohort = client.cohorts.get("c-3");
  await cohort.trainRehatch("s-1", { maxSteps: 3 });
  await cohort.advanceTraining("s-1", "job-1");

  assert.equal(requests[0]!.url, "http://api.test/v1/cohorts/c-3/slots/s-1/rehatch/train");
  assert.deepEqual(requests[0]!.body, {
    strategy: "distillation",
    max_steps: 3,
    target_fitness: 0.9,
  });
  assert.equal(
    requests[1]!.url,
    "http://api.test/v1/cohorts/c-3/slots/s-1/rehatch/train/job-1/advance",
  );
});

test("non-2xx maps to AiosApiError with aios_code", async () => {
  const { client } = mockClient(() => ({
    status: 401,
    body: { detail: "invalid API key", aios_code: "unauthorized" },
  }));
  await assert.rejects(
    () => client.cohorts.list(),
    (err: unknown) => {
      assert.ok(err instanceof AiosApiError);
      assert.equal(err.status, 401);
      assert.equal(err.aiosCode, "unauthorized");
      assert.equal(err.detail, "invalid API key");
      return true;
    },
  );
});

test("non-JSON error body degrades gracefully", async () => {
  const { client } = mockClient(() => ({
    status: 502,
    body: "Bad Gateway",
    contentType: "text/plain",
  }));
  await assert.rejects(
    () => client.cohorts.list(),
    (err: unknown) => {
      assert.ok(err instanceof AiosApiError);
      assert.equal(err.status, 502);
      assert.equal(err.aiosCode, null);
      return true;
    },
  );
});

test("NDJSON export returns raw text", async () => {
  const ndjson = '{"hash":"a"}\n{"hash":"b"}\n';
  const { client } = mockClient(() => ({
    body: ndjson,
    contentType: "application/x-ndjson",
  }));
  const text = await client.cohorts.get("c-4").exportAudit();
  assert.equal(text, ndjson);
});

test("bearer token header is sent when authToken is set", async () => {
  const requests: Captured[] = [];
  const client = new Client({
    baseUrl: "http://api.test",
    authToken: "jwt-token",
    fetch: async (url, init) => {
      requests.push({
        url,
        method: init?.method ?? "GET",
        headers: (init?.headers ?? {}) as Record<string, string>,
        body: undefined,
      });
      return new Response("[]", {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  await client.cohorts.list();
  assert.equal(requests[0]!.headers["Authorization"], "Bearer jwt-token");
});
