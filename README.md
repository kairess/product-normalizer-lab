# product-normalizer-lab

당근·번개장터·중고나라의 아이폰/갤럭시 매물 글을 정식 제품명·용량·색상·상태로 정규화한다. 이 작업을 **브라우저 안에서** 도는 0.8B 모델로 한다.

- **모델 (GGUF Q4_K_M, 529MB):** [Hugging Face · kairess/used-phone-normalizer-0.8b-gguf](https://huggingface.co/kairess/used-phone-normalizer-0.8b-gguf)
- **코드:** 이 저장소. 학습, 평가, 근거 검사, 카탈로그, JS 정규화기, 패치한 wllama 빌드가 들어 있다

```
입력  "구매하실분들만 연락주세요아이폰 12 미니 네이비 128GB 풀박스 상태좋아요"
출력  {post_type: sell, category: phone, model: "아이폰 12 미니", storage: "128GB", color: "네이비", condition: "used",
       brand: "Apple", line: "아이폰", gen: "12", variant: "미니", ...}
```

## 결과

평가셋 1,000건(eval1k)으로 쟀다. 정답은 Opus 라벨이고, 지표는 판매 폰 글 708건 기준이며 플랫폼별 수집량으로 가중했다.

| | 칸 | 칸오염 | 시세버킷 | 상태 | 크기·속도 |
|---|---|---|---|---|---|
| 규칙·사전 | 78.2% | 21.7% | 93.7% | 83.4% | — |
| Claude Haiku (교사) | 88.2% | 10.4% | 97.7% | 90.1% | API |
| **최종: Qwen3.5-0.8B LoRA, Q4_K_M** (llama.cpp) | **95.2%** | **4.1%** | 97.6% | 97.2% | 529MB |
| **최종, 브라우저 전체 경로** (wllama + JS 정규화기) | **95.4%** | **4.1%** | 97.8% | 97.2% | CPU WASM 글당 약 1초 |

- **칸**: 모델·용량·상태까지 맞혀 시세표의 제 칸에 들어간 비율이다.
- **칸오염**: 시세에 들어간 글 중 틀린 칸에 들어간 비율이다.
- **시세버킷**: 모델·용량까지만 맞힌 비율이다.

학생 모델(0.8B)이 교사(Haiku)보다 정확하다. 교사 라벨 중 규칙과 갈린 글을 Opus가 다시 판정했고, 생성 결과를 원문 근거로 검사하기 때문이다. 자세한 실험 기록은 [docs/REPORT.md](docs/REPORT.md)에 있다.

## 방식

```
매물 DB ─▶ 표본 3.1만 건 ─▶ Haiku 라벨 ─▶ 규칙과 갈린 1.35만 건을 Opus가 재판정 ─▶ Qwen3.5-0.8B LoRA 학습 ─▶ GGUF Q4_K_M
                                                                                               │
브라우저: 입력 자르기 → wllama(llama.cpp WASM) 생성 → 한 줄 파싱 → 근거 검사 → 카탈로그 정식명 → spec ◀┘
```

- 모델은 `유형|분류|모델;모델|용량|색상|상태` 한 줄만 생성한다(최대 64토큰).
- **근거 검사:** 원문에 근거가 없는 모델명·용량·색상(예: 원문에 없는 세대 숫자)은 규칙 값으로 바꾼다.
- **카탈로그:** 아이폰 54종·갤럭시 110종의 별칭, 국내 모델 코드, 공식 색상을 담았다. 신모델은 `normalizer/data/catalog_*.json`에 항목을 추가하면 재학습 없이 대응한다.
- **wllama 패치:** wllama 3.8.1은 llama.cpp의 프롬프트 캐시 상한(기본 8GB)을 바꿀 수 없다. 이 모델은 요청마다 20~40MB를 쌓아 70여 건 만에 브라우저 메모리가 바닥난다. 그래서 상한 옵션(`cache_ram_mib`)을 노출하는 패치를 넣어 빌드한다(`web/wllama/`).

## 구조

```
normalizer/          규칙·사전 추출, 카탈로그, 결합 (Python). data/catalog_*.json
scripts/             표본 추출 → 라벨 검사·재판정 묶음 → 학습 → GGUF 평가 → 근거 검사 → 채점
web/
  normalizer/        JS 정규화기 (브라우저 추론). Python 판과 결과가 같다
  wllama/            wllama 패치와 빌드 스크립트
  e2e.html, e2e.mjs  브라우저 전체 경로로 평가셋 돌리기 (serve.py 로 로컬 서버)
docs/                REPORT.md (실험 기록), LABELING_GUIDE.md (라벨 스키마·기준)
```

아래 폴더는 git에서 뺐다.

| 폴더 | 내용 |
|---|---|
| `data/` | 매물 DB, 표본, 라벨 |
| `preds/` | 예측 |
| `out/` | 체크포인트·GGUF |
| `tools/` | llama.cpp, wllama 빌드 |

### scripts/

| 단계 | 파일 |
|---|---|
| 표본 추출 | `make_eval1k.py` (평가 1천), `make_train.py` (학습 1만), `make_train2.py` (무작위 1만 + 학생 모델이 어려워한 글 1만) |
| 라벨 | `check_labels.py`: 라벨 파일 검사 |
| 라벨 재판정 | `make_fix.py`: Haiku·규칙이 갈린 글을 Opus 재판정 묶음으로 만든다 |
| 학습 | `distill_data.py` (학습 데이터), `train_gen.py` (미세조정) |
| 평가 | `eval_gguf.py` (llama.cpp로 예측), `ground.py` (근거 검사), `score.py` (채점) |
| 한 번에 | `run_final.sh`: 최종 모델 학습 → GGUF 변환 → 평가 |
| 브라우저 | `js_parity.py` / `.mjs` (Python·JS 대조), `web_preds.py` (브라우저 결과 → 채점용) |

라벨은 스크립트가 아니라 Claude 에이전트가 붙였다. 에이전트가 [라벨링 가이드](docs/LABELING_GUIDE.md)를 따라 200건 묶음(`data/*_input_NN.jsonl`)마다 라벨 파일을 만들었다.

## 실행

```bash
uv venv .venv-train && uv pip install --python .venv-train -r requirements.txt
# llama.cpp: GGUF 변환용 소스(tools/llama.cpp)와 릴리스 바이너리 b11491(tools/llama-bin/llama-b11491)

scripts/run_final.sh                                     # 학습 → out/q08_final_lora/model-q4_k_m.gguf → 채점
# 학습 대신 공개 모델을 받으려면 (Hugging Face 에서 접근 승인 후)
hf download kairess/used-phone-normalizer-0.8b-gguf used-phone-normalizer-q4_k_m.gguf --local-dir out/hf-model
.venv-train/bin/python scripts/score.py q08_final_lora_q4   # preds/{이름}_g.jsonl 채점 (규칙·Haiku와 함께)
.venv-train/bin/python scripts/js_parity.py              # Python·JS 정규화기 대조 (다른 결과 0건이어야 함)
```

브라우저 경로는 아래 순서로 평가한다. Chrome과 playwright-core가 필요하다.

```bash
web/wllama/fetch.sh && web/wllama/build.sh               # 패치한 wllama → tools/wllama-build/wllama/{esm,compat}
(cd web && npm install)
python3 web/serve.py &                                   # 저장소 루트를 COOP/COEP 헤더와 함께 :8765 로
node web/e2e.mjs "n=1000" res_web.json                   # compat=force 를 붙이면 Safari용 호환 빌드를 시험
# 받은 모델로 돌리려면: node web/e2e.mjs "n=1000&model=../out/hf-model/used-phone-normalizer-q4_k_m.gguf" res_web.json
.venv-train/bin/python scripts/web_preds.py res_web.json q08_final_lora_web && .venv-train/bin/python scripts/score.py q08_final_lora_web
```

앱에서는 다음처럼 쓴다. `LOAD_PARAMS`에 `cache_ram_mib: 0`이 들어 있다. 이 옵션은 패치한 wllama로만 동작하므로, CDN의 공식 빌드를 쓰지 말고 호환 빌드까지 직접 호스팅한다.

```js
import { Wllama } from '<wllama>/esm/index.js';
import { Catalog, Normalizer, LOAD_PARAMS } from './web/normalizer/index.js';
const wl = new Wllama({ default: '<wllama>/esm/wasm/wllama.wasm' });
wl.setCompat({ wasm: '<wllama>/compat/wasm/wllama.wasm', worker: '<wllama>/compat/wasm/wllama.js' });
await wl.loadModelFromUrl(modelUrl, { ...LOAD_PARAMS, n_gpu_layers: hasWebGPU ? 999 : 0 });
const spec = await new Normalizer(wl, new Catalog([apple, samsung])).normalize(title, body);
```

## 데이터

수집한 게시글 원문과 그 라벨은 저장소에 넣지 않았다. 각 플랫폼의 이용약관 문제가 있고, 본문에 개인정보가 섞여 있을 수 있다. 스크립트가 기대하는 파일은 아래와 같다.

| 파일 | 내용 |
|---|---|
| `data/sise.db` | 매물 DB (SQLite `listings`: platform, article_id, url, title, body, ...). 2026-10-07~12에 12.9만 건 수집 |
| `data/eval1k_input.jsonl`, `eval1k_labels_{0..4}.jsonl`, `eval1k_haiku_{0..4}.jsonl` | 평가셋 원문, Opus 정답, Haiku 라벨 |
| `data/train10k_*`, `train2_*` | 학습 원문과 Haiku 라벨 (200건 묶음) |
| `data/train_fix_input_*`, `train_fix_*` | Opus 재판정 요청과 결과 |

한 줄 형식은 `{"uid": "dg_…", "title": …, "body": …}`(원문)과 `{"uid", "post_type", "category", "models", "storage", "color", "condition", "note"}`(라벨)이다.

## 라이선스

[PolyForm Strict 1.0.0](LICENSE). 연구·학습 같은 비상업 목적으로만 쓸 수 있다. 수정하거나 재배포할 수 없고, 상업적으로 이용할 수 없다.

상업적 이용·라이선스 문의: Taehee Lee <kairess87@gmail.com>

`web/wllama/cache-ram.patch`는 [wllama](https://github.com/ngxson/wllama)·[llama.cpp](https://github.com/ggml-org/llama.cpp)(둘 다 MIT) 소스에 대한 패치다. 원본 코드 부분은 MIT 라이선스를 따른다.
