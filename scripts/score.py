"""평가셋 1,000건(eval1k) 채점. 정답은 Opus 라벨(data/eval1k_labels_*.jsonl, LABELING_GUIDE v1.1).

    .venv-train/bin/python scripts/score.py q08_final_lora_web q08_final_lora_q4   # preds/{이름}_g.jsonl (근거 검사 후)
    .venv-train/bin/python scripts/score.py --subset new q08_final_lora_q4          # 정답 모델이 최신 시리즈인 글만

규칙과 Haiku(교사) 결과는 늘 함께 채점한다. 표본은 플랫폼별 고정 할당(당근 600, 번개장터 250, 중고나라 150)이라
전체 수치는 플랫폼별 수집량(PLATFORM_WEIGHTS)으로 가중한다.

지표 (판매 폰 글 기준)
- 시세 버킷: 판매·폰으로 분류하고 모델과 용량까지 맞힌 비율. 시세표 칸에 제대로 들어가는지.
- 오염: 시세에 들어간 글(판매·폰·단일 모델) 중 실제로는 다른 글이거나 모델이 틀린 비율.
- 3필드: 모델·용량·색상 완전 일치.
- 칸·칸오염: 시세 칸은 실제로 모델 + 용량 + 상태(미개봉·중고·하자) 단위로 나뉜다. 상태까지 맞아야 제 칸에 들어간 것으로
  보고, 상태가 틀린 글도 오염으로 센다. 서비스에 가장 가까운 지표라 모델 선택은 칸오염을 먼저 본다.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
from normalizer.catalog import get_catalog  # noqa: E402
from normalizer.common import norm_color, norm_model, norm_storage  # noqa: E402
from normalizer.pipeline import build_spec  # noqa: E402

FIELDS = ("post_type", "category", "models", "storage", "color", "condition")
KEY = ("post_type", "category", "models", "storage", "condition")  # 시세에 영향을 주는 필드
PLATFORM_NAMES = {"danggeun": "당근", "bunjang": "번개장터", "joonggonara": "중고나라"}
# 서비스 DB 의 플랫폼별 매물 수 (2026-10-12 수집 종료 시점)
PLATFORM_WEIGHTS = {"danggeun": 105878, "bunjang": 19858, "joonggonara": 3789}
NEW_MODELS = re.compile(r"아이폰\s*18|아이폰\s*듀오|갤럭시\s*S26|폴드\s*8|플립\s*8")


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_parts(stem: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted((LAB / "data").glob(f"{stem}_*.jsonl")):
        if p.stem.split("_")[-1].isdigit():
            out.update({r["uid"]: r for r in load(p)})
    return out


def canon(r: dict) -> dict:
    cat = get_catalog()
    return {
        "post_type": r.get("post_type"),
        "category": r.get("category"),
        "models": sorted({norm_model(cat.snap(m) or m) for m in r.get("models") or [] if m}),
        "storage": sorted({norm_storage(s) for s in r.get("storage") or [] if s}),
        "color": sorted({c for c in (norm_color(x) for x in r.get("color") or []) if c}),
        "condition": r.get("condition") or "used",
    }


def rules_pred(inp: dict) -> dict:
    s = build_spec(inp["title"], inp["body"], None)
    return {"post_type": s["post_type"], "category": s["category"], "models": s["models"], "storage": s["storages"],
            "color": s["colors"], "condition": s["condition"]}


def wilson(k: int, n: int) -> tuple[float, float]:
    if not n:
        return 0.0, 0.0
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def sell_phone(c: dict) -> bool:
    return c["post_type"] == "sell" and c["category"] == "phone"


def score(gold: dict[str, dict], pred: dict[str, dict], uids: list[str]) -> dict:
    t = defaultdict(int)
    for u in uids:
        g, p = canon(gold[u]), canon(pred.get(u, {}))
        t["n"] += 1
        t["type"] += g["post_type"] == p["post_type"]
        t["cat"] += g["category"] == p["category"]
        if sell_phone(g):
            t["core"] += 1
            m, s, c = g["models"] == p["models"], g["storage"] == p["storage"], g["color"] == p["color"]
            t["model"] += m
            t["storage"] += s
            t["color"] += c
            t["all3"] += m and s and c
            t["bucket"] += sell_phone(p) and m and s
            t["cell"] += sell_phone(p) and m and s and g["condition"] == p["condition"]
            t["cond"] += g["condition"] == p["condition"]
        if sell_phone(p) and len(p["models"]) == 1:
            t["in_sise"] += 1
            t["polluted"] += not (sell_phone(g) and g["models"] == p["models"])
            t["cell_polluted"] += not (sell_phone(g) and g["models"] == p["models"] and g["storage"] == p["storage"]
                                       and g["condition"] == p["condition"])
    return dict(t)


def weighted(per_platform: dict[str, dict], num: str, den: str) -> float:
    w = PLATFORM_WEIGHTS
    tot = sum(w[p] for p in per_platform if per_platform[p].get(den))
    return sum(w[p] * per_platform[p][num] / per_platform[p][den] for p in per_platform if per_platform[p].get(den)) / tot


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help="preds/{이름}_g.jsonl 의 이름")
    ap.add_argument("--subset", choices=["new"], help="new: 정답 모델이 최신 시리즈(아이폰 18·듀오, S26, 폴드8·플립8)인 글만")
    ap.add_argument("--detail", action="store_true", help="플랫폼별 수치도 출력")
    a = ap.parse_args()

    inputs = {r["uid"]: r for r in load(LAB / "data/eval1k_input.jsonl")}
    gold = load_parts("eval1k_labels")
    preds = {"규칙": {u: rules_pred(r) for u, r in inputs.items()}, "Haiku": load_parts("eval1k_haiku")}
    for n in a.names:
        preds[n] = {r["uid"]: r for r in load(LAB / f"preds/{n}_g.jsonl")}

    uids = [u for u in inputs if u in gold]
    if a.subset == "new":
        uids = [u for u in uids if any(NEW_MODELS.search(m) for m in gold[u].get("models") or [])]
    by_pf: dict[str, list[str]] = defaultdict(list)
    for u in uids:
        by_pf[inputs[u]["platform"]].append(u)

    print(f"{'':20} {'칸':>6} {'칸오염':>6} {'시세버킷':>14} {'오염':>6} {'모델':>6} {'용량':>6} {'색상':>6} {'3필드':>6} {'상태':>6} {'유형':>6} {'분류':>6}")
    for name, pred in preds.items():
        per = {p: score(gold, pred, us) for p, us in by_pf.items()}
        tot = score(gold, pred, uids)
        lo, hi = wilson(tot["bucket"], tot["core"])
        w = lambda num, den: weighted(per, num, den)  # noqa: E731
        print(f"{name:20} {w('cell', 'core'):6.1%} {w('cell_polluted', 'in_sise'):6.1%}"
              f" {w('bucket', 'core'):6.1%} ({lo:.0%}~{hi:.0%})"
              f" {w('polluted', 'in_sise'):6.1%} {w('model', 'core'):6.1%} {w('storage', 'core'):6.1%}"
              f" {w('color', 'core'):6.1%} {w('all3', 'core'):6.1%} {w('cond', 'core'):6.1%}"
              f" {w('type', 'n'):6.1%} {w('cat', 'n'):6.1%}")
        if a.detail:
            print(" " * 21 + "  ".join(f"{PLATFORM_NAMES[p]} 버킷 {s['bucket'] / s['core']:.1%}·3필드 {s['all3'] / s['core']:.1%} (n={s['core']})"
                                       for p, s in per.items() if s.get("core")))
    print(f"\n(판매 폰 글 {sum(score(gold, preds['규칙'], us).get('core', 0) for us in by_pf.values())}건."
          f" 플랫폼별 수집량으로 가중. 괄호는 비가중 95% 신뢰구간)")


if __name__ == "__main__":
    main()
