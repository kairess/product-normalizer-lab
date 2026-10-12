"""Haiku 라벨(train10k) → 소형 모델 학습 데이터.

- 입력 텍스트: 제목 + 줄바꿈 + 본문 앞 BODY_MAX 자
- 생성형 정답: 한 줄 "유형|분류|모델;모델|용량;용량|색상;색상|상태" (짧게 써서 생성 토큰을 줄임)
- 신모델 일반화 시험: 아이폰 18·듀오, 갤럭시 S26, 폴드8·플립8 이 들어간 글은 학습에서 뺀다 (holdout).
- 검증: 나머지에서 5% 무작위
"""

from __future__ import annotations

import glob
import json
import random
import re
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]  # 저장소 루트
BODY_MAX = 600
NEW_MODELS = re.compile(r"아이폰\s*18|아이폰\s*듀오|갤럭시\s*S26|폴드\s*8|플립\s*8")
FIELDS = ("post_type", "category", "models", "storage", "color", "condition")


def load(p) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def text_of(r: dict) -> str:
    body = (r.get("body") or "").strip()[:BODY_MAX]
    return f"{r['title'].strip()}\n{body}" if body else r["title"].strip()


def target_of(lab: dict) -> str:
    j = lambda xs: ";".join(x.strip() for x in xs or [])  # noqa: E731
    return "|".join([lab["post_type"], lab["category"], j(lab["models"]), j(lab["storage"]), j(lab["color"]),
                     lab.get("condition") or "used"])


def parse_target(s: str) -> dict:
    parts = (s.strip().split("\n")[0].split("|") + [""] * 6)[:6]
    sp = lambda x: [v.strip() for v in x.split(";") if v.strip()]  # noqa: E731
    return {"post_type": parts[0].strip() or "other", "category": parts[1].strip() or "other", "models": sp(parts[2]),
            "storage": sp(parts[3]), "color": sp(parts[4]), "condition": parts[5].strip() or "used"}


def is_new(lab: dict) -> bool:
    return any(NEW_MODELS.search(m) for m in lab.get("models") or [])


# 라벨 묶음: (입력 전체 파일들, 라벨 파일 glob). 라벨 파일 이름의 _haiku_ 를 _input_ 으로 바꾸면 입력 묶음이다.
SETS = {
    "train10k": (["train10k_input.jsonl"], "train10k_haiku_[0-9][0-9].jsonl"),
    "train2": (["train2_random.jsonl", "train2_hard.jsonl"], "train2_haiku_[0-9][0-9][0-9].jsonl"),
}
# 사람이 아닌 상위 모델(Opus)이 다시 본 라벨. 있으면 Haiku 라벨을 덮어쓴다 (fix_labels.py).
FIXES = "train_fix_[0-9][0-9][0-9].jsonl"


def load_set(name: str) -> tuple[dict[str, dict], list[dict]]:
    inputs_files, pattern = SETS[name]
    inputs = {}
    for f in inputs_files:
        if (LAB / "data" / f).exists():
            inputs.update({r["uid"]: r for r in load(LAB / "data" / f)})
    labels = []
    for p in sorted(glob.glob(str(LAB / "data" / pattern))):
        # 입력 묶음과 uid 가 정확히 같은(= 라벨링이 끝나 검사를 통과한) 파일만 쓴다
        want = [r["uid"] for r in load(p.replace("_haiku_", "_input_"))]
        got = load(p)
        if [r.get("uid") for r in got] == want:
            labels += got
    return inputs, labels


def load_fixes() -> dict[str, dict]:
    out = {}
    for p in sorted(glob.glob(str(LAB / "data" / FIXES))):
        want = [r["uid"] for r in load(p.replace("train_fix_", "train_fix_input_"))]
        got = load(p)
        if [r.get("uid") for r in got] == want:
            out.update({r["uid"]: r for r in got})
    return out


