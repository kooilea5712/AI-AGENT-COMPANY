import { useEffect, useMemo, useRef, useState } from "react";
import { api, JobRow, Person } from "./api";
import JobView, { Attach } from "./JobView";
import SettingsPage from "./Settings";
import System from "./System";
import Team from "./Team";
import { fmtDate, icon, STATE_VI, ThemeMode, tone, useTheme, WAITING_YOU } from "./lib";

type Page = "jobs" | "team" | "settings" | "system";
type Filter = "all" | "need" | "run" | "done";

export default function App() {
  const [page, setPage] = useState<Page>("jobs");
  const [sel, setSel] = useState<string | null>(() => { try { return localStorage.getItem("sel"); } catch { return null; } });
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [info, setInfo] = useState<{ staff: Person[] } | null>(null);
  const [offline, setOffline] = useState(false);
  const [creating, setCreating] = useState(false);
  const [toasts, setToasts] = useState<{ id: number; text: string; job: string }[]>([]);
  const [theme, setTheme] = useTheme();
  const seen = useRef<Record<string, string>>({});   // job -> trạng thái đã thấy lần trước, để báo khi job chuyển sang "chờ bạn"

  const refresh = () => {
    api.jobs().then((rows) => {
      setOffline(false);
      rows.forEach((j) => {
        const was = seen.current[j.id];
        if (was !== undefined && was !== j.state && WAITING_YOU.has(j.state)) {
          const text = `${j.title.slice(0, 50)}: ${STATE_VI[j.state]}`;
          setToasts((t) => [...t, { id: Date.now() + Math.random(), text, job: j.id }]);
          try { if (Notification.permission === "granted") new Notification("Studio AI", { body: text }); } catch { /* không bắt buộc */ }
        }
        seen.current[j.id] = j.state;
      });
      setJobs(rows);
    }).catch(() => setOffline(true));
    api.staff().then(setInfo).catch(() => {});
  };
  useEffect(() => { refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t); }, []);
  useEffect(() => { try { sel ? localStorage.setItem("sel", sel) : localStorage.removeItem("sel"); } catch { /* bỏ qua */ } }, [sel]);
  useEffect(() => { if (toasts.length) { const t = setTimeout(() => setToasts((x) => x.slice(1)), 7000); return () => clearTimeout(t); } }, [toasts]);

  const director = info?.staff.find((p) => p.id === "director");
  const noClaude = !!director && director.models[0]?.includes("bỏ qua");
  const need = jobs.filter((j) => WAITING_YOU.has(j.state)).length;
  useEffect(() => { document.title = need ? `(${need}) Studio AI` : "Studio AI"; }, [need]);
  const open = (id: string) => { setSel(id); setPage("jobs"); };

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">🎬 <b>Studio AI</b></div>
        <nav>
          <button className={page === "jobs" ? "on" : ""} onClick={() => setPage("jobs")}>📋 Công việc{need > 0 && <span className="count">{need}</span>}</button>
          <button className={page === "team" ? "on" : ""} onClick={() => setPage("team")}>👥 Đội ngũ</button>
          <button className={page === "settings" ? "on" : ""} onClick={() => setPage("settings")}>⚙️ Cài đặt</button>
          <button className={page === "system" ? "on" : ""} onClick={() => setPage("system")}>🛠 Hệ thống</button>
        </nav>
        <div className="grow" />
        <div className="working">
          {info?.staff.filter((p) => p.status === "working").map((p) => <div key={p.id} className="w-row" title={p.tasks[0]?.title}>{icon(p.name)} {p.name}<span className="pulse-dot" /></div>)}
          {info && !info.staff.some((p) => p.status === "working") && <div className="muted small">Cả đội đang rảnh</div>}
        </div>
        <div className="theme">
          {(["system", "light", "dark"] as ThemeMode[]).map((m) => (
            <button key={m} className={theme === m ? "on" : ""} onClick={() => setTheme(m)} title={m === "system" ? "Theo hệ thống" : m === "light" ? "Sáng" : "Tối"}>{m === "system" ? "🖥" : m === "light" ? "☀️" : "🌙"}</button>
          ))}
        </div>
      </aside>
      <div className="content">
        {offline && <div className="banner">Mất kết nối tới backend. Đang thử lại…</div>}
        {page === "jobs" && noClaude && (
          <div className="banner warn">Giám đốc chưa dùng Claude Opus vì chưa có khoá API; đang dùng model dự phòng: <b>{director?.models.find((m) => !m.includes("bỏ qua")) ?? "không có"}</b>.{" "}
            <a href="#" onClick={(e) => { e.preventDefault(); setPage("settings"); }}>Nhập khoá trong Cài đặt</a></div>
        )}
        {page === "jobs" && (
          <div className="cols">
            <JobList jobs={jobs} sel={sel} setSel={setSel} onNew={() => setCreating(true)} />
            <main>{sel && jobs.some((j) => j.id === sel) ? <JobView key={sel} id={sel} staff={info?.staff ?? []} /> : (
              <div className="empty"><div>📋</div><p>Chọn một job ở danh sách bên trái, hoặc tạo job mới.</p><button className="primary" onClick={() => setCreating(true)}>+ Job mới</button></div>
            )}</main>
          </div>
        )}
        {page === "team" && <Team staff={info?.staff ?? []} openJob={open} openSettings={() => setPage("settings")} />}
        {page === "settings" && <SettingsPage />}
        {page === "system" && <System />}
      </div>
      {creating && <NewJob onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); open(id); refresh(); }} />}
      <div className="toasts">{toasts.map((t) => <div key={t.id} className="toast" onClick={() => open(t.job)}>🔔 {t.text}</div>)}</div>
    </div>
  );
}

