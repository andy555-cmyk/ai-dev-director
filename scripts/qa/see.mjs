// AI DEV DIRECTOR v4 "eyes": open a running app in headless Chrome, capture each viewport and measure layout defects.
// Zero dependencies: Node 22+ global WebSocket + Chrome DevTools Protocol.
// usage: node see.mjs --url http://127.0.0.1:5173/ --out DIR [--paths /,/settings] [--sizes 1440x900,390x844]
//        [--chrome PATH] [--wait 1500] [--min-font 12]
// stdout: one JSON report. Exit 0 when the report was produced (defects are data, not a crash), 2 on usage/launch errors.
import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? a.concat([[v.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : 'true']]) : a), []));
const fail = (msg) => { process.stdout.write(JSON.stringify({ ok: false, error: msg }) + '\n'); process.exit(2); };
if (!args.url || !args.out) fail('--url and --out are required');
const base = new URL(args.url);
if (!['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname)) fail('only local apps are inspected');
const paths = (args.paths || base.pathname || '/').split(',').map((p) => p.trim()).filter(Boolean);
const sizes = (args.sizes || '1440x900,390x844').split(',').map((s) => s.split('x').map(Number)).filter(([w, h]) => w > 0 && h > 0);
const waitMs = Math.min(Number(args.wait || 1500), 15000);
const minFont = Number(args['min-font'] || 13);
const chrome = args.chrome || ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium', '/usr/bin/google-chrome', '/usr/bin/chromium'].find(existsSync);
if (!chrome) fail('Chrome not found');
mkdirSync(args.out, { recursive: true });

// The audit runs inside the page. Keep it self-contained (serialised with toString).
function audit(minFont) {
  const vis = (el) => { const s = getComputedStyle(el); const r = el.getBoundingClientRect(); return s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0.05 && r.width > 1 && r.height > 1; };
  const label = (el) => { const id = el.id ? '#' + el.id : ''; const c = (typeof el.className === 'string' && el.className.trim()) ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''; return el.tagName.toLowerCase() + id + c; };
  const text = (el) => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 60);
  const doc = document.documentElement, W = innerWidth, H = innerHeight;
  const leaves = [...document.body.querySelectorAll('*')].filter((el) => vis(el) && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()));
  const defects = [];
  const smallText = leaves.filter((el) => parseFloat(getComputedStyle(el).fontSize) < minFont).slice(0, 30)
    .map((el) => ({ el: label(el), text: text(el), px: parseFloat(getComputedStyle(el).fontSize) }));
  if (smallText.length) defects.push({ kind: 'small_text', count: smallText.length, items: smallText.slice(0, 10) });
  const clipped = leaves.filter((el) => { const s = getComputedStyle(el); return (el.scrollWidth > el.clientWidth + 2 && s.overflowX !== 'visible' && s.textOverflow !== 'ellipsis') || (el.scrollHeight > el.clientHeight + 2 && ['hidden', 'clip'].includes(s.overflowY) && !s.webkitLineClamp); })
    .slice(0, 20).map((el) => ({ el: label(el), text: text(el) }));
  if (clipped.length) defects.push({ kind: 'clipped_text', count: clipped.length, items: clipped.slice(0, 10) });
  const offscreen = leaves.filter((el) => { const r = el.getBoundingClientRect(); return r.right > W + 2 || r.left < -2; }).slice(0, 20).map((el) => ({ el: label(el), text: text(el) }));
  if (offscreen.length) defects.push({ kind: 'off_screen', count: offscreen.length, items: offscreen.slice(0, 10) });
  if (doc.scrollWidth > W + 2) defects.push({ kind: 'horizontal_scroll', count: 1, items: [{ width: doc.scrollWidth, viewport: W }] });
  // Overlap between interactive controls and text blocks that are not ancestors/descendants of each other.
  const boxes = [...document.body.querySelectorAll('button,a,input,textarea,select,[role=button],h1,h2,h3,p,label,li,td,th,img')]
    .filter((el) => vis(el) && getComputedStyle(el).position !== 'fixed').slice(0, 600).map((el) => ({ el, r: el.getBoundingClientRect() }));
  const overlaps = [];
  for (let i = 0; i < boxes.length && overlaps.length < 15; i++) for (let j = i + 1; j < boxes.length && overlaps.length < 15; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
    const x = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left), y = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    if (x > 4 && y > 4 && x * y > 0.2 * Math.min(a.r.width * a.r.height, b.r.width * b.r.height)) {
      const top = document.elementFromPoint(Math.max(a.r.left, b.r.left) + x / 2, Math.max(a.r.top, b.r.top) + y / 2);
      if (top && (a.el.contains(top) || b.el.contains(top) || top.contains(a.el) || top.contains(b.el))) overlaps.push({ a: label(a.el), at: text(a.el), b: label(b.el), bt: text(b.el) });
    }
  }
  if (overlaps.length) defects.push({ kind: 'overlap', count: overlaps.length, items: overlaps.slice(0, 10) });
  // Contrast (WCAG): text colour vs. the first opaque background up the tree. Skips text over images/gradients.
  const rgb = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1 }; };
  const lum = ({ r, g, b }) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bgOf = (el) => { for (let n = el; n; n = n.parentElement) { const s = getComputedStyle(n); if (s.backgroundImage && s.backgroundImage !== 'none') return null; const c = rgb(s.backgroundColor); if (c && c.a > 0.9) return c; } return { r: 255, g: 255, b: 255, a: 1 }; };
  const lowContrast = leaves.map((el) => { const s = getComputedStyle(el), fg = rgb(s.color), bg = bgOf(el); if (!fg || !bg || fg.a < 0.5) return null; const L1 = lum(fg), L2 = lum(bg); const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05); const big = parseFloat(s.fontSize) >= 24 || (parseFloat(s.fontSize) >= 18.6 && Number(s.fontWeight) >= 700); return ratio < (big ? 3 : 4.5) ? { el: label(el), text: text(el), ratio: Math.round(ratio * 100) / 100 } : null; }).filter(Boolean).slice(0, 20);
  if (lowContrast.length) defects.push({ kind: 'low_contrast', count: lowContrast.length, items: lowContrast.slice(0, 10) });
  const tiny = [...document.querySelectorAll('button,a,input:not([type=hidden]),select,[role=button],[role=tab]')].filter(vis).filter((el) => { const r = el.getBoundingClientRect(); return (r.width < 44 || r.height < 44) && !(el.tagName === 'A' && getComputedStyle(el).display === 'inline'); }).slice(0, 20).map((el) => { const r = el.getBoundingClientRect(); return { el: label(el), text: text(el), size: Math.round(r.width) + 'x' + Math.round(r.height) }; });
  if (tiny.length) defects.push({ kind: 'small_target', count: tiny.length, items: tiny.slice(0, 10) });
  // Owner rule: no sentence-final period on screen copy (titles, buttons, labels, short notices).
  const periods = [...document.body.querySelectorAll('h1,h2,h3,h4,button,label,a,th,[role=button],.notice,.toast,p')].filter(vis).map((el) => ({ el, t: text(el) })).filter(({ t }) => t.length > 1 && t.length <= 80 && /[가-힣][.。]$/.test(t)).slice(0, 20).map(({ el, t }) => ({ el: label(el), text: t }));
  if (periods.length) defects.push({ kind: 'trailing_period', count: periods.length, items: periods.slice(0, 10) });
  const visibleText = (document.body.innerText || '').trim().length;
  if (visibleText < 20 && !document.querySelector('canvas,img,svg,video')) defects.push({ kind: 'blank_page', count: 1, items: [{ chars: visibleText }] });
  const imgs = [...document.images].filter((i) => i.complete && i.naturalWidth === 0).slice(0, 10).map((i) => ({ src: i.currentSrc.slice(0, 120) }));
  if (imgs.length) defects.push({ kind: 'broken_image', count: imgs.length, items: imgs });
  const unlabeled = [...document.querySelectorAll('button,a,input,select,textarea')].filter((el) => vis(el) && !text(el) && !el.getAttribute('title') && !(el.labels && el.labels.length) && !el.querySelector('img[alt],svg[aria-label]')).slice(0, 10).map((el) => ({ el: label(el) }));
  if (unlabeled.length) defects.push({ kind: 'unlabeled_control', count: unlabeled.length, items: unlabeled });
  return { title: document.title, chars: visibleText, height: doc.scrollHeight, width: W, viewportHeight: H, defects };
}

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.wait = new Map(); this.events = []; ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && this.wait.has(d.id)) { const [ok, ko] = this.wait.get(d.id); this.wait.delete(d.id); d.error ? ko(new Error(d.error.message)) : ok(d.result); } else if (d.method) this.events.push(d); }; }
  send(method, params = {}, sessionId) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params, sessionId })); return new Promise((ok, ko) => { this.wait.set(id, [ok, ko]); setTimeout(() => { if (this.wait.delete(id)) ko(new Error(method + ' timed out')); }, 30000); }); }
}

