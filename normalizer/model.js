// 브라우저에서 학습한 소형 모델(Qwen3.5-0.8B 미세조정, GGUF)로 매물을 정규화한다.
//
//   import { Wllama } from '<wllama>/esm/index.js';
//   import { Catalog, Normalizer, LOAD_PARAMS } from './index.js';
//   const wl = new Wllama({ default: '<wllama>/esm/wasm/wllama.wasm' });
//   // JSPI·memory64 가 없는 브라우저(Safari 등)용 빌드. 지정하지 않으면 CDN 의 공식 빌드를 받는데, 그건 cache_ram_mib 를 몰라 쓸 수 없다
//   wl.setCompat({ wasm: '<wllama>/compat/wasm/wllama.wasm', worker: '<wllama>/compat/wasm/wllama.js' });
//   await wl.loadModelFromUrl(modelUrl, { ...LOAD_PARAMS, n_gpu_layers: hasWebGPU ? 999 : 0 });
//   const nz = new Normalizer(wl, new Catalog([apple, samsung]));
//   const spec = await nz.normalize(title, body);
//
// 학습·평가(scripts/distill_data.py, train_gen.py, ground.py, eval_gguf.py)와 같은 순서로 처리한다.
// 입력 자르기 → 프롬프트 → 생성(탐욕) → 한 줄 파싱 → 근거 검사 → 카탈로그 정식명 → spec.

import { buildSpec } from './pipeline.js';
import { ground } from './ground.js';
import { head, strip } from './py.js';

export const BODY_MAX = 600; // distill_data.BODY_MAX
export const MAX_IN = 448; // train_gen.MAX_IN (입력 토큰 수)
export const MAX_OUT = 64; // train_gen.MAX_OUT
export const PROMPT = (text) => `매물 정보를 정규화하세요.\n${text}\n정답: `;
// PROMPT(text) 의 토큰 수 - text 의 토큰 수 (Qwen3.5 토크나이저로 잰 값: 13, 드물게 12)
const PROMPT_OVERHEAD = 13;

/**
 * wllama 모델 로드 옵션.
 * - cache_ram_mib: 0 — llama.cpp 서버는 기본으로 지난 요청의 상태를 프롬프트 캐시(최대 8GB)에 쌓는다. 이 모델(하이브리드
 *   구조)은 요청마다 수십 MB 라 브라우저 메모리(4GB)를 70여 건 만에 다 쓰고 멈춘다. 글마다 프롬프트가 달라 재사용할 것도 없다.
 * - n_ctx_checkpoints: 0 — 같은 이유로 슬롯마다 쌓이는 상태 체크포인트(개당 약 19MB, 최대 32개)도 끈다.
 * cache_ram_mib 는 패치한 wllama 가 필요하다 (web/wllama).
 */
export const LOAD_PARAMS = { n_ctx: 1024, n_parallel: 1, cache_ram_mib: 0, n_ctx_checkpoints: 0, cache_idle_slots: false };

/** distill_data.text_of: 제목 + 줄바꿈 + 본문 앞 600자 */
export function textOf(title, body) {
  const b = head(strip(body || ''), BODY_MAX);
  // HF 토크나이저(학습 때)는 NFC 로 정규화한다. llama.cpp 는 하지 않으므로 여기서 맞춘다.
  return (b ? `${strip(title)}\n${b}` : strip(title)).normalize('NFC');
}

/** distill_data.parse_target: "유형|분류|모델;모델|용량;용량|색상;색상|상태" 한 줄 → 필드 */
export function parseTarget(s) {
  const parts = [...strip(s).split('\n')[0].split('|'), '', '', '', '', '', ''].slice(0, 6);
  const sp = (x) => x.split(';').map(strip).filter((v) => v);
  return {
    post_type: strip(parts[0]) || 'other',
    category: strip(parts[1]) || 'other',
    models: sp(parts[2]),
    storage: sp(parts[3]),
    color: sp(parts[4]),
    condition: strip(parts[5]) || 'used',
  };
}

/**
 * 모델 출력 한 줄 → spec. 평가(eval1k)에서 잰 경로와 같다:
 * 파싱 → 근거 검사(근거 없는 모델명·용량·색상은 규칙 값으로) → 카탈로그 정식명(buildSpec, 모르는 이름은 그대로).
 * 유형(post_type)과 상태(condition)는 모델 값을 쓴다 (평가에서 규칙보다 정확: 유형 99.0 vs 97.7%, 상태 96.7 vs 83.4%).
 */
export function specFromOutput(cat, title, body, raw) {
  body = body || '';
  const pred = parseTarget(raw);
  const [g, grounded] = ground(pred, title, body, () => buildSpec(cat, title, body, null));
  return {
    ...buildSpec(cat, title, body, g, { ruleFallback: false }),
    post_type: g.post_type,
    condition: g.condition,
    source: 'model',
    raw: strip(raw),
    grounded_fields_replaced: grounded,
  };
}

export class Normalizer {
  /**
   * @param {object} wllama 모델을 LOAD_PARAMS 로 불러 둔 Wllama 인스턴스
   * @param {import('./catalog.js').Catalog} catalog
   */
  constructor(wllama, catalog) {
    this.wllama = wllama;
    this.catalog = catalog;
  }

  /** 모델 출력 한 줄 (자르기 포함) */
  async generate(title, body) {
    let text = textOf(title, body);
    for (let i = 0; ; i++) {
      const r = await this.wllama.createCompletion({
        prompt: PROMPT(text), max_tokens: MAX_OUT, temperature: 0, stop: ['\n'], cache_prompt: false,
      });
      const nText = r.usage.prompt_tokens - PROMPT_OVERHEAD;
      // 학습 때는 입력을 토큰 448개로 잘랐다. 브라우저에는 토크나이저가 없어 길이를 보고 비율대로 잘라 다시 돌린다 (0.1% 정도)
      if (nText <= MAX_IN || i >= 3) return r.choices[0].text;
      text = head(text, Math.floor(([...text].length * MAX_IN) / nText) - 1);
    }
  }

  async normalize(title, body) {
    const raw = await this.generate(title, body || '');
    return specFromOutput(this.catalog, title, body || '', raw);
  }
}
