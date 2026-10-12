"""매물 1건 → 검색·시세용 규격(spec).

규칙 추출(항상) + LLM 추출(서버가 있으면) + 카탈로그 검증을 결합한다. 실험 근거는
docs/REPORT.md (새 테스트셋 3필드 일치율: 규칙만 75.6%, 결합 91.6%).

- post_type: 규칙 값 (실험에서 규칙이 더 정확)
- category / models / storage / color: LLM 값, LLM 이 없으면 규칙 값
- models: 카탈로그 정식명으로 맞춤. 모르는 이름이면 규칙 값 → 모델 코드 → 그래도 없으면 검토 필요
  (rule_fallback=False 면 모르는 이름도 그대로 두고 검토 필요만 표시. 근거 검사를 거친 소형 모델 출력용 —
   묶음 판매글의 애플워치 같은 이름을 규칙 값으로 바꾸면 단일 모델 글로 보여 시세에 섞인다)
- 규칙과 LLM 의 모델·용량이 다르면 검토 필요 (불일치 13% 구간 정확도 54~60%, 일치 구간 95~96%)
"""

from __future__ import annotations

from .catalog import get_catalog, parse, search_tokens
from .common import norm_model, norm_storage
from .rules import detect_condition, extract

NORMALIZER_VERSION = "2026-10-08.3"


def _same(a: list[str], b: list[str], norm) -> bool:
    return sorted({norm(x) for x in a or []}) == sorted({norm(x) for x in b or []})


def _canon(models: list[str]) -> list[str]:
    """비교용: 카탈로그 정식명으로 맞춘 뒤 비교 (표기 차이를 불일치로 보지 않게)."""
    cat = get_catalog()
    return [cat.snap(m) or m for m in models or []]


def build_spec(title: str, body: str, llm_out: dict | None, *, rule_fallback: bool = True) -> dict:
    cat = get_catalog()
    rule = extract(title, body)
    src = llm_out if llm_out and llm_out.get("post_type") else None
    p = {k: (src.get(k, rule[k]) if src else rule[k]) for k in ("category", "models", "storage", "color")}
    p["post_type"] = rule["post_type"]

    reasons: list[str] = []
    models: list[str] = []
    for m in p["models"] or []:
        s = cat.snap(m)
        if s is None and p["category"] == "phone":
            alt = [cat.snap(x) for x in rule["models"]] if rule_fallback else []
            if alt and all(alt):
                models = [a for a in alt if a]
                break
            code = cat.lookup_code(f"{title} {body[:200]}") if rule_fallback else None
            if code:
                models = [code]
                break
            reasons.append(f"카탈로그에 없는 모델명: {m}")
        models.append(s or m)
    models = list(dict.fromkeys(models))

    if src and p["category"] == "phone" and p["post_type"] in ("sell", "buy"):
        if not _same(_canon(rule["models"]), _canon(src.get("models") or []), norm_model):
            reasons.append("규칙·LLM 모델 불일치")
        elif not _same(rule["storage"], src.get("storage") or [], norm_storage):
            reasons.append("규칙·LLM 용량 불일치")

    storage = [norm_storage(s) for s in p["storage"] or []]
    colors = list(p["color"] or [])
    model = models[0] if models else None
    parsed = parse(model) if model else {"brand": None, "line": None, "gen": None, "variant": None}
    return {
        "post_type": p["post_type"],
        "category": p["category"],
        "models": models,
        "model": model,
        "brand": parsed["brand"],
        "line": parsed["line"],
        "gen": parsed["gen"],
        "variant": parsed["variant"],
        "storages": storage,
        "storage": storage[0] if len(storage) == 1 else None,
        "colors": colors,
        "color": colors[0] if len(colors) == 1 else None,
        "color_official": cat.official_color(model, colors[0]) if model and len(colors) == 1 else None,
        "condition": detect_condition(title, body),
        "needs_review": bool(reasons),
        "review_reason": "; ".join(reasons) or None,
        "source": "llm" if src else "rules",
        "tokens": search_tokens(models, storage, colors),
        "normalizer_version": NORMALIZER_VERSION,
    }
