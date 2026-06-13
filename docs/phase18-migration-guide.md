# Phase 18: 生产级架构升级指南

> 从 SQLite 单机 → PostgreSQL + Redis + Celery 分布式

---

## 一、架构变更

```
Phase 17 (当前)                    Phase 18 (升级后)
─────────────────                  ─────────────────
SQLite (单写入者)        →         PostgreSQL 16 (20 connections)
进程内存 cache           →         Redis 7 (分布式 + LRU)
同步任务阻塞             →         Celery Worker (4 concurrency)
无定时任务               →         Celery Beat (cron schedule)
手动启动 2 进程          →         docker-compose up -d (7 services)
```

## 二、启动命令

```bash
# 1. 创建 .env 配置文件
cat > .env << 'EOF'
DB_PASSWORD=your-strong-password-here
ENCRYPTION_KEY=your-32-byte-fernet-key
JWT_SECRET_KEY=your-jwt-secret
ADMIN_PASSWORD=your-admin-password
EOF

# 2. 一键启动全栈
docker-compose -f docker-compose.prod.yml up -d

# 3. 验证
docker-compose -f docker-compose.prod.yml ps
# 应显示: nginx, postgres, redis, dashboard, admin, celery_worker, celery_beat 全部 healthy

# 4. 访问
# Dashboard: http://localhost:8080
# 管理后台: http://localhost:8001
```

## 三、服务清单

| 服务 | 端口 | 说明 |
|------|------|------|
| nginx | 8080 | 反向代理 → dashboard |
| postgres | 5432 | 主数据库 (pool 20) |
| redis | 6379 | 缓存 + 限流 + Celery broker |
| dashboard | 8000 | 公网 API |
| admin | 8001 | 管理后台 |
| celery_worker | — | 异步任务 (4 workers) |
| celery_beat | — | 定时任务调度 |

## 四、向后兼容

- `DATABASE_URL=sqlite:///./data/twitter_data.db` → 依旧使用 SQLite
- `DATABASE_URL=postgresql://...` → 自动切换 PostgreSQL
- 无 `REDIS_URL` → Redis 缓存降级为进程内存
- 无 Celery → 依旧走同步任务路径

## 五、定时任务

| 任务 | 频率 | 说明 |
|------|------|------|
| `cleanup_expired_tokens` | 每天 03:00 | 清理过期 Refresh Token |
| `check_price_alerts` | 每 5 分钟 | 检查价格预警 → Telegram 推送 |

## 六、容量对比

| 指标 | SQLite | PostgreSQL + Redis |
|------|--------|-------------------|
| 并发写入 | 1 (串行) | 20 (池) |
| 缓存 TTL | 2-60s 进程内 | 分布式, 可调 |
| 并发用户 | 25-30 | 200+ |
| 任务异步 | ❌ | ✅ Celery workers |
| 定时任务 | ❌ | ✅ Celery Beat |
| 限流持久化 | ❌ 重启丢失 | ✅ Redis |
