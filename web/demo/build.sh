#!/usr/bin/env bash
# GitHub Pages 에 올릴 데모 사이트를 out/site 에 만든다. 패치한 wllama 빌드(web/wllama/build.sh)가 먼저 있어야 한다.
#   web/demo/build.sh            # 모델은 Hugging Face 에서 받는다 (배포용)
#   web/demo/build.sh --local    # 모델을 out/q08_final_lora/model-q4_k_m.gguf 에서 링크한다 (오프라인 미리보기)
#   python3 web/serve.py 8780 --root out/site --host 0.0.0.0
set -eu
cd "$(dirname "$0")/../.."
SITE=out/site
W=tools/wllama-build/wllama
MODEL_URL=https://huggingface.co/kairess/used-phone-normalizer-0.8b-gguf/resolve/main/used-phone-normalizer-q4_k_m.gguf

rm -rf $SITE
mkdir -p $SITE/normalizer $SITE/data $SITE/wllama/esm/wasm $SITE/wllama/compat/wasm
cp web/demo/{index.html,style.css,app.js,examples.js,coi-serviceworker.js} $SITE/
cp web/normalizer/*.js $SITE/normalizer/
cp normalizer/data/catalog_*.json $SITE/data/
cp $W/esm/index.js $SITE/wllama/esm/
cp $W/esm/wasm/wllama.wasm $SITE/wllama/esm/wasm/
cp $W/compat/wasm/wllama.js $W/compat/wasm/wllama.wasm $SITE/wllama/compat/wasm/
cp $W/LICENCE $SITE/wllama/LICENSE
touch $SITE/.nojekyll

if [ "${1:-}" = --local ]; then
  mkdir -p $SITE/model
  ln -s "$PWD/out/q08_final_lora/model-q4_k_m.gguf" $SITE/model/used-phone-normalizer-q4_k_m.gguf
  MODEL_URL=model/used-phone-normalizer-q4_k_m.gguf
fi
cat > $SITE/config.js <<JS
export const MODEL_URL = '$MODEL_URL';
export const MODEL_MB = 529;
JS
echo "$SITE ($(du -sh --exclude=model $SITE | cut -f1)) · 모델 $MODEL_URL"
