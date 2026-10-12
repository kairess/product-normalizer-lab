"""규칙 + 사전 기반 추출기 (아이폰/갤럭시). LLM 없이 정규식과 별칭 사전만 사용."""

from __future__ import annotations

import re

# ------------------------------------------------------------------ 모델
_IP_VARIANT = r"(pro\s*max|프로\s*맥스|프맥|promax|프로맥|pro|프로|plus|플러스|\+|mini|미니|max|맥스)?"
_IP_RE = re.compile(
    r"(?:아이폰|iphone|아이뻰|아이퐁|ip)\s*"
    r"(1[1-8]e?|[4-8]s?\+?|x[sr]?|se\s*(?:[23]|20(?:20|22))?(?:\s*세대)?|에어|air|듀오|duo|텐)\s*" + _IP_VARIANT,
    re.I,
)
# 접두어 없는 "14pro", "13미니", "15프맥" (아이폰 맥락에서만 사용)
_IP_BARE_RE = re.compile(r"(?<![\w.])(1[1-8])\s*(pro\s*max|프로\s*맥스|프맥|promax|pro|프로|plus|플러스|mini|미니)", re.I)

_S_RE = re.compile(r"(?<![a-z0-9])s\s?(2[0-6]|1[0-9]|[2-9])(?!\d)\s*(울트라|ultra|플러스|plus|\+|fe|엣지|edge)?", re.I)
_FOLD_RE = re.compile(r"(z\s*)?(?:폴드|fold)\s*([1-8])?(?!\d)\s*(스페셜|special)?", re.I)
_FLIP_RE = re.compile(r"(?:z\s*)?(?:플립|flip)\s*([1-8])?(?!\d)\s*(fe)?", re.I)
_TRIFOLD_RE = re.compile(r"트라이\s*폴드|trifold|tri\s*fold", re.I)
_NOTE_RE = re.compile(r"(?:노트|note)\s*(20|10|[2-9]|fe)(?!\d)\s*(울트라|ultra|플러스|plus|\+)?", re.I)
_A_RE = re.compile(r"(?:갤럭시|galaxy|갤)\s*([amj])\s?(\d{1,3})(?!\d)", re.I)
_KR_LINE_RE = re.compile(r"(퀀텀|와이드|점프|버디)\s*(\d)")

_VARIANT_KO = {
    "pro max": "프로 맥스", "promax": "프로 맥스", "프로맥스": "프로 맥스", "프맥": "프로 맥스", "프로맥": "프로 맥스",
    "pro": "프로", "프로": "프로", "plus": "플러스", "플러스": "플러스", "+": "플러스",
    "mini": "미니", "미니": "미니", "max": "맥스", "맥스": "맥스",
    "ultra": "울트라", "울트라": "울트라", "fe": "FE", "edge": "엣지", "엣지": "엣지",
}


def _variant(v: str | None) -> str:
    if not v:
        return ""
    key = re.sub(r"\s+", " ", v.lower()).strip()
    key = key.replace("프로 맥스", "프로맥스")
    return _VARIANT_KO.get(key, _VARIANT_KO.get(key.replace(" ", ""), ""))


def _iphone(gen: str, var: str | None) -> str:
    g = gen.lower().replace(" ", "")
    if g in ("에어", "air"):
        return "아이폰 에어"
    if g in ("듀오", "duo"):
        return "아이폰 듀오"
    if g == "텐":
        g = "x"
    if g.startswith("se"):
        if re.search(r"3|2022", g):
            return "아이폰 SE 3세대"
        if re.search(r"2(?!0)|2020", g):
            return "아이폰 SE 2세대"
        return "아이폰 SE"
    if g.endswith("+"):
        g, var = g[:-1], "plus"
    v = _variant(var)
    g = g.upper()
    if g == "XS" and v == "맥스":
        return "아이폰 XS 맥스"
    if v == "맥스":  # "아이폰 15 맥스" 같은 축약 → 프로 맥스
        v = "프로 맥스"
    return f"아이폰 {g} {v}".strip()


