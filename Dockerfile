# ===== Codex DeepSeek Proxy — Docker 镜像 =====

FROM python:3.11-slim AS base

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（仅 Linux 所需，不含 macOS 托盘组件）
COPY requirements-linux.txt .
RUN pip install --no-cache-dir -r requirements-linux.txt

# ─── 生产阶段 ──────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# 从 base 阶段复制已安装的包
COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# 安装 curl（用于 healthcheck）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制应用代码
COPY . .

# 创建数据目录（config.json 持久化用）
RUN mkdir -p /root/.codex-ds

# 端口：8787 代理服务，8788 管理面板
EXPOSE 8787 8788

# 环境变量（可在 docker run 或 compose 中覆盖）
ENV DEEPSEEK_API_KEY=""
ENV DEEPSEEK_BASE_URL="https://api.deepseek.com"
ENV DEEPSEEK_MODEL="deepseek-v4-pro"
ENV PROXY_PORT=8787
ENV WEB_PORT=8788

# 启动脚本：将环境变量写入 config.json 后启动代理
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["--no-tray"]
