import { useEffect, useState } from "react";
import { api } from "./api";

export default function System() {
  const [h, setH] = useState<any>(null);
  const [deep, setDeep] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.health(false).then(setH).catch((e) => setH({ error: String(e) }));
  useEffect(() => { load(); }, []);
  const runDeep = async () => { setBusy(true); try { setDeep(await api.health(true)); } catch (e) { setDeep({ error: String(e), roles: {} }); } finally { setBusy(false); } };
  if (!h) return <p className="muted pad">Đang kiểm tra…</p>;
  if (h.error) return <p className="err pad">Không gọi được backend: {h.error}</p>;
  const mark = (ok: boolean) => <span className={ok ? "okc" : "badc"}>●</span>;
  const sb = h.sandbox;
  const roles = deep?.roles ?? h.roles;
  return (
    <div className="pad system">
      <div className="row between"><h2>Hệ thống</h2><button onClick={load}>Kiểm tra lại</button></div>
      <div className="card"><h3>Dịch vụ</h3>
        <p>{mark(h.ollama.ok)} Ollama <span className="muted">{h.ollama.ok ? `${h.ollama.models.length} model: ${h.ollama.models.join(", ")}` : `không có (${h.ollama.error}). Không sao nếu bạn dùng Claude/OmniRoute.`}</span></p>
        <p>{mark(h.omniroute.ok)} OmniRoute <span className="muted">{h.omniroute.ok ? "đang chạy" : "không chạy"}</span></p>
        {sb && <p>{mark(sb.ok)} Sandbox <b>{sb.mode}</b> <span className="muted">{sb.ok ? (sb.image ? `image ${sb.image}, mạng: ${sb.network}` : sb.note) : sb.error}</span></p>}
        {h.artcraft && <p>{mark(h.artcraft.vectorcraft && h.artcraft.pdfcraft)} ArtCraft <span className="muted">VectorCraft {h.artcraft.vectorcraft ? "có" : "thiếu"}, PdfCraft {h.artcraft.pdfcraft ? "có" : "thiếu"}</span></p>}
      </div>
      <div className="card"><h3>Model theo vai</h3>
        <p className="muted small">Mỗi vai thử lần lượt các ứng viên; ứng viên không dùng được (thiếu khoá, bị tắt) bị bỏ qua.</p>
        <button disabled={busy} onClick={runDeep}>{busy ? "Đang thử (có thể mất vài chục giây)…" : "Thử gọi thật từng vai"}</button>
        {deep?.error && <p className="err">{deep.error}</p>}
        {Object.entries<any>(roles).map(([k, v]) => (
          <div key={k} className="rolebox">
            <p>{mark(v.ok ?? v.usable)} <b>{v.label}</b> {v.served_by && <span className="muted">→ {v.served_by}</span>}{v.error && <span className="err"> {v.error}</span>}</p>
            <div className="muted small">{v.chain.map((c: any) => `${c.connection}/${c.model}${c.skip ? ` (bỏ qua: ${c.skip})` : ""}`).join("  →  ")}</div>
          </div>
        ))}
      </div>
      <div className="card"><h3>Công cụ dòng lệnh trên máy</h3>
        {Object.entries<any>(h.tools).map(([k, v]) => <p key={k}>{mark(v.ok)} <b>{k}</b> <span className="muted">{v.version ?? "chưa cài"}</span></p>)}
      </div>
    </div>
  );
}
