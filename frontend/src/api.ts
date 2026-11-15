// Backend chỉ nghe trên localhost; CORS đã mở cho cổng Vite 5173.
export const API = import.meta.env.VITE_API ?? "http://127.0.0.1:8000";

export type JobRow = { id: string; title: string; state: string; step: number; fix_round: number; created_at: number };
export type Job = JobRow & {
  description: string; questions: string | null; error: string | null; note: string | null;
  brief: string | null; plan: string | null; handoff: string | null;
  qa_reports: { name: string; text: string }[];
};
export type Ev = { id: number; ts: number; kind: string; message: string };
export type FileRow = { path: string; size: number };

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
  files: (id: string) => req<FileRow[]>(`/jobs/${id}/files`),
  create: (description: string, files: File[]) => {
    const f = new FormData();
    f.append("description", description);
    files.forEach((x) => f.append("files", x));
    return req<{ id: string }>("/jobs", { method: "POST", body: f });
  },
  answer: (id: string, text: string) => post(`/jobs/${id}/answer`, { text }),
  approveBrief: (id: string) => post(`/jobs/${id}/brief/approve`),
  rejectBrief: (id: string, text: string) => post(`/jobs/${id}/brief/reject`, { text }),
  retry: (id: string, text: string) => post(`/jobs/${id}/retry`, { text }),
  approveHandoff: (id: string) => post(`/jobs/${id}/handoff/approve`),
  rejectHandoff: (id: string, text: string) => post(`/jobs/${id}/handoff/reject`, { text }),
  health: (deep: boolean) => req<any>(`/health${deep ? "?deep=true" : ""}`),
};
