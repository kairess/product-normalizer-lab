// 데모 페이지: 예시는 미리 돌려 둔 모델 출력으로 바로 보여 주고, 모델을 불러오면 이 브라우저에서 직접 돌린다.
// 경로는 web/demo/build.sh 가 만든 사이트 기준이다 (wllama/, normalizer/, data/).

import { Wllama } from './wllama/esm/index.js';
import { Catalog, LOAD_PARAMS, Normalizer, specFromOutput } from './normalizer/index.js';
import { EXAMPLES } from './examples.js';
import { MODEL_MB, MODEL_URL } from './config.js';

const $ = (id) => document.getElementById(id);
const abs = (p) => new URL(p, location.href).href;
const MODEL = abs(new URLSearchParams(location.search).get('model') || MODEL_URL);
// OPFS(모델 저장)·멀티스레드는 HTTPS 나 localhost 에서만 된다. 그 밖(사내망 HTTP 등)에서는 메모리로 받아 단일 스레드로 돈다
const SECURE = window.isSecureContext;

const LABEL = {
  post_type: { sell: '판매', buy: '구매', shop_ad: '업체 광고', other: '교환·기타' },
  category: { phone: '휴대폰', tablet: '태블릿', watch: '워치', earbuds: '이어폰', laptop: '노트북', accessory: '액세서리', parts: '부품', other: '전자기기 아님' },
  condition: { new: '미개봉', used: '중고', broken: '하자 있음' },
};

const wl = new Wllama(
  { default: abs('wllama/esm/wasm/wllama.wasm') },
  // cacheManager 를 주지 않으면 생성자가 OPFS 를 찾다가 예외를 던진다
  { suppressNativeLog: true, logger: { ...console, debug() {} }, ...(SECURE ? {} : { cacheManager: {} }) },
);
// Safari 처럼 JSPI·memory64 가 없는 브라우저용. 지정하지 않으면 패치 없는 CDN 빌드를 받는다
wl.setCompat({ wasm: abs('wllama/compat/wasm/wllama.wasm'), worker: abs('wllama/compat/wasm/wllama.js') });

const EN = new Map(); // 정식명 → 영문명
const catalogReady = Promise.all(
  ['catalog_apple.json', 'catalog_samsung.json'].map((f) => fetch(`data/${f}`).then((r) => r.json())),
).then((datas) => {
  for (const d of datas) for (const m of d.models) EN.set(m.name, m.en);
  return new Catalog(datas);
});

let catalog = null;
let nz = null;
let loadPromise = null;
let active = -1;

// ── 모델 불러오기 ──────────────────────────────────────────

function setLoader(state, title, sub) {
  $('loader').dataset.state = state;
  if (title) $('loader-title').textContent = title;
  if (sub !== undefined) $('loader-sub').textContent = sub;
  syncRun();
}

const mb = (n) => Math.round(n / 1e6);

function onProgress({ loaded, total }) {
  const p = total ? loaded / total : 0;
  $('progress-fill').style.width = `${(p * 100).toFixed(1)}%`;
  if (total && loaded >= total) setLoader('loading', '메모리에 올리는 중', '몇 초 걸립니다.');
  else setLoader('loading', `모델 받는 중 · ${Math.round(p * 100)}%`, `${mb(loaded)} / ${mb(total) || MODEL_MB}MB`);
}

async function fetchBuffer(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`모델 파일을 받지 못했습니다 (HTTP ${r.status})`);
  const total = +r.headers.get('content-length') || 0;
  const reader = r.body.getReader();
  let buf = new Uint8Array(total || 64 << 20);
  let loaded = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (loaded + value.byteLength > buf.length) {
      const bigger = new Uint8Array(Math.max(buf.length * 2, loaded + value.byteLength));
      bigger.set(buf.subarray(0, loaded));
      buf = bigger;
    }
    buf.set(value, loaded);
    loaded += value.byteLength;
    onProgress({ loaded, total });
  }
  return buf.subarray(0, loaded);
}

// 메모리 버퍼를 Blob 처럼 보이게 한다. 529MB 짜리 진짜 Blob 은 디스크를 못 쓰는 창(시크릿 등)에서 Chrome 이 읽지 못한다
// (NotReadableError). wllama 는 모델 파일에서 size, slice().arrayBuffer(), stream() 만 쓴다
function bufferBlob(u8, start = 0, end = u8.length) {
  return {
    size: end - start,
    slice: (a = 0, b = end - start) => bufferBlob(u8, start + a, start + Math.min(b, end - start)),
    arrayBuffer: async () => u8.slice(start, end).buffer,
    stream() {
      let o = start;
      return new ReadableStream({
        pull(c) {
          if (o >= end) return c.close();
          const n = Math.min(8 << 20, end - o);
          c.enqueue(u8.slice(o, o + n)); // 복사본: wllama 가 버퍼를 워커로 넘기면서 떼어 낸다
          o += n;
        },
      });
    },
  };
}

