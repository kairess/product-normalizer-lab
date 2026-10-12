// Python re / str 과 똑같이 동작하게 하는 도구. 규칙·카탈로그·근거 검사의 Python 정규식을 그대로 옮겨 쓰기 위한 것.
//
// Python(유니코드 문자열)과 JS 정규식의 차이:
// - \w \d \b: Python 은 유니코드(한글·전각 숫자 포함), JS 는 ASCII 만 → \p{..} 로 바꾼다.
// - \s: 공백으로 치는 문자가 조금 다르다 (Python 은 \x1c-\x1f·\x85 포함, JS 는 \ufeff 포함).
// - . : Python 은 \n 만 제외, JS 는 \r \u2028 \u2029 도 제외.
// - $ : Python 은 끝 또는 마지막 \n 앞.
// - 문자열 길이·자르기: Python 은 코드 포인트, JS 는 UTF-16 단위 (이모지가 2). → head(), cpBefore(), cpAfter()

const WS = '\\t\\n\\v\\f\\r \\x1c-\\x1f\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
const W = '\\p{L}\\p{N}_';

/** Python 정규식 문자열 → 같은 뜻의 JS RegExp ('u' 플래그는 늘 붙는다). */
export function rx(pattern, flags = '') {
  let out = '';
  let inClass = false;
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i];
    if (c === '\\') {
      const n = pattern[++i];
      if (n === 's') out += inClass ? WS : `[${WS}]`;
      else if (n === 'd') out += '\\p{Nd}';
      else if (n === 'w') out += inClass ? W : `[${W}]`;
      else if (n === 'b') out += `(?:(?<=[${W}])(?![${W}])|(?<![${W}])(?=[${W}]))`;
      else if ('SDWBAZ'.includes(n)) throw new Error(`rx: \\${n} 미지원`);
      else out += '\\' + n;
    } else if (inClass) {
      if (c === ']') inClass = false;
      out += c;
    } else if (c === '[') {
      inClass = true;
      out += c;
      if (pattern[i + 1] === '^') out += pattern[++i];
    } else if (c === '.') {
      out += '[^\\n]';
    } else if (c === '$') {
      out += '(?=\\n?$)';
    } else {
      out += c;
    }
  }
  return new RegExp(out, 'u' + flags);
}

const WS_EDGE = new RegExp(`^[${WS}]+|[${WS}]+$`, 'gu');
const WS_RUN = new RegExp(`[${WS}]+`, 'u');

/** str.strip() */
export const strip = (s) => s.replace(WS_EDGE, '');

/** re.split(r"\s+", s) */
export const splitWs = (s) => s.split(WS_RUN);

const isHigh = (c) => c >= 0xd800 && c <= 0xdbff;
const isLow = (c) => c >= 0xdc00 && c <= 0xdfff;

/** s[:n] (코드 포인트 기준) */
export function head(s, n) {
  let i = 0;
  for (let k = 0; i < s.length && k < n; k++) i += isHigh(s.charCodeAt(i)) && isLow(s.charCodeAt(i + 1)) ? 2 : 1;
  return s.slice(0, i);
}

/** s[max(0, idx - n):idx] (idx 는 UTF-16 위치, n 은 코드 포인트 수) */
export function cpBefore(s, idx, n) {
  let i = idx;
  for (let k = 0; i > 0 && k < n; k++) i -= isLow(s.charCodeAt(i - 1)) && isHigh(s.charCodeAt(i - 2)) ? 2 : 1;
  return s.slice(i, idx);
}

/** s[idx:idx + n] */
export const cpAfter = (s, idx, n) => head(s.slice(idx), n);

/** len(s) */
export function cpLen(s) {
  let n = 0;
  for (const _ of s) n++;
  return n;
}

/** Python 문자열 비교(코드 포인트 순). 정렬용 */
export function cmp(a, b) {
  if (a === b) return 0;
  const A = a[Symbol.iterator]();
  const B = b[Symbol.iterator]();
  for (;;) {
    const x = A.next();
    const y = B.next();
    if (x.done || y.done) return x.done ? (y.done ? 0 : -1) : 1;
    const d = x.value.codePointAt(0) - y.value.codePointAt(0);
    if (d) return d;
  }
}

const ND = /\p{Nd}/u;

/** int(s) — s 는 \d+ 로 잡은 숫자 (전각 등 유니코드 숫자 포함). 큰 수도 정확히 */
export function pyInt(s) {
  let ascii = '';
  for (const ch of s) {
    const cp = ch.codePointAt(0);
    if (cp >= 48 && cp <= 57) {
      ascii += ch;
      continue;
    }
    let z = cp; // 유니코드 숫자는 0~9 가 연속 구간으로 놓인다
    while (ND.test(String.fromCodePoint(z - 1))) z--;
    ascii += String((cp - z) % 10);
  }
  return BigInt(ascii);
}

/** list(dict.fromkeys(xs)) */
export const unique = (xs) => [...new Set(xs)];

/** sorted(set(xs)) */
export const sortedSet = (xs) => [...new Set(xs)].sort(cmp);
