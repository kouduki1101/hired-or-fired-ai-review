/**
 * AIOS TypeScript SDK(docs/05 §4 の高水準API、Python SDK と同一契約)。
 *
 * - 認証: X-API-Key ヘッダ(FR-TN-02)。Bearer は authToken で付与可
 * - エラー: 非2xxは AiosApiError(status, aiosCode, detail)
 * - fetch 注入可(テスト・カスタムトランスポート用)。既定はグローバル fetch
 * - 依存ゼロ(Node 18+ / ブラウザ / edge ランタイム)
 */

export type Json = Record<string, unknown>;
export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

export class AiosApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly aiosCode: string | null;

  constructor(status: number, detail: string, aiosCode: string | null = null) {
    super(`[${status}] ${aiosCode ?? "error"}: ${detail}`);
    this.name = "AiosApiError";
    this.status = status;
    this.detail = detail;
    this.aiosCode = aiosCode;
  }
}

export interface ClientOptions {
  baseUrl?: string;
  apiKey?: string;
  /** OIDC Bearer トークン(apiKey とは排他的に使うのが通例) */
  authToken?: string;
  fetch?: FetchLike;
}

export interface TaskRunOptions {
  messages?: Json[];
  input?: Json;
  importance?: "low" | "normal" | "high";
  difficulty?: "easy" | "normal" | "hard";
  category?: string | null;
}

export class Client {
  readonly cohorts: Cohorts;
  readonly lineage: Lineage;
  readonly approvals: Approvals;
  readonly proposals: Proposals;
  readonly admin: Admin;

  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;
  private readonly fetchImpl: FetchLike;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "http://localhost:8080").replace(/\/+$/, "");
    this.headers = { "Content-Type": "application/json" };
    if (options.apiKey) this.headers["X-API-Key"] = options.apiKey;
    if (options.authToken) this.headers["Authorization"] = `Bearer ${options.authToken}`;
    this.fetchImpl = options.fetch ?? ((url, init) => fetch(url, init));

    this.cohorts = new Cohorts(this);
    this.lineage = new Lineage(this);
    this.approvals = new Approvals(this);
    this.proposals = new Proposals(this);
    this.admin = new Admin(this);
  }

  /** 低水準リクエスト。NDJSON(監査エクスポート)は文字列で返す。 */
  async request<T = Json>(
    method: string,
    path: string,
    body?: Json,
    query?: Record<string, string | number | boolean | undefined>,
  ): Promise<T> {
    let url = this.baseUrl + path;
    if (query) {
      const params = new URLSearchParams();
      for (const [k, v] of Object.entries(query)) {
        if (v !== undefined) params.set(k, String(v));
      }
      const qs = params.toString();
      if (qs) url += `?${qs}`;
    }
    const init: RequestInit = { method, headers: this.headers };
    if (body !== undefined) init.body = JSON.stringify(body);
    const res = await this.fetchImpl(url, init);
    if (res.status >= 400) {
      let detail = await res.text();
      let code: string | null = null;
      try {
        const parsed = JSON.parse(detail) as Json;
        code = (parsed["aios_code"] as string | undefined) ?? null;
        detail = (parsed["detail"] as string | undefined) ?? detail;
      } catch {
        /* 非JSONエラー本文はそのまま */
      }
      throw new AiosApiError(res.status, detail, code);
    }
    const contentType = res.headers.get("content-type") ?? "";
    if (contentType.startsWith("application/x-ndjson")) {
      return (await res.text()) as unknown as T;
    }
    if (res.status === 204) return undefined as unknown as T;
    return (await res.json()) as T;
  }

  get<T = Json>(path: string, query?: Record<string, string | number | boolean | undefined>) {
    return this.request<T>("GET", path, undefined, query);
  }

  post<T = Json>(path: string, body?: Json, query?: Record<string, string | number | boolean>) {
    return this.request<T>("POST", path, body, query);
  }
}

export class CohortHandle {
  readonly cohortId: string;
  readonly tasks: Tasks;
  private readonly c: Client;

  constructor(client: Client, cohortId: string) {
    this.c = client;
    this.cohortId = cohortId;
    this.tasks = new Tasks(client, cohortId);
  }

  get(): Promise<Json> {
    return this.c.get(`/v1/cohorts/${this.cohortId}`);
  }

  // --- 指標・制御ループ ---
  metrics(): Promise<Json> {
    return this.c.get(`/v1/cohorts/${this.cohortId}/metrics/current`);
  }

  metricsHistory(limit = 100): Promise<Json[]> {
    return this.c.get(`/v1/cohorts/${this.cohortId}/metrics/history`, { limit });
  }

  runCycle(dryRun = false): Promise<Json> {
    return this.c.post(`/v1/cohorts/${this.cohortId}/cycles/run`, undefined, {
      dry_run: dryRun,
    });
  }

  pause(): Promise<Json> {
    return this.c.post(`/v1/cohorts/${this.cohortId}/loop`, { action: "pause" });
  }

  resume(): Promise<Json> {
    return this.c.post(`/v1/cohorts/${this.cohortId}/loop`, { action: "resume" });
  }

  autopilotOn(intervalSeconds?: number): Promise<Json> {
    return this.c.post(`/v1/cohorts/${this.cohortId}/loop`, {
      action: "autopilot_on",
      interval_seconds: intervalSeconds,
    });
  }

