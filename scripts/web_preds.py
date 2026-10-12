"""브라우저 정규화기 결과(spec) → 채점용 preds.

    .venv-train/bin/python scripts/web_preds.py <브라우저 결과.json> q08_final_lora_web   # → preds/q08_final_lora_web_g.jsonl
    .venv-train/bin/python scripts/score.py q08_final_lora_web

브라우저 결과는 근거 검사·카탈로그 정식명까지 끝난 spec 이라 _g 이름으로 바로 쓴다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]  # 저장소 루트


def main(src: str, name: str) -> None:
    res = json.loads(Path(src).read_text(encoding="utf-8"))["results"]
    rows = []
    for r in res:
        s = r.get("spec") or {}
        rows.append({"uid": r["uid"], "post_type": s.get("post_type"), "category": s.get("category"),
                     "models": s.get("models") or [], "storage": s.get("storages") or [], "color": s.get("colors") or [],
                     "condition": s.get("condition"), "raw": s.get("raw")})
    out = LAB / f"preds/{name}_g.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    ms = sorted(r["ms"] for r in res if r.get("ms"))
    print(f"{len(rows)}건 (오류 {sum(1 for r in res if r.get('err'))}), 건당 중앙 {ms[len(ms) // 2]}ms → {out.name}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
