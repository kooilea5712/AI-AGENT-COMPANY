// Vỏ Electron của Studio AI.
// Việc của nó: khi mở thì tự bật các dịch vụ cần thiết theo thứ tự (Docker Desktop, Ollama, OmniRoute, backend),
// đợi từng cái sẵn sàng rồi mở giao diện; khi đóng thì tắt đúng những gì NÓ đã bật (không đụng dịch vụ đã chạy sẵn).
// Giao diện web (frontend/dist) do backend phục vụ ở cổng 8000, nên không cần Vite hay Node dev server.
const { app, BrowserWindow, ipcMain, shell, Menu } = require("electron");
const { spawn, spawnSync, execFileSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const BACKEND_URL = "http://127.0.0.1:8000";
const OLLAMA_URL = "http://127.0.0.1:11434";
const OMNIROUTE_URL = "http://127.0.0.1:20128";

// ---------- nhật ký của launcher ----------
const LOG_DIR = path.join(app.getPath("userData"), "logs");
fs.mkdirSync(LOG_DIR, { recursive: true });
const LOG_FILE = path.join(LOG_DIR, "launcher.log");
function log(msg) {
  const line = `${new Date().toISOString()} ${msg}\n`;
  try { fs.appendFileSync(LOG_FILE, line); } catch { /* không có chỗ ghi thì thôi */ }
}

// ---------- tìm thư mục dự án ----------
function findRoot() {
  const ok = (d) => d && fs.existsSync(path.join(d, "backend", "app", "main.py"));
  const cands = [process.env.STUDIO_ROOT];
  for (const f of [path.join(process.resourcesPath || "", "studio-root.txt"), path.join(path.dirname(process.execPath), "studio-root.txt")]) {
    try { cands.push(fs.readFileSync(f, "utf8").trim()); } catch { /* chưa có */ }
  }
  // Chạy từ mã nguồn (electron .) hoặc exe đặt trong dự án: đi ngược lên tìm.
  for (let d = __dirname, i = 0; i < 6; i++, d = path.dirname(d)) cands.push(d);
  for (let d = path.dirname(process.execPath), i = 0; i < 6; i++, d = path.dirname(d)) cands.push(d);
  return cands.find(ok) || null;
}
const ROOT = findRoot();

// ---------- tiện ích HTTP / tiến trình ----------
function ping(url, timeoutMs = 1500) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => { res.resume(); resolve(res.statusCode > 0 && res.statusCode < 500); });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}
async function waitFor(url, seconds, label) {
  const end = Date.now() + seconds * 1000;
  while (Date.now() < end) {
    if (await ping(url)) return true;
    await new Promise((r) => setTimeout(r, 700));
  }
  throw new Error(`${label} không sẵn sàng sau ${seconds} giây`);
}
function which(name) {
  const r = spawnSync("where", [name], { encoding: "utf8", windowsHide: true });
  return r.status === 0 ? r.stdout.split(/\r?\n/)[0].trim() : null;
}
function killTree(pid) {
  try { execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" }); } catch { /* đã thoát */ }
}
// Biến PATH của registry: app mở từ Explorer có thể có PATH cũ hơn so với khi cài winget/npm.
function freshEnv(extra = {}) {
  let p = process.env.PATH || "";
  try {
    const q = (k) => execFileSync("reg", ["query", k, "/v", "Path"], { encoding: "utf8", windowsHide: true }).split(/REG_(?:EXPAND_)?SZ/)[1]?.trim() || "";
    p = [q("HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment"), q("HKCU\\Environment"), p].join(";");
    p = p.replace(/%([^%]+)%/g, (_, n) => process.env[n] || "");
  } catch { /* dùng PATH hiện tại */ }
  return { ...process.env, PATH: p, ...extra };
}

// ---------- dịch vụ ----------
const started = { ollama: null, omniroute: false, backend: null }; // chỉ ghi lại thứ do mình bật
let splash = null;
const status = (id, state, detail = "") => {
  log(`${id}: ${state} ${detail}`);
  if (splash && !splash.isDestroyed()) splash.webContents.send("status", { id, state, detail });
};

async function ensureDocker() {
  // Sandbox Docker là mặc định nên cần engine. Bật Docker Desktop nếu chưa chạy, nhưng KHÔNG chặn giao diện chờ nó.
  const docker = which("docker");
  if (!docker) return status("docker", "skip", "chưa cài Docker");
  const up = () => spawnSync(docker, ["info"], { windowsHide: true, timeout: 8000 }).status === 0;
  if (up()) return status("docker", "ok", "engine đang chạy");
  const exe = "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe";
  if (!fs.existsSync(exe)) return status("docker", "skip", "không thấy Docker Desktop");
  status("docker", "work", "đang bật Docker Desktop…");
  spawn(exe, [], { detached: true, stdio: "ignore" }).unref();
  const end = Date.now() + 90_000;
  while (Date.now() < end) {
    await new Promise((r) => setTimeout(r, 3000));
    if (up()) return status("docker", "ok", "engine sẵn sàng");
  }
  status("docker", "warn", "Docker còn đang khởi động; job dùng sandbox sẽ chạy được khi nó xong");
}

async function ensureOllama() {
  if (await ping(OLLAMA_URL + "/api/tags")) return status("ollama", "ok", "đã chạy sẵn");
  status("ollama", "work", "đang bật…");
  const exe = which("ollama") || path.join(process.env.LOCALAPPDATA || "", "Programs", "Ollama", "ollama.exe");
  if (!fs.existsSync(exe)) throw new Error("Không tìm thấy Ollama. Hãy cài Ollama trước.");
  started.ollama = spawn(exe, ["serve"], { windowsHide: true, stdio: "ignore", env: freshEnv() });
  started.ollama.on("exit", (c) => log(`ollama thoát: ${c}`));
  await waitFor(OLLAMA_URL + "/api/tags", 40, "Ollama");
  status("ollama", "ok", "đã bật");
}

async function ensureOmniroute() {
  if (await ping(OMNIROUTE_URL + "/api/health")) return status("omniroute", "ok", "đã chạy sẵn");
  status("omniroute", "work", "đang bật…");
  // Mặc định OmniRoute nghe 0.0.0.0 không khoá: ép loopback để người khác trong LAN không tiêu quota của bạn.
  const env = freshEnv({ OMNIROUTE_SERVER_HOST: "127.0.0.1" });
  const r = spawnSync("cmd", ["/c", "omniroute", "serve", "--daemon", "--no-open"], { env, windowsHide: true, encoding: "utf8", timeout: 60000 });
  log(`omniroute serve: exit=${r.status} ${(r.stdout || "").slice(-200)}`);
  started.omniroute = true;
  await waitFor(OMNIROUTE_URL + "/api/health", 60, "OmniRoute");
  status("omniroute", "ok", "đã bật");
}

async function ensureBackend() {
  if (await ping(BACKEND_URL + "/staff")) return status("backend", "ok", "đã chạy sẵn");
  status("backend", "work", "đang bật…");
  const py = path.join(ROOT, "backend", ".venv", "Scripts", "python.exe");
  if (!fs.existsSync(py)) throw new Error(`Không thấy Python venv: ${py}`);
  // Giao diện build sẵn: nếu chưa có thì build một lần (cần Node + npm đã cài).
  if (!fs.existsSync(path.join(ROOT, "frontend", "dist", "index.html"))) {
    status("backend", "work", "đang build giao diện lần đầu…");
    const b = spawnSync("cmd", ["/c", "npm", "run", "build"], { cwd: path.join(ROOT, "frontend"), env: freshEnv(), windowsHide: true, encoding: "utf8", timeout: 300000 });
    if (b.status !== 0) throw new Error("Build giao diện lỗi: " + (b.stderr || b.stdout || "").slice(-300));
  }
  const out = fs.openSync(path.join(LOG_DIR, "backend.log"), "a");
  started.backend = spawn(py, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    { cwd: path.join(ROOT, "backend"), windowsHide: true, stdio: ["ignore", out, out], env: freshEnv() });
  started.backend.on("exit", (c) => log(`backend thoát: ${c}`));
  await waitFor(BACKEND_URL + "/staff", 45, "Backend");
  status("backend", "ok", "đã bật");
}

async function startAll() {
  if (!ROOT) throw new Error("Không tìm thấy thư mục dự án Studio AI (cần backend/app/main.py). Đặt biến STUDIO_ROOT hoặc file studio-root.txt cạnh exe.");
  log(`ROOT=${ROOT}`);
  status("docker", "work", "kiểm tra…");
  // Ollama, OmniRoute, backend phải tuần tự (backend gọi hai cái kia); Docker chạy song song vì chậm và không chặn.
  const dockerP = ensureDocker().catch((e) => status("docker", "warn", String(e.message || e)));
  await ensureOllama();
  await ensureOmniroute();
  await ensureBackend();
  status("ui", "ok", "mở giao diện");
  dockerP.then(() => {});
}

function stopAll() {
  // Chỉ tắt thứ do app này bật.
  if (started.backend && started.backend.pid) killTree(started.backend.pid);
  if (started.omniroute) {
    try { spawnSync("cmd", ["/c", "omniroute", "stop"], { env: freshEnv(), windowsHide: true, timeout: 20000 }); } catch { /* bỏ qua */ }
  }
  if (started.ollama && started.ollama.pid) killTree(started.ollama.pid);
  log("đã tắt các dịch vụ do app bật");
}

// ---------- cửa sổ ----------
let main = null;
function createSplash() {
  splash = new BrowserWindow({ width: 520, height: 420, frame: false, resizable: false, show: true, center: true, backgroundColor: "#0e1117",
    title: "Studio AI", webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true } });
  splash.loadFile(path.join(__dirname, "splash.html"));
}
function createMain() {
  main = new BrowserWindow({ width: 1360, height: 860, minWidth: 900, minHeight: 600, title: "Studio AI", backgroundColor: "#0e1117",
    icon: path.join(__dirname, "icon.ico"), show: false, webPreferences: { contextIsolation: true, sandbox: true } });
  main.loadURL(BACKEND_URL);
  main.once("ready-to-show", () => { main.show(); if (splash && !splash.isDestroyed()) splash.close(); });
  // Liên kết ra ngoài mở bằng trình duyệt mặc định; chỉ cho cửa sổ này điều hướng trong nguồn của backend.
  main.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: "deny" }; });
  main.webContents.on("will-navigate", (e, url) => { if (!url.startsWith(BACKEND_URL)) { e.preventDefault(); shell.openExternal(url); } });
  main.webContents.on("did-fail-load", () => setTimeout(() => main && !main.isDestroyed() && main.loadURL(BACKEND_URL), 1500));
  main.on("closed", () => { main = null; });
}

const lock = app.requestSingleInstanceLock();
if (!lock) { app.quit(); } else {
  app.on("second-instance", () => { if (main) { if (main.isMinimized()) main.restore(); main.focus(); } });
  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null);
    createSplash();
    ipcMain.handle("retry", () => { app.relaunch(); app.exit(0); });
    ipcMain.handle("quit", () => app.quit());
    ipcMain.handle("open-logs", () => shell.openPath(LOG_DIR));
    try {
      await startAll();
      createMain();
    } catch (e) {
      log(`LỖI: ${e.stack || e}`);
      if (splash && !splash.isDestroyed()) splash.webContents.send("fatal", String(e.message || e));
    }
  });
  app.on("window-all-closed", () => app.quit());
  let cleaned = false;
  app.on("before-quit", () => { if (!cleaned) { cleaned = true; stopAll(); } });
}
