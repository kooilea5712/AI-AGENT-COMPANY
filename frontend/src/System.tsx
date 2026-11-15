import { useEffect, useState } from "react";
import { api } from "./api";

export default function System() {
  const [h, setH] = useState<any>(null);
  const [deep, setDeep] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.health(false).then(setH).catch((e) => setH({ error: String(e) }));
  useEffect(() => { load(); }, []);
  const runDeep = async () => { setBusy(true); try { setDeep(await api.health(true)); } catch (e) { setDeep({ error: String(e), combos: {} }); } finally { setBusy(false); } };
  if (!h) return <p className="muted pad">Đang kiểm tra…</p>;
  if (h.error) return <p className="err pad">Không gọi được backend: {h.error}</p>;
  const mark = (ok: boolean) => <span className={ok ? "okc" : "badc"}>{ok ? "●" : "●"}</span>;
  const sb = h.sandbox;
  return (
    <div className="pad system">
      <div className="row between"><h2>Hệ thống</h2><button onClick={load}>Kiểm tra lại</button></div>
      <p className="muted">Chế độ LLM: <b>{h.llm_mode}</b> · {h.llm_base_url}</p>
      <div className="card"><h3>Dịch vụ</h3>
        <p>{mark(h.omniroute.ok)} OmniRoute <span className="muted">{h.omniroute.ok ? "đang chạy" : h.omniroute.error}</span></p>
        <p>{mark(h.ollama.ok)} Ollama <span className="muted">{h.ollama.ok ? `${h.ollama.models.length} model: ${h.ollama.models.join(", ")}` : h.ollama.error}</span></p>
        {sb && <p>{mark(sb.ok)} Sandbox <b>{sb.mode}</b> <span className="muted">{sb.ok ? (sb.image ? `image ${sb.image}, mạng: ${sb.network}` : sb.note) : sb.error}</span></p>}
      </div>
      <div className="card"><h3>Công cụ dòng lệnh</h3>
        {Object.entries<any>(h.tools).map(([k, v]) => <p key={k}>{mark(v.ok)} <b>{k}</b> <span className="muted">{v.version ?? "chưa cài"}</span></p>)}
      </div>
      <div className="card"><h3>Combo và model đang phục vụ</h3>
        <p className="muted">Gọi thật từng combo, lần lượt (Ollama phải nạp model nên có thể mất vài chục giây).</p>
        <button disabled={busy} onClick={runDeep}>{busy ? "Đang thử…" : "Thử từng combo"}</button>
        {deep?.error && <p className="err">{deep.error}</p>}
        {deep && Object.entries<any>(deep.combos).map(([k, v]) => <p key={k}>{mark(v.ok)} <b>{k}</b> → {v.ok ? v.served_by : v.error}</p>)}
      </div>
    </div>
  );
}
