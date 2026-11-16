import { useEffect, useState } from "react";
import { api, Cand, Settings as S } from "./api";

type TestRes = { ok: boolean; served_by?: string; skipped?: string[]; error?: string };

export default function SettingsPage() {
  const [s, setS] = useState<S | null>(null);
  const [roles, setRoles] = useState<Record<string, Cand[]>>({});
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [clear, setClear] = useState<Record<string, boolean>>({});
  const [conn, setConn] = useState<Record<string, { base_url: string; enabled: boolean }>>({});
  const [ownerBrief, setOwnerBrief] = useState(false);
  const [sandbox, setSandbox] = useState<"docker" | "local">("docker");
  const [tests, setTests] = useState<Record<string, TestRes | "...">>({});
  const [msg, setMsg] = useState("");
  const [newConn, setNewConn] = useState({ name: "", label: "", base_url: "" });

  const adopt = (x: S) => {
    setS(x); setRoles(JSON.parse(JSON.stringify(x.roles)));
    setConn(Object.fromEntries(Object.entries(x.connections).map(([k, c]) => [k, { base_url: c.base_url, enabled: c.enabled }])));
    setOwnerBrief(x.owner_approves_brief); setSandbox(x.sandbox_mode); setKeys({}); setClear({});
  };
  useEffect(() => { api.settings().then(adopt).catch((e) => setMsg(String(e))); }, []);
  if (!s) return <p className="muted pad">{msg || "Đang tải…"}</p>;

  const save = async () => {
    setMsg("");
    const connections: Record<string, unknown> = {};
    for (const k of Object.keys(s.connections)) {
      const c: Record<string, unknown> = { base_url: conn[k].base_url, enabled: conn[k].enabled };
      if (clear[k]) c.api_key = "__clear__"; else if (keys[k]?.trim()) c.api_key = keys[k].trim();
      connections[k] = c;
    }
    try { adopt(await api.saveSettings({ connections, roles, owner_approves_brief: ownerBrief, sandbox_mode: sandbox })); setMsg("Đã lưu."); }
    catch (e) { setMsg("Lỗi: " + String(e)); }
  };
  const addConn = async () => {
    const name = newConn.name.trim().toLowerCase().replace(/[^a-z0-9_-]/g, "");
    if (!name || !newConn.base_url.trim()) { setMsg("Cần tên (chữ thường/số) và địa chỉ base URL."); return; }
    try { adopt(await api.saveSettings({ connections: { [name]: { label: newConn.label || name, base_url: newConn.base_url.trim(), enabled: true } } })); setNewConn({ name: "", label: "", base_url: "" }); }
    catch (e) { setMsg("Lỗi: " + String(e)); }
  };
  const test = async (role: string) => {
    setTests((t) => ({ ...t, [role]: "..." }));
    await save();   // thử đúng cấu hình đang chỉnh
    try { setTests((t) => ({ ...t, [role]: "..." })); const r = await api.testRole(role); setTests((t) => ({ ...t, [role]: r })); }
    catch (e) { setTests((t) => ({ ...t, [role]: { ok: false, error: String(e) } })); }
  };
  const move = (role: string, i: number, d: number) => setRoles((r) => { const l = [...r[role]]; const j = i + d; if (j < 0 || j >= l.length) return r; [l[i], l[j]] = [l[j], l[i]]; return { ...r, [role]: l }; });
  const preset = async (id: string) => {
    const p = s.presets.find((x) => x.id === id)!;
    try { adopt(await api.saveSettings({ roles: p.roles })); setMsg(`Đã áp dụng: ${p.label}`); } catch (e) { setMsg("Lỗi: " + String(e)); }
  };

  return (
    <div className="pad settings">
      <div className="row between"><h2>Cài đặt</h2><div className="row">{msg && <span className={msg.startsWith("Lỗi") ? "err" : "okc"}>{msg}</span>}<button className="primary" onClick={save}>Lưu thay đổi</button></div></div>
      <p className="muted">Khoá API lưu trong file <code>{s.data_file}</code> ngoài thư mục dự án, không bao giờ vào Git và không hiện lại trên màn hình.</p>

      <div className="card">
        <h3>Chọn nhanh</h3>
        <div className="grid presets">
          {s.presets.map((p) => <div key={p.id} className="preset"><b>{p.label}</b><div className="muted small">{p.note}</div><button onClick={() => preset(p.id)}>Áp dụng</button></div>)}
        </div>
      </div>

      <div className="card">
        <h3>Nhà cung cấp model</h3>
        <p className="muted small">Mỗi vai bên dưới chọn model từ các nhà cung cấp này. Laptop không có Ollama: tắt “Ollama” (hoặc để nguyên, ứng viên lỗi sẽ tự bị bỏ qua) và nhập khoá Claude.</p>
        {Object.entries(s.connections).map(([k, c]) => (
          <div key={k} className="conn">
            <div className="row between">
              <b>{c.label}</b>
              <label className="small"><input type="checkbox" checked={conn[k]?.enabled ?? true} onChange={(e) => setConn({ ...conn, [k]: { ...conn[k], enabled: e.target.checked } })} /> bật</label>
            </div>
            <div className="row">
              <input className="grow" value={conn[k]?.base_url ?? ""} onChange={(e) => setConn({ ...conn, [k]: { ...conn[k], base_url: e.target.value } })} placeholder="Base URL (OpenAI-compatible)" />
            </div>
            {c.needs_key ? (
              <div className="row">
                <input className="grow" type="password" autoComplete="off" value={keys[k] ?? ""} onChange={(e) => { setKeys({ ...keys, [k]: e.target.value }); setClear({ ...clear, [k]: false }); }}
                  placeholder={c.has_key ? `Đã có khoá (${c.key_hint}); nhập khoá mới để thay` : "Dán khoá API vào đây"} />
                {c.has_key && <button onClick={() => setClear({ ...clear, [k]: !clear[k] })}>{clear[k] ? "Giữ khoá" : "Xoá khoá"}</button>}
                <span className={"badge " + (c.has_key && !clear[k] ? "ok" : "warn")}>{c.has_key && !clear[k] ? "có khoá" : "chưa có khoá"}</span>
              </div>
            ) : <div className="muted small">Chạy trên máy này, không cần khoá.</div>}
          </div>
        ))}
        <details><summary>Thêm nhà cung cấp OpenAI-compatible khác</summary>
          <div className="row">
            <input placeholder="tên (vd. openrouter)" value={newConn.name} onChange={(e) => setNewConn({ ...newConn, name: e.target.value })} />
            <input placeholder="nhãn hiển thị" value={newConn.label} onChange={(e) => setNewConn({ ...newConn, label: e.target.value })} />
            <input className="grow" placeholder="https://…/v1" value={newConn.base_url} onChange={(e) => setNewConn({ ...newConn, base_url: e.target.value })} />
            <button onClick={addConn}>Thêm</button>
          </div>
        </details>
      </div>

      <div className="card">
        <h3>Model theo vai</h3>
        <p className="muted small">Mỗi vai có danh sách ứng viên theo thứ tự ưu tiên. Ứng viên đầu lỗi (mạng, hết quota, thiếu khoá) thì tự dùng ứng viên kế. Tên model Claude có thể đổi khi có bản mới.</p>
        {Object.entries(s.roles_meta).map(([role, meta]) => (
          <div key={role} className="rolebox">
            <div className="row between"><div><b>{meta.label}</b><div className="muted small">{meta.hint}</div></div><button onClick={() => test(role)}>Thử</button></div>
            {(roles[role] ?? []).map((c, i) => (
              <div key={i} className="row cand">
                <span className="muted small">{i + 1}.</span>
                <select value={c.connection} onChange={(e) => setRoles({ ...roles, [role]: roles[role].map((x, j) => j === i ? { ...x, connection: e.target.value } : x) })}>
                  {Object.entries(s.connections).map(([k, cc]) => <option key={k} value={k}>{cc.label}</option>)}
                </select>
                <input className="grow" value={c.model} onChange={(e) => setRoles({ ...roles, [role]: roles[role].map((x, j) => j === i ? { ...x, model: e.target.value } : x) })} placeholder="tên model" />
                <button onClick={() => move(role, i, -1)} disabled={i === 0}>↑</button>
                <button onClick={() => move(role, i, 1)} disabled={i === roles[role].length - 1}>↓</button>
                <button onClick={() => setRoles({ ...roles, [role]: roles[role].filter((_, j) => j !== i) })} disabled={roles[role].length === 1}>×</button>
              </div>
            ))}
            <button className="small-btn" onClick={() => setRoles({ ...roles, [role]: [...(roles[role] ?? []), { connection: Object.keys(s.connections)[0], model: "" }] })}>+ thêm ứng viên</button>
            {tests[role] === "..." && <div className="muted small">Đang thử…</div>}
            {tests[role] && tests[role] !== "..." && (() => { const r = tests[role] as TestRes; return (
              <div className={r.ok ? "okc small" : "err small"}>{r.ok ? `✔ ${r.served_by} phục vụ` : `✘ ${r.error}`}{r.skipped && r.skipped.length > 0 && <div className="muted">Bỏ qua: {r.skipped.join(" | ")}</div>}</div>
            ); })()}
          </div>
        ))}
      </div>

      <div className="card">
        <h3>Luồng và an toàn</h3>
        <label className="row"><input type="checkbox" checked={ownerBrief} onChange={(e) => setOwnerBrief(e.target.checked)} />
          <span>Tôi muốn tự duyệt brief <span className="muted small">(mặc định tắt: Giám đốc tự chốt brief, bạn chỉ xem kết quả cuối)</span></span></label>
        <div className="row"><span>Chạy lệnh của agent:</span>
          <select value={sandbox} onChange={(e) => setSandbox(e.target.value as "docker" | "local")}>
            <option value="docker">Docker (cô lập, khuyên dùng)</option><option value="local">Trực tiếp trên máy (KHÔNG cô lập)</option>
          </select></div>
        {sandbox === "local" && <p className="err small">Chế độ trực tiếp chỉ có danh sách đen từ khoá, script do agent viết làm được mọi thứ bạn làm được. Chỉ dùng khi chưa cài Docker.</p>}
        <p className="muted small">Git: sau mỗi lần agent chạy, hệ thống bắt buộc commit; job gắn project làm trên nhánh riêng, không bao giờ push.</p>
      </div>
    </div>
  );
}
