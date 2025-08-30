#!/bin/bash

set -e

echo "🚀 새로운 버전의 배포를 시작합니다..."

echo "➡️ 1. GitHub Secrets로부터 .env 파일을 생성합니다..."
# ENV_CONTENT 환경변수가 있다면 .env 파일 생성
if [ ! -z "$ENV_CONTENT" ]; then
  echo "$ENV_CONTENT" > .env
  echo "✅ .env 파일을 성공적으로 생성했습니다."
else
  echo "⚠️  ENV_CONTENT 환경변수가 설정되지 않았습니다. 기존 .env 파일을 사용합니다."
fi

echo "➡️ 2. 로컬 변경사항을 임시 저장하고 작업 공간을 초기화합니다..."
# .env 파일 보호를 위해 임시 백업
if [ -f .env ]; then
  cp .env .env.backup
fi

# 추적되지 않는 파일을 포함한 모든 변경사항을 임시 저장
git stash
# 원격 저장소의 코드로 강제 초기화
git reset --hard HEAD

# .env 파일 복원
if [ -f .env.backup ]; then
  mv .env.backup .env
fi

echo "➡️ 3. 최신 코드를 가져옵니다 (git pull)..."
git pull

echo "➡️ 4. .env 파일 내용 확인 및 권한 설정..."
if [ -f .env ]; then
  echo "📄 .env 파일 존재 확인: ✅"
  echo "📄 .env 파일 크기: $(wc -c < .env) bytes"
  chmod 600 .env  # .env 파일 보안 권한 설정
else
  echo "❌ .env 파일이 존재하지 않습니다!"
fi

echo "➡️ 5. 기존 컨테이너를 중지합니다 (docker-compose down)..."
sudo docker-compose down

echo "➡️ 6. 새로운 이미지를 빌드합니다 (docker-compose build)..."
sudo docker-compose build

echo "➡️ 7. 새로운 컨테이너를 시작합니다 (docker-compose up -d)..."
sudo docker-compose up -d

echo "➡️ 8. 사용하지 않는 Docker 이미지를 정리하여 디스크 공간을 확보합니다..."
sudo docker image prune -f

echo "✅ 배포가 성공적으로 완료되었습니다!"