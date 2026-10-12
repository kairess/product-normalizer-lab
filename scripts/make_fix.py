"""Haiku 라벨 중 규칙과 갈린 글을 상위 모델(Opus)이 다시 판정하도록 묶는다.

    .venv-train/bin/python scripts/make_fix.py train10k [시작 묶음 번호]   # → data/train_fix_input_{NNN}.jsonl (150건씩)
    .venv-train/bin/python scripts/make_fix.py train2 24                   # 라벨이 끝난 묶음만, 이미 넣은 글은 빼고

평가셋에서 Haiku 가 규칙과 갈린 글(37%)은 Haiku 가 45% 틀렸고, 같은 글(63%)은 6% 틀렸다 (Opus 정답 기준).
그래서 갈린 글만 다시 보면 Haiku 오류의 대부분을 적은 비용으로 고칠 수 있다.
- 갈림 기준: 유형·분류·모델·용량·상태 중 하나라도 다름. 상태만 갈렸고 둘 다 판매 폰이 아니면 뺀다 (시세에 안 쓰임).
- 후보 A·B 는 Haiku·규칙을 글마다 무작위로 배정한다. 판정자가 출처를 보고 한쪽을 믿지 않게 하려는 것.
- 결과(data/train_fix_{NNN}.jsonl)는 distill_data.build(fixes=True) 가 Haiku 라벨 대신 쓴다.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from distill_data import SETS, load_set

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
from score import KEY, canon, rules_pred  # noqa: E402

CHUNK = 150
LABEL_KEYS = ("post_type", "category", "models", "storage", "color", "condition")


def sell_phone(c: dict) -> bool:
    return c["post_type"] == "sell" and c["category"] == "phone"


def main(name: str, first: int = 0) -> None:
    assert name in SETS
    inputs, labels = load_set(name)
    queued = {json.loads(l)["uid"] for p in (LAB / "data").glob("train_fix_input_*.jsonl")
              for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}
    rng = random.Random(f"fix-{name}")
    out = []
    for h in labels:
        if h["uid"] in queued:  # 앞서 판정 묶음에 넣은 글은 건너뛴다 (라벨이 다 모이기 전에 나눠 돌릴 때)
            continue
        inp = inputs[h["uid"]]
        r = rules_pred({"title": inp["title"], "body": inp["body"]})
        ch, cr = canon(h), canon(r)
        diff = [k for k in KEY if ch[k] != cr[k]]
        if not diff or (diff == ["condition"] and not (sell_phone(ch) or sell_phone(cr))):
            continue
        hl = {k: h.get(k) for k in LABEL_KEYS}
        rl = {k: r.get(k) for k in LABEL_KEYS}
        a, b = (hl, rl) if rng.random() < 0.5 else (rl, hl)
        out.append({"uid": h["uid"], "title": inp["title"], "body": inp["body"], "A": a, "B": b, "diff": diff})
    for i in range(0, len(out), CHUNK):
        (LAB / f"data/train_fix_input_{first + i // CHUNK:03d}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out[i:i + CHUNK]), encoding="utf-8")
    n = (len(out) + CHUNK - 1) // CHUNK
    print(f"{name}: 라벨 {len(labels)}건 중 갈린 글 {len(out)}건 → 묶음 {first:03d}~{first + n - 1:03d}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0)
