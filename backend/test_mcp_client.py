"""
MCP Server 验证脚本

用 FastMCP 的 Client 通过 stdio 连接本机 mcp_server.py，逐个调用工具并打印结果。
用于验证 MCP 插件是否跑通 —— 无需 Claude Desktop / Cursor / Node.js。

运行：
    cd backend
    pixi run python test_mcp_client.py

预期：
    - 列出 3 个工具
    - query_user_stats 返回等级/总经验/连续天数
    - query_dimension_stats 返回 health 维度数据
    - record_action 返回 exp_earned > 0（跑步 60 分钟 = 15 EXP）
"""

import asyncio
from datetime import datetime, timedelta
from fastmcp import Client


async def main():
    print("连接 MCP Server (stdio)...")
    # Client 直接传 python 文件路径，FastMCP 会用 stdio 启动它
    async with Client("mcp_server.py") as client:
        print("✅ 连接成功\n")

        # 1. 列出工具
        print("=" * 50)
        print("1) 可用工具列表")
        print("=" * 50)
        tools = await client.list_tools()
        for t in tools:
            desc = (t.description or "").strip().splitlines()[0][:60]
            print(f"  - {t.name}: {desc}")
        print()

        # 2. 查询用户概况（读）
        print("=" * 50)
        print("2) query_user_stats")
        print("=" * 50)
        r = await client.call_tool("query_user_stats", {})
        print(f"  返回: {r}\n")

        # 3. 查询维度（读）
        print("=" * 50)
        print("3) query_dimension_stats(health)")
        print("=" * 50)
        r = await client.call_tool("query_dimension_stats", {"dimension_key": "health"})
        print(f"  返回: {r}\n")

        # 4. 记录行动（写，会真实入库 + 结算经验）
        print("=" * 50)
        print("4) record_action(health, 跑步, 60分钟)")
        print("=" * 50)
        start_time = (datetime.now() - timedelta(minutes=60)).isoformat()
        r = await client.call_tool("record_action", {
            "category": "health",
            "detail": "跑步",
            "duration": 60,
            "start_time": start_time,
        })
        print(f"  返回: {r}\n")

        print("✅ 全部工具调用完成")


if __name__ == "__main__":
    asyncio.run(main())

