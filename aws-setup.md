# AWS EC2 프리티어 배포 가이드

## 🎯 개요
웹사이트 리뷰 플랫폼을 AWS EC2 프리티어로 마이그레이션하는 완전한 가이드입니다.

## 📋 준비사항

### 1. AWS 계정 및 EC2 설정
1. **AWS 계정 생성** (프리티어 적격)
2. **EC2 인스턴스 생성**:
   - **AMI**: Ubuntu Server 22.04 LTS
   - **인스턴스 타입**: t2.micro (프리티어)
   - **스토리지**: 30GB gp3 (프리티어 한도)
   - **키 페어**: 새로 생성하거나 기존 사용

### 2. 보안 그룹 설정
```
인바운드 규칙:
- SSH (22): 내 IP만 허용
- HTTP (80): 0.0.0.0/0
- HTTPS (443): 0.0.0.0/0

아웃바운드 규칙:
- 모든 트래픽: 0.0.0.0/0
```

### 3. Elastic IP 할당 (선택사항)
프로덕션에서는 고정 IP 권장

## 🚀 배포 과정

### 1단계: 서버 접속 및 초기 설정
```bash
# SSH 접속
ssh -i "your-key.pem" ubuntu@your-ec2-ip

# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 필수 패키지 설치
sudo apt install -y git curl wget unzip
```

### 2단계: 프로젝트 클론 및 환경 설정
```bash
# 프로젝트 클론
git clone https://github.com/your-username/webrating.git
cd webrating/backend

# 환경변수 설정
cp .env.example .env
nano .env  # 실제 값으로 수정
```

### 3단계: 배포 스크립트 실행
```bash
# 스크립트 실행 권한 부여
chmod +x deploy.sh

# 배포 실행
./deploy.sh
```

## 🔧 환경변수 설정

### .env 파일 예시
```bash
# Supabase 설정
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key

# Google OAuth 설정  
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# JWT 설정
SECRET_KEY=your-super-secret-key-here

# CORS 설정 (프로덕션 도메인으로 변경)
CORS_ORIGINS=https://yourdomain.com

# 환경 설정
ENVIRONMENT=production
LOG_LEVEL=INFO
```

## 🔒 SSL 인증서 설정

### AWS 관리형 SSL 사용 (권장)
AWS에서 SSL 인증서를 관리하므로 별도 설정이 불필요합니다:

1. **Application Load Balancer (ALB) 사용**:
   - ALB에 SSL 인증서 연결
   - EC2 인스턴스는 HTTP(80)만 처리
   - ALB가 HTTPS 종료 담당

2. **CloudFront 사용**:
   - CloudFront에 SSL 인증서 연결  
   - Origin(EC2)은 HTTP로 통신
   - CloudFront가 HTTPS 종료 담당

### 수동 SSL 설정 (필요시에만)
```bash
# Let's Encrypt 사용 (직접 도메인 연결시)
sudo apt install -y certbot
sudo certbot certonly --standalone -d yourdomain.com
```

## 📊 모니터링 및 로그

### 서비스 상태 확인
```bash
# 컨테이너 상태
docker-compose ps

# 실시간 로그
docker-compose logs -f

# 시스템 리소스
docker stats

# 디스크 사용량
df -h
```

### 로그 위치
- **애플리케이션 로그**: `./logs/`
- **Nginx 로그**: `./logs/nginx/`
- **Docker 로그**: `docker-compose logs`

## 🛡️ 보안 설정

### 1. 방화벽 설정
```bash
# UFW 활성화
sudo ufw enable

# 필수 포트만 허용
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### 2. SSH 보안 강화
```bash
# SSH 설정 수정
sudo nano /etc/ssh/sshd_config

# 다음 설정 추가/수정:
# PasswordAuthentication no
# PermitRootLogin no
# Port 2222  # 기본 포트 변경 (선택사항)

# SSH 재시작
sudo systemctl restart ssh
```

### 3. Fail2Ban 설치
```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

## 💰 비용 최적화

### 프리티어 한도 모니터링
- **EC2**: t2.micro 인스턴스 750시간/월
- **EBS**: 30GB 범용 SSD
- **데이터 전송**: 15GB 아웃바운드

### 비용 절약 팁
1. **인스턴스 스케줄링**: 개발 중이 아닐 때 중지
2. **EBS 최적화**: 사용하지 않는 스냅샷 삭제
3. **로그 로테이션**: 디스크 공간 관리
4. **이미지 최적화**: Supabase Storage 활용

## 🔄 업데이트 및 롤백

### 애플리케이션 업데이트
```bash
# Git pull
git pull origin main

# 재배포
./deploy.sh
```

### 롤백 방법
```bash
# 이전 버전으로 되돌리기
git checkout previous-commit-hash

# 재배포
./deploy.sh
```

## 🆘 문제해결

### 일반적인 문제들

#### 1. 컨테이너 시작 실패
```bash
# 로그 확인
docker-compose logs web

# 환경변수 확인
docker-compose config
```

#### 2. HTTP 연결 문제
```bash
# 포트 80 확인
sudo netstat -tulpn | grep :80

# Nginx 설정 테스트
docker exec nginx nginx -t

# ALB/CloudFront 설정 확인 (AWS 콘솔에서)
```

#### 3. 데이터베이스 연결 오류
```bash
# Supabase 연결 테스트
curl -H "apikey: your-anon-key" "https://your-project.supabase.co/rest/v1/"
```

### 성능 문제

#### 메모리 부족
```bash
# 스왑 파일 생성
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 영구 적용
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 📞 지원 및 문의

### 유용한 명령어
```bash
# 전체 시스템 상태 확인
sudo systemctl status

# 디스크 사용량 상세 분석
sudo du -sh /* | sort -rh

# 네트워크 연결 확인
sudo netstat -tulpn | grep LISTEN

# 프로세스 확인
sudo ps aux | grep python
```

### 로그 모니터링
```bash
# 실시간 로그 모니터링
tail -f logs/nginx/access.log

# 에러 로그만 확인
grep -i error logs/nginx/error.log
```

이 가이드를 따라하면 AWS EC2 프리티어에서 안정적으로 웹사이트 리뷰 플랫폼을 운영할 수 있습니다.