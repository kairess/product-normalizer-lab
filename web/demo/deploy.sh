#!/usr/bin/env bash
# 데모 사이트를 만들어 gh-pages 브랜치에 올린다 (매번 커밋 하나로 덮어쓴다).
#   web/demo/deploy.sh
# 처음 한 번은 저장소 설정에서 Pages 를 켠다:
#   gh api -X POST repos/kairess/product-normalizer-lab/pages -f 'source[branch]=gh-pages' -f 'source[path]=/'
# → https://kairess.github.io/product-normalizer-lab/
set -eu
cd "$(dirname "$0")/../.."
web/demo/build.sh
REMOTE=$(git remote get-url origin)
REV=$(git rev-parse --short HEAD)
cd out/site
git init -q -b gh-pages
git add -A
git commit -qm "Deploy demo from $REV"
git push -f "$REMOTE" gh-pages
rm -rf .git
