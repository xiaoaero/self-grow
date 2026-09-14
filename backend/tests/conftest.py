"""
pytest conftest — 设置测试环境变量并把 backend / tests 目录加入 sys.path

注意：环境变量必须在任何 backend 模块（尤其是 config.py）被导入之前设置，
否则 config 里读到的就是空值。pytest 会最先加载 conftest，所以放在这里。
"""

import os
import sys

# ── 测试环境：登录鉴权 ──────────────────────────────────────────
# JWT 签名密钥（测试专用固定值，避免依赖开发者本机 .env）
os.environ["SELF_GROW_JWT_SECRET"] = "test-secret-for-pytest-0123456789"
# 测试必须走真实鉴权，不能开免鉴权模式
os.environ.pop("SELF_GROW_TRUSTED_MODE", None)

# 确保 backend/ 目录在 sys.path 中
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 让测试模块可以直接 `from helpers import ...`
tests_dir = os.path.dirname(os.path.abspath(__file__))
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)
