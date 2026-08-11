"""
将 pixi 当前锁定版本导出为 requirements.txt（pip / Docker 安装用）。

依赖来源：pixi.toml（`dependencies` 节）是唯一事实源。
本脚本从 `pixi list --format json` 读取已安装包的精确版本，
按 pixi.toml 中声明的核心包名生成固定的 `name==version` 行。

用法：
    cd backend
    pixi run export-reqs        # 或: python tools/export_reqs.py
    # 生成 requirements.txt（版本与 pixi 环境完全一致）

为什么：
    此前 requirements.txt 与 pixi.toml 是两套手写的、版本漂移的事实源
    （例如 langchain-openai 曾一处锁 0.3、一处 1.x）。
    现在以 pixi 为唯一源，导出板避免重复维护。
"""

import json
import subprocess
from pathlib import Path

# 与 pixi.toml [dependencies] 保持一致的核心运行时包
CORE_DEPENDENCIES = (
    "fastapi",
    "uvicorn",
    "httpx",
    "python-dotenv",
    "apscheduler",
    "langchain-openai",
    "pytest",
    "pillow",
    "dashscope",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


def main() -> None:
    out = subprocess.check_output(["pixi", "list", "--json"])
    packages = json.loads(out)

    lines = sorted(
        f"{p['name']}=={p['version']}"
        for p in packages
        if p["name"] in CORE_DEPENDENCIES
    )

    req_path = BACKEND_DIR / "requirements.txt"
    req_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] 已写入 {req_path.relative_to(BACKEND_DIR)}：{len(lines)} 个包")


if __name__ == "__main__":
    main()
