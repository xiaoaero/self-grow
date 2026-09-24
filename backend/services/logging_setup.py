"""
Self Grow — 日志初始化（全项目唯一配置入口）

为什么要有这个文件
------------------
在此之前，全项目唯一的日志配置是 `config.py` 里的一行
`logging.basicConfig(level=logging.INFO)`。它带来三个问题：

1. **写死在 config 里** —— 谁 import 谁生效，之后没人能改全局行为；
   想开 DEBUG 只能改代码（`docs/代码学习顺序.md` 里就是这么写的）
2. **默认格式没有时间戳** —— `basicConfig()` 不传 format 时格式是
   `LEVEL:name:message`，排查时序问题时看不到时间
3. **与 uvicorn 的 dictConfig 互相覆盖** —— 结果是 root / uvicorn.error /
   uvicorn.access 三套格式并存

改成「显式初始化 + 单一入口」后：

- 格式统一带时间戳，并自动带**请求 id**（由 `services/middleware.py` 注入）
- 同时输出到 stderr（`docker logs` 用）和**轮转文件**（容器重建后还能翻旧账）
- 级别由 `SELF_GROW_LOG_LEVEL` 控制，改 .env 重启即可，不用改代码
- 第三方库（httpx / langchain / pymysql…）固定降噪，不吃全局 DEBUG
- 敏感串（`sk-xxx` / `Bearer xxx` / `api_key=xxx`）自动脱敏

调用时机
--------
**必须早于任何业务日志**。目前由 `config.py` 在模块尾部调用 ——
config 是所有模块的必经入口，比 `main.py` 更早拿到控制权。

⚠️ 本模块刻意**不 import 任何项目模块**（连 `config` 都不 import），
日志要用的数据目录从环境变量读或由调用方传入，避免循环依赖。

⚠️ 不要再使用 `logging.basicConfig()`：它只在 root 尚无 handler 时生效，
与 uvicorn 的配置叠加后行为不可预测。
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
from contextvars import ContextVar

__all__ = [
    "setup_logging",
    "force_stderr_only",
    "request_id_var",
    "get_log_dir",
]

# ================================================================
# 请求上下文
# ================================================================

# 由 services/middleware.py 在每个请求开始时 set，这里只负责渲染进日志行。
#
# 为什么用 ContextVar 而不是 threading.local：
# FastAPI 是 async 的，而本项目又大量 `await asyncio.to_thread(...)` 调同步 DB。
# ContextVar 在 asyncio task 创建与 to_thread 里都会**自动复制**，
# 所以线程池里跑出来的日志也能拿到正确的 request_id。
request_id_var: ContextVar[str] = ContextVar("self_grow_request_id", default="-")

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | req=%(request_id)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 第三方库统一降噪：即使全局开到 DEBUG，这些也不跟着放出来。
# langchain 在 DEBUG 下会把整个 prompt 打出来 —— 噪音与隐私双输。
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "openai",
    "langchain",
    "langchain_core",
    "langchain_openai",
    "pymysql",
    "urllib3",
    "asyncio",
    "apscheduler",
    "multipart",
    "python_multipart",
    "mcp",
    "fastmcp",
    "dbutils",
)

# 敏感串脱敏规则。只做「形态匹配」，不追求 100% 覆盖 ——
# 目的是防止 key 随手写进日志后被长期留存，不是把它当安全边界。
_SECRET_RULES = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{4,}"), "sk-***"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{8,}"), r"\1 ***"),
    (
        re.compile(r"(?i)\b(api[_-]?key|password|passwd|secret|token)(\s*[=:]\s*)\S+"),
        r"\1\2***",
    ),
)

_configured = False


# ================================================================
# 两个 Filter
# ================================================================

class _ContextFilter(logging.Filter):
    """给每条日志补 request_id，并做敏感串脱敏

    挂在 **handler** 上而不是 logger 上：logger 上的 filter 只在日志由该
    logger 直接产生时调用，子 logger 冒泡上来的记录不会重跑它。
    挂到 handler 才能覆盖全量（本项目 40 多个模块各自 getLogger）。

    受益点：存量近百处 `log.info(...)` **一行都不用改**，就自动带上了
    request_id 与脱敏。
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        # ① 注入请求上下文
        record.request_id = request_id_var.get()

        # ② 脱敏。任何一步出问题都不许影响日志本身（宁可原样输出）
        try:
            original = record.getMessage()
            cleaned = original
            for pattern, repl in _SECRET_RULES:
                cleaned = pattern.sub(repl, cleaned)
            if cleaned != original:
                # 已把参数格式化进 msg，必须清空 args，否则 formatter
                # 会再走一次 `msg % args` 二次格式化
                record.msg = cleaned
                record.args = ()
        except Exception:  # noqa: BLE001
            pass
        return True


