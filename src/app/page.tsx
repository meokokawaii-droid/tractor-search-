"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { supabase } from "@/lib/supabase";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  AlertTriangle,
  RefreshCw,
  Globe,
  MapPin,
  Tractor,
  Wrench,
  Zap,
  Settings,
  Star,
  Trash2,
  ExternalLink,
  CheckCircle2,
  Filter,
  X,
  Download,
  ChevronDown,
  ChevronUp,
  TrendingUp,
  Link2Off,
  BarChart3,
  Trophy,
  Flame,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface Signal {
  id: string;
  raw_content: string;
  location: string | null;
  region: string | null;
  vehicle_model: string | null;
  part_category: string | null;
  urgency: "high_demand" | "inquiry" | null;
  source: string | null;
  source_url: string | null;
  status: string | null;
  created_at: string;
  pain_point?: string | null;
  source_type?: string | null;
}

interface Alert {
  id: string;
  part_category: string;
  vehicle_model: string | null;
  match_count: number;
  message: string;
  is_active: boolean;
  created_at: string;
}

export default function Dashboard() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [timeFilter, setTimeFilter] = useState<number>(8760);

  // Filters
  const [urgencyTab, setUrgencyTab] = useState<"high_demand" | "all">("high_demand");
  const [regionFilter, setRegionFilter] = useState<string>("all");
  const [partFilter, setPartFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("new"); // 默认只看未处理
  const [sourceTypeFilter, setSourceTypeFilter] = useState<string>("all");

  // Search state
  const [searching, setSearching] = useState(false);
  const [searchProgress, setSearchProgress] = useState<string>("");
  const [searchCurrentIdx, setSearchCurrentIdx] = useState(0);
  const [searchTotal, setSearchTotal] = useState(0);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  // Expanded signal
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Last search time
  const [lastSearchAt, setLastSearchAt] = useState<string | null>(null);

  // Insights panel expand state
  const [insightsExpanded, setInsightsExpanded] = useState(true);

  const abortRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - 400); // ~1 year + buffer
      const [signalsRes, alertsRes] = await Promise.all([
        supabase
          .from("signals")
          .select("*")
          .gte("created_at", cutoffDate.toISOString())
          .order("created_at", { ascending: false })
          .limit(200),
        supabase
          .from("alerts")
          .select("*")
          .eq("is_active", true)
          .order("created_at", { ascending: false }),
      ]);

      if (signalsRes.data) setSignals(signalsRes.data);
      if (alertsRes.data) setAlerts(alertsRes.data);
      setLastUpdate(new Date());
    } catch (error) {
      console.error("Error fetching data:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem("timeFilter");
    if (saved) setTimeFilter(Number(saved));
    const savedSearch = localStorage.getItem("lastSearchAt");
    if (savedSearch) setLastSearchAt(savedSearch);
  }, []);

  useEffect(() => {
    localStorage.setItem("timeFilter", String(timeFilter));
  }, [timeFilter]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const getUrgencyBadge = (urgency: string | null) => {
    if (urgency === "high_demand") {
      return (
        <Badge variant="destructive" className="gap-1">
          <Zap className="w-3 h-3" />
          急需采购
        </Badge>
      );
    }
    return (
      <Badge variant="secondary" className="gap-1">
        询问意向
      </Badge>
    );
  };

  const getStatusBadge = (status: string | null) => {
    switch (status) {
      case "following":
        return <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-200">跟进中</Badge>;
      case "done":
        return <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-200">已成交</Badge>;
      case "invalid":
        return <Badge className="bg-slate-100 text-slate-500 hover:bg-slate-200">无效</Badge>;
      case "dead_link":
        return <Badge className="bg-red-100 text-red-600 hover:bg-red-200">🔗失效</Badge>;
      default:
        return <Badge className="bg-blue-100 text-blue-700 hover:bg-blue-200">未处理</Badge>;
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diff < 60) return "刚刚";
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
    return date.toLocaleDateString("zh-CN");
  };

  const triggerSearch = async () => {
    if (searching) return;
    setSearching(true);
    setSearchCurrentIdx(0);
    setSearchTotal(10);
    setSearchProgress("正在启动搜索...");

    try {
      const res = await fetch("/api/google-search", { method: "POST" });
      const data = await res.json();

      if (data.success) {
        setSearchProgress(`✅ 完成！${data.signals_extracted} 条新线索（共搜索 ${data.keywords_searched} 组关键词）`);
        const now = new Date().toISOString();
        setLastSearchAt(now);
        localStorage.setItem("lastSearchAt", now);
        await fetchData();
      } else {
        setSearchProgress(`❌ 搜索失败: ${data.error || "未知错误"}`);
      }
    } catch (err) {
      setSearchProgress(`❌ 搜索失败: ${String(err)}`);
    } finally {
      setTimeout(() => {
        setSearching(false);
        setSearchProgress("");
      }, 3000);
    }
  };

  const updateSignalStatus = async (id: string, status: string) => {
    setUpdatingId(id);
    try {
      const res = await fetch("/api/signals/update-status", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, status }),
      });
      const data = await res.json();
      if (data.success) {
        setSignals((prev) =>
          prev.map((s) => (s.id === id ? { ...s, status } : s))
        );
      } else {
        console.error("Update failed:", data.error);
      }
    } catch (error) {
      console.error("Error updating status:", error);
    } finally {
      setUpdatingId(null);
    }
  };

  // Export CSV
  const exportCSV = () => {
    const headers = ["日期", "地区", "位置", "车型", "配件类别", "紧急度", "痛点", "来源类型", "状态", "来源链接", "内容摘要"];
    const rows = filteredSignals.map((s) => [
      new Date(s.created_at).toLocaleDateString("zh-CN"),
      s.region || "",
      s.location || "",
      s.vehicle_model || "",
      s.part_category || "",
      s.urgency === "high_demand" ? "急需采购" : "询问意向",
      s.pain_point || "",
      s.source_type === "forum" ? "论坛" : s.source_type === "youtube" ? "YouTube" : s.source_type === "news" ? "新闻" : s.source_type === "general_web" ? "网页" : "",
      s.status === "following" ? "跟进中" : s.status === "done" ? "已成交" : s.status === "invalid" ? "无效" : s.status === "dead_link" ? "链接失效" : "未处理",
      s.source_url || "",
      `"${(s.raw_content || "").replace(/"/g, '""').substring(0, 200)}"`,
    ]);

    const csvContent = "\uFEFF" + [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `农机需求信号_${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Dynamic filter options from data
  const regionOptions = useMemo(() => {
    const regions = new Set<string>();
    signals.forEach((s) => {
      if (s.region && s.region !== "Unknown") regions.add(s.region);
    });
    return ["all", ...Array.from(regions).sort()];
  }, [signals]);

  const partOptions = useMemo(() => {
    const parts = new Set<string>();
    signals.forEach((s) => {
      if (s.part_category) parts.add(s.part_category);
    });
    return ["all", ...Array.from(parts).sort()];
  }, [signals]);

  const statusOptions = [
    { value: "all", label: "全部状态" },
    { value: "new", label: "未处理" },
    { value: "following", label: "跟进中" },
    { value: "done", label: "已成交" },
    { value: "invalid", label: "无效" },
    { value: "dead_link", label: "链接失效" },
  ];

  const sourceTypeOptions = [
    { value: "all", label: "全部来源" },
    { value: "forum", label: "论坛" },
    { value: "youtube", label: "YouTube" },
    { value: "news", label: "新闻" },
    { value: "general_web", label: "网页" },
  ];

  // Combined filtering logic
  const filteredSignals = useMemo(() => {
    return signals.filter((s) => {
      if (timeFilter !== 0) {
        const diffHours =
          (new Date().getTime() - new Date(s.created_at).getTime()) /
          (1000 * 60 * 60);
        if (diffHours > timeFilter) return false;
      }
      if (urgencyTab === "high_demand" && s.urgency !== "high_demand") return false;
      if (regionFilter !== "all" && s.region !== regionFilter) return false;
      if (partFilter !== "all" && s.part_category !== partFilter) return false;
      if (statusFilter !== "all" && s.status !== statusFilter) return false;
      if (sourceTypeFilter !== "all" && s.source_type !== sourceTypeFilter) return false;
      return true;
    });
  }, [signals, timeFilter, urgencyTab, regionFilter, partFilter, statusFilter, sourceTypeFilter]);

  // Demand Insights — all computed from existing data, zero API cost
  const demandInsights = useMemo(() => {
    // Hot vehicle models TOP 10
    const modelCounts: Record<string, number> = {};
    filteredSignals.forEach((s) => {
      if (s.vehicle_model && !s.vehicle_model.includes("unspecified")) {
        modelCounts[s.vehicle_model] = (modelCounts[s.vehicle_model] || 0) + 1;
      }
    });
    const hotModels = Object.entries(modelCounts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 10);

    // Hot parts TOP 10
    const partCounts: Record<string, number> = {};
    filteredSignals.forEach((s) => {
      if (s.part_category) {
        partCounts[s.part_category] = (partCounts[s.part_category] || 0) + 1;
      }
    });
    const hotParts = Object.entries(partCounts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 10);

    // Pain point distribution
    const painCounts: Record<string, number> = {};
    filteredSignals.forEach((s) => {
      if (s.pain_point) {
        painCounts[s.pain_point] = (painCounts[s.pain_point] || 0) + 1;
      }
    });
    const painDistribution = Object.entries(painCounts)
      .sort(([, a], [, b]) => b - a);

    // Region demand distribution
    const regionCounts: Record<string, number> = {};
    filteredSignals.forEach((s) => {
      if (s.region && s.region !== "Unknown") {
        regionCounts[s.region] = (regionCounts[s.region] || 0) + 1;
      }
    });
    const regionDistribution = Object.entries(regionCounts)
      .sort(([, a], [, b]) => b - a);

    // Model + Part combo ranking (most valuable insight for stocking decisions)
    const comboCounts: Record<string, number> = {};
    filteredSignals.forEach((s) => {
      if (s.vehicle_model && s.part_category && !s.vehicle_model.includes("unspecified")) {
        const key = `${s.vehicle_model}|||${s.part_category}`;
        comboCounts[key] = (comboCounts[key] || 0) + 1;
      }
    });
    const hotCombos = Object.entries(comboCounts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 8)
      .map(([key, count]) => {
        const [model, part] = key.split("|||");
        return { model, part, count };
      });

    // Max count for bar chart scaling
    const maxModelCount = hotModels.length > 0 ? hotModels[0][1] : 1;
    const maxPartCount = hotParts.length > 0 ? hotParts[0][1] : 1;
    const maxComboCount = hotCombos.length > 0 ? hotCombos[0].count : 1;
    const maxPainCount = painDistribution.length > 0 ? painDistribution[0][1] : 1;
    const maxRegionCount = regionDistribution.length > 0 ? regionDistribution[0][1] : 1;

    return {
      hotModels,
      hotParts,
      painDistribution,
      regionDistribution,
      hotCombos,
      maxModelCount,
      maxPartCount,
      maxComboCount,
      maxPainCount,
      maxRegionCount,
    };
  }, [filteredSignals]);

  // Trending parts breakdown (for quick tag bar)
  const trendingParts = useMemo(() => {
    const counts: Record<string, number> = {};
    filteredSignals.forEach((s) => {
      if (s.part_category) {
        counts[s.part_category] = (counts[s.part_category] || 0) + 1;
      }
    });
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5);
  }, [filteredSignals]);

  const stats = {
    total: filteredSignals.length,
    highDemand: filteredSignals.filter((s) => s.urgency === "high_demand").length,
    following: signals.filter((s) => s.status === "following").length,
    regions: [...new Set(filteredSignals.map((s) => s.region).filter(Boolean))].length,
  };

  const timeFilterOptions = [
    { value: 1, label: "1小时" },
    { value: 24, label: "24小时" },
    { value: 168, label: "7天" },
    { value: 720, label: "30天" },
    { value: 4320, label: "半年" },
    { value: 8760, label: "1年" },
  ];

  const latestSignalDate = signals.length > 0 ? new Date(signals[0].created_at) : null;
  const dataAgeDays = latestSignalDate
    ? Math.floor((new Date().getTime() - latestSignalDate.getTime()) / (1000 * 60 * 60 * 24))
    : 0;
  const isDataStale = dataAgeDays > 30;

  const activeFilterCount =
    (urgencyTab !== "all" ? 1 : 0) +
    (regionFilter !== "all" ? 1 : 0) +
    (partFilter !== "all" ? 1 : 0) +
    (statusFilter !== "all" ? 1 : 0) +
    (sourceTypeFilter !== "all" ? 1 : 0);

  const hasInsights = demandInsights.hotModels.length > 0 || demandInsights.hotParts.length > 0 || demandInsights.painDistribution.length > 0;

  return (
    <div className="min-h-screen bg-slate-50 p-3 md:p-4">
      <div className="max-w-7xl mx-auto space-y-4">
        {/* Data Stale Warning */}
        {isDataStale && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-center justify-between">
            <div className="flex items-center gap-2 text-amber-700">
              <AlertTriangle className="w-5 h-5" />
              <span className="text-sm">
                最新数据已 {dataAgeDays} 天未更新，点击右侧刷新搜索
              </span>
            </div>
          </div>
        )}

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Tractor className="w-6 h-6 text-slate-700" />
            <h1 className="text-xl font-bold text-slate-900">全球农机需求监控</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={triggerSearch}
              disabled={searching}
              className="inline-flex items-center gap-1 h-8 px-3 text-sm rounded-md bg-emerald-600 text-white hover:bg-emerald-700 transition-colors disabled:opacity-50"
            >
              <Zap className="w-4 h-4" />
              {searching ? "搜索中..." : "刷新搜索"}
            </button>
            <button
              onClick={exportCSV}
              disabled={filteredSignals.length === 0}
              className="inline-flex items-center gap-1 h-8 px-3 text-sm rounded-md bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 transition-colors disabled:opacity-40"
            >
              <Download className="w-4 h-4" />
              导出
            </button>
            <a
              href="/setup"
              className="inline-flex items-center gap-1 h-8 px-3 text-sm rounded-md hover:bg-slate-100 transition-colors"
            >
              <Settings className="w-4 h-4" />
              设置
            </a>
            <div className="flex items-center gap-2 text-sm text-slate-500">
              {lastUpdate && (
                <span className="hidden sm:inline">更新于 {lastUpdate.toLocaleTimeString("zh-CN")}</span>
              )}
              <Button variant="ghost" size="icon" onClick={fetchData} className="h-8 w-8">
                <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              </Button>
            </div>
          </div>
        </div>

        {/* Search Progress */}
        {searching && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
            <div className="flex items-center gap-3">
              <RefreshCw className="w-5 h-5 text-blue-600 animate-spin" />
              <div className="flex-1">
                <p className="text-sm text-blue-700 font-medium">{searchProgress}</p>
                <p className="text-xs text-blue-500 mt-1">
                  搜索关键词中，每组间隔 1.5 秒防限流，预计需要 30-60 秒
                </p>
              </div>
            </div>
            <div className="mt-2 bg-blue-200 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-blue-600 h-full rounded-full transition-all duration-500"
                style={{ width: searching ? "100%" : "0%", animation: searching ? "pulse 2s infinite" : "none" }}
              />
            </div>
          </div>
        )}

        {/* Search Result Status (non-searching) */}
        {searchProgress && !searching && (
          <div
            className={`rounded-lg p-2.5 text-sm ${
              searchProgress.startsWith("✅")
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                : "bg-rose-50 text-rose-700 border border-rose-200"
            }`}
          >
            {searchProgress}
          </div>
        )}

        {/* Last search time */}
        {lastSearchAt && !searching && !searchProgress && (
          <div className="text-xs text-slate-400">
            上次搜索: {new Date(lastSearchAt).toLocaleString("zh-CN")}
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-3">
          <Card className="bg-white">
            <CardContent className="p-3 md:p-4">
              <div className="text-2xl md:text-3xl font-bold text-slate-900">{stats.total}</div>
              <div className="text-xs md:text-sm text-slate-500">当前筛选信号</div>
            </CardContent>
          </Card>
          <Card className="bg-white">
            <CardContent className="p-3 md:p-4">
              <div className="text-2xl md:text-3xl font-bold text-rose-600">{stats.highDemand}</div>
              <div className="text-xs md:text-sm text-slate-500">急需采购</div>
            </CardContent>
          </Card>
          <Card className="bg-white">
            <CardContent className="p-3 md:p-4">
              <div className="text-2xl md:text-3xl font-bold text-amber-600">{stats.following}</div>
              <div className="text-xs md:text-sm text-slate-500">跟进中</div>
            </CardContent>
          </Card>
          <Card className="bg-white">
            <CardContent className="p-3 md:p-4">
              <div className="text-2xl md:text-3xl font-bold text-emerald-600">{stats.regions}</div>
              <div className="text-xs md:text-sm text-slate-500">覆盖地区</div>
            </CardContent>
          </Card>
        </div>

        {/* ========== 需求洞察面板 ========== */}
        {hasInsights && (
          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
            <button
              onClick={() => setInsightsExpanded(!insightsExpanded)}
              className="w-full flex items-center justify-between p-3 hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <BarChart3 className="w-4 h-4 text-indigo-600" />
                需求洞察
                <span className="text-xs text-slate-400 font-normal">（从当前筛选数据计算，点击条目可筛选）</span>
              </div>
              {insightsExpanded ? (
                <ChevronUp className="w-4 h-4 text-slate-400" />
              ) : (
                <ChevronDown className="w-4 h-4 text-slate-400" />
              )}
            </button>

            {insightsExpanded && (
              <div className="px-3 pb-3 space-y-4">
                {/* 2-column layout: Models + Parts */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Hot Models */}
                  {demandInsights.hotModels.length > 0 && (
                    <div>
                      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 mb-2">
                        <Trophy className="w-3.5 h-3.5 text-amber-500" />
                        热门型号 TOP {demandInsights.hotModels.length}
                      </div>
                      <div className="space-y-1.5">
                        {demandInsights.hotModels.map(([model, count], idx) => (
                          <button
                            key={model}
                            onClick={() => {
                              // Can't filter by model directly, but switch to "all" tab to see this model
                              if (urgencyTab === "high_demand") setUrgencyTab("all");
                            }}
                            className="w-full flex items-center gap-2 group"
                          >
                            <span className={`w-5 text-xs font-bold text-right ${
                              idx < 3 ? "text-amber-500" : "text-slate-400"
                            }`}>{idx + 1}</span>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between mb-0.5">
                                <span className="text-sm text-slate-700 truncate group-hover:text-indigo-600 transition-colors">{model}</span>
                                <span className="text-xs font-bold text-slate-500 ml-2">{count}条</span>
                              </div>
                              <div className="bg-slate-100 rounded-full h-1.5 overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all ${
                                    idx < 3 ? "bg-amber-400" : "bg-slate-300"
                                  }`}
                                  style={{ width: `${(count / demandInsights.maxModelCount) * 100}%` }}
                                />
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Hot Parts */}
                  {demandInsights.hotParts.length > 0 && (
                    <div>
                      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 mb-2">
                        <Wrench className="w-3.5 h-3.5 text-indigo-500" />
                        热门配件 TOP {demandInsights.hotParts.length}
                      </div>
                      <div className="space-y-1.5">
                        {demandInsights.hotParts.map(([part, count], idx) => (
                          <button
                            key={part}
                            onClick={() => setPartFilter(part === partFilter ? "all" : part)}
                            className="w-full flex items-center gap-2 group"
                          >
                            <span className={`w-5 text-xs font-bold text-right ${
                              idx < 3 ? "text-indigo-500" : "text-slate-400"
                            }`}>{idx + 1}</span>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between mb-0.5">
                                <span className={`text-sm truncate transition-colors ${
                                  partFilter === part ? "text-indigo-600 font-semibold" : "text-slate-700 group-hover:text-indigo-600"
                                }`}>{part}</span>
                                <span className="text-xs font-bold text-slate-500 ml-2">{count}条</span>
                              </div>
                              <div className="bg-slate-100 rounded-full h-1.5 overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all ${
                                    partFilter === part ? "bg-indigo-600" : idx < 3 ? "bg-indigo-400" : "bg-slate-300"
                                  }`}
                                  style={{ width: `${(count / demandInsights.maxPartCount) * 100}%` }}
                                />
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* 3-column: Pain points + Regions + Model+Part Combos */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* Pain Points */}
                  {demandInsights.painDistribution.length > 0 && (
                    <div>
                      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 mb-2">
                        <Flame className="w-3.5 h-3.5 text-orange-500" />
                        痛点分布
                      </div>
                      <div className="space-y-1">
                        {demandInsights.painDistribution.map(([pain, count]) => (
                          <div key={pain} className="flex items-center gap-2">
                            <span className="text-xs text-orange-600 min-w-[70px]">🔥 {pain}</span>
                            <div className="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className="h-full rounded-full bg-orange-400"
                                style={{ width: `${(count / demandInsights.maxPainCount) * 100}%` }}
                              />
                            </div>
                            <span className="text-xs font-bold text-slate-400">{count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Region Distribution */}
                  {demandInsights.regionDistribution.length > 0 && (
                    <div>
                      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 mb-2">
                        <MapPin className="w-3.5 h-3.5 text-emerald-500" />
                        地区需求分布
                      </div>
                      <div className="space-y-1">
                        {demandInsights.regionDistribution.map(([region, count]) => (
                          <button
                            key={region}
                            onClick={() => setRegionFilter(region === regionFilter ? "all" : region)}
                            className="w-full flex items-center gap-2 group"
                          >
                            <span className={`text-xs min-w-[70px] transition-colors ${
                              regionFilter === region ? "text-emerald-600 font-semibold" : "text-slate-600 group-hover:text-emerald-600"
                            }`}>{region}</span>
                            <div className="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  regionFilter === region ? "bg-emerald-600" : "bg-emerald-400"
                                }`}
                                style={{ width: `${(count / demandInsights.maxRegionCount) * 100}%` }}
                              />
                            </div>
                            <span className="text-xs font-bold text-slate-400">{count}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Model + Part Combo — the most actionable insight */}
                  {demandInsights.hotCombos.length > 0 && (
                    <div>
                      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 mb-2">
                        <TrendingUp className="w-3.5 h-3.5 text-rose-500" />
                        型号+配件 组合排行
                        <span className="text-[10px] text-rose-400">备货重点</span>
                      </div>
                      <div className="space-y-1">
                        {demandInsights.hotCombos.map(({ model, part, count }, idx) => (
                          <button
                            key={`${model}-${part}`}
                            onClick={() => setPartFilter(part === partFilter ? "all" : part)}
                            className="w-full flex items-center gap-2 group"
                          >
                            <span className={`w-4 text-xs font-bold text-right ${
                              idx < 2 ? "text-rose-500" : "text-slate-400"
                            }`}>{idx + 1}</span>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1 mb-0.5">
                                <span className="text-xs text-slate-700 truncate group-hover:text-rose-600 transition-colors">
                                  {model}
                                </span>
                                <span className="text-[10px] text-slate-400">+</span>
                                <span className={`text-xs truncate ${
                                  partFilter === part ? "text-rose-600 font-semibold" : "text-slate-500"
                                }`}>{part}</span>
                              </div>
                              <div className="bg-slate-100 rounded-full h-1 overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    partFilter === part ? "bg-rose-600" : idx < 2 ? "bg-rose-400" : "bg-slate-300"
                                  }`}
                                  style={{ width: `${(count / demandInsights.maxComboCount) * 100}%` }}
                                />
                              </div>
                            </div>
                            <span className="text-xs font-bold text-rose-500">{count}条</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Trending Parts Quick Tags */}
        {trendingParts.length > 0 && (
          <div className="bg-white rounded-lg border border-slate-200 p-3">
            <div className="flex items-center gap-1.5 text-sm font-medium text-slate-700 mb-2">
              <TrendingUp className="w-4 h-4 text-emerald-600" />
              热门需求品类
            </div>
            <div className="flex flex-wrap gap-2">
              {trendingParts.map(([part, count]) => (
                <button
                  key={part}
                  onClick={() => setPartFilter(part === partFilter ? "all" : part)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1 text-sm rounded-full transition-colors ${
                    partFilter === part
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  <Wrench className="w-3 h-3" />
                  {part}
                  <span className={`text-xs font-bold ${
                    partFilter === part ? "text-slate-300" : "text-slate-400"
                  }`}>
                    {count}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Urgent Alerts */}
        {alerts.length > 0 && (
          <Card className="border-rose-200 bg-rose-50">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-rose-700 text-base">
                <AlertTriangle className="w-5 h-5" />
                加急囤货建议
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {alerts.slice(0, 3).map((alert) => (
                <div key={alert.id} className="bg-white rounded-lg p-3 border border-rose-100">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <Wrench className="w-4 h-4 text-rose-600" />
                        <span className="font-semibold text-slate-900">{alert.part_category}</span>
                        {alert.vehicle_model && (
                          <Badge variant="outline" className="text-xs">{alert.vehicle_model}</Badge>
                        )}
                      </div>
                      <p className="text-sm text-slate-600 mt-1">{alert.message}</p>
                    </div>
                    <div className="bg-rose-600 text-white px-2 py-1 rounded text-sm font-bold">
                      {alert.match_count}条
                    </div>
                  </div>
                  <div className="text-xs text-slate-400 mt-2">{formatTime(alert.created_at)}</div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Urgency Tabs */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setUrgencyTab("high_demand")}
            className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors ${
              urgencyTab === "high_demand"
                ? "bg-rose-100 text-rose-700 border border-rose-200"
                : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
            }`}
          >
            <span className="flex items-center gap-1.5">
              <Zap className="w-4 h-4" />
              急需采购
            </span>
          </button>
          <button
            onClick={() => setUrgencyTab("all")}
            className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors ${
              urgencyTab === "all"
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
            }`}
          >
            <span className="flex items-center gap-1.5">
              <Globe className="w-4 h-4" />
              全部信号
            </span>
          </button>
        </div>

        {/* Filters Bar */}
        <div className="flex items-center gap-2 flex-wrap bg-white rounded-lg p-3 border border-slate-200">
          <div className="flex items-center gap-1.5 text-sm text-slate-500 mr-1">
            <Filter className="w-4 h-4" />
            筛选
            {activeFilterCount > 0 && (
              <span className="bg-slate-900 text-white text-xs px-1.5 py-0.5 rounded-full">
                {activeFilterCount}
              </span>
            )}
          </div>

          {/* Time Filter */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-slate-400">时间</span>
            {timeFilterOptions.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setTimeFilter(opt.value)}
                className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                  timeFilter === opt.value
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div className="w-px h-6 bg-slate-200" />

          {/* Region Filter */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-slate-400">地区</span>
            <select
              value={regionFilter}
              onChange={(e) => setRegionFilter(e.target.value)}
              className="text-sm bg-slate-100 border-none rounded-full px-3 py-1 text-slate-700 focus:ring-2 focus:ring-slate-300 outline-none cursor-pointer"
            >
              <option value="all">全部</option>
              {regionOptions
                .filter((r) => r !== "all")
                .map((region) => (
                  <option key={region} value={region}>{region}</option>
                ))}
            </select>
          </div>

          <div className="w-px h-6 bg-slate-200" />

          {/* Part Filter */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-slate-400">配件</span>
            <select
              value={partFilter}
              onChange={(e) => setPartFilter(e.target.value)}
              className="text-sm bg-slate-100 border-none rounded-full px-3 py-1 text-slate-700 focus:ring-2 focus:ring-slate-300 outline-none cursor-pointer"
            >
              <option value="all">全部</option>
              {partOptions
                .filter((p) => p !== "all")
                .map((part) => (
                  <option key={part} value={part}>{part}</option>
                ))}
            </select>
          </div>

          <div className="w-px h-6 bg-slate-200" />

          {/* Status Filter */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-slate-400">状态</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="text-sm bg-slate-100 border-none rounded-full px-3 py-1 text-slate-700 focus:ring-2 focus:ring-slate-300 outline-none cursor-pointer"
            >
              {statusOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="w-px h-6 bg-slate-200" />

          {/* Source Type Filter */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-slate-400">来源</span>
            <select
              value={sourceTypeFilter}
              onChange={(e) => setSourceTypeFilter(e.target.value)}
              className="text-sm bg-slate-100 border-none rounded-full px-3 py-1 text-slate-700 focus:ring-2 focus:ring-slate-300 outline-none cursor-pointer"
            >
              {sourceTypeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Clear Filters */}
          {activeFilterCount > 0 && (
            <button
              onClick={() => {
                setRegionFilter("all");
                setPartFilter("all");
                setStatusFilter("new");
                setSourceTypeFilter("all");
              }}
              className="ml-auto text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1"
            >
              <X className="w-3 h-3" />
              清除筛选
            </button>
          )}
        </div>

        {/* Signal Cards */}
        <div className="space-y-3">
          {loading ? (
            <div className="text-center py-12 text-slate-400">
              <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3" />
              加载中...
            </div>
          ) : filteredSignals.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-lg border border-slate-200">
              <div className="text-slate-400 mb-2">
                <Globe className="w-12 h-12 mx-auto mb-2 opacity-30" />
                暂无符合条件的信号
              </div>
              <p className="text-sm text-slate-400 mb-4">试试调整筛选条件或刷新搜索</p>
              <button
                onClick={() => setStatusFilter("all")}
                className="text-sm text-blue-600 hover:underline"
              >
                查看全部状态信号 →
              </button>
            </div>
          ) : (
            filteredSignals.map((signal) => (
              <div
                key={signal.id}
                className={`bg-white rounded-lg border p-4 transition-shadow hover:shadow-md ${
                  signal.status === "invalid"
                    ? "opacity-50 border-slate-100"
                    : signal.status === "dead_link"
                    ? "opacity-50 border-red-100"
                    : signal.urgency === "high_demand"
                    ? "border-rose-200 hover:border-rose-300"
                    : "border-slate-200 hover:border-slate-300"
                }`}
              >
                {/* Card Header */}
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    {getUrgencyBadge(signal.urgency)}
                    {getStatusBadge(signal.status)}
                    {signal.source_type && (
                      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${
                        signal.source_type === 'forum'
                          ? 'bg-purple-100 text-purple-700'
                          : signal.source_type === 'youtube'
                          ? 'bg-red-100 text-red-700'
                          : signal.source_type === 'news'
                          ? 'bg-sky-100 text-sky-700'
                          : 'bg-slate-100 text-slate-500'
                      }`}>
                        {signal.source_type === 'forum' && '💬'}
                        {signal.source_type === 'youtube' && '▶️'}
                        {signal.source_type === 'news' && '📰'}
                        {signal.source_type === 'general_web' && '🌐'}
                        {signal.source_type === 'forum' ? '论坛' : signal.source_type === 'youtube' ? 'YouTube' : signal.source_type === 'news' ? '新闻' : '网页'}
                      </span>
                    )}
                    {signal.pain_point && (
                      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700">
                        🔥 {signal.pain_point}
                      </span>
                    )}
                    {signal.region && signal.region !== "Unknown" && (
                      <span className="flex items-center gap-1 text-xs text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full">
                        <MapPin className="w-3 h-3" />
                        {signal.region}
                      </span>
                    )}
                    {signal.part_category && (
                      <span className="flex items-center gap-1 text-xs text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full">
                        <Wrench className="w-3 h-3" />
                        {signal.part_category}
                      </span>
                    )}
                    {signal.vehicle_model && (
                      <Badge variant="outline" className="text-xs">{signal.vehicle_model}</Badge>
                    )}
                  </div>
                  <span className="text-xs text-slate-400 whitespace-nowrap">
                    {formatTime(signal.created_at)}
                  </span>
                </div>

                {/* Card Content */}
                <div className="mb-3">
                  <p className={`text-sm text-slate-700 leading-relaxed ${
                    expandedId === signal.id ? "" : "line-clamp-2"
                  }`}>
                    {signal.raw_content}
                  </p>
                  {signal.raw_content && signal.raw_content.length > 100 && (
                    <button
                      onClick={() => setExpandedId(expandedId === signal.id ? null : signal.id)}
                      className="text-xs text-blue-600 hover:underline mt-1 inline-flex items-center gap-0.5"
                    >
                      {expandedId === signal.id ? (
                        <>收起 <ChevronUp className="w-3 h-3" /></>
                      ) : (
                        <>展开全文 <ChevronDown className="w-3 h-3" /></>
                      )}
                    </button>
                  )}
                  {signal.location && (
                    <p className="text-xs text-slate-400 mt-1">📍 {signal.location}</p>
                  )}
                </div>

                {/* Card Actions */}
                <div className="flex items-center gap-2 pt-3 border-t border-slate-100">
                  <a
                    href={signal.source_url || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ${
                      signal.source_url
                        ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                        : "bg-slate-50 text-slate-400 cursor-not-allowed"
                    }`}
                    onClick={(e) => { if (!signal.source_url) e.preventDefault(); }}
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    打开来源
                  </a>

                  {/* Dead link button — always visible for non-dead signals */}
                  {signal.status !== "dead_link" && signal.status !== "invalid" && signal.status !== "done" && (
                    <button
                      onClick={() => updateSignalStatus(signal.id, "dead_link")}
                      disabled={updatingId === signal.id}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md transition-colors bg-slate-50 text-slate-400 hover:bg-red-50 hover:text-red-500"
                      title="标记此链接已失效/404"
                    >
                      <Link2Off className="w-3 h-3" />
                      链接失效
                    </button>
                  )}

                  {signal.status !== "following" && signal.status !== "done" && signal.status !== "invalid" && signal.status !== "dead_link" && (
                    <button
                      onClick={() => updateSignalStatus(signal.id, "following")}
                      disabled={updatingId === signal.id}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors bg-slate-100 text-slate-700 hover:bg-amber-50 hover:text-amber-700"
                    >
                      <Star className="w-3.5 h-3.5" />
                      标记跟进
                    </button>
                  )}

                  {signal.status === "following" && (
                    <button
                      onClick={() => updateSignalStatus(signal.id, "done")}
                      disabled={updatingId === signal.id}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors bg-amber-100 text-amber-700 hover:bg-emerald-50 hover:text-emerald-700"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      标记成交
                    </button>
                  )}

                  {/* Right-side actions */}
                  {(signal.status === "invalid" || signal.status === "dead_link") ? (
                    <button
                      onClick={() => updateSignalStatus(signal.id, "new")}
                      disabled={updatingId === signal.id}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ml-auto bg-slate-100 text-slate-500 hover:bg-blue-50 hover:text-blue-600"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      恢复
                    </button>
                  ) : (
                    <div className="flex items-center gap-1 ml-auto">
                      <button
                        onClick={() => updateSignalStatus(signal.id, "invalid")}
                        disabled={updatingId === signal.id}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md transition-colors bg-slate-50 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                        title="标记为无效/不相关"
                      >
                        <Trash2 className="w-3 h-3" />
                        无效
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
