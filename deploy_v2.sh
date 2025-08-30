#!/bin/bash

set -e

echo "🚀 새로운 버전의 배포를 시작합니다..."

echo "➡️ 1. 작업 공간을 정리하고 최신 코드를 가져옵니다..."
# 로컬 변경사항을 무시하고 원격 저장소의 main 브랜치와 강제로 동기화합니다.
git fetch origin
git reset --hard origin/main

# ✏️ git 작업 이후에 .env 파일을 생성하여 삭제되는 것을 방지합니다.
echo "➡️ 2. GitHub Secret으로부터 .env 파일을 생성합니다..."
if [ -z "$ENV_FILE_CONTENT" ]; then
  echo "🚨 에러: ENV_FILE_CONTENT 환경 변수가 설정되지 않았습니다."
  exit 1
fi
echo "$ENV_FILE_CONTENT" > .env
echo ".env 파일 생성이 완료되었습니다."

echo "➡️ 3. Docker 컨테이너를 다시 빌드하고 시작합니다..."
sudo docker-compose up --build -d

echo "➡️ 4. 사용하지 않는 Docker 이미지를 정리하여 디스크 공간을 확보합니다..."
sudo docker image prune -f

echo "✅ 배포가 성공적으로 완료되었습니다!"