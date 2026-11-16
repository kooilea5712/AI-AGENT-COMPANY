import { useEffect, useMemo, useRef, useState } from "react";
import Markdown from "react-markdown";
import { API, api, Ev, FileRow, Flow, GitInfo, Job, Msg, Person, Task } from "./api";
import FlowView from "./Flow";
import { fmtDate, fmtDur, fmtTime, icon, RUNNING, STATE_VI, STEPS, tone, useNow } from "./lib";

type Tab = "progress" | "chat" | "docs" | "log" | "files" | "git";

export default function JobView({ id, staff }: { id: string; staff: Person[] }) {
  const [job, setJob] = useState<Job | null>(null);
  const [flow, setFlow] = useState<Flow | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [files, setFiles] = useState<FileRow[]>([]);
  const [events, setEvents] = useState<Ev[]>([]);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [tab, setTab] = useState<Tab>("progress");
  const [err, setErr] = useState("");

  const load = () => {
    api.job(id).then(setJob).catch((e) => setErr(String(e)));
    api.flow(id).then(setFlow).catch(() => {});
    api.tasks(id).then(setTasks).catch(() => {});
    api.files(id).then(setFiles).catch(() => {});
    api.conversation(id).then(setMsgs).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 2000); return () => clearInterval(t); }, [id]);

  // SSE: EventSource tự nối lại và gửi Last-Event-ID nên nhật ký không mất khi rớt kết nối.
  useEffect(() => {
    const es = new EventSource(`${API}/jobs/${id}/events`);
    es.onmessage = (m) => setEvents((old) => { const e: Ev = JSON.parse(m.data); return old.some((o) => o.id === e.id) ? old : [...old, e]; });
    return () => es.close();
  }, [id]);

  if (!job) return <p className="muted pad">{err || "Đang tải…"}</p>;
  const s = job.state;
  const tabs: [Tab, string][] = [["progress", "Tiến trình"], ["chat", `Giám đốc (${msgs.length})`], ["docs", "Tài liệu"], ["log", `Nhật ký (${events.length})`], ["files", `File (${files.length})`], ["git", "Git"]];
  return (
    <div className="jobview">
      <div className="jobhead">
        <h2>{job.title}</h2>
        <span className={"badge " + tone(s)}>{STATE_VI[s] ?? s}</span>
        {job.round > 1 && <span className="badge">đợt {job.round}</span>}
        {job.fix_round > 0 && <span className="badge">vòng sửa {job.fix_round}/2</span>}
        {job.workspace && <span className="badge" title={job.workspace}>📁 project trên máy</span>}
        <CostChip job={job} reload={load} setErr={setErr} />
        {RUNNING.has(s) && s !== "lessons" && (
          <button className="small-btn danger" onClick={() => { if (confirm("Dừng job này? Mọi thứ đã làm được giữ lại; bạn có thể bấm Tiếp tục sau.")) api.cancel(id).then(load).catch((e) => setErr(String(e))); }}>⏹ Dừng job</button>
        )}
      </div>
      {err && <p className="err">{err}</p>}
      <NeedsYou job={job} reload={load} setErr={setErr} />
      <div className="tabs">
        {tabs.map(([k, v]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{v}</button>)}
      </div>
      {tab === "progress" && <Progress job={job} flow={flow} tasks={tasks} staff={staff} />}
      {tab === "chat" && <Chat job={job} msgs={msgs} reload={load} setErr={setErr} />}
      {tab === "docs" && <Docs job={job} />}
      {tab === "log" && <Log events={events} />}
      {tab === "files" && <Files id={id} files={files} job={job} />}
      {tab === "git" && <GitTab id={id} job={job} />}
    </div>
  );
}

const usd = (x: number) => "$" + (x < 0.01 && x > 0 ? x.toFixed(4) : x.toFixed(2));