def find_models(text: str, iphone_ctx: bool) -> list[str]:
    t = re.sub(r"(아이폰|iphone)\s*17\s*(?:에어|air)", r"\1 에어", text.lower())
    t = re.sub(r"(아이폰|iphone)\s*(?:18\s*)?(?:듀오|duo|폴드|fold)", r"\1 듀오", t)
    found: list[tuple[int, str]] = []
    for m in _IP_RE.finditer(t):
        found.append((m.start(), _iphone(m.group(1), m.group(2))))
    if iphone_ctx and not found:
        for m in _IP_BARE_RE.finditer(t):
            found.append((m.start(), _iphone(m.group(1), m.group(2))))
    for m in _S_RE.finditer(t):
        v = _variant(m.group(2))
        found.append((m.start(), f"갤럭시 S{m.group(1)} {v}".strip()))
    if _TRIFOLD_RE.search(t):
        found.append((_TRIFOLD_RE.search(t).start(), "갤럭시 Z 트라이폴드"))
    else:
        for m in _FOLD_RE.finditer(t):
            if m.group(3):
                name = "갤럭시 Z 폴드 스페셜 에디션"
            elif m.group(2):
                name = f"갤럭시 Z 폴드{m.group(2)}"
            else:
                name = "갤럭시 Z 폴드" if m.group(1) else "갤럭시 폴드"
            found.append((m.start(), name))
    for m in _FLIP_RE.finditer(t):
        name = f"갤럭시 Z 플립{m.group(1) or ''}" + (" FE" if m.group(2) else "")
        found.append((m.start(), name))
    for m in _NOTE_RE.finditer(t):
        n = m.group(1).upper()
        name = "갤럭시 노트 FE" if n == "FE" else f"갤럭시 노트{n} {_variant(m.group(2))}".strip()
        found.append((m.start(), name))
    for m in _A_RE.finditer(t):
        found.append((m.start(), f"갤럭시 {m.group(1).upper()}{m.group(2)}"))
    for m in _KR_LINE_RE.finditer(t):
        found.append((m.start(), f"갤럭시 {m.group(1)}{m.group(2)}"))
    out: list[str] = []
    for _, name in sorted(found):
        if name not in out:
            out.append(name)
    # "갤럭시 Z 폴드"와 "갤럭시 Z 폴드5"가 함께 잡히면 구체적인 쪽만 남김
    return [n for n in out if not any(o != n and o.startswith(n) and o[len(n):].strip()[:1].isdigit() for o in out)]


# ------------------------------------------------------------------ 용량
_STORAGE_RE = re.compile(r"(?<![\d.,])(16|32|64|128|256|512)\s*(gb|g|기가바이트|기가|기)?(?![\d,])", re.I)
_TB_RE = re.compile(r"(?<![\d.])([12])\s*(tb|테라|t)(?![a-z])", re.I)
_RAM_CTX = re.compile(r"(램|ram|메모리)\s*[:]?\s*$", re.I)


def find_storage(text: str, require_unit: bool) -> list[str]:
    out = []
    for m in _STORAGE_RE.finditer(text):
        if require_unit and not m.group(2):
            continue
        if _RAM_CTX.search(text[max(0, m.start() - 8) : m.start()]):
            continue
        if not m.group(2) and int(m.group(1)) < 64:
            continue
        val = f"{m.group(1)}GB"
        if val not in out:
            out.append(val)
    for m in _TB_RE.finditer(text):
        val = f"{m.group(1)}TB"
        if val not in out:
            out.append(val)
    return out


