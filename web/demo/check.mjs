// 데모 페이지를 headless Chrome 으로 열어 예시를 페이지와 같은 경로로 돌리고, examples.js 의 raw(미리 돌린 출력)와 비교한다.
//   web/demo/build.sh --local && python3 web/serve.py 8780 --root out/site &
//   node web/demo/check.mjs                 # 다른 예시가 있으면 1 로 끝난다
//   node web/demo/check.mjs cands.json out.json   # 후보({title, body, ...} 배열)를 돌려 raw·spec 을 붙여 저장
import fs from 'node:fs';
import { chromium } from 'playwright-core';
import { EXAMPLES } from './examples.js';

const [, , inPath, outPath] = process.argv;
const items = inPath ? JSON.parse(fs.readFileSync(inPath, 'utf8')) : EXAMPLES;
const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: true });
const page = await browser.newPage();
page.on('console', (m) => { if (m.type() === 'error') console.error('[page]', m.text().slice(0, 300)); });
await page.goto(process.env.URL || 'http://127.0.0.1:8780/');
// GitHub Pages 처럼 헤더가 없으면 서비스 워커가 한 번 새로 고친다. 격리될 때까지 기다린다
await page.waitForFunction(() => window.demo && (crossOriginIsolated || !isSecureContext || !navigator.serviceWorker), null, { timeout: 60_000 });
const info = await page.evaluate(() => ({ isolated: crossOriginIsolated, secure: isSecureContext }));
console.log(JSON.stringify(info));

const out = [];
let diff = 0;
for (const [i, ex] of items.entries()) {
  const t = Date.now();
  const { raw, spec } = await page.evaluate(([a, b]) => window.demo.normalize(a, b), [ex.title, ex.body]);
  const same = raw.trim() === (ex.raw || '').trim();
  if (!inPath && !same) diff++;
  out.push({ ...ex, raw: raw.trim(), spec });
  console.log(`${String(i + 1).padStart(2)} ${inPath ? '' : same ? 'ok  ' : 'DIFF'} ${Date.now() - t}ms  ${ex.tag}\n   ${raw.trim()}`
    + `\n   → ${spec.post_type}/${spec.category} [${spec.models.join(', ')}] ${spec.storages.join(',')} ${spec.color_official || spec.colors.join(',')} ${spec.condition}${spec.grounded_fields_replaced ? ' (근거 검사)' : ''}`);
}
if (outPath) fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
await browser.close();
process.exit(diff ? 1 : 0);
