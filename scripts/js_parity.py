"""JS 정규화기(web/normalizer)가 Python 판과 같은 결과를 내는지 대조한다.

    .venv-train/bin/python scripts/js_parity.py            # Python 결과 → 임시 파일, node scripts/js_parity.mjs 로 JS 결과와 비교

대상 (매물 약 5만 2천 건 + 문자열 사례)
- 규칙: extract, detect_condition, build_spec(규칙만)
- 모델 출력 경로: parse_target → ground → build_spec (+ 유형·상태는 모델 값). eval1k(최종 Q4)와 후보 풀(파일럿) 예측
- LLM 라벨 경로: build_spec(Haiku 라벨) — 다양한 모델명 표기로 카탈로그 snap 을 시험
- 카탈로그·공통: snap, lookup_code, parse, official_color, norm_model, norm_color, norm_storage (실제 값 + 변형)
- 입력 텍스트: text_of + NFC (학습 때 HF 토크나이저가 한 정규화)
"""

from __future__ import annotations

import glob
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
from normalizer.catalog import get_catalog, parse  # noqa: E402
from normalizer.common import norm_color, norm_model, norm_storage  # noqa: E402
from normalizer.pipeline import build_spec  # noqa: E402
from normalizer.rules import detect_condition, extract  # noqa: E402

from distill_data import load, parse_target, text_of  # noqa: E402
from ground import color_grounded, ground, grounded, storage_grounded  # noqa: E402

JS_DIR = LAB / "web/normalizer"


def spec_from_output(title: str, body: str, raw: str) -> dict:
    """model.js 의 specFromOutput 과 같은 조합 (평가에서 잰 경로)."""
    pred = parse_target(raw)
    g, changed = ground(pred, title, body)
    return {**build_spec(title, body, g, rule_fallback=False), "post_type": g["post_type"], "condition": g["condition"], "source": "model",
            "raw": raw.strip(), "grounded_fields_replaced": changed}


def variants(name: str) -> list[str]:
    return [name, name.lower(), name.upper(), name.replace(" ", ""), f"삼성 {name}", f"애플 {name}", f"{name} 5G",
            f"{name} 자급제", f" {name} ", name.replace("갤럭시", "galaxy").replace("아이폰", "iphone")]


def main() -> None:
    cases = []
    add = lambda kind, inp, out: cases.append({"kind": kind, "in": inp, "out": out})  # noqa: E731

    listings = {}
    for n in ("eval1k_input.jsonl", "train10k_input.jsonl", "pool_input.jsonl"):
        for r in load(LAB / "data" / n):
            listings.setdefault(r["uid"], r)
    print(f"매물 {len(listings)}건")
    for u, r in listings.items():
        t, b = r["title"], r.get("body") or ""
        add("extract", [t, b], extract(t, b))
        add("condition", [t, b], detect_condition(t, b))
        add("spec_rules", [t, b], build_spec(t, b, None))
        add("text_of", [t, b], unicodedata.normalize("NFC", text_of({"title": t, "body": b})))

    raws = {}
    for p in ("preds/q08_final_lora_q4.jsonl", "preds/pool_qwen.jsonl"):
        for r in load(LAB / p):
            raws.setdefault(r["uid"], r["raw"])
    for u, raw in raws.items():
        r = listings[u]
        add("spec_model", [r["title"], r.get("body") or "", raw], spec_from_output(r["title"], r.get("body") or "", raw))
        add("parse_target", [raw], parse_target(raw))

    labels = []
    for p in sorted(glob.glob(str(LAB / "data/*_haiku_*.jsonl"))) + sorted(glob.glob(str(LAB / "data/train_fix_[0-9]*.jsonl"))):
        try:
            labels += load(p)
        except json.JSONDecodeError:
            continue
    names, colors, storages = set(), set(), set()
    seen = set()
    for lab in labels:
        u = lab.get("uid")
        if u not in listings or u in seen or not isinstance(lab.get("models"), list):
            continue
        seen.add(u)
        llm = {k: lab.get(k) for k in ("post_type", "category", "models", "storage", "color")}
        if not all(isinstance(llm[k], list) for k in ("models", "storage", "color")):
            continue
        r = listings[u]
        add("spec_llm", [r["title"], r.get("body") or "", llm], build_spec(r["title"], r.get("body") or "", llm))
        names.update(x for x in llm["models"] if isinstance(x, str))
        colors.update(x for x in llm["color"] if isinstance(x, str))
        storages.update(x for x in llm["storage"] if isinstance(x, str))

    cat = get_catalog()
    for m in cat.models.values():
        names.add(m.name)
        for c in m.colors:
            colors.update([c.get("name") or "", *(c.get("aliases") or []), c.get("en") or ""])
    names |= {v for n in list(names) for v in variants(n)}
    names |= {f"SM-{c}" for c in cat._code} | set(cat._code) | {f"갤럭시 {c}" for c in cat._code}
    for n in sorted(names):
        add("snap", [n], cat.snap(n))
        add("lookup_code", [n], cat.lookup_code(n))
        add("parse", [n], parse(n))
        add("norm_model", [n], norm_model(n))
        add("grounded", [n, n.lower()], grounded(n, n.lower()))
    for c in sorted(colors):
        add("norm_color", [c], norm_color(c))
        add("color_grounded", [c, "색상 " + c], color_grounded(c, "색상 " + c))
    for s in sorted(storages | {"128", "1", "2T", "１２８GB", "256기가", "1테라", " 512 gb ", "64G", "12345678901234567890"}):
        add("norm_storage", [s], norm_storage(s))
        add("storage_grounded", [s, "용량 " + s], storage_grounded(s, "용량 " + s))
    for m in [m for m in cat.models.values() if m.colors][:300]:
        for c in m.colors[:4]:
            for raw in (c.get("name") or "", *(c.get("aliases") or [])[:2], "블랙", "화이트"):
                add("official_color", [m.name, raw], cat.official_color(m.name, raw))

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/js_parity_cases.jsonl")
    out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")
    print(f"사례 {len(cases)}개 → {out}")
    res = subprocess.run(["node", str(LAB / "scripts/js_parity.mjs"), str(out)], capture_output=True, text=True)
    print(res.stdout, res.stderr)
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
