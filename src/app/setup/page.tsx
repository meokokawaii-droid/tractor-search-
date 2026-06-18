"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Copy, Check, Globe, Search, Settings, Key, Clock, Play, Zap, Database } from "lucide-react";
import { useState } from "react";

const currentKeywords = [
  '"Kubota tractor broke down" help',
  '"Kubota hydraulic pump" failure repair',
  '"Kubota" parts where to buy forum',
  '"Kubota tractor" not working fix',
  '"Kubota L3400" problems help',
  '"Kubota M9540" broke down advice',
  '"Kubota" engine failure help',
  '"Kubota" transmission problem fix',
  '"Kubota tractor" maintenance parts needed',
  '"Kubota" broken parts replacement help',
];

const searchExample = `// 触发搜索（使用默认关键词）
curl -X POST http://localhost:3000/api/google-search \\
  -H "Content-Type: application/json"

// 使用自定义关键词
curl -X POST http://localhost:3000/api/google-search \\
  -H "Content-Type: application/json" \\
  -d '{"keywords": ["Kubota L2201 parts forum", "Kubota seat broken help"]}'`;

const edgeFunctionExample = `// 手动触发 Edge Function 自动搜索
curl -X POST https://aapkzvsfaquznrvrtgdn.supabase.co/functions/v1/auto-search \\
  -H "Authorization: Bearer YOUR_ANON_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"keywords": ["Kubota urgently needed"]}'`;

