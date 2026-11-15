// Production (exe / backend phục vụ UI): cùng nguồn nên để trống. Dev (Vite 5173): gọi backend 8000, CORS đã mở.
export const API: string = import.meta.env.DEV ? (import.meta.env.VITE_API ?? "http://127.0.0.1:8000") : "";

export type JobRow = { id: string; title: string; state: string; step: number; fix_round: number; created_at: number; updated_at: number; actor: string | null };
export type Job = JobRow & {
  description: string; questions: string | null; error: string | null; note: string | null;
  brief: string | null; plan: string | null; handoff: string | null;
  qa_reports: { name: string; text: string }[];
};
export type Ev = { id: number; ts: number; kind: string; message: string; actor: string | null };
export type FileRow = { path: string; size: number };
export type Segment = { state: string; label: string; step: number; actor: string | null; started: number; ended: number | null; tool_calls: number; llm_calls: number; errors: number };
export type Handoff = { from: string; to: string; at: number; why: string };
export type Flow = {
  job_id: string; state: string; segments: Segment[]; handoffs: Handoff[];
  current: { actor: string | null; label: string; since: number; working: boolean; waiting_owner: boolean } | null;
};
export type Person = {
  id: string; name: string; title: string; human: boolean; active: boolean; combo: string | null;
  duties: string[]; tools: string[]; status: "working" | "waiting" | "idle" | "planned";
  tasks: { id: string; title: string; state: string; label: string }[]; jobs_touched: number;
};
export type StaffInfo = { staff: Person[]; models: Record<string, string>; llm_mode: string };

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + path, init);
  if (!r.ok) throw new Error(`${r.status}: ${(await r.text()).slice(0, 300)}`);
  return r.json();
}
const post = (path: string, body?: unknown) =>
  req<{ state: string }>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

export const api = {
  jobs: () => req<JobRow[]>("/jobs"),
  job: (id: string) => req<Job>(`/jobs/${id}`),
  flow: (id: string) => req<Flow>(`/jobs/${id}/flow`),
  staff: () => req<StaffInfo>("/staff"),
  files: (id: string) => req<FileRow[]>(`/jobs/${id}/files`),
  fileUrl: (id: string, path: string) => `${API}/jobs/${id}/files/${path}`,
  fileText: async (id: string, path: string) => (await fetch(`${API}/jobs/${id}/files/${path}`)).text(),
  create: (description: string, files: File[]) => {
    const f = new FormData();
    f.append("description", description);
    files.forEach((x) => f.append("files", x));
    return req<{ id: string }>("/jobs", { method: "POST", body: f });
  },
  answer: (id: string, text: string) => post(`/jobs/${id}/answer`, { text }),
  approveBrief: (id: string) => post(`/jobs/${id}/brief/approve`),
  rejectBrief: (id: string, text: string) => post(`/jobs/${id}/brief/reject`, { text }),
  approveHandoff: (id: string) => post(`/jobs/${id}/handoff/approve`),
  rejectHandoff: (id: string, text: string) => post(`/jobs/${id}/handoff/reject`, { text }),
  retry: (id: string, text: string) => post(`/jobs/${id}/retry`, { text }),
  health: (deep: boolean) => req<any>(`/health${deep ? "?deep=true" : ""}`),
};
