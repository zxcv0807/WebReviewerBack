#AWS EC2 배포를 하면서

##개요
시스템 아키텍처는 다음과 같은 흐름을 따른다. 
사용자의 요청은 먼저 AWS의 DNS 서비스인 Route 53을 통해 EC2 인스턴스의 고정 IP주소로 전달된다.
EC2 인스턴스 내부에서는 Nginx가 요청을 받아, 리버스 프록시를 통해 트래픽을 전달한다. 이 때, SSL/TLS 인증서를 통해 모든 통신은 암호화(HTTPS)가 되어 보안을 확보한다. 
또한 AWS의 로드밸런서(ALB)를 도입하여 SSL 처리 및 트래픽 분산을 더욱 효율적으로 관리하였다. 

## 1. AWS EC2 기반의 핵심 인프라 구축

### EC2 인스턴스 생성
AWS Management Console을 통해 EC2 인스턴스를 생성.
리전은 한국 사용자를 위한 서울 리전을 선택.
운영체제는 ubuntu를 사용했다. Amazon Linux와 ubuntu중, ubuntu가 장기간의 보안 업데이트와 안정적인 지원을 보장하며, 방대한 커뮤니티와 자료가 존재한다는 것이 매력적이라고 생각했다.
t3.micro 프리티어를 선택하여 최소한의 비용으로 시작. 

### 로컬에서 접속(SSH)
인스턴스를 생성할 때, .pem 파일을 잘 보관해두었다가, 로컬에서 터미널로 해당 파일에 있는 폴더로 이동하여,
다운로드한 파일을 소유자만 읽을 수 있도록 한 뒤, ec2에 접속한다.
```bash
chmod 400 your-key.pem
ssh -i "your-key.pem" ubuntu@your-ip
```
이는 공개 키 암호화 방식을 사용하는 것이다. 

### FastAPI 배포 준비
패키지 업데이트
```bash
sudo apt update -y && sudo apt upgrade -y
```
Docker 설치
```bash
sudo apt install docker.io -y
sudo systemctl start docker
sudo systemctl enable docker
```
깃허브에서 가져오기
```bash
git clone your-repository
```
Dockerfile 작성 후, 컨테이너 실행
```bash
docker run -d -p 80:8000 your-directory
```

## 2. SSL 인증

### 탄력적 IP 할당
EC2 인스턴스를 생성하면 기본적으로 동적 퍼블릭 IP주소가 할당된다. 이를 해결하기 위해 탄력적 IP를 사용한다. 이는 사용자의 AWS 계정에 귀속되는 고정된 퍼블릭 IPv4 주소이다.

### 보안 그룹
인바운드 규칙과 아웃바운드 규칙으로 나뉜다.
인바운드는 외부에서 인스턴스로 들어오는 트래픽을, 아웃바운드는 인스턴스에서 외부로 나가는 트래픽을 제어한다. 일반적으로 아웃바운드는 모든 트래픽을 허용하도록 기본 설정되어 있다. 

- 인바운드 규칙
SSH(포트 22): 현재 작업 중인 내 IP만 접근을 허용하여, 보안을 유지한다.
HTTP(포트 80): 일반적인 웹 트래픽을 허용하는 규칙.
HTTPS(포트 443): SSL/TLS 인증서가 적용된 후의 암호화된 웹 트래픽을 허용하는 규칙.

### 도메인 마련
비용 절감을 위해, 도메인 등록 업체 중에서 가장 저렴한 도메인을 구입.

### EC2 인스턴스와 도메인 연결
- AWS Management Console에서 Route 53으로 이동
- 호스팅 영역 생성
- 레코드 생성
- 'A 레코드' 유형을 선택하고, 할당받은 탄력적 IP주소를 입력
- '도메인 구매처의 DNS 설정으로 이동하여 Route 53에 네임서버 4개를 붙여넣기

### AWS에서 제공해주는 무료 SSL 인증서 발급 및 적용
- AWS Management Console에서 Certificate Manager로 이동
- '인증서 요청' 클릭 후, '퍼블릭 인증서 요청' 선택
- 내 도메인을 추가
- DNS 검증을 선택 후, 요청
- 인증서 세부 페이지에서 'Route 53에서 레코드 생성' 클릭하면 자동으로 추가됨.
- 로드 밸런서에 연결해서 사용해야하기에, 로드 밸런서 메뉴로 이동하여 ALB 생성
- 리스터 설정에서 HTTPS 프로토콜 추가, '보안 리스너 설정'에서 방금 발급받은 인증서를 선택
- 로드 밸런서가 요청을 전달할 대상 그룹으로 내 EC2 인스턴스 지정
- Route 53으로 돌아가, 이전에 생성했던 A 레코드의 대상을 EC2 IP 주소에서 새로 생성한 로드 밸런서의 DNS 이름으로 변경.

### trouble shooting
도메인은 비용, 목적, 신뢰도에서 차이를 가진다.
나는 최소한의 비용을 위해, 신뢰도가 떨어질 수 있지만, 저렴한 도메인을 선택했다.

EC2 서비스에서 Status를 확인했을 때, healthy, unhealthy가 아닌 unused가 보인다면, 가용 영역의 불일치 문제일 수 있다.
EC2 인스턴스의 세부 정보에서 가용 영역이, 로드 밸런서의 가용 영역 및 서브넷 목록에 포함되어 있는지 확인하고, 포함되어 있지 않다면, 네트워크 매핑 섹션에서 서브넷 편집을 통해 수정해야 한다.