# ================================================================
# 初始化
# ================================================================

def get_log_dir(data_dir: str | None = None) -> str:
    """返回日志目录（不创建）"""
    base = data_dir or os.getenv("SELF_GROW_DATA_DIR")
    if not base:
        # 开发模式：落 backend/logs/，与 config.DATA_DIR 的默认值保持一致
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "logs")


def _build_formatter() -> logging.Formatter:
    """构建统一 formatter

    `defaults` 是兜底：万一某条记录没经过 `_ContextFilter`
    （例如第三方库自带 handler），`%(request_id)s` 也不会 KeyError。
    """
    try:
        return logging.Formatter(
            _LOG_FORMAT, _DATE_FORMAT, defaults={"request_id": "-"}
        )
    except TypeError:  # Python < 3.10
        return logging.Formatter(
            _LOG_FORMAT.replace(" | req=%(request_id)s", ""), _DATE_FORMAT
        )


def _build_file_handler(
    component: str,
    data_dir: str | None,
    formatter: logging.Formatter,
    context_filter: _ContextFilter,
) -> logging.Handler | None:
    """构建轮转文件 handler

    失败（无权限 / 磁盘满）时只降级为纯 stderr —— 日志不该成为
    服务起不来的原因。

    ⚠️ 文件名必须按 component 区分：app 与 mcp 是**两个容器**，
    却共享同一个 /data 卷。写同一个文件会让两边互相破坏轮转。
    """
    try:
        log_dir = get_log_dir(data_dir)
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, f"{component}.log"),
            maxBytes=10 * 1024 * 1024,   # 10MB，与 compose 的容器日志轮转对齐
            backupCount=5,
            encoding="utf-8",            # 项目里有 emoji，必须显式指定
            delay=True,                  # 真正写第一条日志时才建文件
        )
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("日志文件不可用，仅输出到 stderr：%s", exc)
        return None

    handler.setFormatter(formatter)
    handler.addFilter(context_filter)
    return handler


def setup_logging(
    component: str = "app",
    data_dir: str | None = None,
    level: str | None = None,
) -> None:
    """初始化全项目日志。幂等：重复调用直接返回。

    Args:
        component: 组件名，决定日志文件名（`app.log` / `mcp.log`）。
        data_dir:  数据目录，日志落在 `<data_dir>/logs/`。
                   默认读 `SELF_GROW_DATA_DIR`，再默认到 `backend/`。
        level:     级别覆盖，默认读 `SELF_GROW_LOG_LEVEL`（再默认 INFO）。
    """
    global _configured
    if _configured:
        return

    # ── 级别：环境变量优先，非法值回落 INFO ──
    level_name = (level or os.getenv("SELF_GROW_LOG_LEVEL", "INFO")).strip().upper()
    numeric_level = getattr(logging, level_name, None)
    if not isinstance(numeric_level, int):
        level_name = "INFO"
        numeric_level = logging.INFO

    root = logging.getLogger()
    # 先清掉既有 handler（uvicorn / pytest / 旧 basicConfig 可能已经装过）
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(numeric_level)

    formatter = _build_formatter()
    context_filter = _ContextFilter()

    # ① stderr —— `docker logs` / 前台运行时看这个
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(context_filter)
    root.addHandler(stream_handler)

    # ② 轮转文件 —— 容器重建后仍可追溯
    file_handler = _build_file_handler(
        component, data_dir, formatter, context_filter
    )
    if file_handler is not None:
        root.addHandler(file_handler)

    # ③ 第三方库降噪
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True

    logging.getLogger(__name__).info(
        "日志已初始化 component=%s level=%s file=%s",
        component,
        level_name,
        file_handler.baseFilename if file_handler is not None else "（未启用）",
    )


def force_stderr_only() -> None:
    """把 root 上所有「控制台 handler」的输出流强制换到 stderr。

    专给 MCP 的 stdio 传输用：那种模式下 **stdout 是 JSON-RPC 通道**，
    任何非协议内容写进去都会让客户端报「解析失败」，而且极难定位
    （看起来像工具调用坏了，其实是日志污染了协议流）。

    `mcp_server.py` 原本已经手工用 `file=sys.stderr` 打了提示，
    但那只是「约定」—— 谁在 MCP 路径上加一个 `print()` 就破功。
    本函数把这件事变成「保证」。
    """
    for handler in logging.getLogger().handlers:
        # FileHandler 继承自 StreamHandler，必须排除
        if isinstance(handler, logging.FileHandler):
            continue
        if isinstance(handler, logging.StreamHandler):
            if getattr(handler, "stream", None) is not sys.stderr:
                handler.stream = sys.stderr
