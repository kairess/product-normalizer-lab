"""2차 학습 표본 2만 건: 무작위 절반 + 현재 학생 모델이 어려워하는 글 절반.

    .venv-train/bin/python scripts/make_train2.py pool      # 후보 풀 → data/pool_input.jsonl
    .venv-train/bin/python scripts/make_train2.py score     # 학생 모델(Qwen 파일럿)로 풀 예측 → preds/pool_qwen.jsonl (GPU)
    .venv-train/bin/python scripts/make_train2.py random    # 무작위 1만 건 → data/train2_random.jsonl, 묶음 data/train2_input_{000..049}.jsonl
    .venv-train/bin/python scripts/make_train2.py hard      # 어려운 글 1만 건 → data/train2_hard.jsonl, 묶음 data/train2_input_{050..099}.jsonl

- 평가셋(eval1k)·1차 학습셋(train10k)·옛 정답셋(gold, test2)에 있는 글과, 내용이 같은 재게시 글은 뺀다.
- 어려운 글: 학생 예측(근거 검사 후)과 규칙이 시세 필드(유형·분류·모델·용량·상태)에서 갈리거나,
  학생이 생성한 토큰 중 가장 낮은 확률이 0.6 미만인 글. 1차 학습셋 무작위 표본에 없던 오류 유형을 더 모으려는 것.
- 플랫폼 할당(각 1만): 번개장터 2,500, 중고나라 1,194(남은 것을 반씩), 나머지 당근.
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from pathlib import Path

from make_eval1k import BODY_MAX, LAB, PREFIX, load_uids

SEED = 20261011
CHUNK = 200
TOTAL = 20000
POOL = {"danggeun": 30000, "bunjang": 9000, "joonggonara": 3000}
KEY = ("post_type", "category", "models", "storage", "condition")
CONF_MIN = 0.6


def key_of(title: str, body: str) -> str:
    return f"{title.strip()}|{(body or '')[:200].strip()}"


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def pool() -> None:
    used = load_uids("gold_input.jsonl", "test2_input.jsonl", "eval1k_input.jsonl", "train10k_input.jsonl")
    seen = {key_of(r["title"], r["body"]) for n in ("eval1k_input.jsonl", "train10k_input.jsonl")
            for r in load(LAB / "data" / n)}
    con = sqlite3.connect(f"file:{LAB / 'data/sise.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rng = random.Random(SEED)
    out = []
    for platform, n in POOL.items():
        cand = []
        for r in con.execute("SELECT id, article_id, url, title, body FROM listings WHERE platform=? ORDER BY id", (platform,)):
            uid, k = f"{PREFIX[platform]}_{r['article_id']}", key_of(r["title"], r["body"])
            if uid in used or k in seen:
                continue
            seen.add(k)
            cand.append({"uid": uid, "listing_id": r["id"], "platform": platform, "url": r["url"], "title": r["title"],
                         "body": (r["body"] or "")[:BODY_MAX]})
        take = rng.sample(cand, min(n, len(cand)))
        print(f"{platform}: 중복 뺀 후보 {len(cand)} 중 {len(take)}건")
        out += take
    (LAB / "data/pool_input.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    print(f"→ data/pool_input.jsonl {len(out)}건")


def score(model_dir: str = "out/qwen08_aug_pilot/final", bs: int = 96) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from distill_data import parse_target, text_of
    from train_gen import MAX_IN, MAX_OUT, PROMPT

    total = torch.cuda.get_device_properties(0).total_memory / 2**30
    torch.cuda.set_per_process_memory_fraction(min(1.0, 20 / total))
    tok = AutoTokenizer.from_pretrained(LAB / model_dir)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(LAB / model_dir, dtype=torch.bfloat16).cuda().eval()
    rows = load(LAB / "data/pool_input.jsonl")
    rows.sort(key=lambda r: len(text_of(r)))  # 길이가 비슷한 글끼리 묶어 패딩 낭비를 줄인다
    out_p = LAB / "preds/pool_qwen.jsonl"
    with out_p.open("w", encoding="utf-8") as f:
        for i in range(0, len(rows), bs):
            chunk = rows[i:i + bs]
            prompts = [PROMPT.format(text=tok.decode(tok(text_of(r), add_special_tokens=False)["input_ids"][:MAX_IN]))
                       for r in chunk]
            enc = tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
            with torch.no_grad():
                g = model.generate(**enc, max_new_tokens=MAX_OUT, do_sample=False, pad_token_id=tok.pad_token_id,
                                   eos_token_id=tok.eos_token_id, output_scores=True, return_dict_in_generate=True)
            seq = g.sequences[:, enc["input_ids"].shape[1]:]
            probs = torch.stack([s.float().softmax(-1).gather(1, seq[:, j:j + 1]).squeeze(1)
                                 for j, s in enumerate(g.scores)], 1)  # (bs, steps)
            for r, ids, pr in zip(chunk, seq, probs):
                n = int((ids != tok.pad_token_id).sum())
                s = tok.decode(ids, skip_special_tokens=True)
                f.write(json.dumps({"uid": r["uid"], **parse_target(s), "raw": s.strip(),
                                    "min_p": round(float(pr[:max(1, n)].min()), 4)}, ensure_ascii=False) + "\n")
            if i // bs % 20 == 0:
                print(f"{i + len(chunk)}/{len(rows)}", flush=True)
    print(f"→ {out_p}")


HALF = {"bunjang": 2500, "joonggonara": 1194}  # 묶음마다(무작위·어려운) 플랫폼 할당. 당근은 나머지


def write_chunks(picked: list[dict], first: int) -> None:
    for i in range(0, len(picked), CHUNK):
        (LAB / f"data/train2_input_{first + i // CHUNK:03d}.jsonl").write_text(
            "".join(json.dumps({k: r[k] for k in ("uid", "title", "body")}, ensure_ascii=False) + "\n"
                    for r in picked[i:i + CHUNK]), encoding="utf-8")


def take(cands: list[dict], n_total: int, rng: random.Random) -> list[dict]:
    picked = []
    quota = {**HALF, "danggeun": n_total - sum(HALF.values())}
    for pf, q in quota.items():
        c = [r for r in cands if r["platform"] == pf]
        picked += rng.sample(c, min(q, len(c)))
    rest = [r for r in cands if r["uid"] not in {p["uid"] for p in picked}]
    picked += rng.sample(rest, max(0, min(len(rest), n_total - len(picked))))  # 할당이 모자라면 아무 플랫폼으로 채움
    rng.shuffle(picked)
    return picked


def select_random() -> None:
    """무작위 1만 건 → 묶음 000~049. 학생 모델 예측과 상관없이 먼저 라벨링을 시작한다."""
    rows = load(LAB / "data/pool_input.jsonl")
    picked = take(rows, TOTAL // 2, random.Random(SEED))
    (LAB / "data/train2_random.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in picked), encoding="utf-8")
    write_chunks(picked, 0)
    print({pf: sum(r["platform"] == pf for r in picked) for pf in POOL}, f"→ 묶음 000~{len(picked) // CHUNK - 1:03d}")


def select_hard() -> None:
    """무작위로 뽑히지 않은 글 중 어려운 글 1만 건 → 묶음 050~099."""
    sys.path.insert(0, str(LAB))
    from ground import ground
    from normalizer.pipeline import build_spec

    from score import canon

    done = {r["uid"] for r in load(LAB / "data/train2_random.jsonl")}
    rows = [r for r in load(LAB / "data/pool_input.jsonl") if r["uid"] not in done]
    preds = {r["uid"]: r for r in load(LAB / "preds/pool_qwen.jsonl")}
    hard = []
    for r in rows:
        p, _ = ground(preds[r["uid"]], r["title"], r["body"])
        s = build_spec(r["title"], r["body"], None)
        rule = {"post_type": s["post_type"], "category": s["category"], "models": s["models"], "storage": s["storages"],
                "color": s["colors"], "condition": s["condition"]}
        cp, cr = canon(p), canon(rule)
        if any(cp[k] != cr[k] for k in KEY) or preds[r["uid"]]["min_p"] < CONF_MIN:
            hard.append(r)
    print(f"남은 후보 {len(rows)} 중 어려운 글 {len(hard)}건 ({len(hard) / len(rows):.0%})",
          {pf: sum(r["platform"] == pf for r in hard) for pf in POOL})
    picked = take(hard, TOTAL // 2, random.Random(SEED + 1))
    (LAB / "data/train2_hard.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in picked), encoding="utf-8")
    write_chunks(picked, TOTAL // 2 // CHUNK)
    print({pf: sum(r["platform"] == pf for r in picked) for pf in POOL}, f"→ 묶음 050~{50 + len(picked) // CHUNK - 1:03d}")


if __name__ == "__main__":
    {"pool": pool, "score": score, "random": select_random, "hard": select_hard}[sys.argv[1]]()
