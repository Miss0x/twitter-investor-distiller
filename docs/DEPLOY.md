# 投资信号蒸馏台 — 生产部署指南

> 适用版本: v2.x  |  适用读者: 运维工程师

## 一、部署架构

```
                        用户
                         │
                         ▼
                    ┌─────────┐
                    │  Nginx  │ :80/:443 (反向代理)
                    └────┬────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ┌─────────┐    ┌──────────┐    ┌──────────┐
   │Dashboard│    │Dashboard │    │  Admin   │ :8001
   │  :8000  │    │(多实例)  │    │  后台    │
   └────┬────┘    └────┬─────┘    └────┬─────┘
        │              │              │
        └──────────────┼──────────────┘
                       ▼
              ┌────────────────┐
              │   PostgreSQL   │ :5432
              │     Redis      │ :6379
              └────────────────┘
                       ▲
                       │
              ┌────────┴────────┐
              │ Celery Worker   │ (异步任务)
              │ Celery Beat     │ (定时调度)
              └─────────────────┘
```

## 二、5 分钟快速部署

### 1. 准备服务器
- Linux（推荐 Ubuntu 22.04+）
- Docker 24.0+ 和 Docker Compose v2.20+
- 域名 + SSL 证书（Let's Encrypt 免费）
- 至少 2GB 内存（chromadb 需要）

### 2. 克隆代码
```bash
git clone <repo-url> /opt/twitter-distiller
cd /opt/twitter-distiller
```

### 3. 生成密钥
```bash
# 一键生成 4 个密钥
export JWT_SECRET_KEY=$(openssl rand -hex 32)
export ENCRYPTION_KEY=$(openssl rand -hex 32)
export ADMIN_PASSWORD="YourStrongPass!$(openssl rand -hex 8)"
export DASHBOARD_TOKEN=$(openssl rand -hex 16)
export DB_PASSWORD=$(openssl rand -hex 16)
```

### 4. 创建 .env
```bash
cp config/.env.example .env
# 编辑 .env，至少填入以下 4 个必填项
# （DEV: 没有 ? 语法保护，所以可以填空字符串，PROD 强制必填）
```

### 5. 启动（开发）
```bash
docker compose up -d
curl http://localhost:8080/   # 应返回 HTML
```

### 6. 启动（生产）
```bash
# 确保 .env 4 个必填项都已设置
docker compose -f docker-compose.prod.yml up -d
# 验证
docker compose ps   # 所有服务 healthy
```

## 三、关键环境变量（必须设置）

| 变量 | 生成命令 | 用途 |
|------|---------|------|
| `JWT_SECRET_KEY` | `openssl rand -hex 32` | 用户登录令牌签名 |
| `ENCRYPTION_KEY` | `openssl rand -hex 32` | 用户配置 Fernet 加密 |
| `ADMIN_PASSWORD` | 强密码 | 管理后台登录 |
| `DB_PASSWORD` | `openssl rand -hex 16` | PostgreSQL 密码 |

**生产环境必须设置，否则 `docker compose` 会拒绝启动。**

## 四、故障排查

### 服务无法启动
```bash
docker compose logs dashboard    # 查看应用日志
docker compose logs nginx       # 查看 nginx 日志
docker compose ps               # 查看健康状态
```

### healthcheck 失败
```bash
docker inspect --format='{{.State.Health.Status}}' twitter-distiller-dashboard-1
# 返回 "unhealthy" 则需要查看 logs
```

### 数据库连接失败
```bash
docker compose exec postgres pg_isready -U distiller
docker compose exec dashboard env | grep DATABASE_URL
```

### nginx 502 Bad Gateway
```bash
# 1. 检查 dashboard 容器是否 healthy
docker compose ps
# 2. 检查 nginx 配置
docker compose exec nginx nginx -t
# 3. 查看 nginx 错误日志
docker compose logs nginx | grep error
```

### 端口冲突
- 80 / 443 / 8000 / 8001 / 5432 / 6379 不能被其他服务占用
- 改 `docker-compose.yml` 的 `ports:` 字段

## 五、运维命令

```bash
# 查看所有服务状态
docker compose ps

# 查看实时日志
docker compose logs -f --tail=100 dashboard

# 重启单个服务
docker compose restart dashboard

# 数据库备份（生产）
docker compose exec postgres pg_dump -U distiller twitter_distiller > backup_$(date +%Y%m%d).sql

# 数据库恢复
cat backup_20260101.sql | docker compose exec -T postgres psql -U distiller -d twitter_distiller

# 进入容器调试
docker compose exec dashboard bash
docker compose exec postgres psql -U distiller

# 升级新版本
git pull
docker compose build
docker compose up -d
```

## 六、安全检查清单

- [ ] `.env` 文件**不**提交到 git（已通过 .gitignore 保护）
- [ ] 4 个必填密钥已设置且与开发环境不同
- [ ] 防火墙只暴露 80/443（其他端口 127.0.0.1 绑定）
- [ ] 启用 HTTPS（Let's Encrypt 自动续期）
- [ ] 定期备份数据库（建议每天）
- [ ] 监控 `/api/health` 端点（生产可观测性）

## 七、性能调优

```yaml
# docker-compose.yml 调整 worker 数
dashboard:
  command: gunicorn src.interfaces.web_api:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000

# PostgreSQL 调整
postgres:
  command: postgres -c shared_buffers=256MB -c max_connections=200

# Redis 调整
redis:
  command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
```

## 八、监控集成（可选）

- 健康检查端点: `GET /`（返回 HTML 200）
- 日志: `docker compose logs > /var/log/distiller.log`
- 监控: Uptime Kuma / Prometheus / Grafana
- 错误追踪: Sentry（需 `pip install sentry-sdk`）
