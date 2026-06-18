# 全球农机售后需求监控仪 (Global Agricultural Machinery Demand Monitor)

实时监控全球农机配件需求信号的系统。

## 功能特性

- **Google Search 自动抓取**: 通过 Google Custom Search API 搜索论坛和公开市场需求
- **AI 信号提取**: 自动过滤 Kubota 相关配件需求，识别地区、车型、配件类型
- **紧急度判定**: 自动标记"急需采购"或"询问意向"
- **加急囤货建议**: 检测到同型号配件连续 3+ 个需求时自动生成告警
- **定时自动化**: 支持定时执行搜索任务

## API 使用

### 手动触发 Google Search

```bash
POST /api/google-search
Content-Type: application/json

# 使用默认关键词
{}

# 自定义关键词
{
  "keywords": ["Kubota L2201 parts", "tractor seat Thailand"]
}
```

### 手动提交数据

```bash
POST /api/process-raw-data
Content-Type: application/json

# 单条数据
{
  "content": "URGENT! Looking for Kubota seat for L2201...",
  "location": "Nigeria",
  "source": "forum"
}

# 多条数据（数组）
[
  { "content": "...", "location": "..." },
  { "content": "...", "location": "..." }
]
```

### Edge Function 自动搜索

```bash
POST https://your-project.supabase.co/functions/v1/auto-search
Authorization: Bearer YOUR_ANON_KEY
Content-Type: application/json

{}
```

## 配置

### 环境变量

```env
GOOGLE_API_KEY=your_google_api_key
GOOGLE_SEARCH_ENGINE_ID=your_search_engine_id
```

### 定时任务配置

在 Supabase SQL Editor 中执行：

```sql
SELECT cron.schedule(
  'auto-search-hourly',
  '0 * * * *',
  $$
  SELECT net.http_post(
    url := 'https://your-project.supabase.co/functions/v1/auto-search',
    headers := '{"Content-Type": "application/json"}'::jsonb
  );
  $$
);
```

## 支持的关键词

**品牌**: Kubota, 久保田

**配件**: filter, seat, pump, engine, transmission, hydraulic, belt, bearing, gasket, valve, cylinder, tire, battery, radiator, clutch, brake, steering
(中文: 滤芯, 座椅, 泵, 发动机, 变速箱, 液压, 轮胎, 电瓶)

**地区关键词**: Africa, Southeast Asia, South Asia, Middle East, Latin America, Europe, North America, East Asia

**紧急关键词**:
- 高需求: urgent, immediately, asap, 急需, 急购, 立即, broken, problem
- 询问: asking, interested, quote, 询问, 询价, where to buy

## 数据库结构

- `signals`: 存储提取的需求信号
- `alerts`: 存储加急囤货建议

## 开发

```bash
npm run dev
```

访问 http://localhost:3000/setup 查看配置指南。
