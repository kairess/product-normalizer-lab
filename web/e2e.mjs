// headless Chrome 으로 web/e2e.html 을 열어 평가셋을 돌리고 결과(spec)를 JSON 으로 저장한다.
//   python3 web/serve.py &                         # 저장소 루트를 COOP/COEP 헤더와 함께 :8765 로 띄움
//   node web/e2e.mjs "n=1000" res_web.json         # → scripts/web_preds.py res_web.json q08_final_lora_web
// CHROME 환경변수로 브라우저 경로를 바꾼다 (기본 /usr/bin/google-chrome).
import fs from 'node:fs';
import { chromium } from 'playwright-core';

const [, , query = '', out = 'res_web.json'] = process.argv;
const browser = await chromium.launch({
  executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: true, args: ['--enable-unsafe-webgpu'],
});
const page = await browser.newPage();
page.on('console', (m) => { if (m.type() === 'error') console.error('[page]', m.text().slice(0, 300)); });
await page.goto(`http://127.0.0.1:${process.env.PORT || 8765}/web/e2e.html?${query}`);
await page.waitForFunction(() => window.status !== 'loading', null, { timeout: 7_200_000, polling: 5000 });
const st = await page.evaluate(() => window.status);
if (st !== 'done') { console.log(st); process.exit(1); }
const res = await page.evaluate(() => window.result);
fs.writeFileSync(out, JSON.stringify(res));
const ms = res.results.filter((r) => r.ms).map((r) => r.ms).sort((a, b) => a - b);
console.log(`done n=${res.results.length} err=${res.results.filter((r) => r.err).length}`
  + ` median ${ms[ms.length >> 1]}ms p90 ${ms[Math.floor(ms.length * 0.9)]}ms → ${out}`);
await browser.close();