function JobList({ jobs, sel, setSel, onNew }: { jobs: JobRow[]; sel: string | null; setSel: (id: string) => void; onNew: () => void }) {
  const [q, setQ] = useState("");
  const [f, setF] = useState<Filter>("all");
  const shown = useMemo(() => jobs.filter((j) => {
    if (q && !j.title.toLowerCase().includes(q.toLowerCase())) return false;
    if (f === "need") return WAITING_YOU.has(j.state);
    if (f === "run") return tone(j.state) === "run";
    if (f === "done") return j.state === "done";
    return true;
  }), [jobs, q, f]);
  const FILTERS: [Filter, string][] = [["all", "Tất cả"], ["need", "Cần bạn"], ["run", "Đang chạy"], ["done", "Xong"]];
  return (
    <section className="list">
      <button className="primary wide" onClick={onNew}>+ Job mới</button>
      <input placeholder="Tìm job…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="chips">{FILTERS.map(([k, v]) => <button key={k} className={f === k ? "on" : ""} onClick={() => setF(k)}>{v}</button>)}</div>
      <div className="jobs">
        {shown.length === 0 && <p className="muted">Không có job.</p>}
        {shown.map((j) => (
          <div key={j.id} className={"jobrow" + (sel === j.id ? " sel" : "")} onClick={() => setSel(j.id)}>
            <div className="jt">{j.title}</div>
            <div className="jm">
              <span className={"badge " + tone(j.state)}>{STATE_VI[j.state] ?? j.state}</span>
              <span className="muted small">{j.actor ? `${icon(j.actor)} ${j.actor}` : ""}</span>
            </div>
            <div className="muted small">{fmtDate(j.created_at)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function NewJob({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [desc, setDesc] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [ws, setWs] = useState("");
  const [wsCheck, setWsCheck] = useState<{ ok: boolean; note?: string; error?: string } | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const checkWs = async () => { try { setWsCheck(await api.checkWorkspace(ws)); } catch (e) { setWsCheck({ ok: false, error: String(e) }); } };
  const submit = async () => {
    setBusy(true); setErr("");
    try {
      try { if (Notification.permission === "default") Notification.requestPermission(); } catch { /* không bắt buộc */ }
      onCreated((await api.create(desc, files, ws.trim())).id);
    } catch (e) { setErr(String(e)); setBusy(false); }
  };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Job mới</h2>
        <p className="muted">Mô tả việc cần làm. Giám đốc sẽ đọc, có thể hỏi lại, rồi viết brief cho bạn duyệt.</p>
        <textarea autoFocus rows={7} placeholder="Ví dụ: Viết script Python đổi tên ảnh theo ngày chụp, có chế độ chạy thử…" value={desc} onChange={(e) => setDesc(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && desc.trim()) submit(); }} />
        <Attach files={files} setFiles={setFiles} />
        <details open={!!ws}><summary>📁 Làm trực tiếp trên một thư mục trong máy (không bắt buộc)</summary>
          <p className="muted small">Agent sửa thẳng project của bạn, trên nhánh Git riêng <code>studio/&lt;mã-job&gt;</code> và commit sau mỗi lần chạy; hệ thống không push và không đụng nhánh khác. Thư mục phải sạch (không có thay đổi chưa commit).</p>
          <div className="row"><input className="grow" placeholder="Ví dụ: D:\Projects\my-app" value={ws} onChange={(e) => { setWs(e.target.value); setWsCheck(null); }} />
            <button disabled={!ws.trim()} onClick={checkWs}>Kiểm tra</button></div>
          {wsCheck && <div className={wsCheck.ok ? "okc small" : "err small"}>{wsCheck.ok ? "✔ " + wsCheck.note : "✘ " + wsCheck.error}</div>}
        </details>
        {err && <p className="err">{err}</p>}
        <div className="row end"><button onClick={onClose}>Huỷ</button><button className="primary" disabled={busy || !desc.trim()} onClick={submit}>Tạo job <span className="muted">(Ctrl+Enter)</span></button></div>
      </div>
    </div>
  );
}
