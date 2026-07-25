# Appointly

通用多租户预约 SaaS 后端。技术栈：Django 5.2、DRF、MySQL 8.4、Redis 7、RabbitMQ 4、Celery 5。

详细需求见 [`.scratch/appointment-saas/PRD.md`](.scratch/appointment-saas/PRD.md)。

## 前置条件

| 工具 | 版本 | 说明 |
|------|------|------|
| Python | 3.12 | 通过 `uv python pin 3.12` 管理 |
| uv | 最新 | Python 包与虚拟环境 |
| Docker Desktop | 最新 | 本地 MySQL / Redis / RabbitMQ |
| Git | 最新 | 代码与 CI |

## 本地开发（Windows PowerShell）

### 1. 克隆并进入项目

```powershell
git clone git@github.com:Hanzlgit/appointly.git
cd appointly
```

### 2. 安装 Python 依赖

```powershell
uv python pin 3.12
uv sync --group dev
```

### 3. 配置环境变量

```powershell
Copy-Item .env.example .env
# 本地默认值可直接使用，无需修改
```

### 4. 启动基础设施

```powershell
docker compose up -d
docker compose ps   # 确认 mysql / redis / rabbitmq 均为 healthy
```

服务端口：

- MySQL: `3306`
- Redis: `16379`（容器内仍为 6379；Windows 常保留 6379）
- RabbitMQ AMQP: `25672`（容器内仍为 5672；Windows 常保留 5672），管理界面: http://localhost:15672（用户/密码 `appointly`）

### 5. 初始化数据库并启动

```powershell
uv run python manage.py migrate
uv run python manage.py runserver
```

验证：

- 健康检查: http://127.0.0.1:8000/health/live
- API 文档: http://127.0.0.1:8000/api/docs/
- Ping: http://127.0.0.1:8000/api/v1/ping/

### 6. 代码质量（可选）

```powershell
uv run pre-commit install
uv run ruff check .
uv run ruff format --check .
uv run python manage.py test
```

### 7. Celery（可选，需 RabbitMQ 已启动）

```powershell
# 终端 1
uv run celery -A config worker -l info

# 终端 2
uv run celery -A config beat -l info
```

## GitHub 配置

仓库地址：https://github.com/Hanzlgit/appointly

### 首次推送

```powershell
git add .
git commit -m "chore: bootstrap project environment"
git push -u origin main
```

### CI（自动）

PR 和 push 到 `main` 会触发 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)：

- Ruff check / format
- MySQL 上运行 Django 测试

### CD（需手动配置）

#### 1. GitHub Environments

在仓库 **Settings → Environments** 创建 `production` 环境，并启用 **Required reviewers**（人工确认发布）。

#### 2. GitHub Secrets

在 **Settings → Secrets and variables → Actions** 添加：

| Secret | 说明 |
|--------|------|
| `DEPLOY_HOST` | 云服务器 IP 或域名 |
| `DEPLOY_USER` | SSH 用户名（如 `ubuntu`） |
| `DEPLOY_SSH_KEY` | 部署用 SSH 私钥（完整内容） |

应用密钥（`DJANGO_SECRET_KEY`、数据库密码等）**不要**放进 GitHub Secrets，保留在服务器 `deploy/.env` 中。

#### 3. 发布流程

1. 合并代码到 `main` → 自动构建镜像推送到 `ghcr.io/hanzlgit/appointly`
2. 创建版本 Tag（如 `v0.1.0`）或在 Actions 中手动触发 **Build and Deploy** workflow
3. `production` 环境审批通过后，自动 SSH 到服务器执行 `docker compose pull && up -d && migrate`

## 云服务器部署

目标：Linux 服务器，Docker Compose 运行 Nginx + Gunicorn + Celery + MySQL + Redis + RabbitMQ。

### 你需要做的（一次性）

#### 1. SSH 登录服务器

```bash
ssh your-user@your-server-ip
```

#### 2. 运行 bootstrap 脚本

```bash
curl -fsSL https://raw.githubusercontent.com/Hanzlgit/appointly/main/deploy/scripts/bootstrap-server.sh | bash
```

或手动：

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 重新登录

# 克隆项目
sudo mkdir -p /opt/appointly && sudo chown $USER:$USER /opt/appointly
git clone git@github.com:Hanzlgit/appointly.git /opt/appointly
cd /opt/appointly/deploy
cp .env.example .env
```

#### 3. 编辑生产环境变量

```bash
nano /opt/appointly/deploy/.env
```

必须修改：

- `DJANGO_SECRET_KEY` — 可用 `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` 生成
- `DJANGO_ALLOWED_HOSTS` — 你的域名或 IP
- `MYSQL_ROOT_PASSWORD`、`MYSQL_PASSWORD`
- `RABBITMQ_PASSWORD`
- `DATABASE_URL`、`CELERY_BROKER_URL` 中的密码与上面一致

#### 4. 登录 GitHub Container Registry

服务器需要拉取私有镜像（若仓库为 private）：

```bash
echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin
```

PAT 需要 `read:packages` 权限。

#### 5. 首次启动

```bash
cd /opt/appointly/deploy
export IMAGE_TAG=latest
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec web uv run python manage.py migrate
docker compose -f docker-compose.prod.yml exec web uv run python manage.py createsuperuser
```

#### 6. 配置部署 SSH 密钥

在**本地**生成部署专用密钥（若还没有）：

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\appointly_deploy -N '""'
```

将公钥追加到服务器 `~/.ssh/authorized_keys`，私钥内容填入 GitHub Secret `DEPLOY_SSH_KEY`。

#### 7. 防火墙

```bash
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443   # 若后续加 HTTPS
sudo ufw enable
```

### 日常运维

```bash
cd /opt/appointly/deploy

# 查看状态
docker compose -f docker-compose.prod.yml ps

# 查看日志
docker compose -f docker-compose.prod.yml logs -f web

# 手动备份 MySQL
docker compose -f docker-compose.prod.yml --profile backup run --rm backup /usr/local/bin/backup-mysql
```

备份文件保存在 Docker volume `mysql_backups`，保留 14 天。

## 项目结构

```
appointly/
├── appointly/          # Django 应用（业务模块将逐步添加）
├── config/             # Django 项目配置
├── deploy/             # 生产部署配置
├── tests/              # 测试
├── docker-compose.yml  # 本地基础设施
├── Dockerfile          # 应用镜像
└── pyproject.toml      # 依赖与工具配置
```

## 当前进度

- [x] 本地 Docker Compose（MySQL / Redis / RabbitMQ）
- [x] uv + Python 3.12 虚拟环境
- [x] Django 骨架 + 健康检查 + Swagger
- [x] Ruff + pre-commit
- [x] GitHub Actions CI
- [x] GitHub Actions CD（需配置 Secrets 和 production 环境）
- [x] 生产 Docker Compose 模板
- [ ] 业务模块实现（见 PRD）
