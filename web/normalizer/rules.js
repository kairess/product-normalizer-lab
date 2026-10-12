// normalizer/rules.py 의 JS 판: 규칙 + 사전 기반 추출기 (아이폰/갤럭시). 정규식은 Python 원본을 그대로 옮겼다.

import { cmp, cpBefore, cpAfter, head, pyInt, rx, strip } from './py.js';

// ------------------------------------------------------------------ 모델
const IP_VARIANT = String.raw`(pro\s*max|프로\s*맥스|프맥|promax|프로맥|pro|프로|plus|플러스|\+|mini|미니|max|맥스)?`;
const IP_RE = rx(
  String.raw`(?:아이폰|iphone|아이뻰|아이퐁|ip)\s*` +
    String.raw`(1[1-8]e?|[4-8]s?\+?|x[sr]?|se\s*(?:[23]|20(?:20|22))?(?:\s*세대)?|에어|air|듀오|duo|텐)\s*` + IP_VARIANT,
  'gi',
);
// 접두어 없는 "14pro", "13미니", "15프맥" (아이폰 맥락에서만 사용)
const IP_BARE_RE = rx(String.raw`(?<![\w.])(1[1-8])\s*(pro\s*max|프로\s*맥스|프맥|promax|pro|프로|plus|플러스|mini|미니)`, 'gi');

const S_RE = rx(String.raw`(?<![a-z0-9])s\s?(2[0-6]|1[0-9]|[2-9])(?!\d)\s*(울트라|ultra|플러스|plus|\+|fe|엣지|edge)?`, 'gi');
const FOLD_RE = rx(String.raw`(z\s*)?(?:폴드|fold)\s*([1-8])?(?!\d)\s*(스페셜|special)?`, 'gi');
const FLIP_RE = rx(String.raw`(?:z\s*)?(?:플립|flip)\s*([1-8])?(?!\d)\s*(fe)?`, 'gi');
const TRIFOLD_RE = rx(String.raw`트라이\s*폴드|trifold|tri\s*fold`, 'i');
const NOTE_RE = rx(String.raw`(?:노트|note)\s*(20|10|[2-9]|fe)(?!\d)\s*(울트라|ultra|플러스|plus|\+)?`, 'gi');
const A_RE = rx(String.raw`(?:갤럭시|galaxy|갤)\s*([amj])\s?(\d{1,3})(?!\d)`, 'gi');
const KR_LINE_RE = rx(String.raw`(퀀텀|와이드|점프|버디)\s*(\d)`, 'g');

const VARIANT_KO = new Map(Object.entries({
  'pro max': '프로 맥스', promax: '프로 맥스', 프로맥스: '프로 맥스', 프맥: '프로 맥스', 프로맥: '프로 맥스',
  pro: '프로', 프로: '프로', plus: '플러스', 플러스: '플러스', '+': '플러스',
  mini: '미니', 미니: '미니', max: '맥스', 맥스: '맥스',
  ultra: '울트라', 울트라: '울트라', fe: 'FE', edge: '엣지', 엣지: '엣지',
}));
const WS_RUN = rx(String.raw`\s+`, 'g');

function variant(v) {
  if (!v) return '';
  let key = strip(v.toLowerCase().replace(WS_RUN, ' '));
  key = key.replaceAll('프로 맥스', '프로맥스');
  return VARIANT_KO.get(key) ?? VARIANT_KO.get(key.replaceAll(' ', '')) ?? '';
}

const SE3 = rx('3|2022');
const SE2 = rx('2(?!0)|2020');

