"""
Tractor Search MCP — 命令行交互工具
直接调用 MCP Server 的 5 个工具，无需任何 AI 客户端。
"""
import json
import sys
import os

# 确保能导入 mcp_server
DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DEMO_DIR)
os.chdir(DEMO_DIR)

from mcp_server import mcp as server


async def call_tool(name, args):
    """调用 MCP 工具并返回结果文本"""
    result = await server.call_tool(name, args)
    content = result[0]  # list of content blocks
    if content and hasattr(content[0], "text"):
        return content[0].text
    return str(result)


def print_json(text):
    """漂亮地打印 JSON"""
    try:
        data = json.loads(text)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(text)


def show_menu():
    print()
    print("=" * 55)
    print("  Tractor Search MCP — 命令行工具")
    print("=" * 55)
    print()
    print("  [1] 查看流水线状态     (get_pipeline_status)")
    print("  [2] 搜索需求信号       (search_demand_signal)")
    print("  [3] 搜索 B2B 公司      (search_b2b_company)")
    print("  [4] 生成外联邮件       (generate_email)")
    print("  [5] 运行完整流水线     (run_full_pipeline)")
    print("  [0] 退出")
    print()


async def main():
    import asyncio

    while True:
        show_menu()
        choice = input("  请选择 [0-5]: ").strip()

        if choice == "0":
            print("  再见！")
            break

        elif choice == "1":
            print("\n  正在读取流水线状态...\n")
            text = await call_tool("get_pipeline_status", {})
            print_json(text)

        elif choice == "2":
            query = input("  搜索关键词 (如 'Kubota tractor parts needed Philippines'): ").strip()
            if not query:
                print("  关键词不能为空")
                continue
            num = input("  结果数量 (回车默认20): ").strip()
            num = int(num) if num else 20
            print(f"\n  正在搜索: {query} ...\n")
            text = await call_tool("search_demand_signal", {"query": query, "num_results": num})
            print_json(text)

        elif choice == "3":
            query = input("  搜索关键词 (如 'kubota tractor parts importer Japan'): ").strip()
            if not query:
                print("  关键词不能为空")
                continue
            num = input("  结果数量 (回车默认20): ").strip()
            num = int(num) if num else 20
            print(f"\n  正在搜索: {query} ...\n")
            text = await call_tool("search_b2b_company", {"query": query, "num_results": num})
            print_json(text)

        elif choice == "4":
            url = input("  source_url (信号/公司的来源链接): ").strip()
            if not url:
                print("  source_url 不能为空")
                continue
            stype = input("  类型 [signal/b2b] (回车默认 signal): ").strip()
            stype = stype if stype in ("signal", "b2b") else "signal"
            print(f"\n  正在生成邮件...\n")
            text = await call_tool("generate_email", {"source_url": url, "source_type": stype})
            print_json(text)

        elif choice == "5":
            confirm = input("  完整流水线需要 10-30 分钟，确认运行? [y/n]: ").strip().lower()
            if confirm != "y":
                print("  已取消")
                continue
            print("\n  正在运行完整流水线（demo.py）...\n")
            text = await call_tool("run_full_pipeline", {})
            print_json(text)

        else:
            print("  无效选择")

        print()
        input("  按回车继续...")
        # 清屏
        os.system("cls" if os.name == "nt" else "clear")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