export default function SetupPage() {
  const [copied, setCopied] = useState<string | null>(null);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="min-h-screen bg-slate-50 p-4 md:p-8">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Settings className="w-8 h-8 text-slate-700" />
            <div>
              <h1 className="text-2xl font-bold text-slate-900">系统配置</h1>
              <p className="text-slate-500">SerpAPI 搜索引擎配置与管理</p>
            </div>
          </div>
          <a
            href="/"
            className="inline-flex items-center gap-2 h-9 px-2.5 text-sm font-medium rounded-lg border border-slate-200 bg-white hover:bg-slate-50 transition-colors"
          >
            <Globe className="w-4 h-4" />
            Dashboard
          </a>
        </div>

        {/* Step 1: SerpAPI Key */}
        <Card className="bg-white border-2 border-emerald-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <span className="w-8 h-8 bg-emerald-100 rounded-full flex items-center justify-center text-emerald-700 font-bold">1</span>
              <Key className="w-5 h-5" />
              配置 SerpAPI 密钥
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-slate-600">申请 SerpAPI 密钥（替代已下线的 Google Custom Search API）：</p>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                <div>
                  <div className="font-medium">SerpAPI 官网</div>
                  <div className="text-sm text-slate-500">serpapi.com</div>
                </div>
                <Badge className="bg-emerald-100 text-emerald-700">API Key</Badge>
              </div>
            </div>
            <div className="bg-slate-100 p-3 rounded-lg">
              <p className="text-sm text-slate-700 font-medium mb-2">.env.local 配置：</p>
              <div className="font-mono text-sm text-slate-600">SERPAPI_KEY=your_serpapi_key_here</div>
            </div>
            <div className="bg-amber-50 border border-amber-200 p-3 rounded-lg text-sm text-amber-700">
              💡 免费账户每月 100 次搜索。每次"刷新搜索"消耗约 10 次（10 组关键词 × 1 次/组）。
            </div>
          </CardContent>
        </Card>

        {/* Step 2: Supabase */}
        <Card className="bg-white border-2 border-blue-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <span className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center text-blue-700 font-bold">2</span>
              <Database className="w-5 h-5" />
              Supabase 数据库配置
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-slate-600">确保以下环境变量已配置：</p>
            <div className="bg-slate-100 p-3 rounded-lg space-y-1 font-mono text-sm">
              <div className="text-slate-600">SUPABASE_URL=https://xxx.supabase.co</div>
              <div className="text-slate-600">NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co</div>
              <div className="text-slate-600">NEXT_PUBLIC_SUPABASE_ANON_KEY=sb_publishable_xxx</div>
              <div className="text-emerald-600 font-medium">SUPABASE_SERVICE_ROLE_KEY=sb_secret_xxx  ← 写入必须</div>
            </div>
            <div className="bg-blue-50 border border-blue-200 p-3 rounded-lg text-sm text-blue-700">
              🔑 <strong>Service Role Key</strong> 是写入数据库的必要密钥（绕过 RLS 策略）。在 Supabase Dashboard → Settings → API → Secret Keys 中获取。
            </div>
          </CardContent>
        </Card>

        {/* Step 3: Search Keywords */}
        <Card className="bg-white">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <span className="w-8 h-8 bg-slate-100 rounded-full flex items-center justify-center text-slate-700 font-bold">3</span>
              <Search className="w-5 h-5" />
              搜索关键词配置
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-slate-600">系统默认搜索以下关键词（聚焦真实用户求助场景）：</p>
            <div className="grid gap-2">
              {currentKeywords.map((kw, i) => (
                <div key={i} className="flex items-center gap-2 p-2 bg-slate-50 rounded text-sm">
                  <Badge variant="secondary" className="shrink-0">{i + 1}</Badge>
                  <code className="text-slate-700">{kw}</code>
                </div>
              ))}
            </div>
            <div className="bg-slate-100 p-3 rounded-lg text-sm text-slate-600">
              💡 搜索策略：使用 "broke down"、"failure repair"、"help" 等求助场景词，过滤掉供应商页面，精准锁定真实买家需求。
            </div>
          </CardContent>
        </Card>

        {/* Step 4: Manual Search */}
        <Card className="bg-white">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <span className="w-8 h-8 bg-slate-100 rounded-full flex items-center justify-center text-slate-700 font-bold">4</span>
              <Play className="w-5 h-5" />
              手动触发搜索
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-slate-600">API 端点：</p>
            <div className="relative">
              <pre className="bg-slate-900 text-emerald-400 p-4 rounded-lg font-mono text-sm overflow-x-auto whitespace-pre-wrap">
                {searchExample}
              </pre>
              <Button
                variant="ghost"
                size="sm"
                className="absolute top-2 right-2"
                onClick={() => copyToClipboard(searchExample, "search")}
              >
                {copied === "search" ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
              </Button>
            </div>
            <p className="text-sm text-slate-500">
              💡 推荐直接在 Dashboard 首页点击「刷新搜索」按钮，无需使用 curl。
            </p>
          </CardContent>
        </Card>

        {/* Step 5: Auto Scheduled Search */}
        <Card className="bg-white border-2 border-purple-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <span className="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center text-purple-700 font-bold">5</span>
              <Clock className="w-5 h-5" />
              定时自动搜索
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-slate-600">配置 Supabase Cron 定时任务，每天自动搜索：</p>
            <div className="bg-slate-100 p-3 rounded text-sm text-slate-700 space-y-2">
              <div>1. 进入 Supabase Dashboard</div>
              <div>2. Database → Extensions → 启用 <code className="bg-white px-1 rounded">pg_cron</code></div>
              <div>3. SQL Editor 执行：</div>
              <pre className="mt-2 bg-slate-900 text-emerald-400 p-2 rounded font-mono text-xs overflow-x-auto">{`SELECT cron.schedule(
  'auto-search-daily',
  '0 8 * * *',
  $$
  SELECT
    net.http_post(
      url := 'https://aapkzvsfaquznrvrtgdn.supabase.co/functions/v1/auto-search',
      headers := '{"Content-Type": "application/json"}'::jsonb
    );
  $$
);`}</pre>
            </div>
            <div className="bg-purple-50 border border-purple-200 p-3 rounded-lg text-sm text-purple-700">
              ⏰ 上面的 Cron 表达式 <code>0 8 * * *</code> 表示每天早上 8 点自动执行搜索。可根据需要调整时间。
            </div>
          </CardContent>
        </Card>

        {/* Data Flow */}
        <Card className="bg-white">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Zap className="w-5 h-5 text-amber-600" />
              数据流程
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col md:flex-row items-center justify-between gap-4 p-4">
              <div className="text-center">
                <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <Search className="w-6 h-6 text-blue-600" />
                </div>
                <div className="font-medium">SerpAPI 搜索</div>
                <div className="text-sm text-slate-500">全球关键词扫描</div>
              </div>
              <div className="text-slate-300 text-2xl md:rotate-0 rotate-90">→</div>
              <div className="text-center">
                <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <Settings className="w-6 h-6 text-emerald-600" />
                </div>
                <div className="font-medium">智能提取</div>
                <div className="text-sm text-slate-500">过滤供应商 + 信号分析</div>
              </div>
              <div className="text-slate-300 text-2xl md:rotate-0 rotate-90">→</div>
              <div className="text-center">
                <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <Globe className="w-6 h-6 text-purple-600" />
                </div>
                <div className="font-medium">Dashboard</div>
                <div className="text-sm text-slate-500">实时展示 + 状态管理</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
