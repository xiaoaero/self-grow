"""
SQLite → MySQL 数据迁移

把 backend/data.db（本地那份有真实进度：test Lv188、246+ 条行动记录）
整表搬到 MySQL。

用法
----
    cd backend
    pixi run python tools/migrate_sqlite_to_mysql.py            # 迁移（先清空目标表）
    pixi run python tools/migrate_sqlite_to_mysql.py --dry-run   # 只统计不写

Docker 里（老库在 `data` 卷里，路径由 `SELF_GROW_DATA_DIR` 决定）：

    docker compose up -d mysql
    docker compose run --rm app python tools/migrate_sqlite_to_mysql.py

源库路径不用手填 —— 脚本按 `--sqlite` → `SELF_GROW_DATA_DIR/data.db` →
`backend/data.db` 的顺序探测（见 `resolve_sqlite_path()`）。

要点
----
1. **显式列出字段名**，不靠列顺序 —— 两份 DDL 虽然同源，但插入顺序不该成为依赖
2. **保留原 id**：AUTO_INCREMENT 列允许显式赋值，这样自增序列之外的外键
   （如 `habit_checkins.habit_id`）指向的还是同一行
3. 迁完**重置每张表的 AUTO_INCREMENT** 到 max(id)+1，否则新数据会撞主键
4. 全程 `SET FOREIGN_KEY_CHECKS=0` 包住 —— 不依赖表之间的依赖顺序，
   迁完再用 LEFT JOIN 抽查孤儿记录
5. 类型不做转换：SQLite 存的就是字符串/整数/浮点，直接按值插入；
   时间列在两边都是字符串（这是有意保留的取舍，见迁移方案 §5）
"""

import argparse
import os
import sqlite3
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

import config
from db.connection import get_conn, backend_name, close_pool, now_str


def sqlite_tables(src: sqlite3.Connection) -> list:
    return [r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]


def columns_of(src: sqlite3.Connection, table: str) -> list:
    return [r[1] for r in src.execute(f'PRAGMA table_info("{table}")')]