const profile = mkdtempSync(join(tmpdir(), 'director-see-'));
const proc = spawn(chrome, ['--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--hide-scrollbars', '--mute-audio', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const cleanup = () => { try { proc.kill('SIGKILL'); } catch {} try { rmSync(profile, { recursive: true, force: true }); } catch {} };
process.on('exit', cleanup);
const wsUrl = await new Promise((ok, ko) => { let buf = ''; const t = setTimeout(() => ko(new Error('Chrome did not start')), 20000); proc.stderr.on('data', (c) => { buf += c; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) { clearTimeout(t); ok(m[1]); } }); proc.on('exit', () => ko(new Error('Chrome exited'))); }).catch((e) => fail(e.message));
const ws = new WebSocket(wsUrl);
await new Promise((ok, ko) => { ws.onopen = ok; ws.onerror = () => ko(new Error('CDP connect failed')); }).catch((e) => fail(e.message));
const cdp = new CDP(ws);

const pages = [];
for (const path of paths) for (const [w, h] of sizes) {
  const url = new URL(path, base).href;
  const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  const s = (m, p) => cdp.send(m, p, sessionId);
  await s('Runtime.enable'); await s('Log.enable'); await s('Page.enable');
  await s('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w < 600 });
  const mark = cdp.events.length;
  let navError = null;
  try { const nav = await s('Page.navigate', { url }); navError = nav.errorText || null; } catch (e) { navError = e.message; }
  await new Promise((r) => setTimeout(r, waitMs));
  const ev = cdp.events.slice(mark).filter((e) => e.sessionId === sessionId);
  const consoleErrors = ev.filter((e) => (e.method === 'Runtime.exceptionThrown') || (e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error') || (e.method === 'Log.entryAdded' && e.params.entry.level === 'error'))
    .slice(0, 20).map((e) => (e.params.exceptionDetails ? (e.params.exceptionDetails.exception?.description || e.params.exceptionDetails.text) : e.params.entry ? e.params.entry.text : e.params.args.map((a) => a.value ?? a.description).join(' ')).slice(0, 300));
  let result = { defects: [] };
  try { const r = await s('Runtime.evaluate', { expression: '(' + audit.toString() + ')(' + minFont + ')', returnByValue: true }); result = r.result.value || result; } catch (e) { result.defects.push({ kind: 'audit_failed', count: 1, items: [{ error: e.message }] }); }
  if (navError) result.defects.push({ kind: 'navigation_error', count: 1, items: [{ error: navError }] });
  if (consoleErrors.length) result.defects.push({ kind: 'console_error', count: consoleErrors.length, items: consoleErrors.map((t) => ({ text: t })) });
  const name = (path.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '') || 'home') + '_' + w + 'x' + h + '.png';
  try { const shot = await s('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }); writeFileSync(join(args.out, name), Buffer.from(shot.data, 'base64')); } catch (e) { result.defects.push({ kind: 'screenshot_failed', count: 1, items: [{ error: e.message }] }); }
  pages.push({ path, url, size: w + 'x' + h, screenshot: join(args.out, name), ...result });
  await cdp.send('Target.closeTarget', { targetId });
}
const total = pages.reduce((n, p) => n + p.defects.reduce((m, d) => m + d.count, 0), 0);
const report = { ok: true, checked_at: new Date().toISOString(), min_font: minFont, pages, defect_total: total, clean: total === 0 };
writeFileSync(join(args.out, 'see_report.json'), JSON.stringify(report, null, 2));
process.stdout.write(JSON.stringify(report) + '\n');
ws.close(); cleanup(); process.exit(0);
