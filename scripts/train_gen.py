"""생성형 소형 모델 미세조정: 매물 텍스트 → "유형|분류|모델|용량|색상|상태" 한 줄.

    .venv-train/bin/python scripts/train_gen.py --model Qwen/Qwen3.5-0.8B --name qwen08 --lora   # 최종 설정은 scripts/run_final.sh
    옵션: --n 2000 (학습 건수 제한, 학습 곡선용) --epochs 3 --lr 5e-5
          --sets train10k,train2 (라벨 묶음) --include-new (신모델 글도 학습, 최종 모델용) --fixes (Opus 재검 라벨 반영)
          --mem 20 (GPU 메모리 상한 GB) --best (에폭마다 검증 손실이 가장 낮은 모델을 남김)

- 학습: Haiku 라벨(train10k)에서 신모델(holdout) 제외. 정답 토큰에만 손실.
- GPU 는 다른 작업과 같이 쓸 수 있으므로 이 프로세스의 메모리를 --mem GB 로 제한한다 (기본 8).
- 끝나면 평가셋(eval1k)과 신모델 holdout 에 대해 예측해 preds/{name}.jsonl, preds/{name}_holdout.jsonl 로 저장.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments)

from distill_data import LAB, build, eval_examples, parse_target, with_augmentation

PROMPT = "매물 정보를 정규화하세요.\n{text}\n정답: "
MAX_IN = 448
MAX_OUT = 64


class SFTData(Dataset):
    def __init__(self, rows, tok):
        self.items = []
        eos = tok.eos_token_id
        for r in rows:
            text_ids = tok(r["text"], add_special_tokens=False)["input_ids"][:MAX_IN]
            text = tok.decode(text_ids)
            p = tok(PROMPT.format(text=text), add_special_tokens=False)["input_ids"]
            t = tok(r["target"], add_special_tokens=False)["input_ids"][:MAX_OUT] + [eos]
            self.items.append({"input_ids": p + t, "labels": [-100] * len(p) + t})

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


def collate(pad_id):
    def f(batch):
        n = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), n), pad_id)
        lab = torch.full((len(batch), n), -100)
        att = torch.zeros((len(batch), n), dtype=torch.long)
        for i, b in enumerate(batch):
            L = len(b["input_ids"])
            ids[i, :L] = torch.tensor(b["input_ids"])
            lab[i, :L] = torch.tensor(b["labels"])
            att[i, :L] = 1
        return {"input_ids": ids, "labels": lab, "attention_mask": att}
    return f


@torch.no_grad()
def predict(model, tok, rows, bs=32) -> list[dict]:
    model.eval()
    tok.padding_side = "left"
    out = []
    for i in range(0, len(rows), bs):
        chunk = rows[i:i + bs]
        prompts = [PROMPT.format(text=tok.decode(tok(r["text"], add_special_tokens=False)["input_ids"][:MAX_IN]))
                   for r in chunk]
        enc = tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        gen = model.generate(**enc, max_new_tokens=MAX_OUT, do_sample=False, pad_token_id=tok.pad_token_id,
                             eos_token_id=tok.eos_token_id)
        for r, g in zip(chunk, gen[:, enc["input_ids"].shape[1]:]):
            s = tok.decode(g, skip_special_tokens=True)
            out.append({"uid": r["uid"], **parse_target(s), "raw": s.strip()})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--lora", action="store_true")
    ap.add_argument("--n", type=int, default=0, help="학습 건수 제한 (0=전부)")
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=0)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--aug", type=float, default=0, help="세대 숫자 바꾸기 증강 비율 (예: 0.5)")
    ap.add_argument("--sets", default="train10k")
    ap.add_argument("--include-new", action="store_true")
    ap.add_argument("--fixes", action="store_true")
    ap.add_argument("--mem", type=float, default=8)
    ap.add_argument("--best", action="store_true")
    ap.add_argument("--r", type=int, default=32, help="LoRA rank")
    a = ap.parse_args()

    if torch.cuda.is_available():
        total = torch.cuda.get_device_properties(0).total_memory / 2**30
        torch.cuda.set_per_process_memory_fraction(min(1.0, a.mem / total))
    tok = AutoTokenizer.from_pretrained(a.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16).cuda()
    if a.lora:
        from peft import LoraConfig, get_peft_model
        model = get_peft_model(model, LoraConfig(r=a.r, lora_alpha=2 * a.r, lora_dropout=0.05, target_modules="all-linear",
                                                 task_type="CAUSAL_LM"))
        model.print_trainable_parameters()
    model.gradient_checkpointing_enable()
    if a.lora:
        model.enable_input_require_grads()
    lr = a.lr or (2e-4 if a.lora else 5e-5)

    d = build(sets=tuple(a.sets.split(",")), include_new=a.include_new, fixes=a.fixes)
    train_rows = d["train"][: a.n] if a.n else d["train"]
    if a.aug:
        train_rows = with_augmentation(train_rows, a.aug)
    print(f"학습 {len(train_rows)} / 검증 {len(d['val'])} / 신모델 holdout {len(d['holdout_new'])}")
    out_dir = LAB / "out" / a.name
    args = TrainingArguments(
        output_dir=str(out_dir), per_device_train_batch_size=a.bs, gradient_accumulation_steps=max(1, 32 // a.bs),
        learning_rate=lr, num_train_epochs=a.epochs, lr_scheduler_type="cosine",
        warmup_steps=max(1, int(0.03 * math.ceil(len(train_rows) / 32) * a.epochs)),
        bf16=True, logging_steps=20, gradient_checkpointing=True, eval_strategy="epoch", save_strategy="epoch" if a.best else "no", report_to=[],
        load_best_model_at_end=a.best, metric_for_best_model="eval_loss", save_total_limit=2 if a.best else None,
        save_only_model=True,
        per_device_eval_batch_size=a.bs, dataloader_num_workers=2, seed=0,
        remove_unused_columns=False,
    )
    t0 = time.time()
    trainer = Trainer(model=model, args=args, train_dataset=SFTData(train_rows, tok), eval_dataset=SFTData(d["val"], tok),
                      data_collator=collate(tok.pad_token_id))
    trainer.train()
    train_min = (time.time() - t0) / 60
    if a.lora:
        model = model.merge_and_unload()
    model.save_pretrained(out_dir / "final")
    tok.save_pretrained(out_dir / "final")

    t0 = time.time()
    preds = predict(model, tok, eval_examples())
    pred_sec = time.time() - t0
    (LAB / "preds").mkdir(exist_ok=True)
    (LAB / f"preds/{a.name}.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in preds),
                                               encoding="utf-8")
    hold = predict(model, tok, d["holdout_new"])
    (LAB / f"preds/{a.name}_holdout.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in hold),
                                                       encoding="utf-8")
    exact = sum(p["raw"] == r["target"] for p, r in zip(hold, d["holdout_new"])) / max(1, len(hold))
    bad = sum(not p["raw"] or p["raw"].count("|") != 5 for p in preds)
    meta = {"model": a.model, "lora": a.lora, "r": a.r if a.lora else None, "sets": a.sets, "include_new": a.include_new,
            "fixes": a.fixes, "best": a.best, "n_train": len(train_rows), "aug": a.aug, "epochs": a.epochs, "lr": lr,
            "train_min": round(train_min, 1), "eval_pred_sec_gpu": round(pred_sec, 1), "format_errors": bad,
            "holdout_exact_vs_haiku": round(exact, 3),
            "eval_loss": [h["eval_loss"] for h in trainer.state.log_history if "eval_loss" in h]}
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
