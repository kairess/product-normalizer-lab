#!/bin/bash
# wllama 3.8.1 소스(+ llama.cpp 46ca246)를 받아 cache-ram.patch 를 적용하고, emsdk 4.0.20·emdawn 을 받는다.
# 작업 폴더는 tools/wllama-build (git 제외).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HERE/../../tools/wllama-build" && cd "$HERE/../../tools/wllama-build"
if [ ! -d wllama ]; then
  git clone --depth 1 --branch 3.8.1 https://github.com/ngxson/wllama.git
  cd wllama
  git submodule update --init --depth 1 llama.cpp || (cd llama.cpp && git fetch --depth 1 origin 46ca246de9bb1c35269722a6240d37d9dfd79cad && git checkout FETCH_HEAD)
  git apply "$HERE/cache-ram.patch"   # cache_ram_mib·n_ctx_checkpoints 옵션 노출 (요청마다 메모리가 쌓여 70여 건 만에 멈추는 문제)
  cd ..
fi
if [ ! -d emsdk ]; then
  git clone --depth 1 https://github.com/emscripten-core/emsdk.git
  cd emsdk && ./emsdk install 4.0.20 && ./emsdk activate 4.0.20 && cd ..
fi
mkdir -p wllama/build/emdawn
if [ ! -d wllama/build/emdawn/emdawnwebgpu_pkg ]; then
  DAWN_TAG=v20260317.182325
  curl -L -o wllama/build/emdawn.zip "https://github.com/google/dawn/releases/download/${DAWN_TAG}/emdawnwebgpu_pkg-${DAWN_TAG}.zip"
  python3 -c "import zipfile; zipfile.ZipFile('wllama/build/emdawn.zip').extractall('wllama/build/emdawn')"
fi
echo FETCH_DONE
