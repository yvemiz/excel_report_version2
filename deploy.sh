#!/bin/bash
# ==============================================================================
# 高校发展检验报告生成系统 - 服务器一键极速部署与更新脚本 (国内镜像优化版)
# 适用环境：CentOS / Ubuntu / Debian + 宝塔面板 + Docker
# ==============================================================================

set -e

echo "======================================================="
echo " 正在启动高校发展检验报告系统 (国内高速镜像优化版)..."
echo "======================================================="

# 1. 检查 Docker 环境
if ! command -v docker &> /dev/null; then
    echo "[ERROR] 未检测到 Docker，请在宝塔面板『软件商店』安装 Docker，或执行 curl -fsSL https://get.docker.com | bash"
    exit 1
fi

# 2. 自动配置国内 Docker Hub 镜像加速器（解决国外 Docker Hub 拉取缓慢甚至超时问题）
configure_docker_mirrors() {
    DAEMON_FILE="/etc/docker/daemon.json"
    NEED_RELOAD=0
    
    mkdir -p /etc/docker
    # 如果配置文件不存在，或含有已失效的旧源（网易、百度、已下线源），自动更新为当前高可用源
    if [ ! -f "$DAEMON_FILE" ] || grep -q -E "c\.163\.com|baidubce\.com|dockerproxy\.net" "$DAEMON_FILE" 2>/dev/null; then
        echo "[INFO] 正在配置国内 Docker 镜像加速源..."
        [ -f "$DAEMON_FILE" ] && cp "$DAEMON_FILE" "${DAEMON_FILE}.bak.$(date +%s)"
        cat > "$DAEMON_FILE" << 'EOF'
{
  "registry-mirrors": [
    "https://docker.1panel.live",
    "https://docker.m.daocloud.io",
    "https://dockerpull.cn",
    "https://dockerproxy.cn"
  ]
}
EOF
        NEED_RELOAD=1
    elif ! grep -q "registry-mirrors" "$DAEMON_FILE"; then
        echo "[INFO] 正在为现有 daemon.json 添加国内 Docker 镜像加速源..."
        cp "$DAEMON_FILE" "${DAEMON_FILE}.bak.$(date +%s)"
        cat > "$DAEMON_FILE" << 'EOF'
{
  "registry-mirrors": [
    "https://docker.1panel.live",
    "https://docker.m.daocloud.io",
    "https://dockerpull.cn",
    "https://dockerproxy.cn"
  ]
}
EOF
        NEED_RELOAD=1
    fi

    if [ "$NEED_RELOAD" -eq 1 ]; then
        echo "[INFO] 正在重启 Docker 服务以生效加速镜像..."
        systemctl daemon-reload || true
        systemctl restart docker || true
        echo "[INFO] Docker 镜像加速源已生效！"
    fi
}

configure_docker_mirrors

# 3. 检查 .env 配置文件
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "[INFO] 未检测到 .env 文件，正在从 .env.example 复制..."
        cp .env.example .env
        echo "[WARN] 请使用宝塔文件管理或 vim 编辑 .env，填入真实的 DEEPSEEK_API_KEY 后重新运行本脚本！"
        exit 1
    else
        echo "[ERROR] 缺少 .env 配置文件！"
        exit 1
    fi
fi

# 4. 准备本地挂载目录
echo "[INFO] 检查并准备本地挂载目录..."
mkdir -p ./backend/data/uploads
mkdir -p ./backend/data/exports
mkdir -p ./backend/static/charts
chmod -R 777 ./backend/data ./backend/static/charts 2>/dev/null || true

# 5. 基础镜像加速预拉取（避免在 docker build 时直连官方国外源导致卡死）
pull_base_image() {
    local target_image=$1
    if docker image inspect "$target_image" >/dev/null 2>&1; then
        echo "[INFO] 本地已存在基础镜像 $target_image，直接复用。"
        return 0
    fi

    echo "[INFO] 正在通过国内加速节点预拉取基础镜像: $target_image ..."
    local proxies=(
        "docker.1panel.live/library"
        "docker.m.daocloud.io/library"
        "dockerpull.cn/library"
        "swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library"
    )

    local success=0
    for proxy in "${proxies[@]}"; do
        local proxy_img="${proxy}/${target_image}"
        echo "[INFO] 尝试从 ${proxy_img} 拉取..."
        if docker pull "${proxy_img}"; then
            docker tag "${proxy_img}" "${target_image}"
            echo "[SUCCESS] 成功拉取并关联镜像标签为 ${target_image}！"
            success=1
            break
        fi
    done

    if [ "$success" -eq 0 ]; then
        echo "[WARN] 代理节点拉取未完成，尝试官方通道拉取..."
        docker pull "$target_image" || true
    fi
}

pull_base_image "python:3.11-slim"
pull_base_image "nginx:alpine"

# 6. 极速构建并启动容器
echo "[INFO] 正在利用本地高速镜像构建并启动容器..."
if docker compose version &> /dev/null; then
    docker compose down --remove-orphans 2>/dev/null || true
    docker compose up -d --build
elif command -v docker-compose &> /dev/null; then
    docker-compose down --remove-orphans 2>/dev/null || true
    docker-compose up -d --build
else
    echo "[ERROR] 未检测到 docker compose 命令，请检查 Docker Compose 插件是否已安装。"
    exit 1
fi

echo "======================================================="
echo " [SUCCESS] 极速部署完成！"
echo " 容器运行状态："
docker ps --filter "name=excel_report" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo "======================================================="
echo " 访问地址说明："
echo " 1. 前端直连访问: http://47.111.132.154:8080"
echo " 2. 后端健康检查: http://47.111.132.154:8008/api/health"
echo " 3. 推荐在宝塔面板将 80 端口站点反向代理至 http://127.0.0.1:8080 (记得关闭 proxy_buffering)"
echo "======================================================="