# ------------------------------------------------------------------ 색상
_COLORS = [
    # (패턴, 출력) — 긴 것부터
    ("스페이스\\s*그레이|스페이스\\s*그래이|space\\s*gr[ae]y|스그", "스페이스 그레이"),
    ("스페이스\\s*블랙|space\\s*black", "스페이스 블랙"),
    ("블랙\\s*티타늄|black\\s*titanium", "블랙 티타늄"),
    ("화이트\\s*티타늄|white\\s*titanium", "화이트 티타늄"),
    ("내추럴\\s*티타늄|네추럴\\s*티타늄|natural\\s*titanium", "내추럴 티타늄"),
    ("블루\\s*티타늄|blue\\s*titanium", "블루 티타늄"),
    ("데저트\\s*티타늄|desert\\s*titanium", "데저트 티타늄"),
    ("티타늄\\s*그레이", "티타늄 그레이"), ("티타늄\\s*블랙", "티타늄 블랙"), ("티타늄\\s*실버\\s*블루", "티타늄 실버블루"),
    ("티타늄\\s*바이올렛", "티타늄 바이올렛"), ("티타늄\\s*옐로우?", "티타늄 옐로"), ("티타늄\\s*화이트\\s*실버", "티타늄 화이트실버"),
    ("코스믹\\s*오렌지|cosmic\\s*orange", "코스믹 오렌지"), ("딥\\s*블루|deep\\s*blue", "딥 블루"),
    ("미드나이트\\s*그린|미드나잇\\s*그린", "미드나이트 그린"), ("퍼시픽\\s*블루", "퍼시픽 블루"), ("시에라\\s*블루", "시에라 블루"),
    ("알파인\\s*그린", "알파인 그린"), ("딥\\s*퍼플", "딥 퍼플"), ("라이트\\s*골드", "라이트 골드"), ("클라우드\\s*화이트", "클라우드 화이트"),
    ("스카이\\s*블루", "스카이 블루"), ("세이지", "세이지"), ("라벤더", "라벤더"), ("미스트\\s*블루", "미스트 블루"),
    ("팬텀\\s*블랙", "팬텀 블랙"), ("팬텀\\s*화이트", "팬텀 화이트"), ("팬텀\\s*실버", "팬텀 실버"), ("팬텀\\s*바이올렛", "팬텀 바이올렛"),
    ("팬텀\\s*그린", "팬텀 그린"), ("팬텀\\s*그레이", "팬텀 그레이"), ("팬텀\\s*핑크", "팬텀 핑크"),
    ("미스틱\\s*브론즈", "미스틱 브론즈"), ("미스틱\\s*블랙", "미스틱 블랙"), ("오로라\\s*글로우", "오로라 글로우"),
    ("아이시\\s*블루", "아이시 블루"), ("실버\\s*쉐도우|실버\\s*섀도우", "실버 쉐도우"), ("코발트\\s*바이올렛", "코발트 바이올렛"),
    ("앰버\\s*옐로우?", "앰버 옐로"), ("마블\\s*그레이", "마블 그레이"), ("그라파이트|그래파이트|graphite", "그래파이트"),
    ("제트\\s*블랙|jet\\s*black", "제트 블랙"), ("로즈\\s*골드|rose\\s*gold", "로즈 골드"), ("그레이\\s*그린", "그레이 그린"),
    ("크림", "크림"), ("보라퍼플", "퍼플"),
    ("미드나이트|미드나잇|midnight", "미드나이트"), ("스타라이트|스타라잇|starlight", "스타라이트"),
    ("블랙|black|검정색?|검은색", "블랙"), ("화이트|white|흰색|하얀색", "화이트"), ("실버|silver", "실버"),
    ("골드|gold", "골드"), ("블루|blue|파란색", "블루"), ("레드|red|빨간색", "레드"), ("그린|green|초록색?", "그린"),
    ("핑크|pink|분홍색?", "핑크"), ("퍼플|purple|보라색?", "퍼플"), ("옐로우?|yellow|노란색", "옐로"),
    ("코랄|coral", "코랄"), ("네이비|navy", "네이비"), ("민트|mint", "민트"), ("그레이|gr[ae]y|회색", "그레이"),
    ("오렌지|orange", "오렌지"), ("티타늄|titanium", "티타늄"), ("바이올렛|violet", "바이올렛"), ("베이지", "베이지"),
]
_COLOR_RE = [(re.compile(p, re.I), name) for p, name in _COLORS]


def find_colors(text: str) -> list[str]:
    spans: list[tuple[int, int, str]] = []
    for rx, name in _COLOR_RE:
        for m in rx.finditer(text):
            if any(not (m.end() <= s or m.start() >= e) for s, e, _ in spans):
                continue
            spans.append((m.start(), m.end(), name))
    out = []
    for _, _, name in sorted(spans):
        if name not in out:
            out.append(name)
    return out


# ------------------------------------------------------------------ 글 유형 / 카테고리
_BUY_RE = re.compile(r"삽니다|구합니다|구해요|구매합니다|구매해요|매입합니다|구함|구매원해요|찾습니다|찾아요|사요(?!\w)|구매희망")
_SHOP_RE = re.compile(r"대량\s*판매|도매|매입\s*전문|모든\s*휴대폰|중고폰\s*싼곳|중고폰\s*매장|전기종|기종\s*다수|최저가\s*\d", re.I)
_CAT_RULES = [
    ("earbuds", re.compile(r"버즈|buds|에어팟|airpods", re.I)),
    ("watch", re.compile(r"워치|watch", re.I)),
    ("tablet", re.compile(r"아이패드|ipad|갤럭시\s*탭|갤탭|(?<![a-z])tab\s*s?\d|탭\s*s\d", re.I)),
    ("laptop", re.compile(r"맥북|macbook|갤럭시\s*북|갤북", re.I)),
]
_ACC_RE = re.compile(
    r"케이스|필름|강화유리|충전기|케이블|거치대|스트랩|범퍼|그립톡|어댑터|보조\s*배터리|s\s*펜|카드\s*지갑|폰\s*커버|플립\s*커버|맥세이프\s*(?:배터리|카드|지갑)|짐벌|렌즈\s*보호",
    re.I,
)
_ACC_INCL_RE = re.compile(r"(케이스|필름|강화유리|충전기|케이블|s\s*펜)[^\n]{0,6}(포함|증정|드림|드려요|같이|서비스|함께|\+)", re.I)
_RENTAL_RE = re.compile(r"대여|렌탈|렌트(?!카)")
_BOX_ONLY_RE = re.compile(r"빈\s*박스|공\s*박스|박스\s*만|박스\s*(?:및|와|랑|\+)|(?:^|\s)박스\s*(?:판매|팝니다)?\s*$|박스\s*\(?\s*(?:구성품|설명서)")
_PARTS_RE = re.compile(r"메인\s*보드|액정\s*(?:단품|만|부품)|부품\s*(?:판매|팝니다|단품)|후면\s*유리|하우징|배터리\s*단품|카메라\s*모듈", re.I)