로드 밸런서의 보안 그룹 vs EC2 인스턴스의 보안 그룹
로드 밸랜서의 보안 그룹: 인터넷의 모든 사용자의 접속(HTTP, HTTPS)을 허용하는 역할
EC2 인스턴스의 보안 그룹: 오직 로드 밸런서의 요청만 허용하는 역할

사용자의 요청은 HTTPS로 로드 밸런서에 도착하고, 로드 밸런서는 SSL 처리를 끝내고, 암호화되지 않는 HTTP 요청을 EC2 인스턴스로 보낸다.
EC2 안의 FastAPI는 로드 밸런서로부터 HTTP 요청을 받았기에 다른 리소스를 생성할 때, http://로 시작하는 주소를 만들게 된다.
=> FastAPI에게 "우리는 로드 밸런서 뒤에서 작동하고 있으니, 로드 밸런서가 전달해주는 요청을 믿어라" 라고 알려주어야 한다.


## 3. CI/CD
1) Github actions runner를 사용하는 방법.(이전 방법)
로컬 컴퓨터 터미널에서 Github Actions(로봇)이 EC2 서버에 접속할 때 사용할 전용 열쇠를 만든다.
```bash
ssh-keygen -t rsa -b 4096 -C "github-actions" -f github-actions-key
```
실행하면 github-actions-key(비밀키)와 github-actions-key.pub(공개키)가 생성된다.

github-actions-key.pub을 EC2 서버에 추가하고,
Github 저장소에서 Settings > Secrets and variables > Actions 로 이동, New repository secret을 눌러 아래의 정보를 등록한다.
AWS_EC2_HOST: EC2 퍼블릭 IP 주소
AWS_EC2_USERNAME: EC2 접속 사용자 이름 (보통 ubuntu)
AWS_EC2_SSH_PRIVATE_KEY: github-actions-key의 전체 내용을 붙여넣는다.

로컬의 프로젝트 폴더 안에 .github/workflows 라는 폴더를 만든다.
그 안에 deploy.yml이라는 파일을 만들고 코드를 작성한다.

### trouble shooting
Github Actions IP에 SSH를 허용하여 실제로 CI/CD가 적용되는지 확인하기 위해서, 
EC2 서비스에서 보안 그룹의 인바운드 규칙을 편집하여 SSH TCP (22 port) Anywhere-IPv4 규칙을 추가했다.
하지만 이는 모든 주소에서 ssh 접속을 허용하기 때문에, 보안에 굉장히 취약하다.
그래서 해결방법을 알아보니, Github의 actions 섹션의 모든 IP주소를 보안 그룹에 등록해야 한다. 하지만 IP주소가 너무 많아, 다른 방법을 찾아보았는데, 보안까지 해결해주는 방법 중 하나인 self-hosted를 내 프로젝트에 적용하기로 결정했다.

2) self-hosted를 통한 CI/CD (현재 방법)
### EC2 인스턴스를 Github Actions를 위한 러너로 등록
- Github 프로젝트 저장소로 이동
- Settings > Actions > Runners > New self-hosted runner 클릭
- OS는 Linux, 아키텍처는 x64
- EC2 인스턴스에 SSH로 접속한 뒤, Github페이지에서 보이는 모든 명령어 실행. 이 때, ./run.sh는 ssh 접속을 끊으면 러너가 종료되기 때문에 아래의 명령어를 사용해 항상 러너가 켜져 있게 함.
```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

### deploy.yml 수정 및 보안 관리
기존의 appleboy/ssh-action을 모두 삭제하면서, 수정

EC2 보안그룹에서 이전에 Github Actions를 위해 추가했던 ssh 규칙 제거.
Github 저장소에서 필요없어진 Secret 제거 
(AWS_EC2_HOST, AWS_EC2_USERNAME, AWS_EC2_SSH_PRIVATE_KEY)

### trouble shooting
Github Actions Runner에서 self-hosted runner로 변경하면 .env파일 부재를 해결해야한다.

Github Actions에서는 Github(외부인)이 EC2에 들어와서 작업을 하여 항상 .env파일이 존재했고, git pull을 통해 변경된 것을 적용해주는 방식이다.
Self-Hosted는 자동화 로봇이 매번 임시 작업 폴더를 배정받고, 배포작업을 하기 때문이다.
그래서 .env파일을 Github Secret에 등록을 하고, .github/workflows/deploy.yml 파일에서 Github Secret을 사용하여 .env 파일을 생성하는 코드를 추가해야한다.

이는 서버에 수동으로 어떤 파일을 놓아두었는지에 따라 배포가 성공하거나 실패하는 '상태 의존적인 배포'를 방지하고, Git 저장소의 코드와 Github Secrets의 설정만으로 언제나 동일한 결과를 보장하는 현대적인 DevOps의 핵심 원칙이다.


## 그 외 명령어들

현재 실행중인 컨테이너의 목록 확인
```bash
sudo docker ps
```
실행 중이거나, 종료되었거나, 에러가 발생한 모든 컨테이너의 목록 확인
```bash
sudo docker ps -a
```
특정 컨테이너의 내부에서 출력되는 모든 로그 확인
```bash
sudo docker logs 컨테이너_이름_또는_ID
sudo docker-compose logs 컨테이너_이름_또는_ID
```
디스크 사용량 확인
```bash
df -h
```
사용하지 않는 docker 리소스 제거
```bash
docker system prune -a -f
```