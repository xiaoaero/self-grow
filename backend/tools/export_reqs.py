"""
将 pixi 当前锁定版本导出为 requirements.txt（pip / Docker 安装用）。

依赖来源：pixi.toml（`dependencies` / `pypi-dependencies` 节）是唯一事实源。
本脚本读取 pixi 环境里**实际安装的 Python 发行版元数据**，生成 `name==version` 行。

用法：
    cd backend
    pixi run export-reqs        # 或: python tools/export_reqs.py
    # 生成 requirements.txt（版本与 pixi 环境完全一致）

为什么不用 `pixi list --json`：
    那份清单是 **conda 视角**，包含 `_openmp_mutex`、`bzip2`、`ca-certificates`、
    `brotli-python` 这类 C 库 / conda 专有包——pip 既解析不了（下划线开头不合法），
    也找不到（PyPI 上没有 `brotli-python`，只有 `brotli`）。
    曾经直接拿它生成 requirements.txt，结果 Docker 构建在
    `RUN pip install -r requirements.txt` 这一步直接失败：
        ERROR: Invalid requirement: '_openmp_mutex==4.5'
    改为读取 importlib.metadata（Python 发行版视角）后，得到的就是 pip 真正需要的清单。

为什么：
    以 pixi.toml 为唯一源，requirements.txt 自动同步，无需手动维护白名单。
"""

import json
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

# pip 自身与构建期工具不进 requirements（镜像里自带，且容易与系统包冲突）
EXCLUDE = {"pip", "wheel", "distribute"}

# 在 pixi 环境里枚举所有已安装的 Python 发行版（含 conda 装的，只要有 dist-info）
_SCAN_CODE = (
    "import json;"
    "from importlib.metadata import distributions;"
    "d={};"
    "[d.__setitem__(x.metadata['Name'], x.version) "
    " for x in distributions() if x.metadata['Name']];"
    "print(json.dumps(d))"
)


def collect_installed() -> dict[str, str]:
    out = subprocess.check_output(["pixi", "run", "python", "-c", _SCAN_CODE], text=True)
    # pixi run 可能输出额外日志，取最后一个 JSON 对象
    start = out.find("{")
    return json.loads(out[start:])


def main() -> None:
    installed = collect_installed()

    lines = sorted(
        f"{name}=={version}"
        for name, version in installed.items()
        if name.lower() not in EXCLUDE
    )

    req_path = BACKEND_DIR / "requirements.txt"
    req_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] 已写入 {req_path.relative_to(BACKEND_DIR)}：{len(lines)} 个包")


if __name__ == "__main__":
    main()
