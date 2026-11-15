import { useEffect, useMemo, useRef, useState } from "react";
import Markdown from "react-markdown";
import { API, api, Ev, FileRow, Flow, Job, Person } from "./api";
import FlowView from "./Flow";
import { fmtDur, fmtTime, icon, RUNNING, STATE_VI, STEPS, tone, useNow } from "./lib";

type Tab = "progress" | "docs" | "log" | "files";

export default function JobView({ id, staff }: { id: string; staff: Person[] }) {
  const [job, setJob] = useState<Job | null>(null);
  const [flow, setFlow] = useState<Flow | null>(null);
  const [files, setFiles] = useState<FileRow[]>([]);
  const [events, setEvents] = useState<Ev[]>([]);
  const [tab, setTab] = useState<Tab>("progress");
  const [err, setErr] = useState("");

  const load = () => {
    api.job(id).then(setJob).catch((e) => setErr(String(e)));
    api.flow(id).then(setFlow).catch(() => {});
    api.files(id).then(setFiles).catch(() => {});
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
  const tabs: [Tab, string][] = [["progress", "Tiến trình"], ["docs", "Tài liệu"], ["log", `Nhật ký (${events.length})`], ["files", `File (${files.length})`]];
  return (
    <div className="jobview">
      <div className="jobhead">
        <h2>{job.title}</h2>
        <span className={"badge " + tone(s)}>{STATE_VI[s] ?? s}</span>
        {job.fix_round > 0 && <span className="badge">vòng sửa {job.fix_round}/2</span>}
      </div>
      {err && <p className="err">{err}</p>}
      <NeedsYou job={job} reload={load} setErr={setErr} />
      <div className="tabs">
        {tabs.map(([k, v]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{v}</button>)}
      </div>
      {tab === "progress" && <Progress job={job} flow={flow} staff={staff} />}
      {tab === "docs" && <Docs job={job} />}
      {tab === "log" && <Log events={events} />}
      {tab === "files" && <Files id={id} files={files} />}
    </div>
  );
}

/** Thẻ "Cần bạn": mọi hành động của chủ studio nằm một chỗ, luôn ở đầu trang job. */
function NeedsYou({ job, reload, setErr }: { job: Job; reload: () => void; setErr: (s: string) => void }) {
  const [text, setText] = useState("");
  const s = job.state;
  const act = (fn: () => Promise<unknown>) => async () => {
    setErr("");
    try { await fn(); setText(""); reload(); } catch (e) { setErr(String(e)); }
  };
  if (s === "waiting_answer") return (
    <div className="card warn">
      <h3>🧭 Giám đốc cần bạn trả lời</h3><pre>{job.questions}</pre>
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Trả lời (có thể ghi “dùng mặc định”)" />
      <div className="row"><button className="primary" disabled={!text.trim()} onClick={act(() => api.answer(job.id, text))}>Gửi trả lời</button></div>
    </div>
  );
  if (s === "awaiting_brief") return (
    <div className="card warn">
      <h3>Brief đang chờ bạn duyệt</h3>
      <p className="muted">Xem brief ở tab Tài liệu. Duyệt thì Giám đốc lập kế hoạch và giao việc.</p>
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ghi chú nếu muốn trả lại brief…" />
      <div className="row">
        <button className="primary" onClick={act(() => api.approveBrief(job.id))}>Duyệt brief</button>
        <button disabled={!text.trim()} onClick={act(() => api.rejectBrief(job.id, text))}>Trả lại brief</button>
      </div>
    </div>
  );
  if (s === "awaiting_handoff") return (
    <div className="card warn">
      <h3>Bàn giao đang chờ bạn duyệt</h3>
      <p className="muted">Kiểm định đã PASS. Xem HANDOFF.md ở tab Tài liệu và file ở tab File trước khi duyệt.</p>
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ghi chú nếu muốn trả lại bàn giao…" />
      <div className="row">
        <button className="primary" onClick={act(() => api.approveHandoff(job.id))}>Duyệt bàn giao</button>
        <button disabled={!text.trim()} onClick={act(() => api.rejectHandoff(job.id, text))}>Trả lại bàn giao</button>
      </div>
    </div>
  );
  if (s === "blocked") return (
    <div className="card bad">
      <h3>Job đã dừng</h3><p>{job.error}</p>
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Hướng dẫn thêm cho agent (không bắt buộc)…" />
      <div className="row"><button className="primary" onClick={act(() => api.retry(job.id, text))}>Tiếp tục từ bước đã dừng</button></div>
    </div>
  );
  return null;
}

function Progress({ job, flow, staff }: { job: Job; flow: Flow | null; staff: Person[] }) {
  const now = useNow();
  const cur = flow?.current;
  const who = staff.find((p) => p.name === cur?.actor);
  return (
    <div>
      {cur && (
        <div className={"now " + tone(job.state)}>
          <div className="now-av">{icon(cur.actor)}</div>
          <div>
            <div className="now-who"><b>{cur.actor ?? (job.state === "done" ? "Cả đội" : "—")}</b>{who && <span className="muted"> · {who.title}</span>}</div>
            <div>{job.state === "done" ? "Job đã hoàn tất và được bạn duyệt bàn giao" : cur.label}</div>
            {who && <div className="muted small">Nhiệm vụ: {who.duties.slice(0, 2).join("; ")}</div>}
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
      {flow && <Timeline flow={flow} />}
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

function Docs({ job }: { job: Job }) {
  const sec = (title: string, body: string | null, open = false) => body ? (
    <details open={open} className="card"><summary>{title}</summary><div className="md"><Markdown>{body}</Markdown></div></details>
  ) : null;
  return (
    <div>
      <details className="card" open><summary>Yêu cầu gốc</summary><pre>{job.description}</pre></details>
      {sec("Brief", job.brief, job.state === "awaiting_brief")}
      {sec("Kế hoạch", job.plan)}
      {job.qa_reports.map((q) => sec(`Báo cáo Kiểm định · ${q.name}`, q.text, q === job.qa_reports[job.qa_reports.length - 1]))}
      {sec("HANDOFF.md", job.handoff, job.state === "awaiting_handoff")}
      {!job.brief && <p className="muted">Chưa có tài liệu nào ngoài yêu cầu gốc.</p>}
    </div>
  );
}

const KIND_VI: Record<string, string> = { state: "trạng thái", llm: "model", tool: "công cụ", tool_error: "lỗi công cụ", error: "lỗi", warn: "cảnh báo", final: "kết luận", resume: "tiếp tục", lessons: "bài học" };

function Log({ events }: { events: Ev[] }) {
  const [actor, setActor] = useState<string>("");
  const [q, setQ] = useState("");
  const [noise, setNoise] = useState(false);   // ẩn các dòng "gọi combo / model phục vụ" cho dễ đọc
  const [follow, setFollow] = useState(true);
  const box = useRef<HTMLDivElement>(null);
  const actors = useMemo(() => Array.from(new Set(events.map((e) => e.actor).filter(Boolean))) as string[], [events]);
  const shown = events.filter((e) => (!actor || e.actor === actor) && (!q || e.message.toLowerCase().includes(q.toLowerCase()))
    && (noise || !(e.kind === "llm")));
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

const TEXT_EXT = /\.(md|txt|py|js|ts|json|svg|html|css|csv|log|yml|yaml|toml|sh|ps1)$/i;
const IMG_EXT = /\.(png|jpe?g|gif|webp)$/i;

function Files({ id, files }: { id: string; files: FileRow[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const [text, setText] = useState("");
  useEffect(() => {
    setText("");
    if (open && TEXT_EXT.test(open)) api.fileText(id, open).then((t) => setText(t.slice(0, 40000)));
  }, [open, id]);
  const groups = useMemo(() => {
    const g: Record<string, FileRow[]> = {};
    files.forEach((f) => { const k = f.path.includes("/") ? f.path.split("/")[0] : "(gốc)"; (g[k] ||= []).push(f); });
    return g;
  }, [files]);
  return (
    <div className="filespane">
      <div className="filelist">
        {Object.entries(groups).sort(([a], [b]) => (a === "deliverables" ? -1 : b === "deliverables" ? 1 : a.localeCompare(b))).map(([g, list]) => (
          <div key={g}>
            <div className="grp">{g === "deliverables" ? "📦 deliverables (sản phẩm giao)" : g}</div>
            {list.map((f) => (
              <div key={f.path} className={"file" + (open === f.path ? " on" : "")} onClick={() => setOpen(f.path)}>
                <span>{f.path.split("/").slice(g === "(gốc)" ? 0 : 1).join("/")}</span><span className="muted">{f.size} B</span>
              </div>
            ))}
          </div>
        ))}
        {files.length === 0 && <p className="muted">Chưa có file.</p>}
      </div>
      <div className="preview">
        {!open && <p className="muted">Chọn một file để xem.</p>}
        {open && (
          <>
            <div className="row between"><b>{open}</b><a className="btn" href={api.fileUrl(id, open)} download target="_blank" rel="noreferrer">Tải về</a></div>
            {IMG_EXT.test(open) && <div className="checker"><img src={api.fileUrl(id, open)} alt={open} /></div>}
            {/\.svg$/i.test(open) && <div className="checker"><img src={api.fileUrl(id, open)} alt={open} /></div>}
            {TEXT_EXT.test(open) && (/\.md$/i.test(open) ? <div className="md"><Markdown>{text}</Markdown></div> : <pre>{text}</pre>)}
            {!IMG_EXT.test(open) && !TEXT_EXT.test(open) && <p className="muted">Không xem trước được định dạng này; bấm “Tải về”.</p>}
          </>
        )}
      </div>
    </div>
  );
}
