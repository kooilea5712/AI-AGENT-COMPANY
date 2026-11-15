import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { API, api, Ev, FileRow, Job, JobRow } from "./api";

// Tám bước của thiết kế; job.step cho biết đang ở bước nào (bước 5 tự kiểm nằm trong bước 4).
const STEPS = ["Tiếp nhận", "Duyệt brief", "Lập kế hoạch", "Thực thi", "Tự kiểm", "Kiểm định", "Bàn giao", "Rút kinh nghiệm"];
const STATE_VI: Record<string, string> = {
  intake: "Giám đốc đang tiếp nhận", waiting_answer: "Giám đốc hỏi lại bạn", awaiting_brief: "Chờ bạn duyệt brief",
  planning: "Đang lập kế hoạch", executing: "Kỹ sư đang làm", qa: "Kiểm định đang kiểm",
  handoff: "Đang viết bàn giao", awaiting_handoff: "Chờ bạn duyệt bàn giao", lessons: "Đang rút kinh nghiệm",
  done: "Hoàn tất", blocked: "Dừng, cần bạn quyết định",
};
const WAITING_YOU = new Set(["waiting_answer", "awaiting_brief", "awaiting_handoff"]);

export default function App() {
  const [tab, setTab] = useState<"jobs" | "system">("jobs");
  const [sel, setSel] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const refresh = () => api.jobs().then(setJobs).catch(() => {});
  useEffect(() => { refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t); }, []);

  return (
    <div className="app">
      <header>
        <b>Studio AI</b>
        <nav>
          <button className={tab === "jobs" ? "on" : ""} onClick={() => setTab("jobs")}>Công việc</button>
          <button className={tab === "system" ? "on" : ""} onClick={() => setTab("system")}>Hệ thống</button>
        </nav>
      </header>
      {tab === "system" ? <System /> : (
        <div className="cols">
          <aside>
            <NewJob onCreated={(id) => { setSel(id); refresh(); }} />
            <h3>Danh sách job</h3>
            {jobs.length === 0 && <p className="muted">Chưa có job.</p>}
            {jobs.map((j) => (
              <div key={j.id} className={"jobrow" + (sel === j.id ? " sel" : "")} onClick={() => setSel(j.id)}>
                <div>{j.title}</div>
                <span className={"badge " + (WAITING_YOU.has(j.state) ? "warn" : j.state === "blocked" ? "bad" : j.state === "done" ? "ok" : "")}>
                  {STATE_VI[j.state] ?? j.state}
                </span>
              </div>
            ))}
          </aside>
          <main>{sel ? <JobView key={sel} id={sel} /> : <p className="muted">Chọn một job hoặc tạo job mới.</p>}</main>
        </div>
      )}
    </div>
  );
}

function NewJob({ onCreated }: { onCreated: (id: string) => void }) {
  const [desc, setDesc] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true); setErr("");
    try { const r = await api.create(desc, files); setDesc(""); setFiles([]); onCreated(r.id); }
    catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  return (
    <div className="card">
      <h3>Tạo job mới</h3>
      <textarea rows={5} placeholder="Mô tả việc cần làm…" value={desc} onChange={(e) => setDesc(e.target.value)} />
      <input type="file" multiple onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
      <button className="primary" disabled={busy || !desc.trim()} onClick={submit}>Tạo job</button>
      {err && <p className="err">{err}</p>}
    </div>
  );
}