/** Chip chi phí: tiền ước tính / hạn mức + token. Bấm để đổi hạn mức của job. Rê chuột xem chi tiết theo model. */
function CostChip({ job, reload, setErr }: { job: Job; reload: () => void; setErr: (s: string) => void }) {
  const u = job.usage;
  if (!u) return null;
  const pct = u.budget ? u.cost / u.budget : 0;
  const tip = [`Mức đầu tư: ${u.tier === "economy" ? "tiết kiệm" : "quan trọng"}`, `${u.calls} lượt gọi model`,
    ...u.by_model.map((m) => `${m.connection}/${m.model}: ${m.tokens_in + m.tokens_out} token, ${m.priced ? usd(m.cost) : "chưa có đơn giá"}`),
    u.unpriced_calls ? "Có lượt dùng model trả phí chưa có đơn giá: tiền thật có thể cao hơn số hiển thị. Nhập đơn giá ở Cài đặt." : "Chi phí là ước tính theo đơn giá bạn nhập."].join("\n");
  const change = () => {
    const v = prompt("Hạn mức chi phí cho job này (USD). 0 = không giới hạn; để trống = dùng mặc định trong Cài đặt.", u.budget ? String(u.budget) : "");
    if (v === null) return;
    api.setBudget(job.id, v.trim() === "" ? null : Number(v)).then(reload).catch((e) => setErr(String(e)));
  };
  return (
    <button className={"badge cost" + (pct >= 1 ? " bad" : pct >= 0.8 ? " warn" : "")} title={tip} onClick={change}>
      {u.tier === "economy" ? "🌱 " : "⭐ "}💰 {usd(u.cost)}{u.budget ? ` / ${usd(u.budget)}` : ""} · {Math.round((u.tokens_in + u.tokens_out) / 1000)}k token{u.unpriced_calls ? " ⚠" : ""}
    </button>
  );
}

/** Chọn file đính kèm (nhiều file, bỏ từng file được). Dùng cho mọi hành động của chủ. */
export function Attach({ files, setFiles }: { files: File[]; setFiles: (f: File[]) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="attach">
      <button type="button" onClick={() => ref.current?.click()}>📎 Đính kèm file</button>
      <input ref={ref} type="file" multiple hidden onChange={(e) => { setFiles([...files, ...Array.from(e.target.files ?? [])]); e.target.value = ""; }} />
      {files.map((f, i) => <span key={i} className="chip file-chip">{f.name}<b onClick={() => setFiles(files.filter((_, j) => j !== i))}>×</b></span>)}
    </div>
  );
}