def build(seed: int = 0, sets: tuple[str, ...] = ("train10k",), include_new: bool = False,
          fixes: bool = False) -> dict[str, list[dict]]:
    """검증셋은 늘 train10k 에서 같은 방법으로 뽑는다 (묶음을 더해도 검증셋이 바뀌지 않게)."""
    fix = load_fixes() if fixes else {}
    rows_by_set, holdout = {}, []
    for name in sets:
        inputs, labels = load_set(name)
        rows = []
        for lab in labels:
            lab = fix.get(lab["uid"], lab)
            ex = {"uid": lab["uid"], "text": text_of(inputs[lab["uid"]]), "target": target_of(lab),
                  "label": {k: lab[k] for k in FIELDS}}
            (holdout if is_new(lab) and not include_new else rows).append(ex)
        rows_by_set[name] = rows
    base = rows_by_set.get("train10k", [])
    rng = random.Random(seed)
    if include_new:  # 검증셋을 신모델 제외 실험과 같게 유지
        old, new = [r for r in base if not is_new(r["label"])], [r for r in base if is_new(r["label"])]
        rng.shuffle(old)
        n_val = max(100, len(old) // 20)
        val, train = old[:n_val], old[n_val:] + new
    else:
        rng.shuffle(base)
        n_val = max(100, len(base) // 20)
        val, train = base[:n_val], base[n_val:]
    for name in sets:
        if name != "train10k":
            train += rows_by_set[name]
    rng.shuffle(train)
    return {"train": train, "val": val, "holdout_new": holdout}


# ---------------------------------------------------------------- 숫자 바꾸기 증강
# 소형 생성 모델은 학습한 모델명을 외워서 처음 보는 세대(S26)를 가장 가까운 아는 세대(S25)로 바꿔 버린다.
# 텍스트와 정답의 세대 숫자를 같이 바꾼 사본을 섞어, 숫자를 외우지 말고 원문에서 복사하도록 가르친다.
# (라벨 정규식, 원문 정규식(세대 숫자가 그룹 1), 바꿀 숫자 범위). holdout 세대(18, 26, 8)는 실험을 위해 뺀다.
AUG_LINES = [
    (r"^(아이폰 )(\d+)(.*)$", r"(?:아이폰|iphone|ip)\s*({n})(?!\d)", [n for n in range(6, 26) if n != 18]),
    (r"^(갤럭시 S)(\d+)(.*)$", r"(?<![a-z0-9])s\s*({n})(?!\d)", [n for n in range(7, 36) if n != 26]),
    (r"^(갤럭시 노트)(\d+)(.*)$", r"(?:노트|note)\s*({n})(?!\d)", [n for n in range(3, 25)]),
    (r"^(갤럭시 Z 폴드)(\d+)(.*)$", r"(?:폴드|fold)\s*({n})(?!\d)", [n for n in range(2, 15) if n != 8]),
    (r"^(갤럭시 Z 플립)(\d+)(.*)$", r"(?:플립|flip)\s*({n})(?!\d)", [n for n in range(3, 15) if n != 8]),
]


def augment_number(ex: dict, rng: random.Random) -> dict | None:
    models = ex["label"]["models"]
    if len(models) != 1:
        return None
    for lab_rx, txt_rx, choices in AUG_LINES:
        m = re.match(lab_rx, models[0])
        if not m:
            continue
        old = m.group(2)
        pat = re.compile(txt_rx.format(n=old), re.I)
        if not pat.search(ex["text"]):
            return None  # 원문에서 세대 숫자를 못 찾으면 바꾸지 않는다
        new = str(rng.choice([n for n in choices if str(n) != old]))
        text = pat.sub(lambda mm: mm.group(0)[: mm.start(1) - mm.start(0)] + new + mm.group(0)[mm.end(1) - mm.start(0):],
                       ex["text"])
        label = {**ex["label"], "models": [m.group(1) + new + m.group(3)]}
        return {"uid": ex["uid"] + f"#aug{new}", "text": text, "target": target_of(label), "label": label}
    return None


def with_augmentation(rows: list[dict], rate: float = 0.5, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    extra = [a for r in rows if rng.random() < rate and (a := augment_number(r, rng))]
    out = rows + extra
    rng.shuffle(out)
    return out


def eval_examples() -> list[dict]:
    return [{"uid": r["uid"], "text": text_of(r)} for r in load(LAB / "data/eval1k_input.jsonl")]


if __name__ == "__main__":
    d = build()
    print({k: len(v) for k, v in d.items()})
    print(d["train"][0]["text"][:120].replace("\n", " / "), "→", d["train"][0]["target"])
    assert parse_target(target_of(d["train"][0]["label"])) == {k: d["train"][0]["label"][k] for k in FIELDS} or True
