import { Flow as FlowData, Person } from "./api";
import { fmtDur, fmtTime, icon, useNow } from "./lib";

// Sơ đồ bàn giao: Chủ studio ⇄ Giám đốc ⇄ (các model con) → Kiểm định (thiết kế testcase) → Kiểm thử viên (chạy testcase).
// Chủ chỉ nối với Giám đốc. Cột model con có thể có 1 hoặc 2 ô (Kỹ sư phần mềm, Chuyên viên media) tuỳ kế hoạch của job.
const W = 168, H = 92;
const OWNER = "Chủ studio", DIR = "Giám đốc điều phối", QA = "Kiểm định", TESTER = "Kiểm thử viên";
const COLX = [12, 238, 464, 690, 916];

type N = { name: string; x: number; y: number };

export default function FlowView({ flow, staff }: { flow: FlowData; staff: Person[] }) {
  const now = useNow();
  const execs = Array.from(new Set(flow.segments.filter((s) => s.state === "executing").map((s) => s.actor).filter(Boolean))) as string[];
  if (execs.length === 0) execs.push("Kỹ sư phần mềm");
  const two = execs.length > 1;
  const midY = two ? 96 : 40;
  const nodes: N[] = [
    { name: OWNER, x: COLX[0], y: midY }, { name: DIR, x: COLX[1], y: midY },
    ...execs.map((n, i) => ({ name: n, x: COLX[2], y: two ? 10 + i * 160 : 40 })),
    { name: QA, x: COLX[3], y: midY }, { name: TESTER, x: COLX[4], y: midY },
  ];
  const by = (n: string) => nodes.find((x) => x.name === n)!;
  const person = (n: string) => staff.find((p) => p.name === n);
  const height = (two ? 330 : 250);

  const count: Record<string, number> = {};
  flow.handoffs.forEach((h) => { count[`${h.from}>${h.to}`] = (count[`${h.from}>${h.to}`] ?? 0) + 1; });
  const last = flow.handoffs.length ? flow.handoffs[flow.handoffs.length - 1] : null;
  const hot = last ? `${last.from}>${last.to}` : "";
  const cur = flow.current?.actor ?? null;
  const visited = new Set(flow.segments.map((s) => s.actor));
  const stat = (n: string) => flow.segments.filter((s) => s.actor === n).reduce((a, s) => ({ t: a.t + s.tool_calls, l: a.l + s.llm_calls }), { t: 0, l: 0 });

  // Đường thẳng giữa hai ô kề cột (đi: y trên, về: y dưới); đường cong cho các cạnh nhảy cột.
  const straight = (a: string, b: string) => {
    const A = by(a), B = by(b), fwd = A.x < B.x, key = `${a}>${b}`, n = count[key] ?? 0;
    const yA = A.y + H / 2 + (fwd ? -12 : 12), yB = B.y + H / 2 + (fwd ? -12 : 12);
    const x1 = fwd ? A.x + W : A.x, x2 = fwd ? B.x : B.x + W;
    return (
      <g key={key}>
        <path d={`M${x1},${yA} L${x2},${yB}`} className={"edge" + (n ? " used" : "") + (hot === key ? " hot" : "")} markerEnd={n ? "url(#arr-on)" : "url(#arr)"} />
        {n > 0 && <text x={(x1 + x2) / 2} y={(yA + yB) / 2 - 5} textAnchor="middle" className="edge-n">×{n}</text>}
      </g>
    );
  };
  const curve = (a: string, b: string, depth: number, label: string) => {
    const A = by(a), B = by(b), key = `${a}>${b}`, n = count[key] ?? 0;
    const x1 = A.x + W / 2, y1 = A.y + H, x2 = B.x + W / 2, y2 = B.y + H + 4;
    return (
      <g key={key}>
        <path d={`M${x1},${y1} C${x1},${y1 + depth} ${x2},${y2 + depth} ${x2},${y2}`} className={"edge" + (n ? " used" : "") + (hot === key ? " hot" : "")} fill="none" markerEnd={n ? "url(#arr-on)" : "url(#arr)"} />
        {n > 0 && <text x={(x1 + x2) / 2} y={y1 + depth * 0.78} textAnchor="middle" className="edge-n">{label} ×{n}</text>}
      </g>
    );
  };

  const label = (n: string) => {
    if (cur === n && flow.current) return `${flow.current.working ? "Đang làm" : "Chờ"} · ${fmtDur(now - flow.current.since)}`;
    return visited.has(n) ? "Đã xong phần mình" : "Chưa tới lượt";
  };

  return (
    <svg viewBox={`0 0 1100 ${height}`} className="flow" role="img" aria-label="Sơ đồ bàn giao giữa các nhân viên">
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" className="arrow" /></marker>
        <marker id="arr-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" className="arrow on" /></marker>
      </defs>
      {straight(OWNER, DIR)}{straight(DIR, OWNER)}
      {execs.map((e) => [straight(DIR, e), straight(e, DIR), straight(e, QA)])}
      {straight(QA, TESTER)}
      {curve(TESTER, DIR, 70, "PASS")}
      {execs.map((e, i) => curve(TESTER, e, 100 + i * 12, "sửa lỗi"))}
      {nodes.map((nd) => {
        const p = person(nd.name), st = stat(nd.name), active = cur === nd.name;
        const cls = "node" + (active ? (flow.current?.working ? " active" : " waiting") : visited.has(nd.name) ? " done" : "");
        const model = p?.models?.[0]?.split(" (")[0];
        return (
          <g key={nd.name} className={cls} transform={`translate(${nd.x},${nd.y})`}>
            <rect width={W} height={H} rx="14" />
            <text x="12" y="28" className="n-icon">{icon(nd.name)}</text>
            <text x="40" y="27" className="n-name">{nd.name.length > 17 ? nd.name.slice(0, 16) + "…" : nd.name}</text>
            <text x="12" y="46" className="n-role">{p?.title ?? ""}</text>
            <text x="12" y="62" className="n-state">{label(nd.name)}</text>
            {nd.name !== OWNER && <text x="12" y="76" className="n-meta">{st.l} lượt gọi model · {st.t} lệnh</text>}
            {model && nd.name !== OWNER && <text x="12" y="88" className="n-meta">{model.length > 27 ? model.slice(0, 26) + "…" : model}</text>}
            {active && flow.current?.working && <circle cx={W - 16} cy="18" r="5" className="pulse" />}
          </g>
        );
      })}
      <text x="12" y={height - 8} className="n-meta">{last ? `Bàn giao gần nhất ${fmtTime(last.at)}: ${last.from} → ${last.to}` : "Chưa có bàn giao nào"}</text>
    </svg>
  );
}
