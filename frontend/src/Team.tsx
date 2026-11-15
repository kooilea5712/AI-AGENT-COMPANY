import { Person } from "./api";
import { icon } from "./lib";

const STATUS: Record<Person["status"], [string, string]> = {
  working: ["Đang làm việc", "run"], waiting: ["Chờ bạn", "warn"], idle: ["Rảnh", "ok"], planned: ["Chưa dựng", ""],
};

export default function Team({ staff, models, mode, openJob }: { staff: Person[]; models: Record<string, string>; mode: string; openJob: (id: string) => void }) {
  const active = staff.filter((p) => p.active), planned = staff.filter((p) => !p.active);
  const card = (p: Person) => {
    const [label, cls] = STATUS[p.status];
    const model = p.combo && !p.human ? p.combo.split(" + ").map((c) => `${c}${mode === "direct" ? ` → ${models[c] ?? "?"}` : ""}`).join(", ") : null;
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
        {model && <div className="muted small p-model">Model: {model}</div>}
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
      <p className="muted">Mỗi nhân viên là một agent AI có vai trò và công cụ riêng. Bạn là chủ tịch: chỉ duyệt ở hai điểm (brief và bàn giao).</p>
      <div className="grid">{active.map(card)}</div>
      <h3 className="sub">Vai trong thiết kế, chưa dựng</h3>
      <div className="grid">{planned.map(card)}</div>
    </div>
  );
}
