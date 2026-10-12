// normalizer/common.py 의 JS 판: 비교용 정규화(모델명·색상·용량)와 색상 별칭.

import { cpLen, pyInt, rx } from './py.js';

export const POST_TYPES = ['sell', 'buy', 'shop_ad', 'other'];
export const CATEGORIES = ['phone', 'tablet', 'watch', 'earbuds', 'laptop', 'accessory', 'parts', 'other'];

// 비교용 영→한 토큰 (예측·정답 양쪽에 동일하게 적용)
const MODEL_TOKENS = [
  [String.raw`iphone|아이뻰|아이퐁`, '아이폰'],
  [String.raw`galaxy|겔럭시|갤(?!럭시)`, '갤럭시'],
  [String.raw`promax|pro\s*max|프맥`, '프로맥스'],
  [String.raw`pro`, '프로'],
  [String.raw`max`, '맥스'],
  [String.raw`mini`, '미니'],
  [String.raw`plus|\+`, '플러스'],
  [String.raw`ultra`, '울트라'],
  [String.raw`edge`, '엣지'],
  [String.raw`fold`, '폴드'],
  [String.raw`flip`, '플립'],
  [String.raw`note`, '노트'],
  [String.raw`air`, '에어'],
  [String.raw`갤럭시갤럭시`, '갤럭시'],
].map(([p, r]) => [rx(p, 'g'), r]);
const MODEL_STRIP = rx(String.raw`[\s\-_()]`, 'g');

export function normModel(s) {
  s = String(s || '').toLowerCase();
  for (const [re, rep] of MODEL_TOKENS) s = s.replace(re, rep);
  return s.replace(MODEL_STRIP, '');
}

export const COLOR_ALIASES = new Map(Object.entries({
  흰색: '화이트', 하얀색: '화이트', white: '화이트', 화이트색: '화이트',
  검정: '블랙', 검정색: '블랙', 검은색: '블랙', black: '블랙', 블랙색: '블랙',
  스그: '스페이스그레이', spacegray: '스페이스그레이', spacegrey: '스페이스그레이', 스페이스그래이: '스페이스그레이',
  스블: '스페이스블랙', 미드나잇: '미드나이트', 스타라잇: '스타라이트',
  silver: '실버', gold: '골드', blue: '블루', red: '레드', green: '그린',
  pink: '핑크', purple: '퍼플', yellow: '옐로', 옐로우: '옐로', 그래이: '그레이',
  gray: '그레이', grey: '그레이', navy: '네이비', 레드색: '레드', 빨강: '레드',
  productred: '레드', '(product)red': '레드', 프로덕트레드: '레드',
  로즈골드: '로즈골드', rosegold: '로즈골드', 자급제: '',
  네추럴티타늄: '내추럴티타늄', 은색: '실버', 회색: '그레이', 초록: '그린', 보라: '퍼플',
}));
const COLOR_STRIP = rx(String.raw`[\s\-_]`, 'g');
const COLOR_SUFFIX = rx(String.raw`색$`);
const alias = (s) => (COLOR_ALIASES.has(s) ? COLOR_ALIASES.get(s) : s);

export function normColor(s) {
  s = alias(String(s || '').toLowerCase().replace(COLOR_STRIP, ''));
  s = cpLen(s) > 2 ? s.replace(COLOR_SUFFIX, '') : s;
  return alias(s);
}

const WS_ALL = rx(String.raw`\s`, 'g');
const STORAGE_RE = rx(String.raw`^(\d+)(GB|G|기가|TB|T|테라)?$`);

export function normStorage(s) {
  s = String(s || '').toUpperCase().replace(WS_ALL, '');
  const m = STORAGE_RE.exec(s);
  if (!m) return s;
  const n = pyInt(m[1]);
  const unit = m[2] || 'GB';
  if (['TB', 'T', '테라'].includes(unit) || n === 1n || n === 2n) return `${n}TB`;
  return `${n}GB`;
}
