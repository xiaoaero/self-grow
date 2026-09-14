# ================================================================
# Self Grow — 生产镜像
#
# 设计要点（逐条对应 docs/Docker技术详解与部署实战.md）：
#  1. 先只 COPY requirements.txt 再 pip install —— 利用镜像层缓存，
#     改业务代码不会重装 177 个依赖
#  2. python:3.12-slim 而非 python:3.12 —— 体积从 ~1GB 降到 ~150MB 基础
#  3. CMD 用 exec 形式 —— 让应用成为 PID 1，才能收到 SIGTERM 优雅退出
#  4. 密钥一律不写进镜像 —— 镜像分层，写进去再删也能被 docker history 看到
#  5. 以非 root 用户运行 —— 容器逃逸时权限受限
#
# 构建（项目根目录）：
#   docker build -t self-grow:1.2 .
# ================================================================

FROM python:3.12-slim

# Python 不缓冲输出，日志能实时进 docker logs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ── 依赖层（变化频率低，放前面以命中缓存）──────────────────
# requirements.txt 由 `pixi run export-reqs` 从 pixi 锁定版本导出，
# 与开发环境版本完全一致（改依赖请改 pixi.toml 后重新导出，不要手工编辑）
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# ── 代码层（变化频率高，放后面）────────────────────────────
COPY . .

# ── 非 root 用户 + 数据目录预建 ────────────────────────────
# 预建 /data 并授权：命名卷首次创建时会继承镜像里该目录的所有权，
# 这样容器以 appuser 运行时才能写 data.db 与 uploads/
RUN useradd -m -u 1000 -s /usr/sbin/nologin appuser \
    && mkdir -p /data/uploads \
    && chown -R appuser:appuser /data /app

WORKDIR /app/backend

# ── 非敏感默认值 ──────────────────────────────────────────
# 敏感项（JWT 密钥 / AI Key）由 docker-compose 的 environment 注入
ENV PORT=3001
ENV SELF_GROW_DATA_DIR=/data
ENV SELF_GROW_FRONTEND_DIR=/app/frontend

USER appuser

EXPOSE 3001

# 健康检查（config 里没有额外依赖，直接用标准库）
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3001/api/health', timeout=4).status==200 else 1)"

CMD ["python", "main.py"]
