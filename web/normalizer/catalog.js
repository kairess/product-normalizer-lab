// normalizer/catalog.py 의 JS 판: 아이폰/갤럭시 폰 카탈로그.
//
// - 모델명 검증과 정식명 맞추기(snap): 별칭·모델 코드(SM-A155N, A155)·흔한 오기를 정식명으로 바꾼다.
// - 정식명을 검색 토큰 {브랜드, 라인, 세대, 변형}으로 분해한다(parse).
// - 모델별 공식 색상으로 정규화한다(officialColor).
// 데이터는 normalizer/data/catalog_*.json 을 파일 이름 순으로 넘긴다 (Python 과 같은 순서여야 결과가 같다).

import { normColor, normModel } from './common.js';
import { rx, strip } from './py.js';

// ---------------------------------------------------------------- 내장 목록 (JSON 이 없을 때의 최소 집합)
const IPHONE = [
  '3G', '3GS', '4', '4S', '5', '5C', '5S', '6', '6 플러스', '6S', '6S 플러스', 'SE', '7', '7 플러스',
  '8', '8 플러스', 'X', 'XS', 'XS 맥스', 'XR', '11', '11 프로', '11 프로 맥스', 'SE 2세대',
  '12 미니', '12', '12 프로', '12 프로 맥스', '13 미니', '13', '13 프로', '13 프로 맥스', 'SE 3세대',
  '14', '14 플러스', '14 프로', '14 프로 맥스', '15', '15 플러스', '15 프로', '15 프로 맥스',
  '16', '16 플러스', '16 프로', '16 프로 맥스', '16e', '17', '에어', '17 프로', '17 프로 맥스', '17e',
  '18 프로', '18 프로 맥스',
];
const range = (a, b) => Array.from({ length: b - a }, (_, i) => a + i);
const GALAXY = [
  'S2', 'S3', 'S4', 'S5', 'S6', 'S6 엣지', 'S6 엣지 플러스', 'S7', 'S7 엣지', 'S8', 'S8 플러스',
  'S9', 'S9 플러스', 'S10', 'S10e', 'S10 플러스', 'S10 5G', 'S20 FE', 'S21 FE', 'S23 FE', 'S24 FE', 'S25 FE',
  'S25 엣지',
  ...range(20, 27).flatMap((n) => ['', ' 플러스', ' 울트라'].map((v) => `S${n}${v}`)),
  '노트', '노트2', '노트3', '노트4', '노트5', '노트 FE', '노트8', '노트9', '노트10', '노트10 플러스',
  '노트20', '노트20 울트라',
  '폴드', 'Z 폴드', 'Z 플립', 'Z 폴드 스페셜 에디션', 'Z 트라이폴드', 'Z 플립7 FE',
  ...range(2, 9).map((n) => `Z 폴드${n}`),
  ...range(3, 9).map((n) => `Z 플립${n}`),
];
const BUILTIN = ['아이폰', ...IPHONE.map((m) => `아이폰 ${m}`), '갤럭시 S', ...GALAXY.map((m) => `갤럭시 ${m}`)];
const LONGTAIL_RE = rx(String.raw`^갤럭시(?:[amj]\d{1,2}s?|퀀텀\d?|와이드\d?|점프\d?|버디\d?|a퀀텀)$`, 'i');

// ---------------------------------------------------------------- 표기 보정 (snap 전에 적용)
const PRE_FIXES = [
  [rx(String.raw`^(?:삼성|samsung|애플|apple)\s*`, 'gi'), ''],
  [rx(String.raw`\s*(?:5g|lte|자급제|공기계|일반(?:모델)?|기본(?:형|모델)?)\s*$`, 'gi'), ''],
  [rx(String.raw`아이폰\s*(?:17\s*에어|에어\s*17|17\s*air)`, 'gi'), '아이폰 에어'],
  [rx(String.raw`아이폰\s*se\s*(?:1|1세대|2016)\s*$`, 'gi'), '아이폰 SE'],
  [rx(String.raw`아이폰\s*se\s*(?:2|2020)\s*$`, 'gi'), '아이폰 SE 2세대'],
  [rx(String.raw`아이폰\s*se\s*(?:3|2022)\s*$`, 'gi'), '아이폰 SE 3세대'],
  [rx(String.raw`아이폰\s*미니\s*(\d+)`, 'gi'), '아이폰 $1 미니'],
  [rx(String.raw`갤럭시\s*(폴드|플립)\s*(\d)`, 'gi'), '갤럭시 Z $1$2'],
  [rx(String.raw`갤럭시\s*z\s*(폴드|플립)\s+(\d)`, 'gi'), '갤럭시 Z $1$2'],
];

function preFix(name) {
  let s = strip(String(name || ''));
  for (const [re, rep] of PRE_FIXES) s = strip(s.replace(re, rep));
  return s;
}

const CODE_STRIP = rx(String.raw`[\s-]`, 'g');

function normCode(code) {
  const c = String(code || '').replace(CODE_STRIP, '').toUpperCase();
  return c.startsWith('SM') ? c.slice(2) : c;
}

