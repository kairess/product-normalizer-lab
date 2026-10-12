"""서비스 DB(data/sise.db)에서 학습용 표본을 뽑는다 (Haiku 라벨링 → 소형 모델 증류용).

    python scripts/make_train.py [--db data/sise.db]

- 플랫폼별 할당: 당근 7,500, 번개장터 2,000, 중고나라 500 (수집량 비율보다 번개·중고나라를 늘림).
- 평가셋(eval1k)과 기존 정답셋(gold, test2)에 있는 글, 같은 글을 다시 올린 중복은 뺀다.
- 출력: data/train10k_input.jsonl, 라벨링용 묶음 data/train10k_input_{00..49}.jsonl (200건씩)
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3

from make_eval1k import BODY_MAX, LAB, PREFIX, load_uids

QUOTA = {"danggeun": 7500, "bunjang": 2000, "joonggonara": 500}
SEED = 20261009
CHUNK = 200


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(LAB / "data" / "sise.db"))
    a = ap.parse_args()
    used = load_uids("gold_input.jsonl", "test2_input.jsonl", "eval1k_input.jsonl")
    eval_keys = {f"{r['title'].strip()}|{r['body'][:200].strip()}"
                 for r in map(json.loads, (LAB / "data/eval1k_input.jsonl").read_text(encoding="utf-8").splitlines())}
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rng = random.Random(SEED)
    picked: list[dict] = []
    for platform, n in QUOTA.items():
        rows = con.execute(
            "SELECT id, platform, article_id, url, title, body FROM listings WHERE platform=? ORDER BY id", (platform,)
        ).fetchall()
        seen = set(eval_keys)  # 평가셋과 내용이 같은 재게시 글도 뺀다
        pool = []
        for r in rows:
            uid = f"{PREFIX[platform]}_{r['article_id']}"
            key = f"{r['title'].strip()}|{(r['body'] or '')[:200].strip()}"
            if uid in used or key in seen:
                continue
            seen.add(key)
            pool.append(r)
        take = min(n, len(pool))
        for r in rng.sample(pool, take):
            picked.append({"uid": f"{PREFIX[platform]}_{r['article_id']}", "listing_id": r["id"], "platform": platform,
                           "url": r["url"], "title": r["title"], "body": (r["body"] or "")[:BODY_MAX]})
        print(f"{platform}: 후보 {len(pool)} 중 {take}건")
    rng.shuffle(picked)
    (LAB / "data/train10k_input.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in picked), encoding="utf-8")
    for i in range(0, len(picked), CHUNK):
        (LAB / f"data/train10k_input_{i // CHUNK:02d}.jsonl").write_text(
            "".join(json.dumps({k: r[k] for k in ("uid", "title", "body")}, ensure_ascii=False) + "\n"
                    for r in picked[i:i + CHUNK]), encoding="utf-8")
    print(f"→ data/train10k_input.jsonl ({len(picked)}건, 묶음 {(len(picked) + CHUNK - 1) // CHUNK}개)")


if __name__ == "__main__":
    main()