def resolve_sqlite_path(explicit: str) -> str:
    """找出源 SQLite 库的位置

    **不能只写死 `backend/data.db`**：容器里 `WORKDIR` 是 `/app/backend`，
    而数据目录被 `SELF_GROW_DATA_DIR=/data` 改到别处了 —— 写死的话在 Docker 里
    必然报「找不到源库」。实测踩过。

    按顺序试（先看用户显式给的，再看两个约定位置）：
      1. `--sqlite` 参数
      2. `config.DB_PATH` —— 即 `SELF_GROW_DATA_DIR/data.db`。
         开发环境里 `DATA_DIR` 就是 `backend/`，所以这一条同时覆盖本地开发
      3. `backend/data.db` —— 兜底（万一 DATA_DIR 被指到了别处，而老库还在原地）
    """
    candidates = [explicit, config.DB_PATH, os.path.join(BACKEND, "data.db")]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    raise SystemExit(
        "找不到源 SQLite 库。已尝试：\n"
        + "\n".join(f"   · {c}" for c in candidates)
        + "\n\n请用 --sqlite <路径> 显式指定。"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    ap.add_argument("--sqlite", default=None,
                    help="源 SQLite 文件（默认按 SELF_GROW_DATA_DIR/data.db → backend/data.db 顺序探测）")
    args = ap.parse_args()

    sqlite_path = resolve_sqlite_path(args.sqlite)

    if backend_name() != "mysql":
        raise SystemExit(
            "当前后端不是 mysql。请在 backend/.env 里设 "
            "SELF_GROW_DB_BACKEND=mysql（或临时用环境变量）"
        )

    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    tables = sqlite_tables(src)
    print(f"源库 {sqlite_path}")
    print(f"目标 {config.MYSQL_USER}@{config.MYSQL_HOST}:{config.MYSQL_PORT}"
          f"/{config.MYSQL_DATABASE}")
    print(f"共 {len(tables)} 张表\n")

    conn = get_conn()
    try:
        # 目标表的列（用于取交集，避免两边列有出入时整条语句失败）
        dst_cols_map = {}
        for t in tables:
            rows = conn.execute("""
                SELECT column_name AS c FROM information_schema.columns
                WHERE table_schema = DATABASE() AND table_name = ?
            """, (t,)).fetchall()
            dst_cols_map[t] = {r["c"] for r in rows}

        conn.execute("SET FOREIGN_KEY_CHECKS=0")

        # 老库里可能留着已经废弃的表（实测有 `routine_streaks`，已被
        # 单数的 `routine_streak` 取代）—— 这类表在目标里根本不存在，
        # 清空和写入都要跳过，否则报 1146。
        existing = [t for t in tables if dst_cols_map.get(t)]
        legacy = [t for t in tables if not dst_cols_map.get(t)]
        if legacy:
            print("以下表在目标库中不存在（老库遗留，跳过）：")
            for t in legacy:
                print("   ·", t)
            print()

        if not args.dry_run:
            for t in existing:
                conn.execute(f"DELETE FROM `{t}`")
            conn.commit()
            print(f"已清空目标库 {len(existing)} 张表\n")

        total_rows = 0
        report = []
        for t in tables:
            cols = columns_of(src, t)
            dst_cols = dst_cols_map.get(t, set())
            use = [c for c in cols if c in dst_cols]
            skipped = [c for c in cols if c not in dst_cols]

            rows = src.execute(f'SELECT * FROM "{t}"').fetchall()
            if not rows:
                report.append((t, 0, 0, skipped, ""))
                continue

            if not use:
                report.append((t, len(rows), 0, skipped, "目标表不存在或无共同列"))
                continue

            col_sql = ", ".join(f"`{c}`" for c in use)
            ph = ", ".join(["?"] * len(use))
            payload = [[r[c] for c in use] for r in rows]

            if not args.dry_run:
                conn.executemany(
                    f"INSERT INTO `{t}` ({col_sql}) VALUES ({ph})", payload)
            total_rows += len(rows)
            report.append((t, len(rows), len(payload), skipped, ""))

        if not args.dry_run:
            # 重置 AUTO_INCREMENT，否则新数据会撞主键
            for t in existing:
                if "id" not in dst_cols_map.get(t, set()):
                    continue
                mx = conn.execute(f"SELECT COALESCE(MAX(id), 0) AS m FROM `{t}`").fetchone()["m"]
                conn.execute(f"ALTER TABLE `{t}` AUTO_INCREMENT = {int(mx) + 1}")

            conn.execute("SET FOREIGN_KEY_CHECKS=1")
            conn.commit()

        print(f"{'表名':32s} {'源行数':>7s} {'已迁':>7s}  备注")
        print("-" * 74)
        legacy_count = 0
        for t, n_src, n_dst, skipped, note in report:
            flag = ""
            if t not in existing:
                # 老库遗留的表（新 DDL 里没有）。**不是失败** ——
                # 上次报了「❌ 数量不一致」把例行清理显示成错误，容易吓人
                flag = "  （老库遗留，已跳过）"
                legacy_count += 1
            elif n_src and n_dst != n_src:
                flag = " ❌ 数量不一致"
            if skipped:
                note = (note + f" 跳过无对应列: {skipped}").strip()
            print(f"{t:32s} {n_src:7d} {n_dst:7d}  {note}{flag}")

        print("-" * 74)
        print(f"{'合计（已迁入目标库）':32s} {total_rows:7d}")
        if legacy_count:
            print(f"另有 {legacy_count} 张老库遗留表未迁移（目标库里没有这些表）")
        if args.dry_run:
            print("\n（--dry-run：没有写入任何数据）")
        else:
            print(f"\n迁移完成于 {now_str()}")
    finally:
        conn.close()
        close_pool()
        src.close()


if __name__ == "__main__":
    main()
