"""
Self Grow — 初始化账号密码

用法：
    pixi run python tools/init_password.py                 # 按内置默认账号设置
    pixi run python tools/init_password.py test 123456     # 指定用户名与新密码

说明：
- 幂等：重复执行会直接覆盖该用户的密码哈希
- 仅用于首次部署 / 忘记密码时重置；不会创建新用户
- 默认账号：test（普通用户）、admin（管理员）
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init import init_db                      # noqa: E402
from db.users import get_user_by_name, get_all_users   # noqa: E402
from db.auth import set_password_hash            # noqa: E402
from services.auth_service import hash_password  # noqa: E402

# 默认初始密码（本地个人系统，按用户指定）
DEFAULT_PASSWORDS = {
    "test": "test123456",
    "admin": "admin123456",
}


def set_password(username: str, password: str) -> bool:
    user = get_user_by_name(username)
    if not user:
        return False
    set_password_hash(user["id"], hash_password(password))
    return True


def main():
    init_db()

    if len(sys.argv) == 3:
        username, password = sys.argv[1], sys.argv[2]
        if set_password(username, password):
            print(f"✅ 已重置「{username}」的密码")
        else:
            print(f"❌ 未找到用户「{username}」。当前用户：{', '.join(u['name'] for u in get_all_users())}")
            sys.exit(1)
        return

    if len(sys.argv) != 1:
        print(__doc__)
        sys.exit(1)

    print("开始初始化账号密码 …")
    for username, password in DEFAULT_PASSWORDS.items():
        if set_password(username, password):
            print(f"  ✅ {username:<6} → {password}")
        else:
            print(f"  ⚠️  跳过 {username}（用户不存在）")

    print("\n完成。请尽快登录并在用户中心修改密码（若后续提供该功能）。")


if __name__ == "__main__":
    main()