/** Thẻ "Cần bạn": mọi hành động của chủ nằm một chỗ, luôn ở đầu trang job; chủ chỉ làm việc với Giám đốc. */
function NeedsYou({ job, reload, setErr }: { job: Job; reload: () => void; setErr: (s: string) => void }) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const s = job.state;
  const act = (fn: () => Promise<unknown>) => async () => {
    setErr("");
    try { await fn(); setText(""); setFiles([]); reload(); } catch (e) { setErr(String(e)); }
  };
  const box = (ph: string) => (<>
    <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder={ph} />
    <Attach files={files} setFiles={setFiles} />
  </>);
  if (s === "waiting_answer") return (
    <div className="card warn">
      <h3>🧭 Giám đốc cần bạn trả lời</h3><pre>{job.questions}</pre>
      {box("Trả lời (có thể ghi “dùng mặc định”)…")}
      <div className="row"><button className="primary" disabled={!text.trim() && files.length === 0} onClick={act(() => api.answer(job.id, text, files))}>Gửi cho Giám đốc</button></div>
    </div>
  );
  if (s === "awaiting_brief") return (
    <div className="card warn">
      <h3>Brief đang chờ bạn duyệt</h3>
      <p className="muted">Bạn đang bật “chủ duyệt brief” trong Cài đặt. Xem brief ở tab Tài liệu.</p>
      {box("Ghi chú nếu muốn trả lại brief…")}
      <div className="row">
        <button className="primary" onClick={act(() => api.approveBrief(job.id))}>Duyệt brief</button>
        <button disabled={!text.trim() && files.length === 0} onClick={act(() => api.rejectBrief(job.id, text, files))}>Trả lại brief</button>
      </div>
    </div>
  );
  if (s === "awaiting_handoff" || s === "done") return (
    <div className={"card " + (s === "done" ? "ok" : "warn")}>
      <h3>{s === "done" ? "Job đã xong. Còn lỗi hoặc muốn làm tiếp?" : "Kết quả cuối đã sẵn sàng"}</h3>
      <p className="muted">Xem HANDOFF.md ở tab Tài liệu, file ở tab File{job.workspace ? ", thay đổi trên nhánh Git ở tab Git" : ""}. Chỉ điểm lỗi hoặc giao thêm việc cho Giám đốc (kèm file nếu cần); Giám đốc sẽ lập kế hoạch bổ sung, không làm lại từ đầu.</p>
      {box("Chỉ ra lỗi hoặc yêu cầu thêm…")}
      <div className="row">
        {s === "awaiting_handoff" && <button className="primary" onClick={act(() => api.approveHandoff(job.id))}>Chấp nhận kết quả</button>}
        <button className={s === "done" ? "primary" : ""} disabled={!text.trim() && files.length === 0} onClick={act(() => api.feedback(job.id, text, files))}>Gửi phản hồi cho Giám đốc</button>
      </div>
    </div>
  );
  if (s === "blocked") return (
    <div className="card bad">
      <h3>Job đã dừng</h3><p>{job.error}</p>
      {(job.error ?? "").includes("hạn mức chi phí") && (
        <div className="row"><span>Nâng hạn mức lên (USD):</span>
          <input type="number" min="0" step="0.5" style={{ width: 110 }} value={text} onChange={(e) => setText(e.target.value)} placeholder={String((job.usage?.budget || 1) * 2)} />
          <button className="primary" disabled={!text.trim()} onClick={act(async () => { await api.setBudget(job.id, Number(text)); await api.retry(job.id, "", []); })}>Nâng hạn mức và tiếp tục</button>
        </div>
      )}
      {box("Hướng dẫn thêm cho Giám đốc (không bắt buộc)…")}
      <div className="row"><button className="primary" onClick={act(() => api.retry(job.id, text, files))}>Tiếp tục từ bước đã dừng</button></div>
    </div>
  );
  return null;
}

function Progress({ job, flow, tasks, staff }: { job: Job; flow: Flow | null; tasks: Task[]; staff: Person[] }) {
  const now = useNow();
  const cur = flow?.current;
  const who = staff.find((p) => p.name === cur?.actor);
  const curTask = tasks.find((t) => t.status === "running");
  return (
    <div>
      {cur && (
        <div className={"now " + tone(job.state)}>
          <div className="now-av">{icon(cur.actor)}</div>
          <div>
            <div className="now-who"><b>{cur.actor ?? (job.state === "done" ? "Cả đội" : "—")}</b>{who && <span className="muted"> · {who.title}</span>}</div>
            <div>{job.state === "done" ? "Job đã hoàn tất" : cur.label}{curTask ? ` — ${curTask.task_id}: ${curTask.title}` : ""}</div>
            {who && <div className="muted small">Nhiệm vụ: {who.duties.slice(0, 2).join("; ")}</div>}
            {who && who.models.length > 0 && <div className="muted small">Model đang dùng: {who.models.find((m) => !m.includes("bỏ qua")) ?? "chưa có ứng viên dùng được, xem Cài đặt"}</div>}
          </div>
          <div className="now-t">
            {job.state === "done" ? <>tổng thời gian<br /><b>{fmtDur(cur.since - (flow?.segments[0]?.started ?? cur.since))}</b></>
              : <>{RUNNING.has(job.state) ? "đang chạy" : "đang chờ"}<br /><b>{fmtDur(now - cur.since)}</b></>}
          </div>
        </div>
      )}
      <div className="steps">
        {STEPS.map((n, i) => {
          const k = i + 1;
          const isCur = job.state !== "done" && job.state !== "blocked" && (k === job.step || (k === 5 && job.step === 4));
          const done = job.state === "done" || (job.state !== "blocked" && k < job.step);
          return <div key={n} className={"step" + (done ? " done" : isCur ? " cur" : "")}><span>{done ? "✓" : k}</span>{n}</div>;
        })}
      </div>
      {flow && <div className="card flowcard"><h3>Luồng bàn giao giữa các nhân viên</h3><FlowView flow={flow} staff={staff} /></div>}
      {tasks.length > 0 && <TaskTable tasks={tasks} job={job} />}
      {flow && <Timeline flow={flow} />}
    </div>
  );
}

