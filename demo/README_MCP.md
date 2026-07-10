# Tractor Search Demo — MCP Server

将 Tractor Search Demo 的核心业务能力通过 MCP (Model Context Protocol) 暴露给 AI 助手。

任何兼容 MCP 协议的客户端（Cursor、VS Code、Claude Desktop 等）均可连接。

## 架构

```
┌─────────────────────────────────────────────┐
│  MCP Client (Cursor / VS Code / Claude…)    │
│                 ↕ stdio (JSON-RPC)           │
│  ┌───────────────────────────────────────┐  │
│  │       mcp_server.py  (FastMCP)        │  │
│  │  5 tools · reuses existing functions  │  │
│  └──────────┬────────────────────────────┘  │
│             │ direct function calls          │
│  ┌──────────┴────────────────────────────┐  │
│  │  demo.py · email_sender.py ·          │  │
│  │  product_inventory.py  (unchanged)     │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

**设计原则：**
- 不修改任何现有文件（demo.py、server.py、viewer.html 等）
- 直接调用已有函数，零逻辑重复
- 遵循 MCP 规范，客户端无关
- 优雅降级：缺少 API Key 时服务器仍可启动，数据查询工具照常工作

## 安装

```bash
cd demo
pip install -r requirements.txt
```

> `mcp>=1.0` 已添加到 requirements.txt。其余依赖（google-search-results、openai、python-dotenv、flask）为原有依赖。

## 环境变量

确保 `demo/.env` 包含：

```ini
SERPAPI_KEY=your_serpapi_key
QWEN_API_KEY=your_qwen_api_key
```

- `search_demand_signal`、`search_b2b_company`、`run_full_pipeline` 需要 SerpAPI + Qwen 密钥
- `generate_email` 需要 Qwen 密钥
- `get_pipeline_status` 不需要任何密钥（仅读取本地 JSON 文件）

## 工具列表 (v0.1)

| 工具 | 说明 | 需要 API Key |
|------|------|:---:|
| `search_demand_signal` | 搜索农机需求信号（SerpAPI + Qwen 提取 + 产品匹配） | ✅ |
| `search_b2b_company` | 搜索 B2B 农机公司（SerpAPI + Qwen 提取 + 产品匹配） | ✅ |
| `generate_email` | 为指定信号/公司生成多语言外联邮件 | ✅ |
| `run_full_pipeline` | 运行完整 demo.py 流水线（搜索→提取→匹配→邮件草稿） | ✅ |
| `get_pipeline_status` | 查看上次流水线运行状态、信号统计、邮件配额 | ❌ |

## 客户端配置

### Cursor

编辑 `~/.cursor/mcp.json`（全局）或项目根目录 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "tractor-search": {
      "command": "python",
      "args": ["c:\\path\\to\\tractor-search-main\\demo\\mcp_server.py"],
      "env": {
        "SERPAPI_KEY": "your_serpapi_key",
        "QWEN_API_KEY": "your_qwen_api_key"
      }
    }
  }
}
```

> **Windows 路径**：使用双反斜杠 `\\` 或正斜杠 `/`。
>
> 如果 `python` 不在 PATH，使用完整路径，例如 `"C:\\Users\\<user>\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe"`。

配置后重启 Cursor，在 Settings → MCP 中确认 `tractor-search` 显示为已连接。

### VS Code

安装 [MCP 扩展](https://marketplace.visualstudio.com/items?itemName=anthropic.mcp) 后，编辑 `.vscode/mcp.json`：

```json
{
  "servers": {
    "tractor-search": {
      "command": "python",
      "args": ["c:\\path\\to\\tractor-search-main\\demo\\mcp_server.py"],
      "env": {
        "SERPAPI_KEY": "your_serpapi_key",
        "QWEN_API_KEY": "your_qwen_api_key"
      }
    }
  }
}
```

### Claude Desktop

编辑配置文件：
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "tractor-search": {
      "command": "python",
      "args": ["c:\\path\\to\\tractor-search-main\\demo\\mcp_server.py"],
      "env": {
        "SERPAPI_KEY": "your_serpapi_key",
        "QWEN_API_KEY": "your_qwen_api_key"
      }
    }
  }
}
```

重启 Claude Desktop 后，工具图标中应显示 5 个 `tractor-search` 工具。

### 其他 MCP 客户端

任何支持 MCP stdio 传输的客户端均可连接。配置要点：

- **Command**: `python`
- **Args**: `mcp_server.py` 的完整路径
- **Transport**: stdio
- **Env**: 传入 `SERPAPI_KEY` 和 `QWEN_API_KEY`（或在 `demo/.env` 中设置）

## 使用示例

连接后，AI 助手可以自然语言调用工具：

```
用户：帮我搜索菲律宾的拖拉机零件需求信号
AI：[调用 search_demand_signal] 找到 5 条需求信号...

用户：看看上次流水线运行的状态
AI：[调用 get_pipeline_status] 上次运行于 2025-07-08，共提取 178 条信号...

用户：为第一条信号生成外联邮件
AI：[调用 generate_email] 已生成日语外联邮件...
```

## 验证安装

```bash
cd demo
python -c "from mcp.server.fastmcp import FastMCP; print('MCP SDK OK')"
python mcp_server.py  # 启动服务器（等待 stdio 输入）
```

如果看到进程挂起等待输入，说明服务器已正常启动。

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `ModuleNotFoundError: No module named 'mcp'` | 未安装 mcp 包 | `pip install mcp` |
| 工具返回 "demo.py not available" | 缺少 API Key | 在 `demo/.env` 中设置 `SERPAPI_KEY` 和 `QWEN_API_KEY` |
| 客户端显示工具但调用超时 | SerpAPI/Qwen API 响应慢 | 增加客户端超时设置 |
| `generate_email` 返回 "Item not found" | source_url 不在缓存中 | 先运行 `run_full_pipeline` 或 `search_demand_signal` |
| Windows 路径报错 | 反斜杠未转义 | 使用 `\\` 或 `/` |

## 扩展性

v0.1 架构支持后续添加更多工具，只需在 `mcp_server.py` 中添加 `@mcp.tool()` 装饰的函数即可，无需修改现有代码或设计。

计划中的后续版本工具：
- `fetch_company_profile` — 抓取公司网站邮箱
- `export_csv` — 导出 YAMM 格式 CSV
- `score_company` — 计算公司优先级评分
- `send_email` — 通过 SMTP 发送邮件
- `merge_pipeline_history` — 合并历史数据
