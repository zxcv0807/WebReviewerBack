#!/bin/bash

set -e

echo "🚀 새로운 버전의 배포를 시작합니다..."

echo "➡️ 1. .env 파일을 백업하고 로컬 변경사항을 정리합니다..."
# .env 파일이 있다면 백업
if [ -f .env ]; then
  cp .env .env.backup
  echo ".env 파일을 백업했습니다."
fi

# 추적되지 않는 파일을 포함한 모든 변경사항을 임시 저장 (.env 제외)
git stash
# 원격 저장소의 코드로 강제 초기화
git reset --hard HEAD

# .env 파일 복원
if [ -f .env.backup ]; then
  mv .env.backup .env
  echo ".env 파일을 복원했습니다."
fi

echo "➡️ 2. 최신 코드를 가져옵니다 (git pull)..."
git pull

echo "➡️ 3. 기존 컨테이너를 중지합니다 (docker-compose down)..."
sudo docker-compose down

echo "➡️ 4. 새로운 이미지를 빌드합니다 (docker-compose build)..."
sudo docker-compose build

echo "➡️ 5. 새로운 컨테이너를 시작합니다 (docker-compose up -d)..."
sudo docker-compose up -d

echo "➡️ 6. 사용하지 않는 Docker 이미지를 정리하여 디스크 공간을 확보합니다..."
sudo docker image prune -f

echo "✅ 배포가 성공적으로 완료되었습니다!"