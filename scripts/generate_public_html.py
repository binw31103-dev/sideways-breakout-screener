#!/usr/bin/env python3
"""Generate a compact single-file report that fits free HTML hosts."""

from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "src/data/stock-data.json").read_text(encoding="utf-8"))
OUTPUT = ROOT / "横盘启动选股公网简版.html"


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def pct(value: float) -> str:
    return f"{value:+.2f}%" if value else "0.00%"


def cls(value: float) -> str:
    return "u" if value > 0 else "d" if value < 0 else ""


stocks = DATA["stocks"]
reports = DATA["reports"]
average_score = sum(item.get("score", 0) for item in stocks) / len(stocks)
categories = Counter(item["currentCategory"] for item in stocks)

report_rows = "".join(
    f"<tr><td>{e(item['version'])}<small>{e(item['date'])}</small></td><td>{e(item['family'])}</td><td>{item['stats']['count']}</td><td class='{cls(item['stats']['averagePerformance'])}'>{pct(item['stats']['averagePerformance'])}</td></tr>"
    for item in reports
)

stock_rows = "".join(
    f"<tr data-q='{e((item['name'] + item['code'] + item['industry'] + item['currentCategory'] + item.get('sectorLeader', '')).lower())}'><td><b>{e(item['name'])}</b><small>{e(item['code'])} · {e(item['industry'])}</small></td><td>{e(item['currentCategory'])}</td><td><b>{item.get('score', 0)}</b></td><td>{item['metrics']['riseFromYearLow']:.1f}%<small>20日 {pct(item['metrics']['change20d'])}</small></td><td>{item['metrics']['weeklyRsi']:.1f}/{item['metrics']['dailyRsi']:.1f}<small>4/8周 {item['metrics'].get('weeklyRsi4w','-')}/{item['metrics'].get('weeklyRsi8w','-')}</small></td><td>{e(item['metrics']['macdClass'])}</td><td><b>{e(item.get('sectorLeader','待验证'))}</b><small>{pct(item.get('sectorLeaderGain',0))} · {e(item['sectorState'])}</small></td><td>{e(item.get('elasticity',{}).get('grade','待验证'))}<small>最大{item.get('elasticity',{}).get('maxStageGain1y',0):.0f}% · 30%波段{item.get('elasticity',{}).get('gain30Count',0)}次 · 连板{item.get('elasticity',{}).get('maxLimitStreak',0)}天</small></td><td>{e(item['financialState'])}<small>{item['parentNetProfit']/100000000:.2f}亿</small></td></tr>"
    for item in sorted(stocks, key=lambda row: row.get("score", 0), reverse=True)
)

category_text = "".join(f"<span><b>{e(name)}</b>{count}只</span>" for name, count in categories.most_common())

document = f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>横盘启动选股研究报告</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f5f2;color:#17201d;font-family:Arial,'Microsoft YaHei',sans-serif;font-size:13px}}main{{width:min(1180px,calc(100% - 24px));margin:18px auto 40px}}header{{background:#17201d;color:#fff;padding:28px;border-radius:6px 6px 0 0}}h1{{margin:4px 0 8px;font-size:30px}}header p{{margin:0;color:#b9c7c0}}.meta{{margin-top:16px;color:#9eaca5;font-size:11px}}.kpis{{display:grid;grid-template-columns:repeat(4,1fr);background:#fff;border:1px solid #d8dedb}}.kpis div{{padding:16px;border-right:1px solid #d8dedb}}.kpis span,.kpis b,.kpis small{{display:block}}.kpis span,small{{color:#6d7772;font-size:10px}}.kpis b{{font-size:24px;margin:3px 0}}.u{{color:#c64038!important}}.d{{color:#19835f!important}}.note{{margin:14px 0;padding:12px 14px;border-left:4px solid #145da0;background:#eaf2ef}}section{{background:#fff;border-top:2px solid #17201d;padding:18px;margin-top:18px}}h2{{margin:0 0 13px;font-size:18px}}table{{width:100%;border-collapse:collapse;font-size:11px}}th,td{{padding:8px;border:1px solid #d8dedb;text-align:left}}th{{background:#f1f4f2;color:#6d7772}}td small{{display:block;margin-top:2px}}.cats{{display:flex;flex-wrap:wrap;gap:8px}}.cats span{{border:1px solid #d8dedb;padding:7px 9px;background:#fff}}.cats b{{margin-right:8px}}input{{width:100%;height:38px;border:1px solid #b9c3be;padding:0 11px;margin-bottom:10px}}.scroll{{overflow:auto}}footer{{padding:14px 2px;color:#6d7772;font-size:10px}}@media(max-width:680px){{main{{width:calc(100% - 12px);margin:6px auto}}header{{padding:21px 17px}}h1{{font-size:23px}}.kpis{{grid-template-columns:1fr 1fr}}.kpis div:nth-child(2),.kpis div:nth-child(4){{border-right:0}}section{{padding:13px}}table{{min-width:850px}}}}
</style></head><body><main><header><small>A股观察池 · {e(DATA['methodologyVersion'])}</small><h1>横盘启动全新 30 只观察池</h1><p>按最新口径从当前A股重新筛选，不合并前面各轮股票。</p><div class='meta'>数据交易日 {e(DATA['asOf'])} · {len(reports)}个全新批次 · {len(stocks)}只新样本 · 与旧48只交集0</div></header>
<div class='kpis'><div><span>全新样本</span><b>{len(stocks)}</b><small>硬性排除旧48只</small></div><div><span>行业开关通过</span><b>{sum(item['sectorState']=='通过' for item in stocks)}</b><small>板块已有其他拉升股</small></div><div><span>中高弹性</span><b>{sum(item.get('elasticity',{}).get('grade') in {'高','中'} for item in stocks)}</b><small>一年波段与涨停记忆</small></div><div><span>平均研究分</span><b>{average_score:.1f}</b><small>开关通过后的比较分</small></div></div>
<div class='note'><b>研究边界：</b>{e(DATA['disclaimer'])} 行业开关使用当日板块快照；正利润不等于扣非、现金流、质押和监管风险已完整排雷。</div>
<section><h2>本轮规则</h2><div class='scroll'><table><thead><tr><th>版本/日期</th><th>规则类别</th><th>样本</th><th>跟踪基线</th></tr></thead><tbody>{report_rows}</tbody></table></div></section>
<section><h2>当前研究分层</h2><div class='cats'>{category_text}</div></section>
<section><h2>{len(stocks)}只新样本核心明细</h2><input id='s' placeholder='搜索名称、代码、行业、分层或拉升标的'><div class='scroll'><table><thead><tr><th>股票/行业</th><th>当前分层</th><th>评分</th><th>低位/涨幅</th><th>周/日RSI</th><th>周MACD</th><th>板块拉升标的</th><th>弹性</th><th>财务开关</th></tr></thead><tbody id='rows'>{stock_rows}</tbody></table></div></section>
<footer>数据来源：{' · '.join(e(item) for item in DATA['sources'])}。仍需核对扣非净利、现金流、质押、减持、监管处罚与行业多日扩散。</footer></main><script>const s=document.querySelector('#s'),r=[...document.querySelectorAll('#rows tr')];s.oninput=()=>{{let q=s.value.toLowerCase();r.forEach(x=>x.hidden=!x.dataset.q.includes(q))}}</script></body></html>"""

if len(document) > 29_000:
    raise SystemExit(f"document too large for free host: {len(document)} characters")

OUTPUT.write_text(document, encoding="utf-8")
print(f"wrote {OUTPUT} ({len(document)} characters, {OUTPUT.stat().st_size} bytes)")
