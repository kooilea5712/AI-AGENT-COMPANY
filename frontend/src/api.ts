// Production (exe / backend phục vụ UI): cùng nguồn nên để trống. Dev (Vite 5173): gọi backend 8000, CORS đã mở.
export const API: string = import.meta.env.DEV ? (import.meta.env.VITE_API ?? "http://127.0.0.1:8000") : "";

export type JobRow = { id: string; title: string; state: string; step: number; fix_round: number; round: number; workspace: string | null; created_at: number; updated_at: number; actor: string | null };
export type TestCase = { id: string; title: string; criterion: string; steps: string[]; setup?: string[]; expect?: Record<string, unknown>; manual_check?: string };
export type Usage = {
  tokens_in: number; tokens_out: number; cost: number; calls: number; unpriced_calls: number; budget: number; tier: "full" | "economy";
  by_model: { model: string; connection: string; tokens_in: number; tokens_out: number; cost: number; priced: number; calls: number }[];
};
export type Job = JobRow & {
  usage: Usage; tier: "full" | "economy"; budget: number | null;
  description: string; questions: string | null; error: string | null; note: string | null; base_branch: string | null;
  brief: string | null; plan: string | null; handoff: string | null; owner_approves_brief: boolean;
  qa_reports: { name: string; text: string }[]; testcases: TestCase[];
};
export type Ev = { id: number; ts: number; kind: string; message: string; actor: string | null };
export type FileRow = { path: string; size: number };
export type Segment = { state: string; label: string; step: number; actor: string | null; started: number; ended: number | null; tool_calls: number; llm_calls: number; errors: number; task_id?: string };
export type Handoff = { from: string; to: string; at: number; why: string };
export type Flow = {
  job_id: string; state: string; segments: Segment[]; handoffs: Handoff[];
  current: { actor: string | null; label: string; since: number; working: boolean; waiting_owner: boolean } | null;
};
export type Task = { task_id: string; round: number; role: string; title: string; depends: string[]; status: string; started: number | null; ended: number | null; report: string | null; actor: string };
export type Msg = { id: number; ts: number; sender: "owner" | "director"; text: string; files: string[] };
export type Person = {
  id: string; name: string; title: string; human: boolean; active: boolean; role: string | null; models: string[];
  duties: string[]; tools: string[]; status: "working" | "waiting" | "idle" | "planned";
  tasks: { id: string; title: string; state: string; label: string }[]; jobs_touched: number;
};
export type Commit = { ts: number; repo: string; hash: string; message: string; files: number };
export type GitInfo = { workspace: string | null; branch: string | null; commits: Commit[]; job_repo: { hash: string; subject: string; ts: number; changed: string }[]; workspace_repo: { hash: string; subject: string; ts: number; changed: string }[] };
export type Conn = { label: string; base_url: string; enabled: boolean; has_key: boolean; key_hint: string; needs_key: boolean };
export type Cand = { connection: string; model: string };
export type Settings = {
  connections: Record<string, Conn>; roles: Record<string, Cand[]>; roles_meta: Record<string, { label: string; hint: string }>;
  presets: { id: string; label: string; note: string; roles: Record<string, [string, string][]> }[];
  owner_approves_brief: boolean; autopilot: boolean; autopilot_retries: number; sandbox_mode: "docker" | "local"; data_file: string;
  default_tier: "full" | "economy"; job_budget_usd: number; downgrade: Record<string, string>; prices: Record<string, { in: number; out: number }>;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + path, init);
  if (!r.ok) {
    let msg = await r.text();
    try { msg = JSON.parse(msg).detail ?? msg; } catch { /* không phải JSON */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}
const json = (method: string, body: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
// Mọi hành động của chủ gửi multipart để kèm file đính kèm được (text + files).
const form = (path: string, text: string, files: File[]) => {
  const f = new FormData();
  f.append("text", text);
  files.forEach((x) => f.append("files", x));
  return req<{ state: string }>(path, { method: "POST", body: f });
};
const bare = (path: string) => req<{ state: string }>(path, { method: "POST" });

export const api = {
  jobs: () => req<JobRow[]>("/jobs"),
  job: (id: string) => req<Job>(`/jobs/${id}`),
  flow: (id: string) => req<Flow>(`/jobs/${id}/flow`),
  tasks: (id: string) => req<Task[]>(`/jobs/${id}/tasks`),
  conversation: (id: string) => req<Msg[]>(`/jobs/${id}/conversation`),
  git: (id: string) => req<GitInfo>(`/jobs/${id}/git`),
  gitShow: (id: string, rev: string, repo: string) => req<{ text: string }>(`/jobs/${id}/git/${rev}?repo=${repo}`),
  staff: () => req<{ staff: Person[] }>("/staff"),
  files: (id: string) => req<FileRow[]>(`/jobs/${id}/files`),
  fileUrl: (id: string, path: string) => `${API}/jobs/${id}/files/${path}`,
  wsFiles: (id: string) => req<{ root: string; files: { path: string; size: number; changed: "A" | "M" | "D" | null }[]; truncated: boolean }>(`/jobs/${id}/workspace/files`),
  wsFileUrl: (id: string, path: string) => `${API}/jobs/${id}/workspace/files/${path}`,
  fileText: async (id: string, path: string) => (await fetch(`${API}/jobs/${id}/files/${path}`)).text(),
  create: (description: string, files: File[], workspace: string, tier: string, budget: string) => {
    const f = new FormData();
    f.append("description", description);
    f.append("workspace", workspace);
    f.append("tier", tier);
    f.append("budget", budget);
    files.forEach((x) => f.append("files", x));
    return req<{ id: string }>("/jobs", { method: "POST", body: f });
  },
  checkWorkspace: (path: string) => {
    const f = new FormData(); f.append("path", path);
    return req<{ ok: boolean; note?: string; error?: string }>("/workspace/check", { method: "POST", body: f });
  },
  message: (id: string, text: string, files: File[]) => form(`/jobs/${id}/message`, text, files),
  answer: (id: string, text: string, files: File[]) => form(`/jobs/${id}/answer`, text, files),
  approveBrief: (id: string) => bare(`/jobs/${id}/brief/approve`),
  rejectBrief: (id: string, text: string, files: File[]) => form(`/jobs/${id}/brief/reject`, text, files),
  approveHandoff: (id: string) => bare(`/jobs/${id}/handoff/approve`),
  feedback: (id: string, text: string, files: File[]) => form(`/jobs/${id}/handoff/reject`, text, files),
  cancel: (id: string) => bare(`/jobs/${id}/cancel`),
  setBudget: (id: string, usd: number | null) => req<Usage>(`/jobs/${id}/budget`, json("PUT", { usd })),
  retry: (id: string, text: string, files: File[]) => form(`/jobs/${id}/retry`, text, files),
  health: (deep: boolean) => req<any>(`/health${deep ? "?deep=true" : ""}`),
  settings: () => req<Settings>("/settings"),
  saveSettings: (patch: unknown) => req<Settings>("/settings", json("PUT", patch)),
  testRole: (role: string) => req<{ ok: boolean; served_by?: string; skipped?: string[]; error?: string }>("/settings/test", json("POST", { role })),
};