function iphone(gen, vr) {
  let g = gen.toLowerCase().replaceAll(' ', '');
  if (g === '에어' || g === 'air') return '아이폰 에어';
  if (g === '듀오' || g === 'duo') return '아이폰 듀오';
  if (g === '텐') g = 'x';
  if (g.startsWith('se')) {
    if (SE3.test(g)) return '아이폰 SE 3세대';
    if (SE2.test(g)) return '아이폰 SE 2세대';
    return '아이폰 SE';
  }
  if (g.endsWith('+')) [g, vr] = [g.slice(0, -1), 'plus'];
  let v = variant(vr);
  g = g.toUpperCase();
  if (g === 'XS' && v === '맥스') return '아이폰 XS 맥스';
  if (v === '맥스') v = '프로 맥스'; // "아이폰 15 맥스" 같은 축약 → 프로 맥스
  return strip(`아이폰 ${g} ${v}`);
}

const AIR_FIX = rx(String.raw`(아이폰|iphone)\s*17\s*(?:에어|air)`, 'g');
const DUO_FIX = rx(String.raw`(아이폰|iphone)\s*(?:18\s*)?(?:듀오|duo|폴드|fold)`, 'g');
const STARTS_DIGIT = /^\p{Nd}/u;

export function findModels(text, iphoneCtx) {
  let t = text.toLowerCase().replace(AIR_FIX, '$1 에어');
  t = t.replace(DUO_FIX, '$1 듀오');
  const found = [];
  for (const m of t.matchAll(IP_RE)) found.push([m.index, iphone(m[1], m[2])]);
  if (iphoneCtx && !found.length) {
    for (const m of t.matchAll(IP_BARE_RE)) found.push([m.index, iphone(m[1], m[2])]);
  }
  for (const m of t.matchAll(S_RE)) found.push([m.index, strip(`갤럭시 S${m[1]} ${variant(m[2])}`)]);
  const tri = TRIFOLD_RE.exec(t);
  if (tri) {
    found.push([tri.index, '갤럭시 Z 트라이폴드']);
  } else {
    for (const m of t.matchAll(FOLD_RE)) {
      let name;
      if (m[3]) name = '갤럭시 Z 폴드 스페셜 에디션';
      else if (m[2]) name = `갤럭시 Z 폴드${m[2]}`;
      else name = m[1] ? '갤럭시 Z 폴드' : '갤럭시 폴드';
      found.push([m.index, name]);
    }
  }
  for (const m of t.matchAll(FLIP_RE)) found.push([m.index, `갤럭시 Z 플립${m[1] || ''}` + (m[2] ? ' FE' : '')]);
  for (const m of t.matchAll(NOTE_RE)) {
    const n = m[1].toUpperCase();
    found.push([m.index, n === 'FE' ? '갤럭시 노트 FE' : strip(`갤럭시 노트${n} ${variant(m[2])}`)]);
  }
  for (const m of t.matchAll(A_RE)) found.push([m.index, `갤럭시 ${m[1].toUpperCase()}${m[2]}`]);
  for (const m of t.matchAll(KR_LINE_RE)) found.push([m.index, `갤럭시 ${m[1]}${m[2]}`]);
  found.sort((a, b) => a[0] - b[0] || cmp(a[1], b[1]));
  const out = [];
  for (const [, name] of found) if (!out.includes(name)) out.push(name);
  // "갤럭시 Z 폴드"와 "갤럭시 Z 폴드5"가 함께 잡히면 구체적인 쪽만 남김
  return out.filter((n) => !out.some((o) => o !== n && o.startsWith(n) && STARTS_DIGIT.test(strip(o.slice(n.length)))));
}

// ------------------------------------------------------------------ 용량
const STORAGE_RE = rx(String.raw`(?<![\d.,])(16|32|64|128|256|512)\s*(gb|g|기가바이트|기가|기)?(?![\d,])`, 'gi');
const TB_RE = rx(String.raw`(?<![\d.])([12])\s*(tb|테라|t)(?![a-z])`, 'gi');
const RAM_CTX = rx(String.raw`(램|ram|메모리)\s*[:]?\s*$`, 'i');

