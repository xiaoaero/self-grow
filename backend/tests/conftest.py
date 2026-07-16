"""
pytest conftest — 将 backend 目录加入 sys.path
"""
import sys
import os

# 确保 backend/ 目录在 sys.path 中
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
