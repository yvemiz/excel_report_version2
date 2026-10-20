# ==============================================================================
# Dockerfile for Frontend (Vue 3 + Vite + Nginx)
# 极速轻量模式：直接使用已打包好的 dist 静态资产，秒级启动，免除服务器跑 npm build 的网络延迟与 CPU/内存压力
# ==============================================================================

FROM nginx:alpine

# 替换 Alpine apk 镜像源为国内阿里云
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories 2>/dev/null || true

# 拷贝静态资源到 Nginx HTML 目录
COPY dist /usr/share/nginx/html

# 拷贝自定义 Nginx 配置文件 (包含 SPA 路由转发与 SSE 无缓冲流式转发)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
