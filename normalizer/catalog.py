"""아이폰/갤럭시 폰 카탈로그.

- 모델명 검증과 정식명 맞추기(snap): 별칭·모델 코드(SM-A155N, A155)·흔한 오기("17 에어", "SE 1세대")를 정식명으로 바꾼다.
- 정식명을 검색 토큰 {브랜드, 라인, 세대, 변형}으로 분해한다(parse).
- 모델별 공식 색상으로 정규화한다(official_color).

데이터는 data/catalog_*.json 이 우선이고, 없는 모델은 내장 목록(_BUILTIN)으로 채운다.
신모델 대응은 JSON에 항목을 하나 추가하는 것으로 끝난다(재학습 불필요).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .common import norm_color, norm_model

DATA_DIR = Path(__file__).parent / "data"

# ---------------------------------------------------------------- 내장 목록 (JSON 이 없을 때의 최소 집합)
_IPHONE = [
    "3G", "3GS", "4", "4S", "5", "5C", "5S", "6", "6 플러스", "6S", "6S 플러스", "SE", "7", "7 플러스",
    "8", "8 플러스", "X", "XS", "XS 맥스", "XR", "11", "11 프로", "11 프로 맥스", "SE 2세대",
    "12 미니", "12", "12 프로", "12 프로 맥스", "13 미니", "13", "13 프로", "13 프로 맥스", "SE 3세대",
    "14", "14 플러스", "14 프로", "14 프로 맥스", "15", "15 플러스", "15 프로", "15 프로 맥스",
    "16", "16 플러스", "16 프로", "16 프로 맥스", "16e", "17", "에어", "17 프로", "17 프로 맥스", "17e",
    "18 프로", "18 프로 맥스",
]
_GALAXY = (
    ["S2", "S3", "S4", "S5", "S6", "S6 엣지", "S6 엣지 플러스", "S7", "S7 엣지", "S8", "S8 플러스",
     "S9", "S9 플러스", "S10", "S10e", "S10 플러스", "S10 5G", "S20 FE", "S21 FE", "S23 FE", "S24 FE", "S25 FE",
     "S25 엣지"]
    + [f"S{n}{v}" for n in range(20, 27) for v in ("", " 플러스", " 울트라")]
    + ["노트", "노트2", "노트3", "노트4", "노트5", "노트 FE", "노트8", "노트9", "노트10", "노트10 플러스",
       "노트20", "노트20 울트라"]
    + ["폴드", "Z 폴드", "Z 플립", "Z 폴드 스페셜 에디션", "Z 트라이폴드", "Z 플립7 FE"]
    + [f"Z 폴드{n}" for n in range(2, 9)]
    + [f"Z 플립{n}" for n in range(3, 9)]
)
_BUILTIN = ["아이폰"] + [f"아이폰 {m}" for m in _IPHONE] + ["갤럭시 S"] + [f"갤럭시 {m}" for m in _GALAXY]
_LONGTAIL_RE = re.compile(r"^갤럭시(?:[amj]\d{1,2}s?|퀀텀\d?|와이드\d?|점프\d?|버디\d?|a퀀텀)$", re.I)


@dataclass
class Model:
    name: str
    brand: str | None = None
    line: str | None = None
    gen: str | None = None
    variant: str | None = None
    en: str | None = None
    release: str | None = None
    storage: list[str] = field(default_factory=list)
    colors: list[dict] = field(default_factory=list)  # [{"name":..., "aliases":[...]}]
    verified: bool = True

    @property
    def slug(self) -> str:
        base = self.en or self.name
        s = re.sub(r"[^0-9a-zA-Z가-힣]+", "-", base.lower()).strip("-")
        return s


# ---------------------------------------------------------------- 표기 보정 (snap 전에 적용)
_PRE_FIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:삼성|samsung|애플|apple)\s*", re.I), ""),
    (re.compile(r"\s*(?:5g|lte|자급제|공기계|일반(?:모델)?|기본(?:형|모델)?)\s*$", re.I), ""),
    (re.compile(r"아이폰\s*(?:17\s*에어|에어\s*17|17\s*air)", re.I), "아이폰 에어"),
    (re.compile(r"아이폰\s*se\s*(?:1|1세대|2016)\s*$", re.I), "아이폰 SE"),
    (re.compile(r"아이폰\s*se\s*(?:2|2020)\s*$", re.I), "아이폰 SE 2세대"),
    (re.compile(r"아이폰\s*se\s*(?:3|2022)\s*$", re.I), "아이폰 SE 3세대"),
    (re.compile(r"아이폰\s*미니\s*(\d+)", re.I), r"아이폰 \1 미니"),
    (re.compile(r"갤럭시\s*(폴드|플립)\s*(\d)", re.I), r"갤럭시 Z \1\2"),
    (re.compile(r"갤럭시\s*z\s*(폴드|플립)\s+(\d)", re.I), r"갤럭시 Z \1\2"),
]


def _pre_fix(name: str) -> str:
    s = str(name or "").strip()
    for rx, rep in _PRE_FIXES:
        s = rx.sub(rep, s).strip()
    return s


class Catalog:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.models: dict[str, Model] = {}  # norm_model(name) -> Model
        self._alias: dict[str, str] = {}  # norm alias -> norm name
        self._code: dict[str, str] = {}  # 코드(대문자, SM- 제거) -> norm name
        for path in sorted(data_dir.glob("catalog_*.json")):
            self._load_json(path)
        for name in _BUILTIN:
            key = norm_model(name)
            if key not in self.models:
                self.models[key] = Model(name=name, **_parse_name(name))

    # -------------------------------------------------- 로딩
    def _load_json(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        brand = data.get("brand")
        for m in data.get("models", []):
            name = m.get("name")
            if not name:
                continue
            key = norm_model(name)
            parsed = _parse_name(name)
            self.models[key] = Model(
                name=name,
                brand=brand or parsed["brand"],
                line=m.get("line") or parsed["line"],
                gen=m.get("gen") if m.get("gen") is not None else parsed["gen"],
                variant=m.get("variant") if m.get("variant") is not None else parsed["variant"],
                en=m.get("en"),
                release=m.get("release"),
                storage=list(m.get("storage") or []),
                colors=list(m.get("colors") or []),
                verified=bool(m.get("verified", True)),
            )
            for a in m.get("aliases") or []:
                self._alias.setdefault(norm_model(_pre_fix(a)), key)
            for c in m.get("codes") or []:
                code = _norm_code(c)
                if code:
                    self._code.setdefault(code, key)
                    self._code.setdefault(code.rstrip("NSKL"), key)  # SM-A155N → A155

    # -------------------------------------------------- 조회
    def get(self, name: str) -> Model | None:
        return self.models.get(norm_model(name))

    def snap(self, name: str) -> str | None:
        """정식명. 모르면 None (롱테일 갤럭시 A/퀀텀 등은 패턴이 맞으면 그대로 허용)."""
        if not name:
            return None
        for cand in (name, _pre_fix(name)):
            key = norm_model(cand)
            if key in self.models:
                return self.models[key].name
            if key in self._alias:
                return self.models[self._alias[key]].name
        code = self.lookup_code(name)
        if code:
            return code
        fixed = _pre_fix(name)
        if _LONGTAIL_RE.match(norm_model(fixed)):
            return fixed
        return None

    def lookup_code(self, text: str) -> str | None:
        """'SM-A155N', 'A155', '갤럭시 A155' 처럼 모델 코드가 들어 있으면 정식명."""
        for m in re.finditer(r"(?:sm-?)?([afgjmnsx])\s?(\d{3,4})([a-z]{0,2})", str(text or ""), re.I):
            code = (m.group(1) + m.group(2)).upper()
            if code in self._code:
                return self.models[self._code[code]].name
        return None

    def is_known(self, name: str) -> bool:
        return self.snap(name) is not None

    def official_color(self, model_name: str, raw_color: str) -> str | None:
        """판매자가 적은 색상 → 해당 모델의 공식 색상명 (못 찾으면 None)."""
        m = self.get(model_name)
        if not m or not m.colors or not raw_color:
            return None
        target = norm_color(raw_color)
        for c in m.colors:
            names = [c.get("name", "")] + list(c.get("aliases") or []) + ([c["en"]] if c.get("en") else [])
            if any(norm_color(n) == target for n in names if n):
                return c.get("name")
        return None


def _norm_code(code: str) -> str:
    c = re.sub(r"[\s-]", "", str(code or "")).upper()
    return c[2:] if c.startswith("SM") else c


_PARSE_RES = [
    (re.compile(r"^아이폰\s*(SE)(?:\s*(\d)세대)?$"), "Apple", "아이폰"),
    (re.compile(r"^아이폰\s*(에어)$"), "Apple", "아이폰"),
    (re.compile(r"^아이폰\s*(\d{1,2}e?|X[SR]?|[3-8][GSC]{0,2})\s*(.*)$"), "Apple", "아이폰"),
    (re.compile(r"^갤럭시\s*S(\d{1,2}e?)\s*(.*)$"), "Samsung", "갤럭시 S"),
    (re.compile(r"^갤럭시\s*노트\s*(\d{0,2})\s*(.*)$"), "Samsung", "갤럭시 노트"),
    (re.compile(r"^갤럭시\s*Z\s*트라이폴드$"), "Samsung", "갤럭시 Z 트라이폴드"),
    (re.compile(r"^갤럭시\s*(?:Z\s*)?폴드\s*(\d?)\s*(.*)$"), "Samsung", "갤럭시 Z 폴드"),
    (re.compile(r"^갤럭시\s*(?:Z\s*)?플립\s*(\d?)\s*(.*)$"), "Samsung", "갤럭시 Z 플립"),
    (re.compile(r"^갤럭시\s*([AMJ])(\d{1,3}s?)\s*(.*)$"), "Samsung", None),
    (re.compile(r"^갤럭시\s*(퀀텀|와이드|점프|버디)\s*(\d?)\s*(.*)$"), "Samsung", None),
]


def _parse_name(name: str) -> dict:
    m = str(name or "").strip()
    for rx, brand, line in _PARSE_RES:
        mm = rx.match(m)
        if not mm:
            continue
        g = mm.groups()
        if line == "갤럭시 Z 트라이폴드":
            return {"brand": brand, "line": line, "gen": "", "variant": ""}
        if line is None:
            return {"brand": brand, "line": f"갤럭시 {g[0]}", "gen": g[1], "variant": g[2].strip()}
        if g[0] == "SE":
            return {"brand": brand, "line": line, "gen": "SE", "variant": f"{g[1]}세대" if g[1] else ""}
        if g[0] == "에어":
            return {"brand": brand, "line": line, "gen": "", "variant": "에어"}
        return {"brand": brand, "line": line, "gen": g[0], "variant": (g[1] if len(g) > 1 else "").strip()}
    return {"brand": None, "line": None, "gen": None, "variant": None}


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    return Catalog()


def parse(name: str) -> dict:
    m = get_catalog().get(name)
    if m:
        return {"brand": m.brand, "line": m.line, "gen": m.gen, "variant": m.variant}
    return _parse_name(name)


def snap(name: str) -> str | None:
    return get_catalog().snap(name)


def is_known(name: str) -> bool:
    return get_catalog().is_known(name)


def search_tokens(models: list[str], storage: list[str], colors: list[str]) -> list[str]:
    toks: list[str] = []
    for m in models:
        p = parse(m)
        toks += [m] + [v for v in (p["line"], p["gen"], p["variant"]) if v]
    toks += list(storage) + list(colors)
    out: list[str] = []
    for t in toks:
        if t and t not in out:
            out.append(t)
    return out
