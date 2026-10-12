// 매물 정규화기 (브라우저용). Python 판(normalizer/, scripts/ground.py)과 결과가 같다.
// 같은지는 scripts/js_parity.py 로 확인한다.

export { Catalog, parseName } from './catalog.js';
export { COLOR_ALIASES, normColor, normModel, normStorage } from './common.js';
export { colorGrounded, ground, grounded, storageGrounded } from './ground.js';
export { LOAD_PARAMS, MAX_IN, MAX_OUT, Normalizer, PROMPT, parseTarget, specFromOutput, textOf } from './model.js';
export { NORMALIZER_VERSION, buildSpec } from './pipeline.js';
export { classify, detectCondition, extract, findColors, findModels, findStorage } from './rules.js';
