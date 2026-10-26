import type {
  ApiKey,
  AuditEntry,
  AuthResponse,
  Case,
  CaseMember,
  CaseSummary,
  Edge,
  Entity,
  EntityDetail,
  GraphResponse,
  Job,
  ModuleInfo,
  ModuleSettings,
  Note,
  Page,
  RescanConfig,
  Report,
  User,
} from "./types";

// In-memory access token (never persisted; restored on load via /auth/refresh cookie).
let accessToken: string | null = null;
export const setAccessToken = (t: string | null) => {
  accessToken = t;
};
export const getAccessToken = () => accessToken;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

interface ReqOpts {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
}

function buildUrl(path: string, params?: ReqOpts["params"]): string {
  const url = path.startsWith("/api") ? path : `/api/v1${path}`;
  if (!params) return url;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `${url}?${s}` : url;
}

async function refreshToken(): Promise<string | null> {
  try {
    const res = await fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" });
    if (!res.ok) return null;
    const data = (await res.json()) as AuthResponse;
    accessToken = data.access_token;
    return accessToken;
  } catch {
    return null;
  }
}

export async function apiFetch<T>(path: string, opts: ReqOpts = {}): Promise<T> {
  const url = buildUrl(path, opts.params);
  const send = (token: string | null) =>
    fetch(url, {
      method: opts.method || "GET",
      headers: {
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      credentials: "include",
    });

  let res = await send(accessToken);
  // Transparent one-shot refresh on expiry (skip for the auth endpoints themselves).
  if (res.status === 401 && !path.includes("/auth/")) {
    const fresh = await refreshToken();
    if (fresh) res = await send(fresh);
  }

  if (!res.ok) {
    let detail: string = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? await res.json() : await res.text()) as T;
}

// --------------------------------------------------------------------- API ---
export const api = {
  auth: {
    register: (email: string, password: string) =>
      apiFetch<AuthResponse>("/auth/register", { method: "POST", body: { email, password } }),
    login: (email: string, password: string, totp_code?: string) =>
      apiFetch<AuthResponse | { totp_required: true }>("/auth/login", {
        method: "POST",
        body: { email, password, totp_code },
      }),
    refresh: () => apiFetch<AuthResponse>("/auth/refresh", { method: "POST" }),
    logout: () => apiFetch<{ message: string }>("/auth/logout", { method: "POST" }),
    me: () => apiFetch<User>("/auth/me"),
    changePassword: (current_password: string, new_password: string) =>
      apiFetch<{ message: string }>("/auth/password", { method: "POST", body: { current_password, new_password } }),
    totpSetup: () => apiFetch<{ secret: string; provisioning_uri: string }>("/auth/totp/setup", { method: "POST" }),
    totpEnable: (code: string) => apiFetch<{ message: string }>("/auth/totp/enable", { method: "POST", body: { code } }),
    totpDisable: (code: string) => apiFetch<{ message: string }>("/auth/totp/disable", { method: "POST", body: { code } }),
  },
  cases: {
    list: () => apiFetch<CaseSummary[]>("/cases"),
    create: (body: { name: string; description?: string; legal_basis: string; aup_accepted: boolean; aup_version?: string }) =>
      apiFetch<Case>("/cases", { method: "POST", body }),
    get: (id: string) => apiFetch<CaseSummary>(`/cases/${id}`),
    update: (id: string, body: Partial<Pick<Case, "name" | "description" | "status" | "legal_basis">>) =>
      apiFetch<Case>(`/cases/${id}`, { method: "PATCH", body }),
    remove: (id: string) => apiFetch<{ message: string }>(`/cases/${id}`, { method: "DELETE" }),
    members: (id: string) => apiFetch<CaseMember[]>(`/cases/${id}/members`),
    addMember: (id: string, email: string, case_role: string) =>
      apiFetch<CaseMember>(`/cases/${id}/members`, { method: "POST", body: { email, case_role } }),
    removeMember: (id: string, userId: string) =>
      apiFetch<{ message: string }>(`/cases/${id}/members/${userId}`, { method: "DELETE" }),
    saveLayout: (id: string, layout: Record<string, { x: number; y: number }>) =>
      apiFetch<{ message: string }>(`/cases/${id}/graph-layout`, { method: "PUT", body: { layout } }),
    getRescan: (id: string) => apiFetch<RescanConfig>(`/cases/${id}/rescan`),
    setRescan: (id: string, body: RescanConfig) => apiFetch<RescanConfig>(`/cases/${id}/rescan`, { method: "PUT", body }),
    notes: (id: string, entityId?: string) =>
      apiFetch<Note[]>(`/cases/${id}/notes`, { params: { entity_id: entityId } }),
    addNote: (id: string, body: { body: string; entity_id?: string; pinned?: boolean }) =>
      apiFetch<Note>(`/cases/${id}/notes`, { method: "POST", body }),
    updateNote: (id: string, noteId: string, body: { body?: string; pinned?: boolean }) =>
      apiFetch<Note>(`/cases/${id}/notes/${noteId}`, { method: "PATCH", body }),
    deleteNote: (id: string, noteId: string) =>
      apiFetch<{ message: string }>(`/cases/${id}/notes/${noteId}`, { method: "DELETE" }),
  },
  entities: {
    list: (caseId: string, params?: Record<string, string | number | boolean | undefined>) =>
      apiFetch<Page<Entity>>(`/cases/${caseId}/entities`, { params }),
    get: (caseId: string, id: string) => apiFetch<EntityDetail>(`/cases/${caseId}/entities/${id}`),
    create: (caseId: string, body: { type: string; value: string; label?: string; tags?: string[]; run_collectors?: boolean; autoexpand?: boolean }) =>
      apiFetch<Entity>(`/cases/${caseId}/entities`, { method: "POST", body }),
    update: (caseId: string, id: string, body: { label?: string; tags?: string[]; pinned?: boolean }) =>
      apiFetch<Entity>(`/cases/${caseId}/entities/${id}`, { method: "PATCH", body }),
    remove: (caseId: string, id: string) =>
      apiFetch<{ deleted: boolean }>(`/cases/${caseId}/entities/${id}`, { method: "DELETE" }),
    bulk: (caseId: string, body: { entity_ids: string[]; action: string; tag?: string; collector_name?: string }) =>
      apiFetch<{ affected: number; jobs_enqueued: number }>(`/cases/${caseId}/entities/bulk`, { method: "POST", body }),
    graph: (caseId: string, params?: { min_confidence?: number; limit?: number }) =>
      apiFetch<GraphResponse>(`/cases/${caseId}/graph`, { params }),
    search: (caseId: string, q: string) => apiFetch<Entity[]>(`/cases/${caseId}/search`, { params: { q } }),
  },
  edges: {
    list: (caseId: string) => apiFetch<Edge[]>(`/cases/${caseId}/edges`),
    create: (caseId: string, body: { source_entity_id: string; target_entity_id: string; relationship: string; attributes?: Record<string, unknown> }) =>
      apiFetch<Edge>(`/cases/${caseId}/edges`, { method: "POST", body }),
    remove: (caseId: string, id: string) => apiFetch<{ message: string }>(`/cases/${caseId}/edges/${id}`, { method: "DELETE" }),
  },
  jobs: {
    list: (caseId: string, params?: { status?: string; limit?: number; offset?: number }) =>
      apiFetch<Page<Job>>(`/cases/${caseId}/jobs`, { params }),
    get: (caseId: string, id: string) => apiFetch<Job>(`/cases/${caseId}/jobs/${id}`),
    run: (caseId: string, collector_name: string, target_entity_id: string) =>
      apiFetch<Job>(`/cases/${caseId}/jobs/run`, { method: "POST", body: { collector_name, target_entity_id } }),
    autoexpand: (caseId: string, body: { seed_entity_id: string; depth?: number; budget?: number; disabled?: string[] }) =>
      apiFetch<Job>(`/cases/${caseId}/jobs/autoexpand`, { method: "POST", body }),
    retry: (caseId: string, id: string) => apiFetch<Job>(`/cases/${caseId}/jobs/${id}/retry`, { method: "POST" }),
    cancel: (caseId: string, id: string) => apiFetch<Job>(`/cases/${caseId}/jobs/${id}/cancel`, { method: "POST" }),
  },
  modules: {
    list: (caseId: string) => apiFetch<ModuleInfo[]>(`/cases/${caseId}/modules`),
    settings: (caseId: string) => apiFetch<ModuleSettings>(`/cases/${caseId}/modules/settings`),
    setSettings: (caseId: string, body: ModuleSettings) =>
      apiFetch<ModuleSettings>(`/cases/${caseId}/modules/settings`, { method: "PUT", body }),
    global: () => apiFetch<ModuleInfo[]>("/modules"),
  },
  keys: {
    list: () => apiFetch<ApiKey[]>("/keys"),
    create: (body: { service: string; value: string; label?: string; scope?: string; case_id?: string }) =>
      apiFetch<ApiKey>("/keys", { method: "POST", body }),
    test: (id: string) => apiFetch<{ id: string; service: string; is_valid: boolean; message: string }>(`/keys/${id}/test`, { method: "POST" }),
    remove: (id: string) => apiFetch<{ message: string }>(`/keys/${id}`, { method: "DELETE" }),
  },
  reports: {
    list: (caseId: string) => apiFetch<Report[]>(`/cases/${caseId}/reports`),
    create: (caseId: string, body: Record<string, unknown>) =>
      apiFetch<Report>(`/cases/${caseId}/reports`, { method: "POST", body }),
    get: (caseId: string, id: string) => apiFetch<Report>(`/cases/${caseId}/reports/${id}`),
    downloadUrl: (caseId: string, id: string, format: string) =>
      `/api/v1/cases/${caseId}/reports/${id}/download?format=${format}`,
  },
  audit: {
    list: (params?: Record<string, string | number | undefined>) => apiFetch<Page<AuditEntry>>("/audit", { params }),
    exportUrl: "/api/v1/audit/export",
  },
};
