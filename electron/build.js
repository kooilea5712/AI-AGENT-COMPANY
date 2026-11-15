// Đóng gói exe: dist-app/Studio AI-win32-x64/Studio AI.exe, và ghi studio-root.txt (đường dẫn dự án) cạnh nó.
const { packager } = require("@electron/packager");
const fs = require("fs");
const path = require("path");
(async () => {
  const root = path.resolve(__dirname, "..");
  const out = path.join(root, "dist-app");
  const dirs = await packager({
    dir: __dirname, name: "Studio AI", platform: "win32", arch: "x64", out, overwrite: true, icon: path.join(__dirname, "icon.ico"),
    ignore: [/^\/build\.js$/, /^\/node_modules\/(?!$)/], prune: false, asar: false,
    win32metadata: { ProductName: "Studio AI", FileDescription: "Studio freelance AI" },
  });
  for (const d of dirs) {
    fs.writeFileSync(path.join(d, "resources", "studio-root.txt"), root, "utf8");
    console.log("Đã build:", path.join(d, "Studio AI.exe"));
  }
})().catch((e) => { console.error(e); process.exit(1); });