export function findStorage(text, requireUnit) {
  const out = [];
  for (const m of text.matchAll(STORAGE_RE)) {
    if (requireUnit && !m[2]) continue;
    if (RAM_CTX.test(cpBefore(text, m.index, 8))) continue;
    if (!m[2] && pyInt(m[1]) < 64n) continue;
    const val = `${m[1]}GB`;
    if (!out.includes(val)) out.push(val);
  }
  for (const m of text.matchAll(TB_RE)) {
    const val = `${m[1]}TB`;
    if (!out.includes(val)) out.push(val);
  }
  return out;
}

// ------------------------------------------------------------------ 색상
const COLORS = [
  // [패턴, 출력] — 긴 것부터
  ['스페이스\\s*그레이|스페이스\\s*그래이|space\\s*gr[ae]y|스그', '스페이스 그레이'],
  ['스페이스\\s*블랙|space\\s*black', '스페이스 블랙'],
  ['블랙\\s*티타늄|black\\s*titanium', '블랙 티타늄'],
  ['화이트\\s*티타늄|white\\s*titanium', '화이트 티타늄'],
  ['내추럴\\s*티타늄|네추럴\\s*티타늄|natural\\s*titanium', '내추럴 티타늄'],
  ['블루\\s*티타늄|blue\\s*titanium', '블루 티타늄'],
  ['데저트\\s*티타늄|desert\\s*titanium', '데저트 티타늄'],
  ['티타늄\\s*그레이', '티타늄 그레이'], ['티타늄\\s*블랙', '티타늄 블랙'], ['티타늄\\s*실버\\s*블루', '티타늄 실버블루'],
  ['티타늄\\s*바이올렛', '티타늄 바이올렛'], ['티타늄\\s*옐로우?', '티타늄 옐로'], ['티타늄\\s*화이트\\s*실버', '티타늄 화이트실버'],
  ['코스믹\\s*오렌지|cosmic\\s*orange', '코스믹 오렌지'], ['딥\\s*블루|deep\\s*blue', '딥 블루'],
  ['미드나이트\\s*그린|미드나잇\\s*그린', '미드나이트 그린'], ['퍼시픽\\s*블루', '퍼시픽 블루'], ['시에라\\s*블루', '시에라 블루'],
  ['알파인\\s*그린', '알파인 그린'], ['딥\\s*퍼플', '딥 퍼플'], ['라이트\\s*골드', '라이트 골드'], ['클라우드\\s*화이트', '클라우드 화이트'],
  ['스카이\\s*블루', '스카이 블루'], ['세이지', '세이지'], ['라벤더', '라벤더'], ['미스트\\s*블루', '미스트 블루'],
  ['팬텀\\s*블랙', '팬텀 블랙'], ['팬텀\\s*화이트', '팬텀 화이트'], ['팬텀\\s*실버', '팬텀 실버'], ['팬텀\\s*바이올렛', '팬텀 바이올렛'],
  ['팬텀\\s*그린', '팬텀 그린'], ['팬텀\\s*그레이', '팬텀 그레이'], ['팬텀\\s*핑크', '팬텀 핑크'],
  ['미스틱\\s*브론즈', '미스틱 브론즈'], ['미스틱\\s*블랙', '미스틱 블랙'], ['오로라\\s*글로우', '오로라 글로우'],
  ['아이시\\s*블루', '아이시 블루'], ['실버\\s*쉐도우|실버\\s*섀도우', '실버 쉐도우'], ['코발트\\s*바이올렛', '코발트 바이올렛'],
  ['앰버\\s*옐로우?', '앰버 옐로'], ['마블\\s*그레이', '마블 그레이'], ['그라파이트|그래파이트|graphite', '그래파이트'],
  ['제트\\s*블랙|jet\\s*black', '제트 블랙'], ['로즈\\s*골드|rose\\s*gold', '로즈 골드'], ['그레이\\s*그린', '그레이 그린'],
  ['크림', '크림'], ['보라퍼플', '퍼플'],
  ['미드나이트|미드나잇|midnight', '미드나이트'], ['스타라이트|스타라잇|starlight', '스타라이트'],
  ['블랙|black|검정색?|검은색', '블랙'], ['화이트|white|흰색|하얀색', '화이트'], ['실버|silver', '실버'],
  ['골드|gold', '골드'], ['블루|blue|파란색', '블루'], ['레드|red|빨간색', '레드'], ['그린|green|초록색?', '그린'],
  ['핑크|pink|분홍색?', '핑크'], ['퍼플|purple|보라색?', '퍼플'], ['옐로우?|yellow|노란색', '옐로'],
  ['코랄|coral', '코랄'], ['네이비|navy', '네이비'], ['민트|mint', '민트'], ['그레이|gr[ae]y|회색', '그레이'],
  ['오렌지|orange', '오렌지'], ['티타늄|titanium', '티타늄'], ['바이올렛|violet', '바이올렛'], ['베이지', '베이지'],
].map(([p, name]) => [rx(p, 'gi'), name]);

