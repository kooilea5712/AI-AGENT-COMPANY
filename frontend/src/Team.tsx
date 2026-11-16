import { Person } from "./api";
import { icon } from "./lib";

const STATUS: Record<Person["status"], [string, string]> = {
  working: ["Đang làm việc", "run"], waiting: ["Chờ bạn", "warn"], idle: ["Rảnh", "ok"], planned: ["Chưa dựng", ""],
};

export default function Team({ staff, openJob, openSettings }: { staff: Person[]; openJob: (id: string) => void; openSettings: () => void }) {
  const active = staff.filter((p) => p.active), planned = staff.filter((p) => !p.active);
  const card = (p: Person) => {
    const [label, cls] = STATUS[p.status];
    return (
      <div key={p.id} className={"card person" + (p.active ? "" : " planned")}>
        <div className="p-head">
          <div className="p-av">{icon(p.name)}</div>
          <div className="grow"><h3>{p.name}</h3><div className="muted small">{p.title}</div></div>
          <span className={"badge " + cls}>{label}</span>
        </div>
        <div className="p-sec">Nhiệm vụ</div>
        <ul>{p.duties.map((d) => <li key={d}>{d}</li>)}</ul>
        {p.tools.length > 0 && <><div className="p-sec">Công cụ</div><div className="chips static">{p.tools.map((t) => <span key={t} className="chip">{t}</span>)}</div></>}
        {p.models.length > 0 && (
          <>
            <div className="p-sec">Model (theo thứ tự ưu tiên) <a href="#" onClick={(e) => { e.preventDefault(); openSettings(); }}>đổi</a></div>
            <ol className="models">{p.models.map((m) => <li key={m} className={m.includes("bỏ qua") ? "muted" : ""}>{m}</li>)}</ol>
          </>
        )}
        {p.tasks.length > 0 && (
          <>
            <div className="p-sec">Đang giữ việc</div>
            {p.tasks.map((t) => <div key={t.id} className="p-task" onClick={() => openJob(t.id)}><b>{t.title}</b><div className="muted small">{t.label}</div></div>)}
          </>
        )}
        {p.active && !p.human && <div className="muted small">Đã tham gia {p.jobs_touched} job</div>}
      </div>
    );
  };
  return (
    <div className="pad">
      <h2>Đội ngũ</h2>
      <p className="muted">Bạn chỉ làm việc với Giám đốc điều phối. Giám đốc (Claude Opus nếu bạn nhập khoá) viết brief, tự duyệt, chia việc cho các model con, rồi Kiểm định (Sonnet) thiết kế testcase và Kiểm thử viên (Haiku hoặc model free) chạy hết.</p>
      <div className="grid">{active.map(card)}</div>
      <h3 className="sub">Vai trong thiết kế, chưa dựng</h3>
      <div className="grid">{planned.map(card)}</div>
    </div>
  );
}
