#!/bin/bash

# 에러 발생 시 스크립트 중단
set -e

echo "🚀 새로운 버전의 배포를 시작합니다..."

# 1. Git 저장소의 코드로 로컬 변경사항을 강제 초기화합니다.
echo "➡️ 1. 로컬 코드를 원격 저장소 기준으로 초기화합니다 (git reset)..."
git reset --hard HEAD

# 2. 최신 코드를 가져옵니다.
echo "➡️ 2. 최신 코드를 가져옵니다 (git pull)..."
git pull

# 3. 기존에 실행 중인 컨테이너를 중지하고 삭제합니다.
echo "➡️ 3. 기존 컨테이너를 중지합니다 (docker-compose down)..."
sudo docker-compose down

# ... (이하 동일) ...