export function findColors(text) {
  const spans = [];
  for (const [re, name] of COLORS) {
    for (const m of text.matchAll(re)) {
      const s = m.index;
      const e = s + m[0].length;
      if (spans.some(([s2, e2]) => !(e <= s2 || s >= e2))) continue;
      spans.push([s, e, name]);
    }
  }
  spans.sort((a, b) => a[0] - b[0] || a[1] - b[1] || cmp(a[2], b[2]));
  const out = [];
  for (const [, , name] of spans) if (!out.includes(name)) out.push(name);
  return out;
}

// ------------------------------------------------------------------ 글 유형 / 카테고리
const BUY_RE = rx('삽니다|구합니다|구해요|구매합니다|구매해요|매입합니다|구함|구매원해요|찾습니다|찾아요|사요(?!\\w)|구매희망');
const SHOP_RE = rx(String.raw`대량\s*판매|도매|매입\s*전문|모든\s*휴대폰|중고폰\s*싼곳|중고폰\s*매장|전기종|기종\s*다수|최저가\s*\d`, 'i');
const CAT_RULES = [
  ['earbuds', rx('버즈|buds|에어팟|airpods', 'i')],
  ['watch', rx('워치|watch', 'i')],
  ['tablet', rx(String.raw`아이패드|ipad|갤럭시\s*탭|갤탭|(?<![a-z])tab\s*s?\d|탭\s*s\d`, 'i')],
  ['laptop', rx(String.raw`맥북|macbook|갤럭시\s*북|갤북`, 'i')],
];
const ACC_RE = rx(
  String.raw`케이스|필름|강화유리|충전기|케이블|거치대|스트랩|범퍼|그립톡|어댑터|보조\s*배터리|s\s*펜|카드\s*지갑|폰\s*커버|플립\s*커버|맥세이프\s*(?:배터리|카드|지갑)|짐벌|렌즈\s*보호`,
  'i',
);
const ACC_INCL_RE = rx(String.raw`(케이스|필름|강화유리|충전기|케이블|s\s*펜)[^\n]{0,6}(포함|증정|드림|드려요|같이|서비스|함께|\+)`, 'i');
const RENTAL_RE = rx('대여|렌탈|렌트(?!카)');
const BOX_ONLY_RE = rx(String.raw`빈\s*박스|공\s*박스|박스\s*만|박스\s*(?:및|와|랑|\+)|(?:^|\s)박스\s*(?:판매|팝니다)?\s*$|박스\s*\(?\s*(?:구성품|설명서)`);
const BOX_FULL_RE = rx(String.raw`풀\s*박|박스\s*(?:포함|있|o\b)`);
const PARTS_RE = rx(String.raw`메인\s*보드|액정\s*(?:단품|만|부품)|부품\s*(?:판매|팝니다|단품)|후면\s*유리|하우징|배터리\s*단품|카메라\s*모듈`, 'i');
const PHONE_WORD_RE = rx('폰|공기계|휴대폰|스마트폰');