const PARSE_RES = [
  [rx(String.raw`^아이폰\s*(SE)(?:\s*(\d)세대)?$`), 'Apple', '아이폰'],
  [rx(String.raw`^아이폰\s*(에어)$`), 'Apple', '아이폰'],
  [rx(String.raw`^아이폰\s*(\d{1,2}e?|X[SR]?|[3-8][GSC]{0,2})\s*(.*)$`), 'Apple', '아이폰'],
  [rx(String.raw`^갤럭시\s*S(\d{1,2}e?)\s*(.*)$`), 'Samsung', '갤럭시 S'],
  [rx(String.raw`^갤럭시\s*노트\s*(\d{0,2})\s*(.*)$`), 'Samsung', '갤럭시 노트'],
  [rx(String.raw`^갤럭시\s*Z\s*트라이폴드$`), 'Samsung', '갤럭시 Z 트라이폴드'],
  [rx(String.raw`^갤럭시\s*(?:Z\s*)?폴드\s*(\d?)\s*(.*)$`), 'Samsung', '갤럭시 Z 폴드'],
  [rx(String.raw`^갤럭시\s*(?:Z\s*)?플립\s*(\d?)\s*(.*)$`), 'Samsung', '갤럭시 Z 플립'],
  [rx(String.raw`^갤럭시\s*([AMJ])(\d{1,3}s?)\s*(.*)$`), 'Samsung', null],
  [rx(String.raw`^갤럭시\s*(퀀텀|와이드|점프|버디)\s*(\d?)\s*(.*)$`), 'Samsung', null],
];
const NONE = { brand: null, line: null, gen: null, variant: null };

export function parseName(name) {
  const m = strip(String(name || ''));
  for (const [re, brand, line] of PARSE_RES) {
    const mm = re.exec(m);
    if (!mm) continue;
    const g = mm.slice(1);
    if (line === '갤럭시 Z 트라이폴드') return { brand, line, gen: '', variant: '' };
    if (line === null) return { brand, line: `갤럭시 ${g[0]}`, gen: g[1], variant: strip(g[2]) };
    if (g[0] === 'SE') return { brand, line, gen: 'SE', variant: g[1] ? `${g[1]}세대` : '' };
    if (g[0] === '에어') return { brand, line, gen: '', variant: '에어' };
    return { brand, line, gen: g[0], variant: strip(g.length > 1 ? g[1] : '') };
  }
  return { ...NONE };
}

const CODE_RE = rx(String.raw`(?:sm-?)?([afgjmnsx])\s?(\d{3,4})([a-z]{0,2})`, 'gi');

export class Catalog {
  /** @param {object[]} datas catalog_*.json 내용들 (파일 이름 순) */
  constructor(datas = []) {
    this.models = new Map(); // normModel(name) -> model
    this.alias = new Map(); // norm alias -> norm name
    this.code = new Map(); // 코드(대문자, SM- 제거) -> norm name
    for (const data of datas) this.#loadJson(data);
    for (const name of BUILTIN) {
      const key = normModel(name);
      if (!this.models.has(key)) this.models.set(key, { name, ...parseName(name), colors: [] });
    }
  }

  #loadJson(data) {
    const brand = data.brand;
    for (const m of data.models || []) {
      const name = m.name;
      if (!name) continue;
      const key = normModel(name);
      const parsed = parseName(name);
      this.models.set(key, {
        name,
        brand: brand || parsed.brand,
        line: m.line || parsed.line,
        gen: m.gen !== undefined && m.gen !== null ? m.gen : parsed.gen,
        variant: m.variant !== undefined && m.variant !== null ? m.variant : parsed.variant,
        colors: [...(m.colors || [])],
      });
      for (const a of m.aliases || []) {
        const k = normModel(preFix(a));
        if (!this.alias.has(k)) this.alias.set(k, key);
      }
      for (const c of m.codes || []) {
        const code = normCode(c);
        if (!code) continue;
        if (!this.code.has(code)) this.code.set(code, key);
        const short = code.replace(/[NSKL]+$/, ''); // SM-A155N → A155
        if (!this.code.has(short)) this.code.set(short, key);
      }
    }
  }

  get(name) {
    return this.models.get(normModel(name)) || null;
  }

  /** 정식명. 모르면 null (롱테일 갤럭시 A/퀀텀 등은 패턴이 맞으면 그대로 허용). */
  snap(name) {
    if (!name) return null;
    for (const cand of [name, preFix(name)]) {
      const key = normModel(cand);
      if (this.models.has(key)) return this.models.get(key).name;
      if (this.alias.has(key)) return this.models.get(this.alias.get(key)).name;
    }
    const code = this.lookupCode(name);
    if (code) return code;
    const fixed = preFix(name);
    if (LONGTAIL_RE.test(normModel(fixed))) return fixed;
    return null;
  }

  /** 'SM-A155N', 'A155', '갤럭시 A155' 처럼 모델 코드가 들어 있으면 정식명. */
  lookupCode(text) {
    for (const m of String(text || '').matchAll(CODE_RE)) {
      const code = (m[1] + m[2]).toUpperCase();
      if (this.code.has(code)) return this.models.get(this.code.get(code)).name;
    }
    return null;
  }

  isKnown(name) {
    return this.snap(name) !== null;
  }

  /** 판매자가 적은 색상 → 해당 모델의 공식 색상명 (못 찾으면 null) */
  officialColor(modelName, rawColor) {
    const m = this.get(modelName);
    if (!m || !m.colors.length || !rawColor) return null;
    const target = normColor(rawColor);
    for (const c of m.colors) {
      const names = [c.name || '', ...(c.aliases || []), ...(c.en ? [c.en] : [])];
      if (names.some((n) => n && normColor(n) === target)) return c.name ?? null;
    }
    return null;
  }

  parse(name) {
    const m = this.get(name);
    if (m) return { brand: m.brand, line: m.line, gen: m.gen, variant: m.variant };
    return parseName(name);
  }

  searchTokens(models, storage, colors) {
    const toks = [];
    for (const m of models) {
      const p = this.parse(m);
      toks.push(m, ...[p.line, p.gen, p.variant].filter((v) => v));
    }
    toks.push(...storage, ...colors);
    const out = [];
    for (const t of toks) if (t && !out.includes(t)) out.push(t);
    return out;
  }
}