async function load() {
  setLoader('loading', '모델 받는 중 · 0%', `0 / ${MODEL_MB}MB`);
  catalog = await catalogReady;
  const params = { ...LOAD_PARAMS, n_gpu_layers: 0 };
  if (SECURE) await wl.loadModelFromUrl(MODEL, { ...params, progressCallback: onProgress });
  else await wl.loadModel([bufferBlob(await fetchBuffer(MODEL))], params);
  nz = new Normalizer(wl, catalog);
  const threads = wl.getNumThreads();
  setLoader('ready', '준비됨', wl.isMultithread()
    ? `이 브라우저의 CPU ${threads}스레드로 돕니다. 예시를 누르거나 글을 직접 넣어 보세요.`
    : '단일 스레드로 돕니다. HTTPS 주소에서는 더 빠릅니다.');
}

function ensureModel() {
  loadPromise ??= load().catch((e) => {
    loadPromise = null;
    setLoader('error', '모델을 불러오지 못했습니다', String(e?.message || e));
    throw e;
  });
  return loadPromise;
}

async function isCached() {
  if (!SECURE) return false;
  try {
    return (await wl.modelManager.getModels()).some((m) => m.url === MODEL);
  } catch {
    return false;
  }
}

// ── 실행 ─────────────────────────────────────────────────

let running = false;
let queued = false;

const input = () => ({ title: $('title').value.trim(), body: $('body').value.trim() });

function syncRun() {
  const st = $('loader').dataset.state;
  const btn = $('run');
  btn.disabled = running;
  btn.textContent = running ? '읽는 중…' : st === 'ready' ? '정규화' : st === 'loading' ? '불러온 뒤 실행' : `모델 받고 실행 · ${MODEL_MB}MB`;
}

async function run() {
  if (running) {
    queued = true;
    return;
  }
  running = true;
  syncRun();
  try {
    do {
      queued = false;
      const { title, body } = input();
      if (!title && !body) {
        renderEmpty('제목이나 본문을 넣어 주세요.');
        continue;
      }
      renderPending();
      await ensureModel();
      const t0 = performance.now();
      const spec = await nz.normalize(title, body);
      if (!queued) render(spec, { ms: performance.now() - t0 });
    } while (queued);
  } catch (e) {
    renderEmpty(`실행하지 못했습니다: ${e?.message || e}`);
  } finally {
    running = false;
    syncRun();
  }
}

// ── 예시 ─────────────────────────────────────────────────

function renderExamples() {
  $('ex-list').replaceChildren(...EXAMPLES.map((ex, i) => {
    const li = document.createElement('li');
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'ex';
    b.setAttribute('aria-pressed', 'false');
    b.innerHTML = '<span class="ex-tag"></span><span class="ex-title"><span class="ex-num"></span></span>';
    b.querySelector('.ex-tag').textContent = ex.tag;
    b.querySelector('.ex-num').textContent = String(i + 1).padStart(2, '0');
    b.querySelector('.ex-title').append(ex.title);
    b.addEventListener('click', () => pick(i));
    li.append(b);
    return li;
  }));
}

function setActive(i) {
  active = i;
  document.querySelectorAll('.ex').forEach((b, j) => b.setAttribute('aria-pressed', String(j === i)));
  $('trap').hidden = i < 0;
  if (i >= 0) $('trap-text').textContent = EXAMPLES[i].trap;
}

async function pick(i, { reveal = true } = {}) {
  const ex = EXAMPLES[i];
  $('title').value = ex.title;
  $('body').value = ex.body;
  setActive(i);
  if ($('loader').dataset.state === 'ready') return run();
  // 모델이 아직 없으면 미리 돌려 둔 출력에 같은 후처리(근거 검사·카탈로그)를 붙여 보여 준다
  catalog ??= await catalogReady;
  if (active === i && !running) render(specFromOutput(catalog, ex.title, ex.body, ex.raw), { cached: true, reveal });
}

// ── 결과 그리기 ───────────────────────────────────────────

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

function renderEmpty(msg) {
  $('result').replaceChildren(el('div', 'res-empty', msg));
}

