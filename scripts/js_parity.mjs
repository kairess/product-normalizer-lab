// js_parity.py 가 만든 Python 결과와 JS 정규화기 결과를 비교한다.   node scripts/js_parity.mjs <cases.jsonl>
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { fileURLToPath } from 'node:url';

const LAB = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const N = await import(path.join(LAB, 'web/normalizer/index.js'));

const dataDir = path.join(LAB, 'normalizer/data');
const catalog = new N.Catalog(
  fs.readdirSync(dataDir).filter((f) => /^catalog_.*\.json$/.test(f)).sort()
    .map((f) => JSON.parse(fs.readFileSync(path.join(dataDir, f), 'utf8'))),
);

const RUN = {
  extract: ([t, b]) => N.extract(t, b),
  condition: ([t, b]) => N.detectCondition(t, b),
  spec_rules: ([t, b]) => N.buildSpec(catalog, t, b, null),
  spec_llm: ([t, b, llm]) => N.buildSpec(catalog, t, b, llm),
  spec_model: ([t, b, raw]) => N.specFromOutput(catalog, t, b, raw),
  text_of: ([t, b]) => N.textOf(t, b),
  parse_target: ([raw]) => N.parseTarget(raw),
  snap: ([n]) => catalog.snap(n),
  lookup_code: ([n]) => catalog.lookupCode(n),
  parse: ([n]) => catalog.parse(n),
  norm_model: ([n]) => N.normModel(n),
  norm_color: ([c]) => N.normColor(c),
  norm_storage: ([s]) => N.normStorage(s),
  grounded: ([m, t]) => N.grounded(m, t),
  color_grounded: ([c, t]) => N.colorGrounded(c, t),
  storage_grounded: ([s, t]) => N.storageGrounded(s, t),
  official_color: ([m, c]) => catalog.officialColor(m, c),
};

function equal(a, b) {
  if (a === b) return true;
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  return ka.length === kb.length && ka.every((k) => k in b && equal(a[k], b[k]));
}

const stats = {};
const examples = {};
const rl = readline.createInterface({ input: fs.createReadStream(process.argv[2]), crlfDelay: Infinity });
const t0 = performance.now();
for await (const line of rl) {
  if (!line) continue;
  const c = JSON.parse(line);
  const s = (stats[c.kind] ??= { n: 0, diff: 0 });
  s.n++;
  let got;
  try {
    got = RUN[c.kind](c.in);
  } catch (e) {
    got = `JS 오류: ${e.message}`;
  }
  if (!equal(got, c.out)) {
    s.diff++;
    (examples[c.kind] ??= []).length < 3 && examples[c.kind].push({ in: c.in, py: c.out, js: got });
  }
}
let bad = 0;
for (const [k, s] of Object.entries(stats)) {
  console.log(`${k.padEnd(18)} ${String(s.n).padStart(6)}건  다름 ${s.diff}`);
  bad += s.diff;
}
for (const [k, ex] of Object.entries(examples)) {
  for (const e of ex) console.log(`\n[${k}]`, JSON.stringify(e).slice(0, 1500));
}
console.log(`\n${((performance.now() - t0) / 1000).toFixed(1)}초, 다른 결과 ${bad}건`);
process.exit(bad ? 1 : 0);
