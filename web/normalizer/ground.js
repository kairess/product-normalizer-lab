// scripts/ground.py 의 JS 판: 생성 결과의 근거 확인.
// 소형 생성 모델은 처음 보는 세대(S26)를 학습한 세대(S25)로 바꿔 쓰는 경향이 있다. 그래서 모델명·용량·색상 값이
// 원문에 근거가 없으면 그 필드는 규칙·카탈로그 결과로 바꾼다. 규칙은 원문에서 뽑으므로 늘 근거가 있다.

import { rx, splitWs } from './py.js';

const GENERIC = new Set(['아이폰', '갤럭시', 'z', 's', 'a', '프로', '맥스', '플러스', '미니', '울트라', '엣지', 'fe', '노트', '폴드', '플립',
  '세대', '퀀텀', '와이드', '점프', '버디']);
const ALIAS = new Map([['에어', ['에어', 'air']], ['듀오', ['듀오', 'duo', '폴드']], ['se', ['se', '에스이']]]);
const NUMS = rx(String.raw`\d+`, 'g');

/** 모델명의 세대 숫자(없으면 핵심 단어)가 원문에 있는가 */
export function grounded(model, text) {
  const t = text.toLowerCase();
  const nums = model.match(NUMS);
  if (nums) return nums.every((n) => rx(String.raw`(?<!\d)${n}(?!\d)`).test(t));
  const words = splitWs(model.toLowerCase()).filter((w) => w && !GENERIC.has(w));
  return words.every((w) => (ALIAS.get(w) || [w]).some((a) => t.includes(a)));
}

const COLOR_ALIAS = new Map(Object.entries({
  블랙: ['black', '검정', '검은', '블랙'], 화이트: ['white', '흰', '하얀', '화이트'], 실버: ['silver'],
  골드: ['gold'], 블루: ['blue', '파랑', '파란'], 그레이: ['gray', 'grey', '회색', '그레이'],
  핑크: ['pink', '분홍'], 퍼플: ['purple', '보라'], 그린: ['green', '초록', '녹색'], 레드: ['red', '빨강', '빨간'],
  옐로우: ['yellow', '노랑', '노란'], 스페이스그레이: ['스그', 'spacegray', 'spacegrey'], 그래파이트: ['graphite'],
  티타늄: ['titanium'], 미드나이트: ['midnight'], 스타라이트: ['starlight'], 네이비: ['navy'],
  크림: ['cream'], 라벤더: ['lavender'], 민트: ['mint'], 버건디: ['burgundy'], 바이올렛: ['violet'],
}));
const WS_ALL = rx(String.raw`\s`, 'g');

export function colorGrounded(color, text) {
  const c = color.toLowerCase().replace(WS_ALL, '');
  const t = text.toLowerCase().replace(WS_ALL, '');
  if (t.includes(c)) return true;
  // 합성 색상(스카이 블루, 블랙 티타늄)은 구성 단어가 모두 원문에 있으면 인정
  const parts = splitWs(color.toLowerCase()).filter((p) => p);
  return parts.every((p) => t.includes(p) || (COLOR_ALIAS.get(p) || []).some((a) => t.includes(a))) ||
    (COLOR_ALIAS.get(c) || []).some((a) => t.includes(a));
}

const STORAGE_VAL = rx(String.raw`^(\d+)\s*(GB|TB)`);

export function storageGrounded(s, text) {
  const m = STORAGE_VAL.exec(s.toUpperCase());
  if (!m) return false;
  const [, n, unit] = m;
  const t = text.toLowerCase();
  if (unit === 'TB') return rx(String.raw`(?<!\d)${n}\s*(?:t|tb|테라|tera)`).test(t) || (n === '1' && t.includes('1024'));
  return rx(String.raw`(?<!\d)${n}(?!\d)`).test(t);
}

const CHECKS = {
  models: grounded,
  storage: storageGrounded,
  color: colorGrounded,
};

/**
 * 모델명·용량·색상 각각, 원문 근거가 없는 값이 있으면 그 필드를 규칙 결과로 바꾼다.
 * @param {() => object} rulesSpec 규칙만으로 만든 spec (buildSpec(cat, title, body, null)). 필요할 때만 부른다
 * @returns {[object, boolean]} [결과, 바꿨는지]
 */
export function ground(pred, title, body, rulesSpec) {
  const text = `${title}\n${body}`;
  const bad = Object.keys(CHECKS).filter((k) => !(pred[k] || []).every((v) => CHECKS[k](v, text)));
  if (!bad.length) return [pred, false];
  const rules = rulesSpec();
  const fromRules = { models: rules.models, storage: rules.storages, color: rules.colors };
  const out = { ...pred };
  for (const k of bad) out[k] = fromRules[k];
  return [out, true];
}
