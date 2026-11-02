#!/usr/bin/env python3
"""Generate a self-contained HTML research report from dashboard JSON."""

from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "src" / "data" / "stock-data.json"
OUTPUT_FILE = ROOT / "横盘启动选股研究报告.html"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def pct(value: float) -> str:
    return f"{value:+.2f}%" if value else "0.00%"


def tone(value: float) -> str:
    return "up" if value > 0 else "down" if value < 0 else "flat"


def profit(value: float | None) -> str:
    if value is None:
        return "待更新"
    return f"{value / 100_000_000:.2f} 亿"


def tag_tone(value: str) -> str:
    if value in {"通过", "图形确认", "v1.3图形确认"}:
        return "blue"
    if value in {"不通过", "弱观察"}:
        return "green"
    if value == "板块强度样本":
        return "violet"
    return "amber"


def report_rows(reports: list[dict]) -> str:
    return "\n".join(
        f"""
        <tr>
          <td><strong>{esc(report['version'])}</strong><small>{esc(report['date'])}</small></td>
          <td>{esc(report['family'])}</td>
          <td>{esc(report['summary'])}</td>
          <td class="num">{report['stats']['count']}</td>
          <td class="num {tone(report['stats']['averagePerformance'])}">{pct(report['stats']['averagePerformance'])}</td>
          <td class="num">{report['stats']['positiveCount']}</td>
        </tr>"""
        for report in reports
    )


def stock_rows(stocks: list[dict]) -> str:
    rows = []
    for stock in stocks:
        metrics = stock["metrics"]
        ma_values = [
            f'<span class="ma {"on" if metrics[f"above{period}"] else "off"}">MA{period}</span>'
            for period in (5, 10, 15, 30, 60, 120)
        ]
        reasons = "".join(f"<li>{esc(item)}</li>" for item in stock["reasons"])
        risks = "".join(f"<li>{esc(item)}</li>" for item in stock["risks"])
        appearances = "".join(
            f'<span><b>{esc(item["date"])}</b>{esc(item["reportVersion"])} · {esc(item["label"])}</span>'
            for item in stock["appearances"]
        )
        search = " ".join(
            [stock["name"], stock["code"], stock["industry"], stock["direction"], stock["currentCategory"]]
        ).lower()
        rows.append(
            f"""
            <details class="stock-record" data-search="{esc(search)}" data-category="{esc(stock['currentCategory'])}" data-performance="{stock['performance']}">
              <summary>
                <span class="stock-id"><strong>{esc(stock['name'])}</strong><small>{esc(stock['code'])} · {esc(stock['industry'])}</small></span>
                <span><em>当前分层</em><i class="tag {tag_tone(stock['currentCategory'])}">{esc(stock['currentCategory'])}</i></span>
                <span class="price"><em>首次 → 当前</em><b>{stock['firstSelectedPrice']:.2f} → {stock['currentPrice']:.2f}</b><small>{esc(stock['firstSelectedDate'])}</small></span>
                <span class="performance {tone(stock['performance'])}"><em>跟踪表现</em><b>{pct(stock['performance'])}</b></span>
                <span class="rsi"><em>周 / 日 RSI</em><b>{metrics['weeklyRsi']:.1f} / {metrics['dailyRsi']:.1f}</b></span>
                <span class="macd"><em>周 MACD</em><b>{esc(metrics['macdClass'])}</b></span>
                <span class="chevron" aria-hidden="true">⌄</span>
              </summary>
              <div class="stock-detail">
                <div class="switches">
                  <div><span>行业启动开关</span><b class="tag {tag_tone(stock['sectorState'])}">{esc(stock['sectorState'])}</b></div>
                  <div><span>财务与风险开关</span><b class="tag {tag_tone(stock['financialState'])}">{esc(stock['financialState'])}</b></div>
                  <div><span>最新归母净利润</span><b>{profit(stock['parentNetProfit'])}</b><small>{esc(stock['profitPeriod'])}</small></div>
                </div>
                <div class="indicator-band">
                  <div><span>研究评分</span><b>{stock.get('score', '-')}</b></div>
                  <div><span>板块拉升标的</span><b>{esc(stock.get('sectorLeader', '待验证'))}</b><small>{pct(stock.get('sectorLeaderGain', 0))}</small></div>
                  <div><span>弹性分层</span><b>{esc(stock.get('elasticity', {}).get('grade', '待验证'))}</b></div>
                  <div><span>一年最大波段</span><b>{stock.get('elasticity', {}).get('maxStageGain1y', 0):.1f}%</b></div>
                </div>
                <div class="indicator-band">
                  <div><span>距一年低点</span><b>{metrics['riseFromYearLow']:.1f}%</b></div>
                  <div><span>20 日</span><b class="{tone(metrics['change20d'])}">{pct(metrics['change20d'])}</b></div>
                  <div><span>60 日</span><b class="{tone(metrics['change60d'])}">{pct(metrics['change60d'])}</b></div>
                  <div><span>60 日波动</span><b>{metrics['range60d']:.1f}%</b></div>
                </div>
                <div class="ma-band">{''.join(ma_values)}</div>
                <div class="notes-grid">
                  <section><h4>继续观察的理由</h4><ul>{reasons}</ul></section>
                  <section class="risks"><h4>降级与风险</h4><ul>{risks}</ul></section>
                </div>
                <div class="action"><span>观察行动</span><strong>{esc(stock['action'])}</strong></div>
                <div class="appearances"><span class="label">入选轨迹</span>{appearances}</div>
              </div>
            </details>"""
        )
    return "\n".join(rows)


