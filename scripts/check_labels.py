"""라벨 파일 검사: 입력과 uid·순서가 같은지, 값이 가이드 형식인지.

    python3 scripts/check_labels.py data/eval1k_input_0.jsonl data/eval1k_labels_0.jsonl
"""

from __future__ import annotations

import json
import re
import sys

POST = {"sell", "buy", "shop_ad", "other"}
CAT = {"phone", "tablet", "watch", "earbuds", "laptop", "accessory", "parts", "other"}
COND = {"new", "used", "broken"}
STORAGE_RE = re.compile(r"^\d+(GB|TB)$")


def main(inp: str, lab: str) -> int:
    want = [json.loads(l)["uid"] for l in open(inp, encoding="utf-8") if l.strip()]
    errs: list[str] = []
    got: list[str] = []
    for n, line in enumerate(open(lab, encoding="utf-8"), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError as e:
            errs.append(f"{n}행 JSON 오류: {e}")
            continue
        got.append(r.get("uid"))
        if r.get("post_type") not in POST:
            errs.append(f"{n}행 post_type={r.get('post_type')!r}")
        if r.get("category") not in CAT:
            errs.append(f"{n}행 category={r.get('category')!r}")
        if r.get("condition") not in COND:
            errs.append(f"{n}행 condition={r.get('condition')!r}")
        for k in ("models", "storage", "color"):
            if not isinstance(r.get(k), list) or not all(isinstance(x, str) for x in r[k]):
                errs.append(f"{n}행 {k} 는 문자열 리스트여야 함")
        for s in r.get("storage") or []:
            if not STORAGE_RE.match(str(s)):
                errs.append(f"{n}행 storage 형식 {s!r} (예: 128GB, 1TB)")
        if "note" in r and not isinstance(r["note"], str):
            errs.append(f"{n}행 note 는 문자열")
    missing = [u for u in want if u not in set(got)]
    extra = [u for u in got if u not in set(want)]
    dup = len(got) - len(set(got))
    if missing:
        errs.append(f"빠진 uid {len(missing)}개: {missing[:5]}")
    if extra:
        errs.append(f"입력에 없는 uid {len(extra)}개: {extra[:5]}")
    if dup:
        errs.append(f"중복 uid {dup}개")
    if not missing and not extra and got != want:
        errs.append("순서가 입력과 다름")
    print(f"입력 {len(want)}건 / 라벨 {len(got)}건")
    for e in errs[:30]:
        print(" -", e)
    print("OK" if not errs else f"오류 {len(errs)}개")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
