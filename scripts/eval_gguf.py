"""GGUF(브라우저·CPU 배포용) 모델을 llama.cpp 서버로 평가셋에 돌려 preds 를 만든다.

    .venv-train/bin/python scripts/eval_gguf.py out/q08_final_lora/model-q4_k_m.gguf q08_final_lora_q4 [--tok out/q08_final_lora/final]
    → preds/q08_final_lora_q4.jsonl (근거 검사 전). 이후 scripts/ground.py, scripts/score.py 로 채점.

- 학습과 같은 프롬프트를 HF 토크나이저로 토큰 id 로 만들어 보낸다 (문자열로 보내면 BOS 처리 차이로 결과가 달라진다).
- 양자화(Q4_K_M 등)로 정확도가 얼마나 떨어지는지 bf16(GPU) 예측과 비교하려는 것.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
import time
import urllib.request
from pathlib import Path

from transformers import AutoTokenizer

from distill_data import LAB, eval_examples, parse_target
from train_gen import MAX_IN, MAX_OUT, PROMPT

SERVER = LAB / "tools/llama-bin/llama-b11491/llama-server"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gguf")
    ap.add_argument("name")
    ap.add_argument("--tok", help="HF 토크나이저 폴더 (기본: gguf 옆의 final/)")
    ap.add_argument("--port", type=int, default=8093)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    gguf = LAB / a.gguf
    tok = AutoTokenizer.from_pretrained(a.tok and LAB / a.tok or gguf.parent / "final")
    proc = subprocess.Popen([str(SERVER), "-m", str(gguf), "--host", "127.0.0.1", "--port", str(a.port),
                             "-t", str(a.threads), "-c", "4096", "-np", "4", "--no-webui"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{a.port}/health", timeout=2)
                break
            except Exception:
                time.sleep(1)
        rows = eval_examples()

        def call(r):
            text = tok.decode(tok(r["text"], add_special_tokens=False)["input_ids"][:MAX_IN])
            ids = tok(PROMPT.format(text=text), add_special_tokens=False)["input_ids"]
            body = json.dumps({"prompt": ids, "n_predict": MAX_OUT, "temperature": 0, "stop": ["\n"],
                               "cache_prompt": False}).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{a.port}/completion", body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as f:
                s = json.load(f)["content"]
            return {"uid": r["uid"], **parse_target(s), "raw": s.strip()}

        t0 = time.time()
        with cf.ThreadPoolExecutor(4) as ex:
            preds = list(ex.map(call, rows))
        out = LAB / f"preds/{a.name}.jsonl"
        out.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in preds), encoding="utf-8")
        print(f"{len(preds)}건 {time.time() - t0:.0f}초 → {out}")
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
