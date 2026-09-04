"""
将 pixi 当前锁定版本导出为 requirements.txt（pip / Docker 安装用）。

依赖来源：pixi.toml（`dependencies` 节）是唯一事实源。
本脚本从 `pixi list --format json` 读取所有已安装包的精确版本，
生成 `name==version` 行，与 pixi.lock 完全一致。

用法：
    cd backend
    pixi run export-reqs        # 或: python tools/export_reqs.py
    # 生成 requirements.txt（版本与 pixi 环境完全一致）

为什么：
    以 pixi.toml 为唯一源，requirements.txt 自动同步，无需手动维护白名单。
"""

import json
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def main() -> None:
    out = subprocess.check_output(["pixi", "list", "--json"])
    packages = json.loads(out)

    lines = sorted(
        f"{p['name']}=={p['version']}"
        for p in packages
    )

    req_path = BACKEND_DIR / "requirements.txt"
    req_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] 已写入 {req_path.relative_to(BACKEND_DIR)}：{len(lines)} 个包")


if __name__ == "__main__":
    main()
