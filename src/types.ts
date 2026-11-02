export type Appearance = {
  code: string;
  name: string;
  direction: string;
  date: string;
  dataDate?: string;
  label: string;
  reportId: string;
  reportVersion: string;
  reportFile: string;
};

export type Metrics = {
  weeklyRsi: number;
  weeklyRsi4w?: number | null;
  weeklyRsi8w?: number | null;
  dailyRsi: number;
  macdClass: string;
  riseFromYearLow: number;
  change20d: number;
  change60d: number;
  range60d: number;
  drawdown3y?: number;
  base12wRange?: number;
  averageAmount20d?: number;
  volumeRatio5v20?: number;
  above5: boolean;
  above10: boolean;
  above15: boolean;
  above30: boolean;
  above60: boolean;
  above120: boolean;
};

export type Elasticity = {
  grade: string;
  maxStageGain1y: number;
  gain30Count: number;
  limitUpDays: number;
  maxLimitStreak: number;
};

export type Stock = {
  code: string;
  name: string;
  industry: string;
  direction: string;
  firstSelectedDate: string;
  firstSelectedPrice: number;
  currentDate: string;
  currentPrice: number;
  performance: number;
  trackedDays: number;
  firstCategory: string;
  currentCategory: string;
  sectorState: string;
  sectorEvidence?: string;
  sectorLeader?: string;
  sectorLeaderCode?: string;
  sectorLeaderGain?: number;
  financialState: string;
  parentNetProfit: number | null;
  profitPeriod: string;
  score?: number;
  elasticity?: Elasticity;
  metrics: Metrics;
  reasons: string[];
  risks: string[];
  action: string;
  appearances: Appearance[];
  sparkline: { date: string; close: number }[];
};

export type Report = {
  id: string;
  version: string;
  file: string;
  date: string;
  family: string;
  summary: string;
  selections: string[];
  stats: {
    count: number;
    averagePerformance: number;
    positiveCount: number;
    strengthCount: number;
  };
};

export type DashboardData = {
  generatedAt: string;
  asOf: string;
  methodologyVersion: string;
  disclaimer: string;
  reports: Report[];
  stocks: Stock[];
  failures: { code: string; name: string; error: string }[];
  sources: string[];
};

export type DailyHistoryItem = {
  key: string;
  model: string;
  code: string;
  name: string;
  industry: string;
  date: string;
  state: string;
  close: number;
  firstSelectedDate: string;
  firstClose: number;
  changeSinceFirst: number;
  selectedCount: number;
  riseYearLow: number;
  change20: number;
  dailyRsi: number;
  weeklyRsi: number;
  range20: number;
  volumeRatio5v20: number;
  sectorState: string;
  sectorLeader: string;
  sectorLeaderGain: number;
  financialState: string;
  riskState: string;
};

export type DailyHistoryDay = {
  date: string;
  generatedAt: string | null;
  dataThrough: string;
  counts: {
    total: number;
    v26: number;
    v13: number;
    positive: number;
    financialPass: number;
  };
  averageChangeSinceFirst: number;
  items: DailyHistoryItem[];
};

export type DailyHistoryData = {
  generatedAt: string;
  dateRange: { start: string; end: string };
  days: DailyHistoryDay[];
  summary: {
    dayCount: number;
    recordCount: number;
    uniqueStockCount: number;
    positiveRecordCount: number;
  };
};
