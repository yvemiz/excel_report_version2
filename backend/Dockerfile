# ==============================================================================
# Dockerfile for Backend (FastAPI + DuckDB + SQLite + Node.js Pi-Agent Sidecar)
# 国内加速优化版：全面采用阿里云 Apt/Pip 镜像与文泉驿中文字体
# ==============================================================================

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com

# 1. 彻底替换 Debian apt 源为阿里云镜像（包含 debian 和 security 源，彻底杜绝外网卡顿）
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's@deb.debian.org@mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources; \
        sed -i 's@security.debian.org@mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's@deb.debian.org@mirrors.aliyun.com@g' /etc/apt/sources.list; \
        sed -i 's@security.debian.org@mirrors.aliyun.com@g' /etc/apt/sources.list; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl \
        procps \
        nodejs \
        fonts-wqy-zenhei \
        fonts-wqy-microhei; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# 2. 复制依赖清单并使用阿里云 Pip 源加速安装
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

# 3. 复制后端源码与预置测试报表数据
COPY backend/ /app/backend/
COPY example/ /app/example/

# 4. 创建必要的持久化数据目录
RUN mkdir -p /app/backend/data/uploads \
             /app/backend/data/exports \
             /app/backend/static/charts

WORKDIR /app/backend
ENV PYTHONPATH=/app/backend

EXPOSE 8008

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8008/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]
