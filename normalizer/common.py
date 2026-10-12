"""공통: 정규화(비교용), 색상 별칭, JSON 스키마."""

from __future__ import annotations

import json
import re
from pathlib import Path

POST_TYPES = ["sell", "buy", "shop_ad", "other"]
CATEGORIES = ["phone", "tablet", "watch", "earbuds", "laptop", "accessory", "parts", "other"]

# 비교용 영→한 토큰 (예측·정답 양쪽에 동일하게 적용)
_MODEL_TOKENS = [
    (r"iphone|아이뻰|아이퐁", "아이폰"),
    (r"galaxy|겔럭시|갤(?!럭시)", "갤럭시"),
    (r"promax|pro\s*max|프맥", "프로맥스"),
    (r"pro", "프로"),
    (r"max", "맥스"),
    (r"mini", "미니"),
    (r"plus|\+", "플러스"),
    (r"ultra", "울트라"),
    (r"edge", "엣지"),
    (r"fold", "폴드"),
    (r"flip", "플립"),
    (r"note", "노트"),
    (r"air", "에어"),
    (r"갤럭시갤럭시", "갤럭시"),
]


def norm_model(s: str) -> str:
    s = str(s or "").lower()
    for pat, rep in _MODEL_TOKENS:
        s = re.sub(pat, rep, s)
    return re.sub(r"[\s\-_()]", "", s)


COLOR_ALIASES = {
    "흰색": "화이트", "하얀색": "화이트", "white": "화이트", "화이트색": "화이트",
    "검정": "블랙", "검정색": "블랙", "검은색": "블랙", "black": "블랙", "블랙색": "블랙",
    "스그": "스페이스그레이", "spacegray": "스페이스그레이", "spacegrey": "스페이스그레이", "스페이스그래이": "스페이스그레이",
    "스블": "스페이스블랙", "미드나잇": "미드나이트", "스타라잇": "스타라이트",
    "silver": "실버", "gold": "골드", "blue": "블루", "red": "레드", "green": "그린",
    "pink": "핑크", "purple": "퍼플", "yellow": "옐로", "옐로우": "옐로", "그래이": "그레이",
    "gray": "그레이", "grey": "그레이", "navy": "네이비", "레드색": "레드", "빨강": "레드",
    "productred": "레드", "(product)red": "레드", "프로덕트레드": "레드",
    "로즈골드": "로즈골드", "rosegold": "로즈골드", "자급제": "",
    "네추럴티타늄": "내추럴티타늄", "옐로우": "옐로", "은색": "실버", "회색": "그레이", "초록": "그린", "보라": "퍼플",
}


def norm_color(s: str) -> str:
    s = re.sub(r"[\s\-_]", "", str(s or "").lower())
    s = COLOR_ALIASES.get(s, s)
    s = re.sub(r"색$", "", s) if len(s) > 2 else s
    return COLOR_ALIASES.get(s, s)


def norm_storage(s: str) -> str:
    s = re.sub(r"\s", "", str(s or "").upper())
    m = re.match(r"(\d+)(GB|G|기가|TB|T|테라)?$", s)
    if not m:
        return s
    n, unit = int(m.group(1)), (m.group(2) or "GB")
    if unit in ("TB", "T", "테라") or n in (1, 2):
        return f"{n}TB"
    return f"{n}GB"


def norm_record(r: dict) -> dict:
    return {
        "post_type": r.get("post_type"),
        "category": r.get("category"),
        "models": sorted({norm_model(m) for m in (r.get("models") or []) if m}),
        "storage": sorted({norm_storage(m) for m in (r.get("storage") or []) if m}),
        "color": sorted({c for c in (norm_color(x) for x in (r.get("color") or [])) if c}),
    }


JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "post_type": {"type": "string", "enum": POST_TYPES},
        "category": {"type": "string", "enum": CATEGORIES},
        "models": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "storage": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "color": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
    },
    "required": ["post_type", "category", "models", "storage", "color"],
    "additionalProperties": False,
}


def load_jsonl(path: str | Path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def save_jsonl(path: str | Path, rows: list[dict]) -> None:
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