// ------------------------------------------------------------------ 상태 (시세 산정용 추정)
const NEW_RE = rx(String.raw`미개봉|단순\s*개봉|새\s*상품(?!\s*급)|새\s*제품(?!\s*급)|미사용(?!\s*급)|새\s*폰(?!\s*급)`);
const BROKEN_RE = rx(
  String.raw`부품용|고장|파손|침수|먹통|벽돌|불량|깨짐|깨져|깨진|금감|금\s*간|안\s*켜|전원\s*(?:안|불량)|` +
    String.raw`(?:액정|화면|디스플레이)\s*(?:나감|줄|멍|번인)|잔상\s*(?:심|있)|번인\s*(?:심|있)|터치\s*(?:안|불량)|페이스\s*아이디\s*(?:안|불)`,
  'g',
);
const BROKEN_BODY_RE = rx(String.raw`부품용|고장|파손|침수|먹통|벽돌|안\s*켜`, 'g');
const NEG_RE = rx(String.raw`^.{0,8}?(?:없|x\b|X\b|아님|아니|무\s|0)`);
const NEW_BODY_RE = rx(String.raw`미개봉|단순\s*개봉`);

function hasUnnegated(re, text) {
  for (const m of text.matchAll(re)) {
    if (cpBefore(text, m.index, 1) === '무') continue; // 무잔상, 무파손
    if (NEG_RE.test(cpAfter(text, m.index + m[0].length, 10))) continue;
    return true;
  }
  return false;
}

/** 'new'(미개봉·단순개봉) | 'broken'(고장·파손·부품용) | 'used'. 키워드 기반 추정이다. */
export function detectCondition(title, body) {
  const t = title || '';
  const b = head(body || '', 400);
  if (hasUnnegated(BROKEN_RE, t) || hasUnnegated(BROKEN_BODY_RE, b)) return 'broken';
  if (NEW_RE.test(t) || NEW_BODY_RE.test(b)) return 'new';
  return 'used';
}

export function classify(title, body, models, nBodyModels) {
  const t = title.toLowerCase();
  let postType = 'sell';
  if (BUY_RE.test(t)) postType = 'buy';
  if (models.length >= 4 || SHOP_RE.test(t) || (nBodyModels >= 7 && SHOP_RE.test(body))) postType = 'shop_ad';
  if (RENTAL_RE.test(t)) postType = 'other';
  let category = null;
  if (BOX_ONLY_RE.test(t) && !BOX_FULL_RE.test(t)) category = 'accessory';
  if (!category) {
    for (const [cat, re] of CAT_RULES) {
      if (re.test(t)) {
        category = cat;
        break;
      }
    }
  }
  if (category === null && PARTS_RE.test(t)) category = 'parts';
  if (category === null && ACC_RE.test(t) && !ACC_INCL_RE.test(t) && !findStorage(t, true).length) category = 'accessory';
  if (category === null) category = models.length || PHONE_WORD_RE.test(t) ? 'phone' : 'other';
  return [postType, category];
}

const IPHONE_CTX_RE = rx('아이폰|iphone|애플|apple');
const GALAXY_TITLE_RE = rx('갤럭시|galaxy|삼성');

export function extract(title, body) {
  body = body || '';
  const textAll = `${title}\n${body}`.toLowerCase();
  const iphoneCtx = IPHONE_CTX_RE.test(textAll) && !GALAXY_TITLE_RE.test(title.toLowerCase());

  let models = findModels(title, iphoneCtx);
  const bodyModels = findModels(body, iphoneCtx);
  if (!models.length) models = bodyModels.slice(0, 1);

  const [postType, category] = classify(title, body, models, bodyModels.length);
  if (postType === 'shop_ad') models = [];

  let storage = findStorage(title, false);
  if (!storage.length) storage = findStorage(head(body, 300), true).slice(0, 1);
  let color = findColors(title);
  if (!color.length) color = findColors(head(body, 300)).slice(0, 1);
  if (category !== 'phone') storage = category === 'tablet' || category === 'laptop' ? storage : [];
  return { post_type: postType, category, models, storage, color };
}