function JobView({ id }: { id: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [files, setFiles] = useState<FileRow[]>([]);
  const [events, setEvents] = useState<Ev[]>([]);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  const load = () => { api.job(id).then(setJob).catch((e) => setErr(String(e))); api.files(id).then(setFiles).catch(() => {}); };
  useEffect(() => { load(); const t = setInterval(load, 2000); return () => clearInterval(t); }, [id]);

  // SSE: EventSource tự nối lại và gửi Last-Event-ID, nên nhật ký không mất khi rớt mạng.
  useEffect(() => {
    const es = new EventSource(`${API}/jobs/${id}/events`);
    es.onmessage = (m) => setEvents((old) => { const e: Ev = JSON.parse(m.data); return old.some((o) => o.id === e.id) ? old : [...old, e]; });
    return () => es.close();
  }, [id]);
  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [events]);

  const act = (fn: () => Promise<unknown>) => async () => {
    setErr("");
    try { await fn(); setText(""); load(); } catch (e) { setErr(String(e)); }
  };

  if (!job) return <p className="muted">{err || "Đang tải…"}</p>;
  const s = job.state;
  return (
    <div>
      <h2>{job.title}</h2>
      <div className="steps">
        {STEPS.map((n, i) => {
          const k = i + 1;
          const cls = s === "blocked" ? "" : k < job.step || s === "done" ? "done" : k === job.step || (k === 5 && job.step === 4) ? "cur" : "";
          return <div key={n} className={"step " + cls}><span>{k}</span>{n}</div>;
        })}
      </div>
      <p><span className={"badge " + (WAITING_YOU.has(s) ? "warn" : s === "blocked" ? "bad" : s === "done" ? "ok" : "")}>{STATE_VI[s] ?? s}</span>
        {job.fix_round > 0 && <span className="muted"> · vòng sửa {job.fix_round}/2</span>}</p>
      {err && <p className="err">{err}</p>}
      {s === "blocked" && <div className="card bad"><b>Job dừng:</b> {job.error}</div>}

      {s === "waiting_answer" && (
        <div className="card warn">
          <h3>Giám đốc hỏi bạn</h3><pre>{job.questions}</pre>
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Trả lời (có thể ghi 'dùng mặc định')" />
          <button className="primary" disabled={!text.trim()} onClick={act(() => api.answer(id, text))}>Gửi trả lời</button>
        </div>
      )}

      {job.brief && (
        <details open={s === "awaiting_brief"}><summary>Brief</summary>
          <div className="md"><Markdown>{job.brief}</Markdown></div>
          {s === "awaiting_brief" && (
            <div className="card warn">
              <button className="primary" onClick={act(() => api.approveBrief(id))}>Duyệt brief</button>
              <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ghi chú khi trả lại brief…" />
              <button disabled={!text.trim()} onClick={act(() => api.rejectBrief(id, text))}>Trả lại brief</button>
            </div>
          )}
        </details>
      )}
      {job.plan && <details><summary>Kế hoạch</summary><div className="md"><Markdown>{job.plan}</Markdown></div></details>}

      {job.qa_reports.length > 0 && (
        <details open><summary>Báo cáo Kiểm định ({job.qa_reports.length})</summary>
          {job.qa_reports.map((q) => <div key={q.name}><b>{q.name}</b><div className="md"><Markdown>{q.text}</Markdown></div></div>)}
        </details>
      )}

      {job.handoff && (
        <details open={s === "awaiting_handoff"}><summary>HANDOFF.md</summary>
          <div className="md"><Markdown>{job.handoff}</Markdown></div>
        </details>
      )}
      {s === "awaiting_handoff" && (
        <div className="card warn">
          <button className="primary" onClick={act(() => api.approveHandoff(id))}>Duyệt bàn giao</button>
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ghi chú khi trả lại bàn giao…" />
          <button disabled={!text.trim()} onClick={act(() => api.rejectHandoff(id, text))}>Trả lại bàn giao</button>
        </div>
      )}

      <h3>File ({files.length})</h3>
      <ul className="files">{files.map((f) => (
        <li key={f.path}><a href={`${API}/jobs/${id}/files/${f.path}`} target="_blank" rel="noreferrer">{f.path}</a> <span className="muted">{f.size} B</span></li>
      ))}</ul>

      <h3>Nhật ký chạy trực tiếp</h3>
      <div className="log" ref={logRef}>
        {events.map((e) => (
          <div key={e.id} className={"ev " + e.kind}>
            <span className="muted">{new Date(e.ts * 1000).toLocaleTimeString("vi-VN")}</span> <b>{e.kind}</b> {e.message}
          </div>
        ))}
      </div>
    </div>
  );
}

function System() {
  const [h, setH] = useState<any>(null);
  const [deep, setDeep] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.health(false).then(setH).catch((e) => setH({ error: String(e) })); }, []);
  const runDeep = async () => { setBusy(true); try { setDeep(await api.health(true)); } finally { setBusy(false); } };
  if (!h) return <p className="muted">Đang kiểm tra…</p>;
  if (h.error) return <p className="err">Không gọi được backend: {h.error}</p>;
  const mark = (ok: boolean) => <span className={ok ? "okc" : "badc"}>{ok ? "✔" : "✘"}</span>;
  return (
    <div className="system">
      <p className="muted">Chế độ LLM: <b>{h.llm_mode}</b> · {h.llm_base_url}</p>
      <h3>Dịch vụ</h3>
      <p>{mark(h.omniroute.ok)} OmniRoute {h.omniroute.status ?? h.omniroute.error}</p>
      <p>{mark(h.ollama.ok)} Ollama {h.ollama.ok ? `— model: ${h.ollama.models.join(", ")}` : h.ollama.error}</p>
      <h3>Công cụ dòng lệnh</h3>
      {Object.entries<any>(h.tools).map(([k, v]) => <p key={k}>{mark(v.ok)} <b>{k}</b> <span className="muted">{v.version ?? "chưa cài"}</span></p>)}
      <h3>Combo và model đang phục vụ</h3>
      <p className="muted">Gọi thật từng combo, tuần tự (Ollama phải nạp model nên có thể mất vài chục giây).</p>
      <button disabled={busy} onClick={runDeep}>{busy ? "Đang thử…" : "Thử từng combo"}</button>
      {deep && Object.entries<any>(deep.combos).map(([k, v]) => (
        <p key={k}>{mark(v.ok)} <b>{k}</b> → {v.ok ? v.served_by : v.error}</p>
      ))}
    </div>
  );
}