# ------------------------------------------------------------------ 상태 (시세 산정용 추정)
_NEW_RE = re.compile(r"미개봉|단순\s*개봉|새\s*상품(?!\s*급)|새\s*제품(?!\s*급)|미사용(?!\s*급)|새\s*폰(?!\s*급)")
_BROKEN_RE = re.compile(
    r"부품용|고장|파손|침수|먹통|벽돌|불량|깨짐|깨져|깨진|금감|금\s*간|안\s*켜|전원\s*(?:안|불량)|"
    r"(?:액정|화면|디스플레이)\s*(?:나감|줄|멍|번인)|잔상\s*(?:심|있)|번인\s*(?:심|있)|터치\s*(?:안|불량)|페이스\s*아이디\s*(?:안|불)"
)
_NEG_RE = re.compile(r"^.{0,8}?(?:없|x\b|X\b|아님|아니|무\s|0)")


def _has_unnegated(rx: re.Pattern, text: str) -> bool:
    for m in rx.finditer(text):
        before = text[max(0, m.start() - 1) : m.start()]
        if before == "무":  # 무잔상, 무파손
            continue
        if _NEG_RE.match(text[m.end() : m.end() + 10]):
            continue
        return True
    return False


def detect_condition(title: str, body: str) -> str:
    """'new'(미개봉·단순개봉) | 'broken'(고장·파손·부품용) | 'used'. 키워드 기반 추정이다."""
    t, b = title or "", (body or "")[:400]
    if _has_unnegated(_BROKEN_RE, t) or _has_unnegated(re.compile(r"부품용|고장|파손|침수|먹통|벽돌|안\s*켜"), b):
        return "broken"
    if _NEW_RE.search(t) or re.search(r"미개봉|단순\s*개봉", b):
        return "new"
    return "used"


def classify(title: str, body: str, models: list[str], n_body_models: int) -> tuple[str, str]:
    t = title.lower()
    post_type = "sell"
    if _BUY_RE.search(t):
        post_type = "buy"
    if len(models) >= 4 or _SHOP_RE.search(t) or (n_body_models >= 7 and _SHOP_RE.search(body)):
        post_type = "shop_ad"

    if _RENTAL_RE.search(t):
        post_type = "other"
    category = None
    if _BOX_ONLY_RE.search(t) and not re.search(r"풀\s*박|박스\s*(?:포함|있|o\b)", t):
        category = "accessory"
    for cat, rx in ([] if category else _CAT_RULES):
        if rx.search(t):
            category = cat
            break
    if category is None and _PARTS_RE.search(t):
        category = "parts"
    if category is None and _ACC_RE.search(t) and not _ACC_INCL_RE.search(t) and not find_storage(t, require_unit=True):
        category = "accessory"
    if category is None:
        category = "phone" if (models or re.search(r"폰|공기계|휴대폰|스마트폰", t)) else "other"
    return post_type, category


def extract(title: str, body: str) -> dict:
    text_all = f"{title}\n{body}".lower()
    iphone_ctx = bool(re.search(r"아이폰|iphone|애플|apple", text_all)) and not re.search(r"갤럭시|galaxy|삼성", title.lower())

    models = find_models(title, iphone_ctx)
    body_models = find_models(body, iphone_ctx)
    if not models:
        models = body_models[:1]

    post_type, category = classify(title, body, models, len(body_models))
    if post_type == "shop_ad":
        models = []

    storage = find_storage(title, require_unit=False) or find_storage(body[:300], require_unit=True)[:1]
    color = find_colors(title) or find_colors(body[:300])[:1]
    if category not in ("phone",):
        storage = storage if category in ("tablet", "laptop") else []
    return {
        "post_type": post_type,
        "category": category,
        "models": models,
        "storage": storage,
        "color": color,
    }


if __name__ == "__main__":
    import sys

    print(extract(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