  autopilotOff(): Promise<Json> {
    return this.c.post(`/v1/cohorts/${this.cohortId}/loop`, { action: "autopilot_off" });
  }

  // --- スロット操作 ---
  setSlotLock(slotId: string, locked: boolean): Promise<Json> {
    return this.c.request("PUT", `/v1/cohorts/${this.cohortId}/slots/${slotId}/lock`, {
      rehatch_lock: locked,
    });
  }

  quarantine(slotId: string): Promise<Json> {
    return this.c.post(`/v1/cohorts/${this.cohortId}/slots/${slotId}/quarantine`);
  }

  restore(slotId: string): Promise<Json> {
    return this.c.post(`/v1/cohorts/${this.cohortId}/slots/${slotId}/restore`);
  }

  // --- 安全境界(FR-SF) ---
  registerNegativeCentroid(
    label: string,
    options: { examples?: number[][]; vector?: number[]; threshold?: number } = {},
  ): Promise<Json> {
    return this.c.post(`/v1/cohorts/${this.cohortId}/safety/negative-centroids`, {
      label,
      examples: options.examples ?? null,
      vector: options.vector ?? null,
      threshold: options.threshold ?? 0.85,
    });
  }

  // --- 学習系 Rehatch(蒸留/LoRA、非同期ジョブ) ---
  trainRehatch(
    slotId: string,
    options: { strategy?: string; maxSteps?: number; targetFitness?: number } = {},
  ): Promise<Json> {
    return this.c.post(`/v1/cohorts/${this.cohortId}/slots/${slotId}/rehatch/train`, {
      strategy: options.strategy ?? "distillation",
      max_steps: options.maxSteps ?? 10,
      target_fitness: options.targetFitness ?? 0.9,
    });
  }

  advanceTraining(slotId: string, jobId: string): Promise<Json> {
    return this.c.post(
      `/v1/cohorts/${this.cohortId}/slots/${slotId}/rehatch/train/${jobId}/advance`,
    );
  }

  // --- 次元拡張(請求項9) ---
  expandDimension(addedDims: number, axisLabels: string[]): Promise<Json> {
    return this.c.post(`/v1/cohorts/${this.cohortId}/scaling/expand`, {
      added_dims: addedDims,
      axis_labels: axisLabels,
    });
  }

  // --- 監査エクスポート(FR-GV-03) ---
  exportAudit(): Promise<string> {
    return this.c.get<string>(`/v1/lineage/export/${this.cohortId}`);
  }

  exportManifest(): Promise<Json> {
    return this.c.get(`/v1/lineage/export/${this.cohortId}/manifest`);
  }
}

class Cohorts {
  constructor(private readonly c: Client) {}

  async create(
    name: string,
    slotCount: number,
    options: { approvalMode?: "auto" | "manual"; emaAlpha?: number } = {},
  ): Promise<CohortHandle> {
    const body = await this.c.post(`/v1/cohorts`, {
      name,
      slot_count: slotCount,
      approval_mode: options.approvalMode ?? "auto",
      ema_alpha: options.emaAlpha ?? 0.1,
    });
    return new CohortHandle(this.c, body["cohort_id"] as string);
  }

  list(): Promise<Json[]> {
    return this.c.get(`/v1/cohorts`);
  }

  get(cohortId: string): CohortHandle {
    return new CohortHandle(this.c, cohortId);
  }
}

class Tasks {
  constructor(
    private readonly c: Client,
    private readonly cohortId: string,
  ) {}

  run(options: TaskRunOptions = {}): Promise<Json> {
    const payload = options.input ?? { messages: options.messages ?? [] };
    return this.c.post(`/v1/cohorts/${this.cohortId}/tasks`, {
      input: payload,
      metadata: {
        importance: options.importance ?? "normal",
        difficulty: options.difficulty ?? "normal",
        category: options.category ?? null,
      },
    });
  }
}

class Lineage {
  constructor(private readonly c: Client) {}

  /** 開示請求応答(¶0224-0226): 担当スロット・世代・由来+説明文。 */
  task(taskId: string): Promise<Json> {
    return this.c.get(`/v1/lineage/tasks/${taskId}`);
  }

  slotHistory(slotId: string): Promise<Json> {
    return this.c.get(`/v1/lineage/slots/${slotId}/history`);
  }
}

class Approvals {
  constructor(private readonly c: Client) {}

  list(status?: string): Promise<Json[]> {
    return this.c.get(`/v1/approvals`, status ? { status } : undefined);
  }

  approve(approvalId: string, comment = ""): Promise<Json> {
    return this.c.post(`/v1/approvals/${approvalId}/approve`, { comment });
  }

  reject(approvalId: string, comment = ""): Promise<Json> {
    return this.c.post(`/v1/approvals/${approvalId}/reject`, { comment });
  }
}

class Proposals {
  constructor(private readonly c: Client) {}

  /** エージェント自律提案(FR-GV-04)。kind: rehatch_request | role_change */
  submit(slotId: string, kind: string, rationale: Json = {}): Promise<Json> {
    return this.c.post(`/v1/proposals`, { slot_id: slotId, kind, rationale });
  }
}

class Admin {
  constructor(private readonly c: Client) {}

  registerWebhook(url: string, secret: string, events?: string[]): Promise<Json> {
    return this.c.post(`/v1/admin/webhooks`, { url, secret, events: events ?? null });
  }

  usage(): Promise<Json> {
    return this.c.get(`/v1/admin/usage`);
  }
}
