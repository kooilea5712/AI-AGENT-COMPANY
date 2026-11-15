import { Flow as FlowData, Person } from "./api";
import { fmtDur, fmtTime, icon, useNow } from "./lib";

// Bốn "ô" cố định của luồng. Ô thực thi lấy tên vai thật (Kỹ sư phần mềm hoặc Chuyên viên media) từ dữ liệu job.
const W = 170, H = 92, Y = 56;
const COL = [20, 250, 480, 710];

type NodeKey = "owner" | "director" | "exec" | "qa";

function execName(flow: FlowData): string {
  return flow.segments.find((s) => s.state === "executing")?.actor ?? "Kỹ sư phần mềm";
}

export default function FlowView({ flow, staff }: { flow: FlowData; staff: Person[] }) {
  const now = useNow();
  const names: Record<NodeKey, string> = { owner: "Chủ studio", director: "Giám đốc điều phối", exec: execName(flow), qa: "Kiểm định" };
  const keyOf = (n: string | null): NodeKey | null => (Object.entries(names).find(([, v]) => v === n)?.[0] as NodeKey) ?? null;
  const person = (k: NodeKey) => staff.find((p) => p.name === names[k]);

  // Đếm bàn giao theo từng cặp (từ -> đến), và cặp nào vừa xảy ra gần nhất để làm động.
  const count: Record<string, number> = {};
  flow.handoffs.forEach((h) => {
    const a = keyOf(h.from), b = keyOf(h.to);
    if (a && b) count[`${a}>${b}`] = (count[`${a}>${b}`] ?? 0) + 1;
  });
  const last = flow.handoffs.length ? flow.handoffs[flow.handoffs.length - 1] : null;
  const hot = last ? `${keyOf(last.from)}>${keyOf(last.to)}` : "";

  const curKey = keyOf(flow.current?.actor ?? null);
  const visited = new Set(flow.segments.map((s) => keyOf(s.actor)).filter(Boolean));
  const stats = (k: NodeKey) => flow.segments.filter((s) => keyOf(s.actor) === k).reduce((a, s) => ({ tools: a.tools + s.tool_calls, llm: a.llm + s.llm_calls }), { tools: 0, llm: 0 });

  const x = (k: NodeKey) => COL[["owner", "director", "exec", "qa"].indexOf(k)];
  // Hai chiều giữa hai ô kề nhau: đi ở y trên, về ở y dưới.
  const edge = (a: NodeKey, b: NodeKey, back = false) => {
    const fwd = x(a) < x(b);
    const y = Y + (back ? 60 : 32);
    const x1 = fwd ? x(a) + W : x(a), x2 = fwd ? x(b) : x(b) + W;
    const key = `${a}>${b}`;
    const n = count[key] ?? 0;
    return (
      <g key={key}>
        <path d={`M${x1},${y} L${x2},${y}`} className={"edge" + (n ? " used" : "") + (hot === key ? " hot" : "")} markerEnd={n ? "url(#arr-on)" : "url(#arr)"} />
        {n > 0 && <text x={(x1 + x2) / 2} y={y - 5} textAnchor="middle" className="edge-n">×{n}</text>}
      </g>
    );
  };
  const qaDir = count["qa>director"] ?? 0;

  const label = (k: NodeKey) => {
    if (curKey === k && flow.current) {
      if (flow.current.working) return `Đang làm · ${fmtDur(now - flow.current.since)}`;
      return `Chờ · ${fmtDur(now - flow.current.since)}`;
    }
    return visited.has(k) ? "Đã xong phần mình" : "Chưa tới lượt";
  };

  return (
    <svg viewBox="0 0 900 290" className="flow" role="img" aria-label="Sơ đồ bàn giao giữa các nhân viên">
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" className="arrow" /></marker>
        <marker id="arr-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" className="arrow on" /></marker>
      </defs>
      {edge("owner", "director")}{edge("director", "owner", true)}
      {edge("director", "exec")}{edge("exec", "director", true)}
      {edge("exec", "qa")}{edge("qa", "exec", true)}
      {/* QA -> Giám đốc: đường vòng phía dưới vì hai ô không kề nhau */}
      <path d={`M${x("qa") + W / 2},${Y + H} C${x("qa") + W / 2},${Y + H + 90} ${x("director") + W / 2},${Y + H + 90} ${x("director") + W / 2},${Y + H + 4}`}
        className={"edge" + (qaDir ? " used" : "") + (hot === "qa>director" ? " hot" : "")} fill="none" markerEnd={qaDir ? "url(#arr-on)" : "url(#arr)"} />
      {qaDir > 0 && <text x={(x("qa") + x("director") + W) / 2} y={Y + H + 76} textAnchor="middle" className="edge-n">PASS ×{qaDir}</text>}

      {(["owner", "director", "exec", "qa"] as NodeKey[]).map((k) => {
        const p = person(k), st = stats(k);
        const active = curKey === k;
        const cls = "node" + (active ? (flow.current?.working ? " active" : " waiting") : visited.has(k) ? " done" : "");
        return (
          <g key={k} className={cls} transform={`translate(${x(k)},${Y})`}>
            <rect width={W} height={H} rx="14" />
            <text x="14" y="30" className="n-icon">{icon(names[k])}</text>
            <text x="44" y="29" className="n-name">{names[k]}</text>
            <text x="14" y="52" className="n-role">{p?.title ?? ""}{p?.combo ? ` · ${p.combo}` : ""}</text>
            <text x="14" y="72" className="n-state">{label(k)}</text>
            {k !== "owner" && <text x="14" y="86" className="n-meta">{st.llm} lượt gọi model · {st.tools} lệnh</text>}
            {active && flow.current?.working && <circle cx={W - 16} cy="18" r="5" className="pulse" />}
          </g>
        );
      })}
      <text x="20" y="278" className="n-meta">{last ? `Bàn giao gần nhất ${fmtTime(last.at)}: ${last.from} → ${last.to}` : "Chưa có bàn giao nào"}</text>
    </svg>
  );
}