function renderPending() {
  const d = el('div', 'res-empty');
  d.append(el('span', 'spinner'), $('loader').dataset.state === 'ready' ? '읽는 중…' : '모델을 불러오는 중입니다. 끝나면 바로 실행합니다.');
  $('result').replaceChildren(d);
}

function headline(spec) {
  if (spec.models.length) return null;
  if (spec.post_type === 'shop_ad') return '여러 기기를 파는 업체 광고';
  if (spec.category === 'other') return '휴대폰 매물이 아닙니다';
  return '모델명 없음';
}

function render(spec, { ms, cached, reveal = true } = {}) {
  const box = $('result');
  const head = el('div', 'res-head');
  const chips = el('div', 'chips');
  chips.append(el('span', 'chip post', LABEL.post_type[spec.post_type] || spec.post_type));
  chips.append(el('span', 'chip', LABEL.category[spec.category] || spec.category));
  head.append(chips, cached
    ? el('span', 'badge', '미리 실행한 결과')
    : el('span', 'badge live', `이 브라우저에서 ${(ms / 1000).toFixed(1)}초`));

  const models = el('div', 'models');
  const none = headline(spec);
  if (none) models.append(el('div', 'model none', none));
  else {
    if (spec.category === 'accessory' || spec.category === 'parts') models.append(el('div', 'model-for', '대상 기기'));
    models.append(el('div', 'model', spec.models.join(' + ')));
    const en = spec.models.map((m) => EN.get(m)).filter(Boolean);
    if (en.length) models.append(el('div', 'model-en', en.join(' + ')));
  }

  const fields = el('dl', 'fields');
  const color = spec.color_official || spec.colors.join(', ');
  const showCond = spec.post_type === 'sell' && spec.category !== 'other';
  for (const [k, v] of [['용량', spec.storages.join(', ')], ['색상', color], ['상태', showCond ? spec.condition : '']]) {
    const d = el('div');
    d.append(el('dt', '', k));
    if (!v) d.append(el('dd', 'dim', '—'));
    else if (k === '상태') {
      const dd = el('dd');
      dd.append(el('span', `cond ${v}`, LABEL.condition[v] || v));
      d.append(dd);
    } else d.append(el('dd', '', v));
    fields.append(d);
  }

  const raw = el('details', 'raw');
  raw.append(el('summary', '', '모델이 낸 한 줄'), el('code', '', spec.raw));
  if (spec.grounded_fields_replaced) raw.append(el('p', '', '원문에 근거가 없는 값은 규칙으로 찾은 값으로 바꿨습니다.'));

  // 휴대폰 매물이 아니거나 광고처럼 채울 칸이 하나도 없으면 빈 표를 그리지 않는다
  box.replaceChildren(head, models, ...(fields.querySelector('dd:not(.dim)') ? [fields] : []), raw);
  // 좁은 화면에서는 결과가 입력란 아래로 밀려 있어 보이게 내려 준다
  const r = box.getBoundingClientRect();
  if (reveal && r.top > innerHeight - 120) box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── 시작 ─────────────────────────────────────────────────

document.querySelectorAll('.mb').forEach((s) => { s.textContent = MODEL_MB; });
if (!SECURE) $('loader-sub').textContent = `${MODEL_MB}MB를 받습니다. 이 주소(HTTP)에서는 저장되지 않아 새로 고치면 다시 받습니다.`;
$('load').addEventListener('click', () => ensureModel().catch(() => {}));
$('form').addEventListener('submit', (e) => {
  e.preventDefault();
  run();
});
$('clear').addEventListener('click', () => {
  $('title').value = '';
  $('body').value = '';
  setActive(-1);
  renderEmpty('직접 써 보세요. 중고 거래 앱에 올라온 글을 그대로 붙여 넣어도 됩니다.');
  $('title').focus();
});
for (const id of ['title', 'body']) {
  $(id).addEventListener('input', () => {
    const ex = EXAMPLES[active];
    if (ex && ($('title').value !== ex.title || $('body').value !== ex.body)) setActive(-1);
  });
}

renderExamples();
syncRun();
pick(0, { reveal: false });
if (await isCached()) ensureModel().catch(() => {});

// 확인용 (web/demo/check.mjs): 페이지와 같은 경로로 돌린 모델 출력과 spec
window.demo = {
  async normalize(title, body) {
    await ensureModel();
    const raw = await nz.generate(title, body);
    return { raw, spec: specFromOutput(catalog, title, body, raw) };
  },
};
