// normalizer/pipeline.py 의 JS 판: 매물 1건 → 검색·시세용 규격(spec).
// 규칙 추출(항상) + 모델 추출(있으면) + 카탈로그 검증을 결합한다. 필드 선택 기준은 Python 쪽 docstring 참고.

import { normModel, normStorage } from './common.js';
import { head, sortedSet } from './py.js';
import { detectCondition, extract } from './rules.js';

export const NORMALIZER_VERSION = '2026-10-08.3';

const same = (a, b, norm) => {
  const x = sortedSet((a || []).map(norm));
  const y = sortedSet((b || []).map(norm));
  return x.length === y.length && x.every((v, i) => v === y[i]);
};

/**
 * @param {import('./catalog.js').Catalog} cat
 * @param {string} title
 * @param {string} body
 * @param {object|null} llmOut {post_type, category, models, storage, color} — 없으면 규칙만
 * @param {{ruleFallback?: boolean}} opts ruleFallback=false 면 카탈로그에 없는 모델명도 규칙 값으로 바꾸지 않는다 (Python 판 docstring 참고)
 */
export function buildSpec(cat, title, body, llmOut, { ruleFallback = true } = {}) {
  body = body || '';
  const rule = extract(title, body);
  const src = llmOut && llmOut.post_type ? llmOut : null;
  const p = {};
  for (const k of ['category', 'models', 'storage', 'color']) p[k] = src && k in src ? src[k] : rule[k];
  p.post_type = rule.post_type;

  const reasons = [];
  let models = [];
  for (const m of p.models || []) {
    const s = cat.snap(m);
    if (s === null && p.category === 'phone') {
      const alt = ruleFallback ? rule.models.map((x) => cat.snap(x)) : [];
      if (alt.length && alt.every((a) => a)) {
        models = alt.filter((a) => a);
        break;
      }
      const code = ruleFallback ? cat.lookupCode(`${title} ${head(body, 200)}`) : null;
      if (code) {
        models = [code];
        break;
      }
      reasons.push(`카탈로그에 없는 모델명: ${m}`);
    }
    models.push(s || m);
  }
  models = [...new Set(models)];

  if (src && p.category === 'phone' && (p.post_type === 'sell' || p.post_type === 'buy')) {
    const canon = (ms) => (ms || []).map((m) => cat.snap(m) || m); // 표기 차이를 불일치로 보지 않게
    if (!same(canon(rule.models), canon(src.models || []), normModel)) reasons.push('규칙·LLM 모델 불일치');
    else if (!same(rule.storage, src.storage || [], normStorage)) reasons.push('규칙·LLM 용량 불일치');
  }

  const storage = (p.storage || []).map(normStorage);
  const colors = [...(p.color || [])];
  const model = models.length ? models[0] : null;
  const parsed = model ? cat.parse(model) : { brand: null, line: null, gen: null, variant: null };
  return {
    post_type: p.post_type,
    category: p.category,
    models,
    model,
    brand: parsed.brand,
    line: parsed.line,
    gen: parsed.gen,
    variant: parsed.variant,
    storages: storage,
    storage: storage.length === 1 ? storage[0] : null,
    colors,
    color: colors.length === 1 ? colors[0] : null,
    color_official: model && colors.length === 1 ? cat.officialColor(model, colors[0]) : null,
    condition: detectCondition(title, body),
    needs_review: reasons.length > 0,
    review_reason: reasons.join('; ') || null,
    source: src ? 'llm' : 'rules',
    tokens: cat.searchTokens(models, storage, colors),
    normalizer_version: NORMALIZER_VERSION,
  };
}