const T_ST: Record<string, [string, string]> = { pending: ["chờ", ""], running: ["đang làm", "run"], done: ["xong", "ok"], failed: ["lỗi", "bad"] };

function TaskTable({ tasks, job }: { tasks: Task[]; job: Job }) {
  const now = useNow();
  const rounds = Array.from(new Set(tasks.map((t) => t.round)));
  return (
    <div className="card">
      <h3>Việc Giám đốc đã giao cho model con</h3>
      {rounds.map((r) => (
        <div key={r}>
          {rounds.length > 1 && <div className="muted small">Đợt {r}{r === job.round ? " (hiện tại)" : ""}</div>}
          <table className="tbl">
            <tbody>
              {tasks.filter((t) => t.round === r).map((t) => {
                const [label, cls] = T_ST[t.status] ?? [t.status, ""];
                return (
                  <tr key={t.task_id}>
                    <td><b>{t.task_id}</b></td><td>{t.title}</td><td>{icon(t.actor)} {t.actor}</td>
                    <td className="muted small">{t.depends.length ? `chờ ${t.depends.join(", ")}` : ""}</td>
                    <td><span className={"badge " + cls}>{label}</span></td>
                    <td className="muted small">{t.started ? fmtDur((t.ended ?? now) - t.started) : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

function Timeline({ flow }: { flow: Flow }) {
  const now = useNow();
  return (
    <div className="card">
      <h3>Dòng thời gian</h3>
      <ol className="timeline">
        {flow.segments.map((s, i) => {
          const prev = flow.segments[i - 1];
          const handed = prev && prev.actor && s.actor && prev.actor !== s.actor;
          const open = s.ended === null;
          return (
            <li key={i} className={open ? "open" : ""}>
              {handed && <div className="handoff">{icon(prev.actor)} {prev.actor} <span>→ bàn giao cho →</span> {icon(s.actor)} {s.actor}</div>}
              <div className="seg">
                <span className="dot">{icon(s.actor)}</span>
                <div className="grow">
                  <b>{s.label}</b> <span className="muted">· {s.actor ?? "—"}</span>
                  <div className="muted small">
                    {fmtTime(s.started)} · {fmtDur((s.ended ?? now) - s.started)}
                    {s.llm_calls > 0 && ` · ${s.llm_calls} lượt gọi model`}{s.tool_calls > 0 && ` · ${s.tool_calls} lệnh/công cụ`}
                    {s.errors > 0 && <span className="errtxt"> · {s.errors} lỗi</span>}
                  </div>
                </div>
                {open && <span className="badge run">hiện tại</span>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** Hội thoại chủ ⇄ Giám đốc. Chủ nhắn bất cứ lúc nào (kèm file); lúc job đang chạy tin được xếp hàng cho Giám đốc đọc ở bước kế tiếp. */
function Chat({ job, msgs, reload, setErr }: { job: Job; msgs: Msg[]; reload: () => void; setErr: (s: string) => void }) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs.length]);
  const send = async () => {
    setErr("");
    try { await api.message(job.id, text, files); setText(""); setFiles([]); reload(); } catch (e) { setErr(String(e)); }
  };
  const queued = RUNNING.has(job.state);
  return (
    <div className="chat">
      <div className="msgs">
        {msgs.map((m) => (
          <div key={m.id} className={"msg " + m.sender}>
            <div className="who">{m.sender === "owner" ? "👤 Bạn" : "🧭 Giám đốc"} <span className="muted small">{fmtDate(m.ts)}</span></div>
            <div className="md"><Markdown>{m.text}</Markdown></div>
            {m.files.map((f) => <a key={f} className="chip" href={api.fileUrl(job.id, f)} target="_blank" rel="noreferrer">📎 {f.split("/").pop()}</a>)}
          </div>
        ))}
        <div ref={end} />
      </div>
      <div className="composer">
        <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Nhắn Giám đốc: thêm yêu cầu, chỉ lỗi, đưa tài liệu…  (Ctrl+Enter để gửi)"
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && (text.trim() || files.length)) send(); }} />
        <Attach files={files} setFiles={setFiles} />
        <div className="row between">
          <span className="muted small">{queued ? "Job đang chạy: Giám đốc sẽ đọc tin này ở bước kế tiếp." : "Bạn chỉ làm việc với Giám đốc; Giám đốc điều phối cả đội."}</span>
          <button className="primary" disabled={!text.trim() && files.length === 0} onClick={send}>Gửi</button>
        </div>
      </div>
    </div>
  );
}

function Docs({ job }: { job: Job }) {
  const sec = (title: string, body: string | null, open = false) => body ? (
    <details open={open} className="card"><summary>{title}</summary><div className="md"><Markdown>{body}</Markdown></div></details>
  ) : null;
  return (
    <div>
      <details className="card" open><summary>Yêu cầu gốc</summary><pre>{job.description}</pre></details>
      {sec(job.owner_approves_brief ? "Brief" : "Brief (do Giám đốc tự duyệt)", job.brief, job.state === "awaiting_brief")}
      {sec("Kế hoạch và các task", job.plan)}
      {job.testcases.length > 0 && (
        <details className="card"><summary>Bộ testcase ({job.testcases.length}) do Kiểm định thiết kế</summary>
          <table className="tbl"><tbody>
            {job.testcases.map((c) => (
              <tr key={c.id}><td><b>{c.id}</b></td><td>{c.title}<div className="muted small">{c.criterion}</div></td>
                <td className="muted small"><code>{c.steps.join(" ; ")}</code></td><td className="muted small">{c.expect ? "máy kiểm lại được" : "cần mắt"}</td></tr>
            ))}
          </tbody></table>
        </details>
      )}
      {job.qa_reports.map((q, i) => sec(`Báo cáo kiểm thử · ${q.name}`, q.text, i === job.qa_reports.length - 1))}
      {sec("HANDOFF.md", job.handoff, job.state === "awaiting_handoff")}
    </div>
  );
}

const KIND_VI: Record<string, string> = { state: "trạng thái", llm: "model", tool: "công cụ", tool_error: "lỗi công cụ", error: "lỗi", warn: "cảnh báo", final: "kết luận", resume: "tiếp tục", lessons: "bài học", git: "git", task: "task", qa: "kiểm thử", message: "tin nhắn" };

function Log({ events }: { events: Ev[] }) {
  const [actor, setActor] = useState<string>("");
  const [q, setQ] = useState("");
  const [noise, setNoise] = useState(false);   // ẩn các dòng "gọi vai / model phục vụ" cho dễ đọc
  const [follow, setFollow] = useState(true);
  const box = useRef<HTMLDivElement>(null);
  const actors = useMemo(() => Array.from(new Set(events.map((e) => e.actor).filter(Boolean))) as string[], [events]);
  const shown = events.filter((e) => (!actor || e.actor === actor) && (!q || e.message.toLowerCase().includes(q.toLowerCase())) && (noise || e.kind !== "llm"));
  useEffect(() => { if (follow) box.current?.scrollTo(0, box.current.scrollHeight); }, [shown.length, follow]);
  const text = () => shown.map((e) => `${fmtTime(e.ts)} [${e.actor}] ${e.kind}: ${e.message}`).join("\n");
  const download = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text()], { type: "text/plain;charset=utf-8" }));
    a.download = "nhat-ky.txt"; a.click();
  };
  return (
    <div>
      <div className="toolbar">
        <input placeholder="Tìm trong nhật ký…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="chips">
          <button className={!actor ? "on" : ""} onClick={() => setActor("")}>Tất cả</button>
          {actors.map((a) => <button key={a} className={actor === a ? "on" : ""} onClick={() => setActor(a)}>{icon(a)} {a}</button>)}
        </div>
        <label><input type="checkbox" checked={noise} onChange={(e) => setNoise(e.target.checked)} /> hiện dòng gọi model</label>
        <label><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> tự cuộn</label>
        <button onClick={() => navigator.clipboard?.writeText(text())}>Sao chép</button>
        <button onClick={download}>Tải .txt</button>
      </div>
      <div className="log" ref={box}>
        {shown.length === 0 && <div className="muted">Không có dòng nào.</div>}
        {shown.map((e) => (
          <div key={e.id} className={"ev " + e.kind}>
            <span className="muted">{fmtTime(e.ts)}</span> <span className="who">{icon(e.actor)}</span> <b>{KIND_VI[e.kind] ?? e.kind}</b> {e.message}
          </div>
        ))}
      </div>
    </div>
  );
}

const TEXT_EXT = /\.(md|txt|py|js|jsx|ts|tsx|json|svg|html|css|csv|log|yml|yaml|toml|sh|ps1|bat|ini|cfg|xml|rs|go|java|c|cpp|h|sql)$/i;
const IMG_EXT = /\.(png|jpe?g|gif|webp)$/i;
const VID_EXT = /\.(mp4|webm|mov|mkv)$/i;
const AUD_EXT = /\.(mp3|wav|ogg|m4a)$/i;
const FLAG: Record<string, [string, string]> = { A: ["mới", "ok"], M: ["đã sửa", "warn"], D: ["đã xoá", "bad"] };

/** Hai nguồn file: Project trên máy (nơi code thật nằm khi job gắn thư mục) và Tài liệu job (brief, kế hoạch, báo cáo...). */
function Files({ id, files, job }: { id: string; files: FileRow[]; job: Job }) {
  const hasWs = !!job.workspace;
  const [src, setSrc] = useState<"ws" | "job">(hasWs ? "ws" : "job");
  const [ws, setWs] = useState<{ root: string; files: { path: string; size: number; changed: "A" | "M" | "D" | null }[]; truncated: boolean } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [onlyChanged, setOnlyChanged] = useState(false);
  useEffect(() => {
    if (!hasWs || src !== "ws") return;
    const load = () => api.wsFiles(id).then(setWs).catch(() => {});
    load(); const t = setInterval(load, 3000);     // làm mới: thấy file mới xuất hiện ngay giữa công đoạn
    return () => clearInterval(t);
  }, [id, src, hasWs]);
  const url = (p: string) => (src === "ws" ? api.wsFileUrl(id, p) : api.fileUrl(id, p));
  useEffect(() => {
    setText("");
    if (open && TEXT_EXT.test(open)) fetch(url(open)).then((r) => r.text()).then((t) => setText(t.slice(0, 60000))).catch(() => {});
  }, [open, id, src]);   // eslint-disable-line react-hooks/exhaustive-deps
  const list: { path: string; size: number; changed?: "A" | "M" | "D" | null }[] = src === "ws" ? (ws?.files ?? []) : files;
  const shown = onlyChanged ? list.filter((f) => f.changed) : list;
  const groups = useMemo(() => {
    const g: Record<string, typeof list> = {};
    shown.forEach((f) => { const k = f.path.includes("/") ? f.path.split("/")[0] : "(gốc)"; (g[k] ||= []).push(f); });
    return g;
  }, [shown]);   // eslint-disable-line react-hooks/exhaustive-deps
  const changedCount = list.filter((f) => f.changed).length;
  return (
    <div>
      {hasWs && (
        <div className="toolbar">
          <div className="chips">
            <button className={src === "ws" ? "on" : ""} onClick={() => { setSrc("ws"); setOpen(null); }}>📁 Project trên máy</button>
            <button className={src === "job" ? "on" : ""} onClick={() => { setSrc("job"); setOpen(null); }}>📄 Tài liệu của job</button>
          </div>
          {src === "ws" && <label><input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} /> chỉ file job này đã đổi ({changedCount})</label>}
          {src === "ws" && ws && <span className="muted small">{ws.root}{ws.truncated ? " · (chỉ hiện 1500 file đầu)" : ""}</span>}
        </div>
      )}
      <div className="filespane">
        <div className="filelist">
          {Object.entries(groups).sort(([a, x], [b, y]) => (a === "deliverables" ? -1 : b === "deliverables" ? 1 : a.localeCompare(b))).map(([g, items]) => (
            <div key={g}>
              <div className="grp">{g === "deliverables" ? "📦 deliverables (sản phẩm giao)" : g === "inputs" ? "📎 inputs (file chủ đính kèm)" : g}</div>
              {items.map((f) => (
                <div key={f.path} className={"file" + (open === f.path ? " on" : "")} onClick={() => setOpen(f.path)}>
                  <span>{f.path.split("/").slice(g === "(gốc)" ? 0 : 1).join("/")}{f.changed && <span className={"badge " + FLAG[f.changed][1]} style={{ marginLeft: 6 }}>{FLAG[f.changed][0]}</span>}</span>
                  <span className="muted">{f.size} B</span>
                </div>
              ))}
            </div>
          ))}
          {shown.length === 0 && <p className="muted">{src === "ws" && !ws ? "Đang tải…" : onlyChanged ? "Job này chưa đổi file nào trong project." : "Chưa có file."}</p>}
        </div>
        <div className="preview">
          {!open && <p className="muted">Chọn một file để xem.</p>}
          {open && (
            <>
              <div className="row between"><b>{open}</b><a className="btn" href={url(open)} download target="_blank" rel="noreferrer">Tải về</a></div>
              {(IMG_EXT.test(open) || /\.svg$/i.test(open)) && <div className="checker"><img src={url(open)} alt={open} /></div>}
              {VID_EXT.test(open) && <video src={url(open)} controls style={{ maxWidth: "100%" }} />}
              {AUD_EXT.test(open) && <audio src={url(open)} controls />}
              {TEXT_EXT.test(open) && (/\.md$/i.test(open) ? <div className="md"><Markdown>{text}</Markdown></div> : <pre className="code">{text}</pre>)}
              {!IMG_EXT.test(open) && !TEXT_EXT.test(open) && !VID_EXT.test(open) && !AUD_EXT.test(open) && <p className="muted">Không xem trước được định dạng này; bấm “Tải về”.</p>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** Mọi lần agent chạy xong đều có commit (hệ thống bắt buộc). Hiện danh sách và xem từng commit. */
function GitTab({ id, job }: { id: string; job: Job }) {
  const [g, setG] = useState<GitInfo | null>(null);
  const [sel, setSel] = useState<{ repo: string; hash: string } | null>(null);
  const [text, setText] = useState("");
  useEffect(() => { api.git(id).then(setG).catch(() => {}); const t = setInterval(() => api.git(id).then(setG).catch(() => {}), 4000); return () => clearInterval(t); }, [id]);
  useEffect(() => { if (sel) api.gitShow(id, sel.hash, sel.repo).then((r) => setText(r.text)).catch((e) => setText(String(e))); }, [sel, id]);
  if (!g) return <p className="muted">Đang tải…</p>;
  return (
    <div>
      <div className="card">
        <h3>Quy tắc Git</h3>
        <p className="muted">Sau MỖI lần agent chạy xong (brief, kế hoạch, từng task, testcase, kiểm thử, bàn giao) hệ thống tự commit; không commit được thì job dừng. Hệ thống không bao giờ push.</p>
        {g.workspace ? (
          <p>📁 Project: <code>{g.workspace}</code><br />Nhánh của job: <code>{g.branch}</code>. Muốn đưa vào nhánh chính, bạn tự merge: <code>git merge {g.branch}</code></p>
        ) : <p className="muted">Job này làm trong thư mục job (không gắn project trên máy); thư mục job là một repo Git.</p>}
      </div>
      <div className="filespane">
        <div className="filelist">
          {g.commits.length === 0 && <p className="muted">Chưa có commit.</p>}
          {g.commits.map((c) => (
            <div key={c.repo + c.hash} className={"file" + (sel?.hash === c.hash ? " on" : "")} onClick={() => setSel({ repo: c.repo, hash: c.hash })}>
              <span><code>{c.hash}</code> {c.message.replace(/^\[studio\] job-[\w-]+ /, "")}<div className="muted small">{c.repo === "workspace" ? "project" : "thư mục job"} · {c.files} file · {fmtTime(c.ts)}</div></span>
            </div>
          ))}
        </div>
        <div className="preview">{sel ? <pre>{text}</pre> : <p className="muted">Chọn một commit để xem các file đã đổi.</p>}</div>
      </div>
    </div>
  );
}
