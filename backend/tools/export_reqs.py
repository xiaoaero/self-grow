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

为什么还要过滤「平台专属包」：
    conda 在解析依赖时会**忽略 PyPI 的 sys_platform 标记**，按宿主平台直接装。
    在 Windows 开发机上，于是 `pywin32` / `pywin32-ctypes` / `win-inet-pton`
    这些「只在 Windows 存在/只对 Windows 有用」的包被装了进来，并随本脚本
    写进了 requirements.txt。到 Linux 容器里构建时：
        ERROR: Could not find a version that satisfies the requirement pywin32==312
    因此必须显式剔除，见 PLATFORM_ONLY。

    注意：**不能用 wheel tag 来判定**。Windows 环境的 site-packages 里，
    cryptography、pydantic_core、pillow 这些跨平台包的 WHEEL 文件同样写着
    `Tag: cp312-cp312-win_amd64`，与 pywin32 长得一模一样，靠 tag 无法区分
    「跨平台包在本平台装的 win 轮子」和「本身就只发布 Windows 版的包」。
    唯一可靠的离线信号就是包名。
"""

import json
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

# pip 自身与构建期工具不进 requirements（镜像里自带，且容易与系统包冲突）
EXCLUDE = {"pip", "wheel", "distribute"}

# 只在 Windows 存在的发行版：Linux 上要么装不上，要么装了纯属噪音。
# 新增时请确认：① PyPI 上确实没有 Linux 可用发行版 ② 确有某个包在 win32 条件下才需要它
PLATFORM_ONLY = {
    # PyPI 上只有 win32/win_amd64 轮子，pip 在 Linux 上直接报
    # "No matching distribution found" —— Docker 构建会死在这一步
    "pywin32",
    # keyring 的条件依赖（sys_platform == "win32"）：纯 Python，Linux 上能装上但没人 import
    "pywin32-ctypes",
    # PySocks 的条件依赖（sys_platform == "win32"）：Win7 以下没有原生 inet_pton 才需要
    "win-inet-pton",
    # 同类历史包名，一并挡住
    "pypiwin32",
    "pyreadline",
    "pyreadline3",
    "pywinpty",
    "win32-setctime",
    "wmi",
}

# 在 pixi 环境里枚举所有已安装的 Python 发行版（含 conda 装的，只要有 dist-info）
_SCAN_CODE = (
    "import json;"
    "from importlib.metadata import distributions;"
    "d={};"
    "[d.__setitem__(x.metadata['Name'], x.version) "
    " for x in distributions() if x.metadata['Name']];"
    "print(json.dumps(d))"
)


def normalize(name: str) -> str:
    """按 PEP 503 归一化包名：`win_inet_pton` / `Win.Inet-Pton` → `win-inet-pton`。

    不做这一步会漏掉包：元数据里的名字可能是下划线形式（PySocks 的依赖就叫
    `win_inet_pton`），而黑名单里写的是规范连字符形式。
    """
    return name.lower().replace("_", "-").replace(".", "-")


def collect_installed() -> dict[str, str]:
    out = subprocess.check_output(["pixi", "run", "python", "-c", _SCAN_CODE], text=True)
    # pixi run 可能输出额外日志，取最后一个 JSON 对象
    start = out.find("{")
    return json.loads(out[start:])


def main() -> None:
    installed = collect_installed()

    lines: list[str] = []
    skipped: list[str] = []
    for name, version in sorted(installed.items()):
        key = normalize(name)
        if key in EXCLUDE:
            continue
        if key in PLATFORM_ONLY:
            skipped.append(f"{name}=={version}")
            continue
        lines.append(f"{name}=={version}")

    req_path = BACKEND_DIR / "requirements.txt"
    req_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[OK] 已写入 {req_path.relative_to(BACKEND_DIR)}：{len(lines)} 个包")
    if skipped:
        # 不打出来的话，下次换台机器就又不知道自己少了什么
        print(f"[SKIP] 已剔除 {len(skipped)} 个平台专属包（仅 Windows 存在）：")
        for item in skipped:
            print(f"       - {item}")


if __name__ == "__main__":
    main()