def category_sections(stocks: list[dict]) -> str:
    order = ["5/10早期修复", "5/10早修复·部分确认", "v1.3图形确认"]
    grouped = defaultdict(list)
    for stock in stocks:
        grouped[stock["currentCategory"]].append(stock)
    sections = []
    for category in order:
        members = sorted(grouped[category], key=lambda item: item["performance"], reverse=True)
        average = sum(item["performance"] for item in members) / len(members) if members else 0
        names = "".join(
            f'<span>{esc(item["name"])} <b class="{tone(item["performance"])}">{pct(item["performance"])}</b></span>'
            for item in members[:8]
        )
        sections.append(
            f"""
            <article class="category-panel">
              <header><i class="dot {tag_tone(category)}"></i><div><h3>{esc(category)}</h3><p>{len(members)} 只 · 入选后均值 <b class="{tone(average)}">{pct(average)}</b></p></div></header>
              <div class="name-stack">{names}</div>
              {f'<small>另有 {len(members) - 8} 只，见下方明细</small>' if len(members) > 8 else ''}
            </article>"""
        )
    return "\n".join(sections)


def main() -> None:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    stocks = data["stocks"]
    reports = data["reports"]
    average_score = sum(item.get("score", 0) for item in stocks) / len(stocks)
    sector_passed = sum(item["sectorState"] == "通过" for item in stocks)
    elastic = sum(item.get("elasticity", {}).get("grade") in {"高", "中"} for item in stocks)
    financial = Counter(item["financialState"] for item in stocks)
    generated = datetime.fromisoformat(data["generatedAt"]).strftime("%Y-%m-%d %H:%M")

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='5' fill='%2317201d'/%3E%3Cpath d='M5 17h5l2.5-7 4 14 3.5-10 2 5h5' fill='none' stroke='%23f4f5f2' stroke-width='2'/%3E%3C/svg%3E">
  <title>横盘启动选股研究报告</title>
  <style>
    :root {{ --bg:#f3f5f2; --paper:#fff; --ink:#17201d; --muted:#6d7772; --line:#d8dedb; --blue:#145da0; --blue-soft:#e8f1f8; --red:#c64038; --green:#19835f; --amber:#9a641c; --amber-soft:#f7eddd; --violet:#6e4a91; }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{ margin:0; color:var(--ink); background:var(--bg); font-family:"Avenir Next","PingFang SC","Microsoft YaHei",sans-serif; line-height:1.6; }}
    button,input,select {{ font:inherit; }}
    main {{ width:min(1320px,calc(100% - 32px)); margin:28px auto 60px; }}
    .masthead {{ background:var(--ink); color:#fff; padding:32px 36px 28px; border-radius:6px 6px 0 0; }}
    .masthead .kicker {{ color:#9fb7aa; font-size:11px; }}
    h1 {{ margin:7px 0 6px; font-size:34px; line-height:1.2; letter-spacing:0; }}
    .masthead p {{ margin:0; color:#bdc9c3; font-size:13px; }}
    .mast-meta {{ display:flex; flex-wrap:wrap; gap:18px; margin-top:22px; padding-top:16px; border-top:1px solid #35413c; color:#aab7b1; font-size:11px; }}
    .summary-grid {{ display:grid; grid-template-columns:repeat(4,1fr); background:var(--paper); border:1px solid var(--line); border-top:0; }}
    .metric {{ padding:20px 22px; }} .metric + .metric {{ border-left:1px solid var(--line); }}
    .metric span,.metric strong,.metric small {{ display:block; }} .metric span {{ color:var(--muted); font-size:11px; }}
    .metric strong {{ margin:5px 0 2px; font-family:Consolas,"SFMono-Regular",monospace; font-size:27px; line-height:1.15; }} .metric small {{ color:#8b948f; font-size:10px; }}
    .up {{ color:var(--red)!important; }} .down {{ color:var(--green)!important; }} .flat {{ color:var(--muted)!important; }}
    .notice {{ margin:18px 0; padding:15px 17px; background:#edf3f0; border-left:4px solid var(--blue); font-size:12px; }}
    .notice strong {{ display:block; margin-bottom:3px; }}
    .section {{ background:var(--paper); border-top:2px solid var(--ink); padding:23px 24px; margin-top:22px; }}
    .section-title {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; margin-bottom:18px; }}
    .section-title span {{ color:var(--blue); font-size:10px; font-weight:700; }} .section-title h2 {{ margin:3px 0 0; font-size:20px; line-height:1.25; }} .section-title p {{ margin:0; color:var(--muted); font-size:10px; text-align:right; }}
    table {{ width:100%; border-collapse:collapse; font-size:11px; }} th {{ color:var(--muted); background:#f4f6f4; text-align:left; font-size:10px; }} th,td {{ padding:10px; border:1px solid var(--line); vertical-align:top; }} td small {{ display:block; color:var(--muted); font-size:9px; margin-top:2px; }} .num {{ text-align:right; font-family:Consolas,"SFMono-Regular",monospace; }}
    .category-grid {{ display:grid; grid-template-columns:repeat(5,1fr); gap:1px; background:var(--line); border:1px solid var(--line); }}
    .category-panel {{ background:var(--paper); padding:14px; min-width:0; }} .category-panel header {{ display:flex; align-items:flex-start; gap:9px; min-height:52px; }} .category-panel h3 {{ margin:0; font-size:12px; }} .category-panel p {{ margin:3px 0 0; color:var(--muted); font-size:9px; }} .category-panel > small {{ color:var(--muted); font-size:9px; }}
    .dot {{ width:8px; height:8px; border-radius:50%; margin-top:5px; flex:0 0 auto; }} .dot.blue {{ background:var(--blue); }} .dot.amber {{ background:var(--amber); }} .dot.green {{ background:var(--green); }} .dot.violet {{ background:var(--violet); }}
    .name-stack {{ border-top:1px solid var(--line); }} .name-stack span {{ display:flex; justify-content:space-between; gap:6px; padding:7px 0; border-bottom:1px solid #e9ecea; font-size:10px; }} .name-stack b {{ font-family:Consolas,"SFMono-Regular",monospace; font-size:9px; }}
    .toolbar {{ position:sticky; top:0; z-index:20; display:grid; grid-template-columns:1fr 190px 150px; gap:8px; padding:10px 0; background:var(--paper); border-top:1px solid var(--line); border-bottom:1px solid var(--line); }}
    .toolbar input,.toolbar select {{ height:38px; border:1px solid var(--line); border-radius:4px; background:#fff; color:var(--ink); padding:0 11px; font-size:11px; }}
    .record-count {{ color:var(--muted); font-size:10px; margin:9px 0; }}
    .stock-record {{ border-bottom:1px solid var(--line); background:#fff; }} .stock-record[hidden] {{ display:none; }}
    .stock-record summary {{ list-style:none; cursor:pointer; display:grid; grid-template-columns:1.25fr 1fr 1.1fr .75fr .75fr 1.1fr 20px; gap:12px; align-items:center; min-height:70px; padding:10px 12px; }} .stock-record summary::-webkit-details-marker {{ display:none; }} .stock-record summary:hover {{ background:#f7f9f7; }}
    .stock-record summary > span {{ min-width:0; }} .stock-record summary em {{ display:block; color:var(--muted); font-style:normal; font-size:9px; }} .stock-record summary b {{ font-size:11px; }} .stock-id strong,.stock-id small {{ display:block; }} .stock-id strong {{ font-size:13px; }} .stock-id small,.price small {{ color:var(--muted); font-size:9px; }} .price b,.performance b,.rsi b {{ font-family:Consolas,"SFMono-Regular",monospace; }} .chevron {{ color:var(--muted); font-size:18px; transition:transform .15s ease; }} details[open] .chevron {{ transform:rotate(180deg); }}
    .tag {{ display:inline-block; border-radius:4px; padding:2px 7px; font-size:9px; font-style:normal; border:1px solid transparent; white-space:nowrap; }} .tag.blue {{ background:var(--blue-soft); border-color:#c7dcea; color:var(--blue); }} .tag.amber {{ background:var(--amber-soft); border-color:#ead4b0; color:var(--amber); }} .tag.green {{ background:#e3f2ec; border-color:#bfe0d3; color:var(--green); }} .tag.violet {{ background:#eee8f4; border-color:#d7c9e5; color:var(--violet); }}
    .stock-detail {{ background:#f6f8f6; border-top:1px solid var(--line); padding:15px 16px 18px; }} .switches {{ display:grid; grid-template-columns:repeat(3,1fr); background:#fff; border:1px solid var(--line); }} .switches > div {{ padding:11px 12px; }} .switches > div + div {{ border-left:1px solid var(--line); }} .switches span,.switches small {{ display:block; color:var(--muted); font-size:9px; }} .switches b {{ font-size:10px; }}
    .indicator-band {{ display:grid; grid-template-columns:repeat(4,1fr); margin-top:10px; background:#fff; border:1px solid var(--line); }} .indicator-band div {{ padding:9px 12px; }} .indicator-band div + div {{ border-left:1px solid var(--line); }} .indicator-band span,.indicator-band b {{ display:block; }} .indicator-band span {{ color:var(--muted); font-size:9px; }} .indicator-band b {{ margin-top:2px; font-family:Consolas,"SFMono-Regular",monospace; font-size:11px; }}
    .ma-band {{ display:flex; flex-wrap:wrap; gap:5px; margin-top:10px; }} .ma {{ border:1px solid var(--line); padding:4px 8px; font-family:Consolas,"SFMono-Regular",monospace; font-size:9px; }} .ma.on {{ color:var(--blue); background:var(--blue-soft); border-color:#c8ddeb; }} .ma.off {{ color:var(--muted); background:#edf0ee; }}
    .notes-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:11px; }} .notes-grid section {{ background:#fff; border:1px solid var(--line); padding:12px 14px; }} .notes-grid h4 {{ margin:0 0 8px; font-size:11px; color:var(--blue); }} .notes-grid .risks h4 {{ color:var(--amber); }} .notes-grid ul {{ margin:0; padding-left:17px; }} .notes-grid li {{ margin:3px 0; color:#4e5954; font-size:10px; }}
    .action {{ display:flex; gap:13px; align-items:baseline; margin-top:10px; padding:11px 13px; background:var(--ink); color:#fff; }} .action span {{ color:#a9b5af; font-size:9px; white-space:nowrap; }} .action strong {{ font-size:10px; }}
    .appearances {{ display:flex; flex-wrap:wrap; gap:7px; margin-top:10px; }} .appearances > span {{ background:#fff; border:1px solid var(--line); padding:5px 8px; font-size:9px; }} .appearances .label {{ color:var(--muted); background:transparent; border:0; padding-left:0; }} .appearances b {{ margin-right:5px; font-family:Consolas,"SFMono-Regular",monospace; }}
    footer {{ margin-top:22px; padding:16px 2px; border-top:1px solid var(--line); color:var(--muted); font-size:10px; display:flex; justify-content:space-between; gap:20px; }}
    @media print {{ body {{ background:#fff; }} main {{ width:100%; margin:0; }} .toolbar {{ display:none; }} .stock-record {{ break-inside:avoid; }} .stock-record:not([open]) .stock-detail {{ display:none; }} }}
    @media (max-width:900px) {{ .summary-grid {{ grid-template-columns:repeat(2,1fr); }} .metric:nth-child(3) {{ border-left:0; border-top:1px solid var(--line); }} .metric:nth-child(4) {{ border-top:1px solid var(--line); }} .category-grid {{ grid-template-columns:repeat(2,1fr); }} .stock-record summary {{ grid-template-columns:1fr auto; gap:8px; }} .stock-record summary > span:nth-child(n+3):not(.performance):not(.chevron) {{ display:none; }} .performance {{ text-align:right; }} .chevron {{ display:none; }} }}
    @media (max-width:620px) {{ main {{ width:calc(100% - 18px); margin:9px auto 32px; }} .masthead {{ padding:24px 20px; }} h1 {{ font-size:25px; }} .summary-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .metric {{ padding:14px; }} .metric strong {{ font-size:22px; }} .section {{ padding:17px 13px; }} .section-title p {{ display:none; }} .category-grid {{ display:block; border:0; background:transparent; }} .category-panel {{ border:1px solid var(--line); margin-bottom:9px; }} .toolbar {{ grid-template-columns:1fr 1fr; }} .toolbar input {{ grid-column:1/-1; }} .toolbar select:last-child {{ display:none; }} .stock-record summary {{ min-height:64px; padding:9px 8px; }} .switches {{ grid-template-columns:1fr; }} .switches > div + div {{ border-left:0; border-top:1px solid var(--line); }} .indicator-band {{ grid-template-columns:repeat(2,1fr); }} .indicator-band div:nth-child(3) {{ border-left:0; border-top:1px solid var(--line); }} .indicator-band div:nth-child(4) {{ border-top:1px solid var(--line); }} .notes-grid {{ grid-template-columns:1fr; }} table {{ min-width:760px; }} .table-scroll {{ overflow:auto; }} footer {{ display:block; }} }}
  </style>
</head>
<body>
  <main>
    <header class="masthead">
      <span class="kicker">A股观察池 · {esc(data['methodologyVersion'])}</span>
      <h1>横盘启动选股研究报告</h1>
      <p>按最新 v1.9 口径从当前A股重新筛选 30 只，不合并前面各轮股票。</p>
      <div class="mast-meta"><span>数据交易日：{esc(data['asOf'])}</span><span>报告生成：{esc(generated)}</span><span>报告批次：{len(reports)}</span><span>唯一股票：{len(stocks)}</span></div>
    </header>

    <section class="summary-grid">
      <div class="metric"><span>本轮全新样本</span><strong>{len(stocks)}</strong><small>与旧 48 只交集为 0</small></div>
      <div class="metric"><span>行业开关通过</span><strong>{sector_passed}</strong><small>板块已有其他拉升标的</small></div>
      <div class="metric"><span>中高弹性</span><strong>{elastic}</strong><small>一年波段与涨停记忆</small></div>
      <div class="metric"><span>平均研究评分</span><strong>{average_score:.1f}</strong><small>前置开关通过后的比较分</small></div>
    </section>

    <div class="notice"><strong>研究边界</strong>{esc(data['disclaimer'])} 行业开关使用当日板块快照；归母净利润为正不代表完整排雷，仍需核对扣非净利、现金流、商誉、质押、减持和监管事项。</div>

    <section class="section">
      <div class="section-title"><div><span>本轮口径</span><h2>全市场重新筛选</h2></div><p>基于低位、RSI/MACD、MA5/10、行业拉升标的和弹性</p></div>
      <div class="table-scroll"><table><thead><tr><th>版本 / 日期</th><th>规则类别</th><th>本轮核心变化</th><th class="num">样本</th><th class="num">均值</th><th class="num">上涨</th></tr></thead><tbody>{report_rows(reports)}</tbody></table></div>
    </section>

    <section class="section">
      <div class="section-title"><div><span>当前分层</span><h2>按研究类别汇总</h2></div><p>类别由当前 RSI、MACD、均线和价格位置重新计算</p></div>
      <div class="category-grid">{category_sections(stocks)}</div>
    </section>

    <section class="section" id="stock-list">
      <div class="section-title"><div><span>持续跟踪</span><h2>{len(stocks)} 只全新样本研究明细</h2></div><p>点击股票行展开理由、风险、指标与观察行动</p></div>
      <div class="toolbar">
        <input id="search" type="search" placeholder="搜索名称、代码、行业或方向" aria-label="搜索股票">
        <select id="category" aria-label="按类别筛选"><option value="">全部类别</option>{''.join(f'<option>{esc(item)}</option>' for item in ['5/10早期修复','5/10早修复·部分确认','v1.3图形确认'])}</select>
        <select id="sort" aria-label="排序"><option value="performance">表现从高到低</option><option value="performance-asc">表现从低到高</option><option value="name">名称排序</option></select>
      </div>
      <div class="record-count" id="record-count">显示 {len(stocks)} / {len(stocks)} 只</div>
      <div id="records">{stock_rows(sorted(stocks, key=lambda item: item['performance'], reverse=True))}</div>
    </section>

    <section class="section">
      <div class="section-title"><div><span>数据与风险</span><h2>当前数据口径</h2></div></div>
      <div class="table-scroll"><table><tbody>
        <tr><th>行情数据</th><td>{esc(data['sources'][0])}。前复权源不可用时，技术指标与价格轨迹使用回退日线口径。</td></tr>
        <tr><th>财务数据</th><td>{esc(data['sources'][1])}。财务开关：通过 {financial.get('通过',0)}、观察 {financial.get('观察',0)}。</td></tr>
        <tr><th>首次入选</th><td>使用报告形成日期；价格使用该日期之前最近交易日收盘。该指标用于研究跟踪，不等同于可执行交易收益。</td></tr>
        <tr><th>行业启动</th><td>{esc(data['sources'][2])}。当日快照不代替多日扩散与周线持续性验证。</td></tr>
      </tbody></table></div>
    </section>

    <footer><span>{esc(data['disclaimer'])}</span><span>文件：横盘启动选股研究报告.html</span></footer>
  </main>
  <script>
    const records = document.getElementById('records');
    const search = document.getElementById('search');
    const category = document.getElementById('category');
    const sort = document.getElementById('sort');
    const count = document.getElementById('record-count');
    const allRecords = Array.from(records.querySelectorAll('.stock-record'));
    function update() {{
      const q = search.value.trim().toLowerCase();
      const c = category.value;
      const sorted = [...allRecords].sort((a,b) => {{
        if (sort.value === 'name') return a.dataset.search.localeCompare(b.dataset.search, 'zh-CN');
        const diff = Number(b.dataset.performance) - Number(a.dataset.performance);
        return sort.value === 'performance-asc' ? -diff : diff;
      }});
      sorted.forEach(item => records.appendChild(item));
      let visible = 0;
      allRecords.forEach(item => {{
        const show = (!q || item.dataset.search.includes(q)) && (!c || item.dataset.category === c);
        item.hidden = !show;
        if (show) visible++;
      }});
      count.textContent = `显示 ${{visible}} / ${{allRecords.length}} 只`;
    }}
    search.addEventListener('input', update);
    category.addEventListener('change', update);
    sort.addEventListener('change', update);
  </script>
</body>
</html>"""
    OUTPUT_FILE.write_text(document, encoding="utf-8")
    print(f"wrote {OUTPUT_FILE} ({OUTPUT_FILE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
