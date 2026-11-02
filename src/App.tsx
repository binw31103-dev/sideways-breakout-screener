import {
  Activity,
  BarChart3,
  CalendarDays,
  ChevronRight,
  CircleAlert,
  FileText,
  Filter,
  Layers3,
  LayoutDashboard,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Target,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import rawData from "./data/stock-data.json";
import historyData from "./data/daily-history.json";
import type { DailyHistoryData, DashboardData, Report, Stock } from "./types";

const data = rawData as DashboardData;
const history = historyData as DailyHistoryData;
type View = "overview" | "reports" | "timeline" | "categories" | "forecast";
type SortKey = "score" | "weeklyRsi" | "riseFromYearLow" | "performance";

const NAV_ITEMS: { id: View; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "汇总", icon: LayoutDashboard },
  { id: "reports", label: "选股报告", icon: FileText },
  { id: "timeline", label: "时间跟踪", icon: CalendarDays },
  { id: "categories", label: "分类观察", icon: Layers3 },
  { id: "forecast", label: "涨跌预估", icon: Target },
];

const categoryOrder = ["5/10早期修复", "5/10早修复·部分确认", "v1.3图形确认"];

function formatPercent(value: number, withSign = true) {
  const sign = withSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatProfit(value: number | null) {
  if (value === null) return "待更新";
  return `${(value / 100_000_000).toFixed(2)} 亿`;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function formatSignedPercent(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function shortDate(value: string) {
  return value.replace("2026-", "").replace("-", "/");
}

function statusTone(value: string) {
  if (["通过", "图形确认", "v1.3图形确认"].includes(value)) return "pass";
  if (["不通过", "弱观察"].includes(value)) return "fail";
  if (value === "板块强度样本") return "strong";
  return "watch";
}

function Sparkline({ stock, large = false }: { stock: Stock; large?: boolean }) {
  const values = stock.sparkline.map((point) => point.close);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = large ? 640 : 132;
  const height = large ? 180 : 38;
  const pad = large ? 10 : 2;
  const points = values
    .map((value, index) => {
      const x = pad + (index / Math.max(values.length - 1, 1)) * (width - pad * 2);
      const y = height - pad - ((value - min) / Math.max(max - min, 0.01)) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const positive = stock.performance >= 0;

  return (
    <svg
      className={large ? "sparkline sparkline-large" : "sparkline"}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${stock.name}近80日价格轨迹`}
      preserveAspectRatio="none"
    >
      {large && (
        <>
          <line x1="0" y1="45" x2={width} y2="45" className="chart-grid" />
          <line x1="0" y1="90" x2={width} y2="90" className="chart-grid" />
          <line x1="0" y1="135" x2={width} y2="135" className="chart-grid" />
        </>
      )}
      <polyline className={positive ? "spark-path positive" : "spark-path negative"} points={points} />
    </svg>
  );
}

function StatusTag({ children, tone }: { children: React.ReactNode; tone: string }) {
  return <span className={`status-tag ${tone}`}>{children}</span>;
}

function SwitchState({ label, value }: { label: string; value: string }) {
  return (
    <div className="switch-state">
      <span>{label}</span>
      <StatusTag tone={statusTone(value)}>{value}</StatusTag>
    </div>
  );
}

function App() {
  const [view, setView] = useState<View>("overview");
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);
  const [forecastStockCode, setForecastStockCode] = useState(data.stocks[0]?.code ?? "");
  const [forecastWindow, setForecastWindow] = useState<"1w" | "1m" | "3m">("1m");
  const [forecastMode, setForecastMode] = useState<"保守型" | "标准型" | "弹性型">("标准型");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("全部类别");
  const [switchFilter, setSwitchFilter] = useState("全部状态");
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [selectedReportId, setSelectedReportId] = useState(data.reports.at(-1)?.id ?? "");
  const [refreshing, setRefreshing] = useState(false);

  const filteredStocks = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return [...data.stocks]
      .filter((stock) => {
        const queryMatch =
          !normalized ||
          stock.name.toLowerCase().includes(normalized) ||
          stock.code.includes(normalized) ||
          stock.industry.toLowerCase().includes(normalized) ||
          stock.direction.toLowerCase().includes(normalized);
        const categoryMatch = category === "全部类别" || stock.currentCategory === category;
        const switchMatch =
          switchFilter === "全部状态" ||
          (switchFilter === "双开关通过" && stock.sectorState === "通过" && stock.financialState === "通过") ||
          (switchFilter === "财务待复核" && stock.financialState !== "通过") ||
          (switchFilter === "行业待验证" && stock.sectorState !== "通过");
        return queryMatch && categoryMatch && switchMatch;
      })
      .sort((a, b) => {
        if (sortKey === "score") return (b.score ?? 0) - (a.score ?? 0);
        if (sortKey === "weeklyRsi") return a.metrics.weeklyRsi - b.metrics.weeklyRsi;
        if (sortKey === "riseFromYearLow") return a.metrics.riseFromYearLow - b.metrics.riseFromYearLow;
        return b.performance - a.performance;
      });
  }, [query, category, switchFilter, sortKey]);

  const stats = useMemo(() => {
    const averageScore = data.stocks.reduce((sum, stock) => sum + (stock.score ?? 0), 0) / data.stocks.length;
    return {
      unique: data.stocks.length,
      sectorPassed: data.stocks.filter((stock) => stock.sectorState === "通过").length,
      elastic: data.stocks.filter((stock) => ["高", "中"].includes(stock.elasticity?.grade ?? "")).length,
      averageScore,
    };
  }, []);

  const forecastStock = useMemo(
    () => data.stocks.find((stock) => stock.code === forecastStockCode) ?? data.stocks[0] ?? null,
    [forecastStockCode],
  );

  const forecast = useMemo(() => (forecastStock ? buildForecast(forecastStock, forecastWindow, forecastMode) : null), [forecastStock, forecastWindow, forecastMode]);

  const refresh = () => {
    setRefreshing(true);
    window.setTimeout(() => {
      setRefreshing(false);
      window.location.reload();
    }, 650);
  };

  const renderView = () => {
    if (view === "reports") {
      return (
        <ReportsView
          reports={data.reports}
          stocks={data.stocks}
          selectedId={selectedReportId}
          onSelect={setSelectedReportId}
          onOpenStock={setSelectedStock}
        />
      );
    }
    if (view === "timeline") return <TimelineView reports={data.reports} stocks={data.stocks} history={history} onOpenStock={setSelectedStock} />;
    if (view === "categories") return <CategoriesView stocks={data.stocks} onOpenStock={setSelectedStock} />;
    if (view === "forecast") {
      return (
        <ForecastView
          stocks={data.stocks}
          selectedCode={forecastStockCode}
          onSelectCode={setForecastStockCode}
          forecastWindow={forecastWindow}
          onChangeWindow={setForecastWindow}
          forecastMode={forecastMode}
          onChangeMode={setForecastMode}
          forecast={forecast}
        />
      );
    }
    return (
      <Overview
        stats={stats}
        stocks={filteredStocks}
        reports={data.reports}
        query={query}
        setQuery={setQuery}
        category={category}
        setCategory={setCategory}
        switchFilter={switchFilter}
        setSwitchFilter={setSwitchFilter}
        sortKey={sortKey}
        setSortKey={setSortKey}
        onOpenStock={setSelectedStock}
      />
    );
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark"><Activity size={18} strokeWidth={2.2} /></div>
          <div>
            <strong>横盘启动</strong>
            <span>研究观察台</span>
          </div>
        </div>
        <nav aria-label="主导航">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.id} className={view === item.id ? "nav-item active" : "nav-item"} onClick={() => setView(item.id)}>
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="method-block">
          <span>当前方法</span>
          <strong>{data.methodologyVersion}</strong>
          <p>周线优先 · 开关先行</p>
        </div>
        <div className="sidebar-foot">
          <CircleAlert size={15} />
          <span>研究观察，不构成交易建议</span>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="mobile-brand">横盘启动研究台</div>
          <div className="page-heading">
            <span>{NAV_ITEMS.find((item) => item.id === view)?.label}</span>
            <h1>{view === "overview" ? "观察池全景" : view === "reports" ? "规则与批次" : view === "timeline" ? "首次入选至今" : view === "categories" ? "研究样本分层" : "涨跌预估面板"}</h1>
          </div>
          <div className="topbar-actions">
            <div className="data-stamp">
              <span>数据交易日</span>
              <strong>{data.asOf}</strong>
            </div>
            <button className="icon-button" onClick={refresh} title="重新读取本地数据" aria-label="刷新页面数据">
              <RefreshCw size={18} className={refreshing ? "spin" : ""} />
            </button>
          </div>
        </header>

        <div className="content-area">{renderView()}</div>
        <footer className="app-footer">
          <span>{data.disclaimer}</span>
          <span>生成于 {new Date(data.generatedAt).toLocaleString("zh-CN", { hour12: false })}</span>
        </footer>
      </main>

      <nav className="mobile-nav" aria-label="移动端主导航">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}>
              <Icon size={19} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {selectedStock && <StockDrawer stock={selectedStock} onClose={() => setSelectedStock(null)} />}
    </div>
  );
}

function Overview({
  stats,
  stocks,
  reports,
  query,
  setQuery,
  category,
  setCategory,
  switchFilter,
  setSwitchFilter,
  sortKey,
  setSortKey,
  onOpenStock,
}: {
  stats: { unique: number; sectorPassed: number; elastic: number; averageScore: number };
  stocks: Stock[];
  reports: Report[];
  query: string;
  setQuery: (value: string) => void;
  category: string;
  setCategory: (value: string) => void;
  switchFilter: string;
  setSwitchFilter: (value: string) => void;
  sortKey: SortKey;
  setSortKey: (value: SortKey) => void;
  onOpenStock: (stock: Stock) => void;
}) {
  return (
    <>
      <section className="metric-strip" aria-label="观察池摘要">
        <Metric label="本轮全新样本" value={String(stats.unique)} note="与旧 48 只交集为 0" />
        <Metric label="行业开关通过" value={String(stats.sectorPassed)} note="板块已有其他拉升标的" />
        <Metric label="中高弹性" value={String(stats.elastic)} note="一年波段与涨停记忆" />
        <Metric label="平均研究评分" value={stats.averageScore.toFixed(1)} note="前置开关通过后的比较分" />
      </section>

      <section className="overview-grid">
        <div className="panel rule-evolution">
          <div className="section-head">
            <div>
              <span className="eyebrow">规则演进</span>
              <h2>全市场重新筛选口径</h2>
            </div>
            <span className="section-meta">{reports[0].date} — {reports.at(-1)?.date}</span>
          </div>
          <div className="report-ribbon">
            {reports.map((report, index) => (
              <div className="ribbon-step" key={report.id}>
                <span className="ribbon-index">{String(index + 1).padStart(2, "0")}</span>
                <div className="ribbon-line"><i /></div>
                <div>
                  <strong>{report.family}</strong>
                  <span>{report.stats.count} 个样本 · {formatPercent(report.stats.averagePerformance)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel status-distribution">
          <div className="section-head compact">
            <div>
              <span className="eyebrow">当前分层</span>
              <h2>样本所处阶段</h2>
            </div>
          </div>
          <CategoryBars stocks={data.stocks} />
        </div>
      </section>

      <section className="stock-section">
        <div className="section-head table-heading">
          <div>
            <span className="eyebrow">持续跟踪</span>
            <h2>观察池明细</h2>
          </div>
          <span className="section-meta">当前显示 {stocks.length} / {data.stocks.length}</span>
        </div>
        <div className="filter-rail">
          <label className="search-field">
            <Search size={17} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、代码、行业" aria-label="搜索股票" />
          </label>
          <label className="select-field">
            <Filter size={16} />
            <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="按当前类别筛选">
              <option>全部类别</option>
              {categoryOrder.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label className="select-field">
            <ShieldCheck size={16} />
            <select value={switchFilter} onChange={(event) => setSwitchFilter(event.target.value)} aria-label="按开关状态筛选">
              <option>全部状态</option>
              <option>双开关通过</option>
              <option>财务待复核</option>
              <option>行业待验证</option>
            </select>
          </label>
          <label className="select-field sort-select">
            <SlidersHorizontal size={16} />
            <select value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)} aria-label="排序方式">
              <option value="score">研究评分从高到低</option>
              <option value="performance">入选后表现</option>
              <option value="weeklyRsi">周 RSI 从低到高</option>
              <option value="riseFromYearLow">距一年低点从近到远</option>
            </select>
          </label>
        </div>
        <StockTable stocks={stocks} onOpenStock={onOpenStock} />
      </section>
    </>
  );
}

function Metric({ label, value, note, performance }: { label: string; value: string; note: string; performance?: number }) {
  return (
    <div className="metric-item">
      <span>{label}</span>
      <strong className={performance === undefined ? "" : performance >= 0 ? "positive-text" : "negative-text"}>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function CategoryBars({ stocks }: { stocks: Stock[] }) {
  const counts = categoryOrder.map((name) => ({ name, count: stocks.filter((stock) => stock.currentCategory === name).length }));
  const max = Math.max(...counts.map((item) => item.count));
  return (
    <div className="category-bars">
      {counts.map((item) => (
        <div className="category-bar" key={item.name}>
          <div><span>{item.name}</span><strong>{item.count}</strong></div>
          <div className="bar-track"><i style={{ width: `${(item.count / max) * 100}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

function buildForecast(stock: Stock, window: "1w" | "1m" | "3m", mode: "保守型" | "标准型" | "弹性型") {
  const closes = stock.sparkline.map((point) => point.close);
  const recent20 = closes.slice(-20);
  const recent60 = closes.slice(-60);
  const current = stock.currentPrice;
  const low20 = Math.min(...recent20);
  const high20 = Math.max(...recent20);
  const low60 = Math.min(...recent60);
  const high60 = Math.max(...recent60);

  const support = Math.max(Math.min(low20, low60), current * 0.7);
  const pressure = Math.max(high20, high60);

  const recentRange20 = ((high20 - low20) / current) * 100;
  const structureUp = ((pressure - current) / current) * 100;
  const structureDown = ((current - support) / current) * 100;

  const windowScale = { "1w": 0.45, "1m": 1, "3m": 1.8 }[window];
  const modeBoost = { "保守型": 0.75, "标准型": 1, "弹性型": 1.35 }[mode];
  const riskPenalty = (stock.financialState !== "通过" ? 1.4 : 0) + (stock.sectorState !== "通过" ? 0.8 : 0);
  const momentum = clamp((stock.metrics.weeklyRsi - 35) / 40 + (stock.metrics.change20d / 18), -0.4, 0.7);

  const volatilityBudget = recentRange20 * windowScale * modeBoost;
  const upside = clamp(Math.min(structureUp, volatilityBudget * (1.05 + momentum) + 1.2), 1.5, 32);
  const downside = clamp(Math.min(structureDown + riskPenalty, volatilityBudget * 0.72 + 1.8 + riskPenalty), 1.5, 18);
  const neutral = clamp(upside * (0.33 + (stock.metrics.dailyRsi >= 50 ? 0.05 : 0) + momentum * 0.08), 1.0, upside - 0.4);

  const baseLow = -(downside * (0.55 + (window === "3m" ? 0.08 : 0) + riskPenalty * 0.03));
  const baseHigh = clamp(Math.max(neutral, upside * 0.58), 1.5, upside);
  const optimisticHigh = clamp(upside * (window === "1w" ? 1.1 : window === "1m" ? 1.18 : 1.28), baseHigh + 0.5, 38);
  const pessimisticLow = -clamp(downside * (window === "1w" ? 0.9 : window === "1m" ? 1.05 : 1.18), 1.5, 22);

  const conviction =
    stock.sectorState === "通过" && stock.financialState === "通过"
      ? stock.currentCategory.includes("v1.3")
        ? "偏高"
        : "中高"
      : stock.currentCategory.includes("红框")
        ? "中"
        : "偏保守";

  return {
    current,
    support,
    pressure,
    recentRange20,
    structureUp,
    structureDown,
    upside,
    downside,
    neutral,
    baseLow,
    baseHigh,
    optimisticHigh,
    pessimisticLow,
    conviction,
  };
}

function ForecastView({
  stocks,
  selectedCode,
  onSelectCode,
  forecastWindow,
  onChangeWindow,
  forecastMode,
  onChangeMode,
  forecast,
}: {
  stocks: Stock[];
  selectedCode: string;
  onSelectCode: (code: string) => void;
  forecastWindow: "1w" | "1m" | "3m";
  onChangeWindow: (value: "1w" | "1m" | "3m") => void;
  forecastMode: "保守型" | "标准型" | "弹性型";
  onChangeMode: (value: "保守型" | "标准型" | "弹性型") => void;
  forecast: ReturnType<typeof buildForecast> | null;
}) {
  const selected = stocks.find((stock) => stock.code === selectedCode) ?? stocks[0];
  const forecasted = stocks.map((stock) => ({ stock, forecast: buildForecast(stock, forecastWindow, forecastMode) }));
  const ordered = [...forecasted].sort((a, b) => b.forecast.upside - a.forecast.upside || a.forecast.downside - b.forecast.downside || (b.stock.score ?? 0) - (a.stock.score ?? 0));
  const topThree = ordered.slice(0, 3);
  const summary = {
    avgBaseLow: forecasted.reduce((sum, item) => sum + item.forecast.baseLow, 0) / forecasted.length,
    avgBaseHigh: forecasted.reduce((sum, item) => sum + item.forecast.baseHigh, 0) / forecasted.length,
    avgUpside: forecasted.reduce((sum, item) => sum + item.forecast.upside, 0) / forecasted.length,
    avgDownside: forecasted.reduce((sum, item) => sum + item.forecast.downside, 0) / forecasted.length,
    positiveCount: forecasted.filter((item) => item.forecast.baseHigh > 0).length,
  };

  return (
    <section className="forecast-layout">
      <div className="forecast-hero panel">
        <div className="section-head">
          <div>
            <span className="eyebrow">涨跌预估</span>
            <h2>把“会涨多少”变成区间、概率和风险来源</h2>
          </div>
          <span className="section-meta">基于现有观察池样本即时计算</span>
        </div>
        <div className="forecast-controls">
          <label className="select-field forecast-select">
            <Search size={16} />
            <select value={selectedCode} onChange={(event) => onSelectCode(event.target.value)} aria-label="选择样本">
              {stocks.map((stock) => (
                <option key={stock.code} value={stock.code}>{stock.name} · {stock.code}</option>
              ))}
            </select>
          </label>
          <label className="select-field forecast-select">
            <CalendarDays size={16} />
            <select value={forecastWindow} onChange={(event) => onChangeWindow(event.target.value as "1w" | "1m" | "3m")} aria-label="选择观察周期">
              <option value="1w">1周</option>
              <option value="1m">1个月</option>
              <option value="3m">3个月</option>
            </select>
          </label>
          <label className="select-field forecast-select">
            <SlidersHorizontal size={16} />
            <select value={forecastMode} onChange={(event) => onChangeMode(event.target.value as "保守型" | "标准型" | "弹性型")} aria-label="选择预估风格">
              <option value="保守型">保守型</option>
              <option value="标准型">标准型</option>
              <option value="弹性型">弹性型</option>
            </select>
          </label>
        </div>

        <div className="forecast-summary-strip" aria-label="全池预估摘要">
          <div className="forecast-summary-card">
            <span>正向样本</span>
            <strong>{summary.positiveCount}</strong>
            <small>中性上沿大于 0 的样本</small>
          </div>
          <div className="forecast-summary-card">
            <span>平均区间</span>
            <strong>{formatSignedPercent(summary.avgBaseLow)} ~ {formatSignedPercent(summary.avgBaseHigh)}</strong>
            <small>全池平均预估</small>
          </div>
          <div className="forecast-summary-card">
            <span>平均弹性</span>
            <strong>{formatSignedPercent(summary.avgUpside)}</strong>
            <small>上行空间均值</small>
          </div>
          <div className="forecast-summary-card">
            <span>平均风险</span>
            <strong>{formatSignedPercent(-summary.avgDownside)}</strong>
            <small>下行风险均值</small>
          </div>
        </div>

        {selected && forecast && (
          <div className="forecast-board">
            <div className="forecast-main">
              <div className="forecast-title">
                <div>
                  <span>{selected.industry}</span>
                  <h3>{selected.name}</h3>
                </div>
                <StatusTag tone={statusTone(selected.currentCategory)}>{selected.currentCategory}</StatusTag>
              </div>
              <div className="forecast-band" aria-label="预估区间示意">
                {(() => {
                  const scale = Math.max(Math.abs(forecast.pessimisticLow), forecast.optimisticHigh, 18);
                  const line = (value: number) => `${50 + (value / scale) * 50}%`;
                  return (
                    <>
                      <span className="forecast-band-axis" />
                      <i className="forecast-band-negative" style={{ left: line(forecast.pessimisticLow), width: `calc(${line(forecast.baseLow)} - ${line(forecast.pessimisticLow)})` }} />
                      <i className="forecast-band-base" style={{ left: line(forecast.baseLow), width: `calc(${line(forecast.baseHigh)} - ${line(forecast.baseLow)})` }} />
                      <i className="forecast-band-positive" style={{ left: line(forecast.baseHigh), width: `calc(${line(forecast.optimisticHigh)} - ${line(forecast.baseHigh)})` }} />
                      <b className="forecast-band-zero" style={{ left: line(0) }}>0</b>
                      <em className="forecast-band-current" style={{ left: line(0) }} />
                    </>
                  );
                })()}
              </div>
              <div className="forecast-range">
                <div>
                  <span>预估区间</span>
                  <strong className={forecast.baseLow < 0 ? "negative-text" : "positive-text"}>{formatSignedPercent(forecast.baseLow)} ~ {formatSignedPercent(forecast.baseHigh)}</strong>
                </div>
                <div>
                  <span>乐观情景</span>
                  <strong className="positive-text">{formatSignedPercent(forecast.baseHigh)} ~ {formatSignedPercent(forecast.optimisticHigh)}</strong>
                </div>
                <div>
                  <span>悲观情景</span>
                  <strong className="negative-text">{formatSignedPercent(forecast.pessimisticLow)} ~ {formatSignedPercent(-forecast.downside * 0.5)}</strong>
                </div>
              </div>
              <div className="forecast-grid">
                <ForecastMetric label="当前价" value={selected.currentPrice.toFixed(2)} note={selected.currentDate} />
                <ForecastMetric label="平台支撑" value={forecast.support.toFixed(2)} note={`下沿空间 ${formatSignedPercent(-forecast.structureDown)}`} />
                <ForecastMetric label="平台压力" value={forecast.pressure.toFixed(2)} note={`上沿空间 ${formatSignedPercent(forecast.structureUp)}`} />
                <ForecastMetric label="20日波动" value={`${forecast.recentRange20.toFixed(1)}%`} note="最近20日价格跨度" />
                <ForecastMetric label="中性预期" value={formatSignedPercent(forecast.neutral)} note={`胜率倾向 ${forecast.conviction}`} />
                <ForecastMetric label="风险标签" value={selected.financialState} note={selected.sectorState} />
              </div>
            </div>
            <div className="forecast-side">
              <div className="forecast-side-card">
                <span>判断顺序</span>
                <ol>
                  <li>先看下沿风险</li>
                  <li>再看平台上沿</li>
                  <li>最后看情绪扩展</li>
                </ol>
              </div>
              <div className="forecast-side-card">
                <span>主要风险</span>
                <ul>
                  {selected.risks.slice(0, 3).map((risk) => (
                    <li key={risk}>{risk}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="forecast-panels">
        <section className="panel">
          <div className="section-head compact">
            <div>
              <span className="eyebrow">预估样本</span>
              <h2>按当前参数即时比较</h2>
            </div>
            <span className="section-meta">点击可切换主样本</span>
          </div>
          <div className="forecast-list">
            {ordered.slice(0, 8).map(({ stock, forecast: item }) => {
              const active = stock.code === selectedCode;
              return (
                <button key={stock.code} className={active ? "forecast-row active" : "forecast-row"} onClick={() => onSelectCode(stock.code)}>
                  <span>
                    <strong>{stock.name}</strong>
                    <small>{stock.industry} · {stock.currentCategory}</small>
                  </span>
                  <b className={item.baseHigh >= 0 ? "positive-text" : "negative-text"}>{formatSignedPercent(item.baseLow)} ~ {formatSignedPercent(item.baseHigh)}</b>
                </button>
              );
            })}
          </div>
        </section>

        <section className="panel">
          <div className="section-head compact">
            <div>
              <span className="eyebrow">示例对比</span>
              <h2>最适合观察的三只样本</h2>
            </div>
          </div>
          <div className="forecast-comparison">
            {topThree.map(({ stock, forecast: item }) => (
              <div key={stock.code} className="comparison-card">
                <div className="comparison-head">
                  <div>
                    <strong>{stock.name}</strong>
                    <small>{stock.code} · {stock.industry}</small>
                  </div>
                  <StatusTag tone={statusTone(stock.sectorState)}>{stock.sectorState}</StatusTag>
                </div>
                <Sparkline stock={stock} />
                <div className="comparison-row">
                  <span>区间</span>
                  <strong>{formatSignedPercent(item.baseLow)} ~ {formatSignedPercent(item.baseHigh)}</strong>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="panel forecast-map-section">
        <div className="section-head compact">
          <div>
            <span className="eyebrow">全池分布</span>
            <h2>上行空间与下行风险矩阵</h2>
          </div>
          <span className="section-meta">越靠左上，结构弹性越好</span>
        </div>
        <div className="forecast-map" role="img" aria-label="观察池预估分布">
          <span className="map-axis x-axis">下行风险</span>
          <span className="map-axis y-axis">上行空间</span>
          <i className="map-grid h1" />
          <i className="map-grid h2" />
          <i className="map-grid v1" />
          <i className="map-grid v2" />
          {forecasted.map(({ stock, forecast: item }) => {
            const left = clamp((item.downside / 18) * 100, 4, 96);
            const bottom = clamp((item.upside / 32) * 100, 5, 95);
            const active = stock.code === selectedCode;
            return (
              <button
                key={stock.code}
                className={active ? "forecast-dot active" : "forecast-dot"}
                style={{ left: `${left}%`, bottom: `${bottom}%` }}
                onClick={() => onSelectCode(stock.code)}
                title={`${stock.name}：下行${item.downside.toFixed(1)}%，上行${item.upside.toFixed(1)}%`}
                aria-label={`${stock.name}预估点`}
              />
            );
          })}
        </div>
      </section>
    </section>
  );
}

function ForecastMetric({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="forecast-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function StockTable({ stocks, onOpenStock }: { stocks: Stock[]; onOpenStock: (stock: Stock) => void }) {
  if (!stocks.length) {
    return (
      <div className="empty-state">
        <Search size={24} />
        <strong>没有符合当前条件的样本</strong>
        <span>调整搜索词或筛选状态后再看。</span>
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>股票 / 行业</th>
            <th>当前分层</th>
            <th>研究分</th>
            <th>距1年低点</th>
            <th>周 RSI</th>
            <th>周 MACD</th>
            <th>板块拉升标的</th>
            <th>弹性</th>
            <th>开关</th>
            <th aria-label="打开详情" />
          </tr>
        </thead>
        <tbody>
          {stocks.map((stock) => (
            <tr key={stock.code} onClick={() => onOpenStock(stock)} tabIndex={0} onKeyDown={(event) => event.key === "Enter" && onOpenStock(stock)}>
              <td>
                <div className="stock-name"><strong>{stock.name}</strong><span>{stock.code}</span></div>
                <small>{stock.industry}</small>
              </td>
              <td><StatusTag tone={statusTone(stock.currentCategory)}>{stock.currentCategory}</StatusTag></td>
              <td className="data-value">{stock.score ?? "-"}</td>
              <td className="data-value">{stock.metrics.riseFromYearLow.toFixed(1)}%</td>
              <td className="data-value">{stock.metrics.weeklyRsi.toFixed(1)}</td>
              <td><span className="macd-text">{stock.metrics.macdClass}</span></td>
              <td><strong>{stock.sectorLeader ?? "待验证"}</strong><small className="positive-text">{formatPercent(stock.sectorLeaderGain ?? 0)}</small></td>
              <td><strong>{stock.elasticity?.grade ?? "待验证"}</strong><small>{stock.elasticity ? `最大${stock.elasticity.maxStageGain1y.toFixed(0)}% · 30%波段${stock.elasticity.gain30Count}次` : ""}</small></td>
              <td>
                <div className="switch-dots" title={`行业：${stock.sectorState}；财务：${stock.financialState}`}>
                  <i className={statusTone(stock.sectorState)} />
                  <i className={statusTone(stock.financialState)} />
                </div>
              </td>
              <td><ChevronRight size={16} className="row-arrow" /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportsView({ reports, stocks, selectedId, onSelect, onOpenStock }: { reports: Report[]; stocks: Stock[]; selectedId: string; onSelect: (id: string) => void; onOpenStock: (stock: Stock) => void }) {
  const selected = reports.find((report) => report.id === selectedId) ?? reports.at(-1)!;
  const cohort = selected.selections.map((code) => stocks.find((stock) => stock.code === code)).filter(Boolean) as Stock[];
  return (
    <div className="reports-layout">
      <aside className="report-index">
        <div className="section-head compact">
          <div><span className="eyebrow">报告档案</span><h2>{reports.length} 个批次</h2></div>
        </div>
        <div className="report-list">
          {[...reports].reverse().map((report) => (
            <button key={report.id} className={selected.id === report.id ? "report-list-item active" : "report-list-item"} onClick={() => onSelect(report.id)}>
              <span>{report.version}</span>
              <strong>{report.family}</strong>
              <small>{report.date} · {report.stats.count} 个样本</small>
            </button>
          ))}
        </div>
      </aside>
      <section className="report-detail">
        <div className="report-title-row">
          <div>
            <span className="eyebrow">{selected.version} · {selected.date}</span>
            <h2>{selected.family}</h2>
            <p>{selected.summary}</p>
          </div>
          <div className="report-score">
            <span>批次均值</span>
            <strong className={selected.stats.averagePerformance >= 0 ? "positive-text" : "negative-text"}>{formatPercent(selected.stats.averagePerformance)}</strong>
          </div>
        </div>
        <div className="report-stat-row">
          <Metric label="样本数" value={String(selected.stats.count)} note={selected.file} />
          <Metric label="上涨样本" value={String(selected.stats.positiveCount)} note={`占比 ${selected.stats.count ? Math.round((selected.stats.positiveCount / selected.stats.count) * 100) : 0}%`} />
          <Metric label="转强度样本" value={String(selected.stats.strengthCount)} note="已不属于低位核心" />
        </div>
        <StockTable stocks={cohort} onOpenStock={onOpenStock} />
      </section>
    </div>
  );
}

function TimelineView({ reports, stocks, history, onOpenStock }: { reports: Report[]; stocks: Stock[]; history: DailyHistoryData; onOpenStock: (stock: Stock) => void }) {
  const maxAbs = Math.max(...reports.map((report) => Math.abs(report.stats.averagePerformance)), 1);
  const byDate = Array.from(new Set(stocks.map((stock) => stock.firstSelectedDate))).sort();
  return (
    <>
      <section className="timeline-summary">
        <div className="section-head">
          <div><span className="eyebrow">批次表现</span><h2>规则演进与结果反馈</h2></div>
          <span className="section-meta">基准：各股首次入选日收盘</span>
        </div>
        <div className="cohort-performance">
          {reports.map((report) => (
            <div className="cohort-row" key={report.id}>
              <div className="cohort-label"><span>{shortDate(report.date)}</span><strong>{report.family}</strong></div>
              <div className="cohort-axis">
                <i className="axis-zero" />
                <i
                  className={report.stats.averagePerformance >= 0 ? "cohort-bar positive" : "cohort-bar negative"}
                  style={{ width: `${Math.max((Math.abs(report.stats.averagePerformance) / maxAbs) * 46, 1)}%`, left: report.stats.averagePerformance >= 0 ? "50%" : undefined, right: report.stats.averagePerformance < 0 ? "50%" : undefined }}
                />
              </div>
              <strong className={report.stats.averagePerformance >= 0 ? "positive-text" : "negative-text"}>{formatPercent(report.stats.averagePerformance)}</strong>
            </div>
          ))}
        </div>
      </section>
      <section className="date-groups">
        <div className="section-head"><div><span className="eyebrow">首次入选</span><h2>按时间查看样本</h2></div></div>
        {byDate.map((dateValue) => {
          const group = stocks.filter((stock) => stock.firstSelectedDate === dateValue).sort((a, b) => b.performance - a.performance);
          return (
            <div className="date-group" key={dateValue}>
              <div className="date-marker"><span>{dateValue.slice(5)}</span><small>{group.length} 只</small></div>
              <div className="date-stock-list">
                {group.map((stock) => (
                  <button key={stock.code} onClick={() => onOpenStock(stock)}>
                    <span><strong>{stock.name}</strong><small>{stock.code} · {stock.currentCategory}</small></span>
                    <Sparkline stock={stock} />
                    <b className={stock.performance >= 0 ? "positive-text" : "negative-text"}>{formatPercent(stock.performance)}</b>
                    <ChevronRight size={16} />
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </section>
      <section className="history-summary">
        <div className="section-head">
          <div><span className="eyebrow">每日历史</span><h2>按交易日查看全部结果</h2></div>
          <span className="section-meta">{history.dateRange.start} — {history.dateRange.end}</span>
        </div>
        <div className="history-meta">
          <Metric label="历史天数" value={String(history.summary.dayCount)} note="已落盘的交易日快照" />
          <Metric label="记录总数" value={String(history.summary.recordCount)} note="v26 + v13 合并结果" />
          <Metric label="唯一股票" value={String(history.summary.uniqueStockCount)} note="跨天去重后的样本" />
          <Metric label="正向记录" value={String(history.summary.positiveRecordCount)} note="相对首次入选为正" />
        </div>
        <div className="history-day-list">
          {history.days.slice().reverse().map((day) => (
            <details key={day.date} className="history-day">
              <summary>
                <strong>{day.date}</strong>
                <span>{day.counts.total} 只 · v26 {day.counts.v26} · v13 {day.counts.v13}</span>
                <b className={day.averageChangeSinceFirst >= 0 ? "positive-text" : "negative-text"}>{formatSignedPercent(day.averageChangeSinceFirst)}</b>
              </summary>
              <div className="history-day-table">
                {day.items.map((item) => (
                  <button key={item.key} onClick={() => onOpenStock(stocks.find((stock) => stock.code === item.code) || stocks[0])}>
                    <span>
                      <strong>{item.name}</strong>
                      <small>{item.code} · {item.model} · {item.state}</small>
                    </span>
                    <b className={item.changeSinceFirst >= 0 ? "positive-text" : "negative-text"}>{formatSignedPercent(item.changeSinceFirst)}</b>
                  </button>
                ))}
              </div>
            </details>
          ))}
        </div>
      </section>
    </>
  );
}

function CategoriesView({ stocks, onOpenStock }: { stocks: Stock[]; onOpenStock: (stock: Stock) => void }) {
  const industries = Array.from(new Set(stocks.map((stock) => stock.industry))).map((industry) => {
    const members = stocks.filter((stock) => stock.industry === industry);
    return { industry, members, average: members.reduce((sum, stock) => sum + stock.performance, 0) / members.length };
  }).sort((a, b) => b.members.length - a.members.length || b.average - a.average);
  return (
    <>
      <section className="category-overview">
        <div className="section-head"><div><span className="eyebrow">当前观察层</span><h2>按研究类别聚合</h2></div></div>
        <div className="category-columns">
          {categoryOrder.map((name) => {
            const members = stocks.filter((stock) => stock.currentCategory === name);
            const average = members.length ? members.reduce((sum, stock) => sum + stock.performance, 0) / members.length : 0;
            return (
              <div className="category-column" key={name}>
                <div className="category-column-head">
                  <span className={`category-dot ${statusTone(name)}`} />
                  <div><strong>{name}</strong><small>{members.length} 只 · 均值 {formatPercent(average)}</small></div>
                </div>
                <div className="category-stock-stack">
                  {members.slice(0, 8).map((stock) => (
                    <button key={stock.code} onClick={() => onOpenStock(stock)}>
                      <span>{stock.name}<small>{stock.code}</small></span>
                      <b className={stock.performance >= 0 ? "positive-text" : "negative-text"}>{formatPercent(stock.performance)}</b>
                    </button>
                  ))}
                  {members.length > 8 && <small className="more-count">另有 {members.length - 8} 只</small>}
                </div>
              </div>
            );
          })}
        </div>
      </section>
      <section className="industry-section">
        <div className="section-head"><div><span className="eyebrow">行业分布</span><h2>样本集中度与开关</h2></div><span className="section-meta">行业为最新财务数据口径</span></div>
        <div className="industry-table">
          {industries.slice(0, 16).map((group) => (
            <div className="industry-row" key={group.industry}>
              <div><strong>{group.industry}</strong><span>{group.members.map((stock) => stock.name).slice(0, 4).join("、")}</span></div>
              <span>{group.members.length} 只</span>
              <div className="mini-stack">{group.members.slice(0, 8).map((stock) => <i key={stock.code} className={statusTone(stock.sectorState)} title={`${stock.name}：${stock.sectorState}`} />)}</div>
              <strong className={group.average >= 0 ? "positive-text" : "negative-text"}>{formatPercent(group.average)}</strong>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function StockDrawer({ stock, onClose }: { stock: Stock; onClose: () => void }) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyDown);
    closeButtonRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  return (
    <div className="drawer-layer" role="dialog" aria-modal="true" aria-label={`${stock.name}研究详情`}>
      <button className="drawer-backdrop" onClick={onClose} aria-label="关闭详情" />
      <aside className="stock-drawer">
        <header className="drawer-head">
          <div>
            <span className="eyebrow">{stock.code} · {stock.industry}</span>
            <h2>{stock.name}</h2>
          </div>
          <button ref={closeButtonRef} className="icon-button" onClick={onClose} aria-label="关闭详情"><X size={19} /></button>
        </header>
        <div className="drawer-scroll">
          <div className="stock-hero-metrics">
            <div><span>首次入选</span><strong>{stock.firstSelectedPrice.toFixed(2)}</strong><small>{stock.firstSelectedDate}</small></div>
            <div className="transition-mark"><ChevronRight size={18} /></div>
            <div><span>当前</span><strong>{stock.currentPrice.toFixed(2)}</strong><small>{stock.currentDate}</small></div>
            <div className={stock.performance >= 0 ? "performance-block positive" : "performance-block negative"}>
              <span>{stock.trackedDays} 天</span><strong>{formatPercent(stock.performance)}</strong>
            </div>
          </div>
          <div className="large-chart"><Sparkline stock={stock} large /><span>近 80 个交易日价格轨迹</span></div>
          <div className="drawer-switches">
            <SwitchState label="行业启动" value={stock.sectorState} />
            <SwitchState label="财务与风险" value={stock.financialState} />
            <SwitchState label="当前分层" value={stock.currentCategory} />
          </div>
          <div className="research-context">
            <div>
              <span>板块拉升标的</span>
              <strong>{stock.sectorLeader ?? "待验证"} {stock.sectorLeaderCode}</strong>
              <small>{formatPercent(stock.sectorLeaderGain ?? 0)} · {stock.sectorEvidence}</small>
            </div>
            <div>
              <span>历史弹性</span>
              <strong>{stock.elasticity?.grade ?? "待验证"}弹性</strong>
              <small>{stock.elasticity ? `一年最大${stock.elasticity.maxStageGain1y.toFixed(0)}% · 30%波段${stock.elasticity.gain30Count}次 · 最高连板${stock.elasticity.maxLimitStreak}天` : "待验证"}</small>
            </div>
          </div>
          <section className="drawer-section">
            <div className="drawer-section-title"><BarChart3 size={17} /><h3>当前指标</h3></div>
            <div className="indicator-grid">
              <Indicator label="研究评分" value={String(stock.score ?? "-")} />
              <Indicator label="周 RSI" value={stock.metrics.weeklyRsi.toFixed(1)} />
              <Indicator label="RSI 4/8周前" value={`${stock.metrics.weeklyRsi4w ?? "-"} / ${stock.metrics.weeklyRsi8w ?? "-"}`} />
              <Indicator label="日 RSI" value={stock.metrics.dailyRsi.toFixed(1)} />
              <Indicator label="距一年低点" value={`${stock.metrics.riseFromYearLow.toFixed(1)}%`} />
              <Indicator label="3年高点回撤" value={`${stock.metrics.drawdown3y?.toFixed(1) ?? "-"}%`} />
              <Indicator label="20 日" value={formatPercent(stock.metrics.change20d)} tone={stock.metrics.change20d} />
              <Indicator label="60 日" value={formatPercent(stock.metrics.change60d)} tone={stock.metrics.change60d} />
              <Indicator label="60 日波动" value={`${stock.metrics.range60d.toFixed(1)}%`} />
            </div>
            <div className="ma-ladder">
              {[5, 10, 15, 30, 60, 120].map((period) => {
                const above = stock.metrics[`above${period}` as keyof typeof stock.metrics] as boolean;
                return <span key={period} className={above ? "above" : "below"}>MA{period}</span>;
              })}
            </div>
            <div className="macd-callout"><Activity size={16} /><span>周 MACD</span><strong>{stock.metrics.macdClass}</strong></div>
          </section>
          <section className="drawer-section split-notes">
            <div>
              <div className="drawer-section-title"><ShieldCheck size={17} /><h3>继续观察的理由</h3></div>
              <ul>{stock.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
            </div>
            <div>
              <div className="drawer-section-title risk-title"><CircleAlert size={17} /><h3>降级与风险</h3></div>
              <ul>{stock.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul>
            </div>
          </section>
          <section className="action-callout">
            <span>观察行动</span>
            <strong>{stock.action}</strong>
          </section>
          <section className="drawer-section">
            <div className="drawer-section-title"><CalendarDays size={17} /><h3>入选轨迹</h3></div>
            <div className="appearance-timeline">
              {stock.appearances.map((appearance, index) => (
                <div key={`${appearance.reportId}-${index}`}>
                  <i />
                  <span>{appearance.date}</span>
                  <strong>{appearance.reportVersion}</strong>
                  <p>{appearance.label}</p>
                </div>
              ))}
            </div>
          </section>
          <section className="finance-line">
            <div><span>最新归母净利润</span><strong>{formatProfit(stock.parentNetProfit)}</strong></div>
            <small>{stock.profitPeriod} · 正利润不代表完整风险排雷</small>
          </section>
        </div>
      </aside>
    </div>
  );
}

function Indicator({ label, value, tone }: { label: string; value: string; tone?: number }) {
  return <div><span>{label}</span><strong className={tone === undefined ? "" : tone >= 0 ? "positive-text" : "negative-text"}>{value}</strong></div>;
}

export default App;
