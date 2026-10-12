"""생성 결과의 모델명 근거 확인: 원문에 없는 세대 숫자를 낸 모델명은 믿지 않는다.

    .venv-train/bin/python scripts/ground.py preds/q08_final_lora.jsonl     # → preds/q08_final_lora_g.jsonl

소형 생성 모델은 처음 보는 세대(S26)를 학습한 세대(S25)로 바꿔 쓰는 경향이 있다. 그래서
- 예측 모델명의 숫자(아이폰 15 → 15, 갤럭시 S24 울트라 → 24, 폴드5 → 5)가 원문에 숫자로 없으면 근거가 없다고 본다.
- 숫자가 없는 이름(아이폰 에어, 아이폰 듀오)도 원문에 이름의 핵심 단어가 없으면 근거가 없다고 본다.
- 근거 없는 모델명이 하나라도 있으면 그 글의 모델명은 규칙·카탈로그 결과로 바꾼다. 규칙은 원문에서 뽑으므로 늘 근거가 있다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
from normalizer.pipeline import build_spec  # noqa: E402

_GENERIC = {"아이폰", "갤럭시", "z", "s", "a", "프로", "맥스", "플러스", "미니", "울트라", "엣지", "fe", "노트", "폴드", "플립",
            "세대", "퀀텀", "와이드", "점프", "버디"}
_ALIAS = {"에어": ("에어", "air"), "듀오": ("듀오", "duo", "폴드"), "se": ("se", "에스이")}


def grounded(model: str, text: str) -> bool:
    t = text.lower()
    nums = re.findall(r"\d+", model)
    if nums:
        return all(re.search(rf"(?<!\d){n}(?!\d)", t) for n in nums)
    words = [w for w in re.split(r"\s+", model.lower()) if w and w not in _GENERIC]
    return all(any(a in t for a in _ALIAS.get(w, (w,))) for w in words)


_COLOR_ALIAS = {
    "블랙": ("black", "검정", "검은", "블랙"), "화이트": ("white", "흰", "하얀", "화이트"), "실버": ("silver",),
    "골드": ("gold",), "블루": ("blue", "파랑", "파란"), "그레이": ("gray", "grey", "회색", "그레이"),
    "핑크": ("pink", "분홍"), "퍼플": ("purple", "보라"), "그린": ("green", "초록", "녹색"), "레드": ("red", "빨강", "빨간"),
    "옐로우": ("yellow", "노랑", "노란"), "스페이스그레이": ("스그", "spacegray", "spacegrey"), "그래파이트": ("graphite",),
    "티타늄": ("titanium",), "미드나이트": ("midnight",), "스타라이트": ("starlight",), "네이비": ("navy",),
    "크림": ("cream",), "라벤더": ("lavender",), "민트": ("mint",), "버건디": ("burgundy",), "바이올렛": ("violet",),
}


def color_grounded(color: str, text: str) -> bool:
    c, t = re.sub(r"\s", "", color.lower()), re.sub(r"\s", "", text.lower())
    if c in t:
        return True
    # 합성 색상(스카이 블루, 블랙 티타늄)은 구성 단어가 모두 원문에 있으면 인정
    parts = [p for p in re.split(r"\s+", color.lower()) if p]
    return all(p in t or any(a in t for a in _COLOR_ALIAS.get(p, ())) for p in parts) or \
        any(a in t for a in _COLOR_ALIAS.get(c, ()))


def storage_grounded(s: str, text: str) -> bool:
    m = re.match(r"(\d+)\s*(GB|TB)", s.upper())
    if not m:
        return False
    n, unit, t = m.group(1), m.group(2), text.lower()
    if unit == "TB":
        return bool(re.search(rf"(?<!\d){n}\s*(?:t|tb|테라|tera)", t) or (n == "1" and "1024" in t))
    return bool(re.search(rf"(?<!\d){n}(?!\d)", t))


def ground(pred: dict, title: str, body: str) -> tuple[dict, bool]:
    """모델명·용량·색상 각각, 원문 근거가 없는 값이 있으면 그 필드를 규칙 결과로 바꾼다."""
    text = f"{title}\n{body}"
    checks = {
        "models": lambda v: grounded(v, text),
        "storage": lambda v: storage_grounded(v, text),
        "color": lambda v: color_grounded(v, text),
    }
    bad = [k for k, ok in checks.items() if not all(ok(v) for v in pred.get(k) or [])]
    if not bad:
        return pred, False
    rules = build_spec(title, body, None)
    from_rules = {"models": rules["models"], "storage": rules["storages"], "color": rules["colors"]}
    return {**pred, **{k: from_rules[k] for k in bad}}, True


def main(path: str) -> None:
    src = {}
    for name in ("eval1k_input.jsonl", "train10k_input.jsonl"):
        src.update({r["uid"]: r for r in map(json.loads, (LAB / "data" / name).read_text(encoding="utf-8").splitlines())})
    p = Path(path)
    rows, fixed = [], 0
    for line in p.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        s = src[r["uid"]]
        g, changed = ground(r, s["title"], s.get("body") or "")
        fixed += changed
        rows.append(g)
    out = p.with_name(p.stem + "_g.jsonl")
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{p.name}: {len(rows)}건 중 {fixed}건 모델명을 규칙 결과로 교체 → {out.name}")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        main(a)
