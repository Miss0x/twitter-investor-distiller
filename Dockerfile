# 多阶段构建 — 减小镜像体积 + 提高安全性
# Stage 1: builder — 安装 Python 依赖
FROM python:3.13-slim AS builder

WORKDIR /app

# 仅安装编译期需要的系统包
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 先复制 requirements 利用 Docker 缓存
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Stage 2: runtime — 最小化运行时镜像
FROM python:3.13-slim

WORKDIR /app

# 运行时只需要 curl (用于 healthcheck) 和时区数据
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 阶段复制预编译的 wheels
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* \
    && rm -rf /wheels

# 创建非 root 用户运行
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

# 复制源码
COPY . .

# 数据目录
VOLUME ["/app/data"]

# 设置所有权并切换用户
RUN chown -R appuser:appuser /app
USER appuser

# 默认启动公网 Dashboard
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["python", "-m", "src.interfaces.web_api"]
