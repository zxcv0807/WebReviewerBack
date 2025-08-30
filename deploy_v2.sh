#!/bin/bash

set -e

echo "🚀 새로운 버전의 배포를 시작합니다..."

echo "➡️ 1. 로컬 변경사항을 임시 저장하고 작업 공간을 초기화합니다..."
# 추적되지 않는 파일을 포함한 모든 변경사항을 임시 저장
git stash
# 원격 저장소의 코드로 강제 초기화
git reset --hard HEAD

echo "➡️ 2. 최신 코드를 가져옵니다 (git pull)..."
git pull

# ✏️ git 작업 이후에 .env 파일을 생성하여 삭제되는 것을 방지합니다.
echo "➡️ 3. GitHub Secret으로부터 .env 파일을 생성합니다..."
if [ -z "$ENV_FILE_CONTENT" ]; then
  echo "🚨 에러: ENV_FILE_CONTENT 환경 변수가 설정되지 않았습니다."
  exit 1
fi
echo "$ENV_FILE_CONTENT" > .env
echo ".env 파일 생성이 완료되었습니다."

echo "➡️ 4. Docker 컨테이너를 다시 빌드하고 시작합니다..."
sudo docker-compose up --build -d

echo "➡️ 5. 사용하지 않는 Docker 이미지를 정리하여 디스크 공간을 확보합니다..."
sudo docker image prune -f

echo "✅ 배포가 성공적으로 완료되었습니다!"