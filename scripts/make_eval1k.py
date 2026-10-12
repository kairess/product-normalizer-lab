"""서비스 DB(data/sise.db)에서 평가셋 1,000건을 뽑는다.

    python scripts/make_eval1k.py [--db data/sise.db]

- 플랫폼별 층화: 당근 600, 번개장터 250, 중고나라 150. 플랫폼 안에서는 무작위라 액세서리·구매글도 실제 비율로 들어간다.
- 같은 글을 다시 올린 중복(제목+본문 앞 200자)과 기존 정답셋(gold, test2)에 있는 글은 뺀다.
- 본문은 1,500자로 자른다. 채점 때 파이프라인에도 같은 길이를 넣는다.
- 출력: data/eval1k_input.jsonl, 라벨링용 묶음 data/eval1k_input_{0..4}.jsonl (200건씩)
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]  # 저장소 루트
QUOTA = {"danggeun": 600, "bunjang": 250, "joonggonara": 150}
PREFIX = {"danggeun": "dg", "bunjang": "bu", "joonggonara": "jo"}
BODY_MAX = 1500
SEED = 20261008


def load_uids(*names: str) -> set[str]:
    out: set[str] = set()
    for n in names:
        p = LAB / "data" / n
        if p.exists():
            out |= {json.loads(l)["uid"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(LAB / "data" / "sise.db"))
    a = ap.parse_args()
    used = load_uids("gold_input.jsonl", "test2_input.jsonl")
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rng = random.Random(SEED)
    picked: list[dict] = []
    for platform, n in QUOTA.items():
        rows = con.execute(
            "SELECT id, platform, article_id, url, title, body FROM listings WHERE platform=? ORDER BY id", (platform,)
        ).fetchall()
        seen: set[str] = set()
        pool = []
        for r in rows:
            uid = f"{PREFIX[platform]}_{r['article_id']}"
            key = f"{r['title'].strip()}|{(r['body'] or '')[:200].strip()}"
            if uid in used or key in seen:
                continue
            seen.add(key)
            pool.append(r)
        for r in rng.sample(pool, n):
            picked.append({
                "uid": f"{PREFIX[platform]}_{r['article_id']}",
                "listing_id": r["id"],
                "platform": platform,
                "url": r["url"],
                "title": r["title"],
                "body": (r["body"] or "")[:BODY_MAX],
            })
        print(f"{platform}: 후보 {len(pool)} 중 {n}건")
    rng.shuffle(picked)
    out = LAB / "data" / "eval1k_input.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in picked), encoding="utf-8")
    for i in range(5):
        chunk = picked[i * 200:(i + 1) * 200]
        (LAB / "data" / f"eval1k_input_{i}.jsonl").write_text(
            "".join(json.dumps({k: r[k] for k in ("uid", "title", "body")}, ensure_ascii=False) + "\n" for r in chunk),
            encoding="utf-8")
    print(f"→ {out} ({len(picked)}건)")


if __name__ == "__main__":
    main()
