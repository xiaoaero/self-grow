# ================================================================
# Self Grow — 生产镜像
#
# 设计要点（逐条对应 docs/Docker技术详解与部署实战.md）：
#  1. 先只 COPY requirements.txt 再 pip install —— 利用镜像层缓存，
#     改业务代码不会重装 129 个依赖
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

# ── 时区（很关键，别删）─────────────────────────────────────
# 容器默认是 UTC，而本项目**大量使用本地时间**：
#   · MySQL 建表默认值的 `CURRENT_TIMESTAMP`（靠连接层 `SET time_zone='+08:00'` 兜，
#     但那要求 MySQL 服务端与连接时区都设对 —— 见 docker-compose.yml 的 mysql 服务）
#   · Python 的 `datetime.date.today()`（每日归档/统计按它算「今天」）
#   · APScheduler 的 `CronTrigger(hour=3)`（每日 03:00 刷新）
#
# 不设时区的后果：
#   1. 定时任务在 UTC 03:00 触发 = 北京时间 11:00 才跑
#   2. 北京时间 00:00~08:00 期间「今天」仍是前一天 → 打卡日期错位
#   3. 数据库里存的时间戳比实际早 8 小时
#
# 不需要 apt-get 装 tzdata：Debian 的 tzdata 是 required 优先级包，slim 基底同样自带。
# 实测 python:3.12-slim 里 /usr/share/zoneinfo/Asia/Shanghai 存在，
# `TZ=Asia/Shanghai date` 直接输出 CST，一条 ENV 就够。
#
# 早先为"保险"写过 `apt-get update && apt-get install tzdata`，代价是每次构建都要
# 从 deb.debian.org 拉 9.6MB 索引（国内实测 4 分钟以上，比装 129 个依赖还慢），
# 还给构建多引入一个网络失败点 —— 已移除。
ENV TZ=Asia/Shanghai

# ── 依赖层（变化频率低，放前面以命中缓存）──────────────────
# requirements.txt 由 `pixi run export-reqs` 从 pixi 锁定版本导出，
# 与开发环境版本完全一致（改依赖请改 pixi.toml 后重新导出，不要手工编辑）。
#
# 注意：导出脚本会剔除 pywin32 / pywin32-ctypes / win_inet_pton 这类
# 「只在 Windows 存在」的包 —— 它们来自 conda 解析，装到 Linux 上会直接报
#   ERROR: No matching distribution found for pywin32==312
# 不要手工把它们加回来。
COPY backend/requirements.txt ./backend/requirements.txt

# pip 源：服务器在国内，直连 pypi.org 拉 129 个包要 6 分钟以上，且容易中断
# （实测一次失败前已跑 388 秒）。换清华源后可降到数十秒。
# 需要走官方源的场景（海外机器 / 合规要求）：
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir \
        --retries 5 --timeout 60 \
        -i "${PIP_INDEX_URL}" \
        -r backend/requirements.txt

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
