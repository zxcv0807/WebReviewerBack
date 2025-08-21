#!/bin/bash

# AWS EC2 배포 스크립트
# 사용법: ./deploy.sh

set -e  # 오류 시 스크립트 중단

echo "🚀 AWS EC2 배포 시작..."

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 환경변수 검증
check_env() {
    echo -e "${BLUE}📋 환경변수 검증 중...${NC}"
    
    if [ ! -f .env ]; then
        echo -e "${RED}❌ .env 파일이 없습니다. .env.example을 참고하여 생성하세요.${NC}"
        exit 1
    fi
    
    source .env
    
    required_vars=("SUPABASE_URL" "SUPABASE_ANON_KEY" "GOOGLE_CLIENT_ID" "GOOGLE_CLIENT_SECRET" "SECRET_KEY")
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            echo -e "${RED}❌ $var 환경변수가 설정되지 않았습니다.${NC}"
            exit 1
        fi
    done
    
    echo -e "${GREEN}✅ 환경변수 검증 완료${NC}"
}

# Docker 설치 및 확인
setup_docker() {
    echo -e "${BLUE}🐳 Docker 설정 확인 중...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "${YELLOW}📦 Docker 설치 중...${NC}"
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $USER
        rm get-docker.sh
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${YELLOW}📦 Docker Compose 설치 중...${NC}"
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
    fi
    
    echo -e "${GREEN}✅ Docker 설정 완료${NC}"
}

# SSL 인증서 설정
setup_ssl() {
    echo -e "${BLUE}🔒 SSL 인증서 설정 중...${NC}"
    
    # SSL 디렉토리 생성
    sudo mkdir -p /etc/nginx/ssl
    
    # 자체 서명된 인증서 생성 (프로덕션에서는 Let's Encrypt 사용 권장)
    if [ ! -f /etc/nginx/ssl/cert.pem ]; then
        echo -e "${YELLOW}🔑 자체 서명된 SSL 인증서 생성 중...${NC}"
        sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout /etc/nginx/ssl/key.pem \
            -out /etc/nginx/ssl/cert.pem \
            -subj "/C=KR/ST=Seoul/L=Seoul/O=WebRating/CN=localhost"
    fi
    
    echo -e "${GREEN}✅ SSL 인증서 설정 완료${NC}"
}

# 방화벽 설정
setup_firewall() {
    echo -e "${BLUE}🔥 방화벽 설정 중...${NC}"
    
    # UFW 설치 및 설정
    if command -v ufw &> /dev/null; then
        sudo ufw --force enable
        sudo ufw allow ssh
        sudo ufw allow 80/tcp
        sudo ufw allow 443/tcp
        echo -e "${GREEN}✅ 방화벽 설정 완료${NC}"
    else
        echo -e "${YELLOW}⚠️  UFW가 설치되지 않았습니다. 수동으로 방화벽을 설정하세요.${NC}"
    fi
}

# 애플리케이션 배포
deploy_app() {
    echo -e "${BLUE}🚀 애플리케이션 배포 중...${NC}"
    
    # 기존 컨테이너 중지 및 제거
    docker-compose down --remove-orphans || true
    
    # 이미지 빌드
    echo -e "${YELLOW}🔨 Docker 이미지 빌드 중...${NC}"
    docker-compose build --no-cache
    
    # 로그 디렉토리 생성
    mkdir -p logs/nginx
    
    # 컨테이너 시작
    echo -e "${YELLOW}▶️ 컨테이너 시작 중...${NC}"
    docker-compose up -d
    
    # 서비스 상태 확인
    sleep 10
    if docker-compose ps | grep -q "Up"; then
        echo -e "${GREEN}✅ 애플리케이션 배포 완료${NC}"
    else
        echo -e "${RED}❌ 애플리케이션 시작 실패${NC}"
        docker-compose logs
        exit 1
    fi
}

# 헬스체크
health_check() {
    echo -e "${BLUE}🏥 헬스체크 중...${NC}"
    
    # 최대 30초 대기
    for i in {1..30}; do
        if curl -f http://localhost/health &> /dev/null; then
            echo -e "${GREEN}✅ 서비스가 정상적으로 실행 중입니다!${NC}"
            return 0
        fi
        echo -e "${YELLOW}⏳ 서비스 시작 대기 중... ($i/30)${NC}"
        sleep 1
    done
    
    echo -e "${RED}❌ 헬스체크 실패. 로그를 확인하세요.${NC}"
    docker-compose logs web
    exit 1
}

# 배포 완료 메시지
completion_message() {
    echo -e "\n${GREEN}🎉 배포 완료!${NC}"
    echo -e "${BLUE}📋 서비스 정보:${NC}"
    echo -e "  • 웹 서비스: https://$(curl -s ifconfig.me || echo 'YOUR_SERVER_IP')"
    echo -e "  • API 문서: https://$(curl -s ifconfig.me || echo 'YOUR_SERVER_IP')/docs"
    echo -e "  • 헬스체크: https://$(curl -s ifconfig.me || echo 'YOUR_SERVER_IP')/health"
    echo -e "\n${YELLOW}📊 모니터링:${NC}"
    echo -e "  • 로그 확인: docker-compose logs -f"
    echo -e "  • 서비스 상태: docker-compose ps"
    echo -e "  • 리소스 사용량: docker stats"
}

# 메인 실행
main() {
    echo -e "${GREEN}🌟 Web Rating Backend 배포 스크립트${NC}"
    echo -e "${BLUE}=====================================${NC}"
    
    check_env
    setup_docker
    setup_ssl
    setup_firewall
    deploy_app
    health_check
    completion_message
}

# 스크립트 실행
main "$@"