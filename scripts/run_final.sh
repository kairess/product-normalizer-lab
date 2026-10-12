#!/usr/bin/env bash
# 최종 모델: 학습 → GGUF(MTP 층 제외)·4비트 양자화 → llama.cpp 로 평가셋 예측 → 근거 검사 → 채점.
# 라벨(data/train10k_*, train2_*, train_fix_*)이 준비돼 있어야 한다. 학습은 GPU 20GB 안팎, 40분 정도 걸린다.
set -eu
cd "$(dirname "$0")/.."
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=.venv-train/bin/python
BIN=tools/llama-bin/llama-b11491
N=q08_final_lora

$PY scripts/train_gen.py --model Qwen/Qwen3.5-0.8B --name $N --lora --epochs 3 --aug 0.5 --mem 20 --bs 8 --best \
    --fixes --sets train10k,train2 --include-new
$PY tools/llama.cpp/convert_hf_to_gguf.py out/$N/final --outtype bf16 --no-mtp --outfile out/$N/model-bf16.gguf
$BIN/llama-quantize out/$N/model-bf16.gguf out/$N/model-q4_k_m.gguf Q4_K_M 8
$PY scripts/eval_gguf.py out/$N/model-q4_k_m.gguf ${N}_q4
$PY scripts/ground.py preds/$N.jsonl preds/${N}_q4.jsonl
$PY scripts/score.py $N ${N}_q4
