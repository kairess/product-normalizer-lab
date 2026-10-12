#!/bin/bash
# 패치한 wllama 를 docker 없이 로컬 emsdk 로 빌드한다 (scripts/docker-compose.yml 의 절차와 같음).
#   web/wllama/fetch.sh && web/wllama/build.sh
#   → tools/wllama-build/wllama/esm (브라우저용 패키지), tools/wllama-build/wllama/compat/wasm (Safari 등 JSPI 없는 브라우저용)
# cmake·ninja 가 필요하다 (PATH 에 없으면 tools/wllama-build/.venv 에 설치해 두면 쓴다).
set -e
cd "$(dirname "$0")/../../tools/wllama-build"
export PATH="$PWD/.venv/bin:$PATH"
source emsdk/emsdk_env.sh > /dev/null
cd wllama
EMDAWN=$PWD/build/emdawn/emdawnwebgpu_pkg

mkdir -p build && cd build
emcmake cmake -G Ninja .. -DGGML_WEBGPU=ON -DGGML_WEBGPU_JSPI=ON -DEMDAWNWEBGPU_DIR="$EMDAWN" -DWLLAMA_TEST_BACKEND=OFF > ../../cmake.log
cmake --build . --target wllama -j 12
cd ..
mkdir -p src/wasm && cp build/wllama.js build/wllama.wasm src/wasm/

if [ -z "$SKIP_COMPAT" ]; then
  mkdir -p build-compat && cd build-compat
  emcmake cmake -G Ninja .. -DWLLAMA_COMPAT=ON -DLLAMA_WASM_MEM64=OFF -DGGML_WEBGPU=ON -DGGML_WEBGPU_JSPI=OFF -DEMDAWNWEBGPU_DIR="$EMDAWN" -DWLLAMA_TEST_BACKEND=OFF > ../../cmake-compat.log
  cmake --build . --target wllama -j 12
  cd ..
  mkdir -p compat/wasm && cp build-compat/wllama.js build-compat/wllama.wasm compat/wasm/
fi

[ -d node_modules ] || npm ci --no-audit --no-fund
npm run build:glue
rm -rf esm
npm run build:worker
# 얕은 clone 이라 llama.cpp 빌드 번호를 못 센다 (git rev-list --count = 1). 고정한 커밋의 번호로 바로잡는다
sed -i "s/LIBLLAMA_VERSION = 'b1-46ca246'/LIBLLAMA_VERSION = 'b11364-46ca246'/" src/workers-code/generated.ts
npx tsup src/index.ts --format cjs,esm --clean
npx terser esm/index.js -o esm/index.min.js --compress --mangle --source-map
npx tsc --emitDeclarationOnly --declaration -p tsconfig.build.json
./scripts/post_build.sh
echo BUILD_DONE
