// สั่ง opencode desktop ให้เปิด session ที่ระบุ (ใช้โดย flashq.py)
// ต้องเปิด desktop พร้อม --remote-debugging-port=9333 (shortcut ตั้งไว้แล้ว)
// วิธี: desktop ใช้ MemoryRouter ที่จำหน้าล่าสุดไว้ใน localStorage
// (`opencode.desktop.window.<id>.last-active-url`) → เขียน route ของ session แล้ว reload หน้าต่าง
// ดูสดได้ต้องเปิดผ่าน "เซิร์ฟเวอร์ที่รันงานอยู่จริง" (เช่น http://127.0.0.1:4096) — เปิดผ่าน sidecar
// จะเห็นแค่ภาพนิ่งตอนเปิด (sidecar ไม่ได้รับ event ของ process อื่น · เจอจริง 2026-10-17)
// → เพิ่ม url นั้นลงรายการเซิร์ฟเวอร์ของ desktop (store "server".list) ให้เองถ้ายังไม่มี
// ใช้: node oc_desktop_open.mjs <sessionID> [serverUrl|sidecar] [port]
// exit 0 = เปิดแล้ว · 2 = ไม่พบ desktop ที่เปิดพอร์ตดีบัก
const [, , sid, server = "sidecar", port = "9333"] = process.argv;
if (!sid) { console.log("usage: oc_desktop_open.mjs <sessionID> [serverUrl|sidecar] [port]"); process.exit(1); }
let pages;
try {
  pages = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json())
    .filter(p => p.type === "page" && p.url.startsWith("oc://renderer"));
} catch {
  console.log(`DESKTOP_OPEN=NO_PORT (เปิด desktop ผ่าน shortcut ที่มี --remote-debugging-port=${port})`);
  process.exit(2);
}
if (!pages.length) { console.log("DESKTOP_OPEN=NO_WINDOW"); process.exit(2); }
const url = server === "sidecar" ? "" : server.trim().replace(/\/+$/, "");
// key ของเซิร์ฟเวอร์ = "sidecar" หรือ url (ServerConnection.key) → base64url ไม่มี padding
const key = Buffer.from(url || "sidecar").toString("base64url");
const route = `/server/${key}/session/${sid}`;
const expr = `(async () => {
  const url = ${JSON.stringify(url)};
  if (url) {
    const st = JSON.parse((await window.api.storeGet("opencode.global.dat", "server")) || "{}");
    st.list = st.list || [];
    if (!st.list.some(c => c.type === "http" && c.http && c.http.url === url)) {
      st.list.push({ type: "http", http: { url } });
      await window.api.storeSet("opencode.global.dat", "server", JSON.stringify(st));
    }
  }
  const ks = Object.keys(localStorage).filter(k => k.startsWith("opencode.desktop.window.") && k.endsWith(".last-active-url"));
  ks.forEach(k => localStorage.setItem(k, ${JSON.stringify(route)}));
  setTimeout(() => location.reload(), 50);
  return ks.length;
})()`;
const page = pages[0];
const n = await new Promise((resolve) => {
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  const t = setTimeout(() => { ws.close(); resolve(-1); }, 8000);
  ws.onopen = () => ws.send(JSON.stringify({ id: 1, method: "Runtime.evaluate", params: { expression: expr, returnByValue: true, awaitPromise: true } }));
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id === 1) { clearTimeout(t); ws.close(); resolve(d.result?.result?.value ?? -1); }
  };
  ws.onerror = () => { clearTimeout(t); resolve(-1); };
});
console.log(n > 0 ? `DESKTOP_OPEN=OK ${sid} via ${url || "sidecar"}` : "DESKTOP_OPEN=FAIL");
process.exit(n > 0 ? 0 : 2);
