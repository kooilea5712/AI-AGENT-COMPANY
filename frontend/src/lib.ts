import { useEffect, useState } from "react";

// Tám bước của thiết kế (bước 5 tự kiểm nằm trong bước 4). Bước 2 do Giám đốc tự chốt.
export const STEPS = ["Tiếp nhận", "Giám đốc duyệt brief", "Lập kế hoạch", "Thực thi", "Tự kiểm", "Kiểm định", "Bàn giao", "Rút kinh nghiệm"];
export const STATE_VI: Record<string, string> = {
  intake: "Giám đốc đang tiếp nhận", waiting_answer: "Giám đốc hỏi bạn", brief_review: "Giám đốc đang duyệt brief",
  awaiting_brief: "Chờ bạn duyệt brief", planning: "Giám đốc đang chia việc", executing: "Đang thực thi",
  qa_design: "Đang thiết kế testcase", qa_run: "Đang chạy testcase",
  handoff: "Đang viết bàn giao", awaiting_handoff: "Chờ bạn xem kết quả", lessons: "Rút kinh nghiệm",
  done: "Hoàn tất", blocked: "Đã dừng",
};
export const WAITING_YOU = new Set(["waiting_answer", "awaiting_brief", "awaiting_handoff", "blocked"]);
export const RUNNING = new Set(["intake", "brief_review", "planning", "executing", "qa_design", "qa_run", "handoff", "lessons"]);

export function tone(state: string): "warn" | "bad" | "ok" | "run" {
  if (state === "blocked") return "bad";
  if (WAITING_YOU.has(state)) return "warn";
  if (state === "done") return "ok";
  return "run";
}

export const ICON: Record<string, string> = {
  "Chủ studio": "👤", "Giám đốc điều phối": "🧭", "Kỹ sư phần mềm": "💻", "Chuyên viên media": "🎨", "Kiểm định": "🔍", "Kiểm thử viên": "🧪", "Hệ thống": "⚙️",
};
export const icon = (name: string | null | undefined) => (name && ICON[name]) || "•";

export function fmtDur(sec: number): string {
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  return m < 60 ? `${m}p ${sec % 60}s` : `${Math.floor(m / 60)}g ${m % 60}p`;
}
export const fmtTime = (ts: number) => new Date(ts * 1000).toLocaleTimeString("vi-VN");
export const fmtDate = (ts: number) => new Date(ts * 1000).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/** Đồng hồ nhảy mỗi giây, dùng cho "đã làm được bao lâu". */
export function useNow(): number {
  const [n, setN] = useState(Date.now() / 1000);
  useEffect(() => { const t = setInterval(() => setN(Date.now() / 1000), 1000); return () => clearInterval(t); }, []);
  return n;
}

/** Lưu lựa chọn giao diện (sáng/tối/hệ thống). localStorage có thể bị chặn nên bọc try/catch. */
export type ThemeMode = "system" | "light" | "dark";
export function useTheme(): [ThemeMode, (m: ThemeMode) => void] {
  const [mode, setMode] = useState<ThemeMode>(() => { try { return (localStorage.getItem("theme") as ThemeMode) || "system"; } catch { return "system"; } });
  useEffect(() => {
    const apply = () => {
      const dark = mode === "dark" || (mode === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
      document.documentElement.dataset.theme = dark ? "dark" : "light";
    };
    apply();
    try { localStorage.setItem("theme", mode); } catch { /* bỏ qua */ }
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [mode]);
  return [mode, setMode];
}
