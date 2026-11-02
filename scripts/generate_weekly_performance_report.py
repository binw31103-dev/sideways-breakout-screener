#!/usr/bin/env python3
"""Generate a weekly HTML performance report and optionally notify Feishu."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path
from typing import Any

from run_daily_screen_and_notify import send_feishu
from screen_latest_30 import fetch_kline


ROOT = Path(__file__).resolve().parents[1]
DAILY_ROOT = ROOT / "output" / "daily"
WEEKLY_ROOT = ROOT / "output" / "weekly"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(start: float, current: float) -> float:
    if not start:
        return 0.0
    return (current / start - 1) * 100


def fmt_pct(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:+.{digits}f}%"


def fmt_price(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def week_bounds(date_value: dt.date) -> tuple[dt.date, dt.date]:
    monday = date_value - dt.timedelta(days=date_value.weekday())
    return monday, monday + dt.timedelta(days=4)


def date_range(start: dt.date, end: dt.date) -> list[str]:
    days = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += dt.timedelta(days=1)
    return days


def collect_week_rows(start: dt.date, end: dt.date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    daily_summary: list[dict[str, Any]] = []
    by_sample: dict[str, dict[str, Any]] = {}
    for date_text in date_range(start, end):
        combined_path = DAILY_ROOT / date_text / "combined.json"
        if not combined_path.exists():
            daily_summary.append({"date": date_text, "v26": 0, "v13": 0, "missing": True})
            continue
        combined = load_json(combined_path)
        data_date = str(combined.get("dataThrough") or date_text)
        day_counts = {"date": data_date, "v26": 0, "v13": 0, "missing": False}
        for model_key, model_name in [("v26", "v2.6统一观察"), ("v13", "v1.3右侧启动")]:
            selected = (combined.get(model_key) or {}).get("selected") or []
            day_counts[model_key] = len(selected)
            for item in selected:
                code = str(item.get("code") or "")
                if not code:
                    continue
                key = f"{model_key}:{code}"
                sample = by_sample.setdefault(
                    key,
                    {
                        "key": key,
                        "model_key": model_key,
                        "model": model_name,
                        "code": code,
                        "name": item.get("name", ""),
                        "industry": item.get("industry", ""),
                        "first_date": data_date,
                        "first_close": float(item.get("close") or 0),
                        "first_state": item.get("state", ""),
                        "appearances": [],
                        "daily_rsi": item.get("dailyRsi", ""),
                        "weekly_rsi": item.get("weeklyRsi", ""),
                        "change20": item.get("change20", ""),
                        "risk_state": item.get("riskState", ""),
                    },
                )
                sample["appearances"].append(
                    {
                        "date": data_date,
                        "close": float(item.get("close") or 0),
                        "state": item.get("state", ""),
                    }
                )
        daily_summary.append(day_counts)
    return daily_summary, list(by_sample.values())


def enrich_performance(samples: list[dict[str, Any]]) -> None:
    for sample in samples:
        code = str(sample["code"])
        start_date = str(sample["first_date"])
        start_close = float(sample["first_close"] or 0)
        fallback_close = float(sample["appearances"][-1]["close"]) if sample.get("appearances") else start_close
        fallback_date = str(sample["appearances"][-1]["date"]) if sample.get("appearances") else start_date
        try:
            kline, source = fetch_kline(code)
        except Exception as exc:
            sample.update(
                {
                    "source": "本周入池快照",
                    "current_date": fallback_date,
                    "current_close": fallback_close,
                    "change_since_first": pct(start_close, fallback_close),
                    "latest_day_change": 0.0,
                    "high_date": fallback_date,
                    "high_gain": pct(start_close, fallback_close),
                    "low_date": fallback_date,
                    "low_gain": pct(start_close, fallback_close),
                    "tracking_days": len(sample.get("appearances") or []),
                    "data_error": str(exc),
                    "close_log": "; ".join(
                        f"{item['date']}:{float(item['close']):.2f}" for item in sample.get("appearances") or []
                    ),
                    "gain_log": "; ".join(
                        f"{item['date']}:{pct(start_close, float(item['close'])):+.2f}%"
                        for item in sample.get("appearances") or []
                    ),
                }
            )
            continue
        selected_rows = [row for row in kline if str(row.get("date", "")) >= start_date]
        if not selected_rows:
            sample.update(
                {
                    "source": source,
                    "current_date": fallback_date,
                    "current_close": fallback_close,
                    "change_since_first": pct(start_close, fallback_close),
                    "latest_day_change": 0.0,
                    "high_date": fallback_date,
                    "high_gain": pct(start_close, fallback_close),
                    "low_date": fallback_date,
                    "low_gain": pct(start_close, fallback_close),
                    "tracking_days": len(sample.get("appearances") or []),
                    "data_error": "入池日之后无K线",
                    "close_log": "; ".join(
                        f"{item['date']}:{float(item['close']):.2f}" for item in sample.get("appearances") or []
                    ),
                    "gain_log": "; ".join(
                        f"{item['date']}:{pct(start_close, float(item['close'])):+.2f}%"
                        for item in sample.get("appearances") or []
                    ),
                }
            )
            continue
        closes = [(str(row["date"]), float(row["close"])) for row in selected_rows]
        gains = [(date_text, pct(start_close, close)) for date_text, close in closes if close]
        current_date, current_close = closes[-1]
        high_date, high_gain = max(gains, key=lambda item: item[1])
        low_date, low_gain = min(gains, key=lambda item: item[1])
        previous_close = closes[-2][1] if len(closes) > 1 else start_close
        sample.update(
            {
                "source": source,
                "current_date": current_date,
                "current_close": current_close,
                "change_since_first": pct(start_close, current_close),
                "latest_day_change": pct(previous_close, current_close),
                "high_date": high_date,
                "high_gain": high_gain,
                "low_date": low_date,
                "low_gain": low_gain,
                "tracking_days": len(closes),
                "close_log": "; ".join(f"{date_text}:{close:.2f}" for date_text, close in closes),
                "gain_log": "; ".join(f"{date_text}:{gain:+.2f}%" for date_text, gain in gains),
            }
        )


def tone(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "flat"
    return "up" if number > 0 else "down" if number < 0 else "flat"


def rows_html(samples: list[dict[str, Any]]) -> str:
    rows = []
    for index, item in enumerate(samples, 1):
        rows.append(
            f"""
            <tr>
              <td class="rank">{index}</td>
              <td><strong>{esc(item['name'])}</strong><small>{esc(item['code'])} · {esc(item.get('industry', ''))}</small></td>
              <td>{esc(item['model'])}<small>{esc(item.get('first_state', ''))}</small></td>
              <td>{esc(item['first_date'])}<small>{fmt_price(item.get('first_close'))}</small></td>
              <td>{esc(item.get('current_date', '-'))}<small>{fmt_price(item.get('current_close'))}</small></td>
              <td class="{tone(item.get('change_since_first'))}">{fmt_pct(item.get('change_since_first'))}</td>
              <td class="{tone(item.get('latest_day_change'))}">{fmt_pct(item.get('latest_day_change'))}</td>
              <td class="{tone(item.get('high_gain'))}">{fmt_pct(item.get('high_gain'))}<small>{esc(item.get('high_date', '-'))}</small></td>
              <td class="{tone(item.get('low_gain'))}">{fmt_pct(item.get('low_gain'))}<small>{esc(item.get('low_date', '-'))}</small></td>
              <td>{esc(item.get('tracking_days', '-'))}</td>
            </tr>
            <tr class="log-row">
              <td></td>
              <td colspan="9"><b>每日记录</b> {esc(item.get('close_log', ''))}<br><b>较入池涨跌</b> {esc(item.get('gain_log', ''))}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def daily_html(daily_summary: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"""
        <tr>
          <td>{esc(item['date'])}</td>
          <td>{'缺日报' if item.get('missing') else '已统计'}</td>
          <td>{item.get('v26', 0)}</td>
          <td>{item.get('v13', 0)}</td>
          <td>{item.get('v26', 0) + item.get('v13', 0)}</td>
        </tr>
        """
        for item in daily_summary
    )


def render_html(
    output_path: Path,
    start: dt.date,
    end: dt.date,
    daily_summary: list[dict[str, Any]],
    samples: list[dict[str, Any]],
) -> None:
    positive = sum(1 for item in samples if float(item.get("change_since_first") or 0) > 0)
    average = sum(float(item.get("change_since_first") or 0) for item in samples) / len(samples) if samples else 0
    best = max(samples, key=lambda item: float(item.get("change_since_first") or -999), default=None)
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A股双模型本周票池涨幅周报</title>
  <style>
    :root {{ --bg:#f6f7f9; --panel:#fff; --text:#1f2937; --muted:#667085; --line:#d9dee7; --accent:#2563eb; --up:#b42318; --down:#0f766e; --warn:#b45309; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; line-height:1.58; }}
    main {{ width:min(1180px,calc(100% - 32px)); margin:28px auto 48px; }}
    header {{ padding:28px 0 18px; border-bottom:1px solid var(--line); margin-bottom:18px; }}
    h1,h2 {{ margin:0; line-height:1.25; }} h1 {{ font-size:30px; }} h2 {{ font-size:20px; margin-bottom:12px; }}
    .subtitle {{ color:var(--muted); margin:8px 0 0; }}
    .tag {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:3px 10px; color:var(--muted); background:#fff; font-size:12px; margin-bottom:10px; }}
    .grid {{ display:grid; grid-template-columns:repeat(12,1fr); gap:16px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; box-shadow:0 1px 2px rgba(16,24,40,.04); }}
    .span-12 {{ grid-column:span 12; }} .span-3 {{ grid-column:span 3; }}
    .kpi span,.kpi strong,.kpi small {{ display:block; }} .kpi span {{ color:var(--muted); font-size:13px; }} .kpi strong {{ font-size:28px; margin:4px 0; }} .kpi small {{ color:var(--muted); }}
    .callout {{ border-left:4px solid var(--accent); background:#eff6ff; padding:12px 14px; border-radius:6px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }} th,td {{ border:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; }} th {{ background:#f2f4f7; color:var(--muted); }}
    td small {{ display:block; color:var(--muted); font-size:12px; margin-top:2px; }} .rank {{ color:var(--muted); text-align:center; width:42px; }}
    .up {{ color:var(--up); font-weight:700; }} .down {{ color:var(--down); font-weight:700; }} .flat {{ color:var(--muted); }}
    .log-row td {{ background:#fbfcfd; color:#475467; font-size:12px; }}
    .table-wrap {{ overflow:auto; }}
    footer {{ margin-top:18px; color:var(--muted); font-size:12px; }}
    @media (max-width:760px) {{ main {{ width:min(100% - 20px,1180px); margin-top:18px; }} h1 {{ font-size:24px; }} .span-3 {{ grid-column:span 6; }} .card {{ padding:14px; }} table {{ min-width:920px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <span class="tag">观察池周报</span>
      <h1>A股双模型本周票池涨幅周报</h1>
      <p class="subtitle">统计区间：{start.isoformat()} 至 {end.isoformat()}。仅汇总本周实际入池股票，不补票、不放宽条件。</p>
    </header>
    <section class="grid">
      <article class="card span-3 kpi"><span>本周入池样本</span><strong>{len(samples)}</strong><small>v2.6 + v1.3 去重后</small></article>
      <article class="card span-3 kpi"><span>上涨样本</span><strong>{positive}</strong><small>按入池日至当前收盘</small></article>
      <article class="card span-3 kpi"><span>平均涨跌</span><strong class="{tone(average)}">{fmt_pct(average)}</strong><small>等权观察</small></article>
      <article class="card span-3 kpi"><span>本周最佳</span><strong>{esc(best['name']) if best else '-'}</strong><small>{fmt_pct(best.get('change_since_first')) if best else '-'}</small></article>
      <article class="card span-12">
        <div class="callout">本报告只用于观察池研究，不构成投资建议。涨跌统计以项目现有日筛选结果和腾讯前复权日K为主；仍需复核扣非净利、现金流、质押、减持、监管处罚、行业启动强度和图形。</div>
      </article>
      <article class="card span-12">
        <h2>每日入池概览</h2>
        <div class="table-wrap"><table><thead><tr><th>日期</th><th>状态</th><th>v2.6</th><th>v1.3</th><th>合计</th></tr></thead><tbody>{daily_html(daily_summary)}</tbody></table></div>
      </article>
      <article class="card span-12">
        <h2>本周入池股票涨幅明细</h2>
        <div class="table-wrap"><table><thead><tr><th>#</th><th>股票</th><th>模型</th><th>入池日/价</th><th>当前日/价</th><th>较入池</th><th>最新日</th><th>最高</th><th>最大回撤</th><th>跟踪日</th></tr></thead><tbody>{rows_html(samples)}</tbody></table></div>
      </article>
    </section>
    <footer>生成时间：{esc(generated_at)} · 文件：{esc(output_path)}</footer>
  </main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")


def feishu_card(
    start: dt.date,
    end: dt.date,
    output_path: Path,
    daily_summary: list[dict[str, Any]],
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    average = sum(float(item.get("change_since_first") or 0) for item in samples) / len(samples) if samples else 0
    lines = [
        f"**统计区间：{start.isoformat()} 至 {end.isoformat()}**",
        f"本周实际入池 {len(samples)} 只｜上涨 {sum(1 for item in samples if float(item.get('change_since_first') or 0) > 0)} 只｜平均 {fmt_pct(average)}",
        f"HTML周报：`{output_path}`",
        "",
        "| 股票 | 模型 | 入池价->当前价 | 较入池 | 最新日 | 最高/回撤 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in samples:
        lines.append(
            "| "
            f"{item['name']} {item['code']} | "
            f"{item['model']} | "
            f"{fmt_price(item.get('first_close'))}->{fmt_price(item.get('current_close'))} | "
            f"{fmt_pct(item.get('change_since_first'))} | "
            f"{fmt_pct(item.get('latest_day_change'))} | "
            f"{fmt_pct(item.get('high_gain'))}/{fmt_pct(item.get('low_gain'))} |"
        )
    empty_days = [
        item["date"]
        for item in daily_summary
        if not item.get("missing") and item.get("v26", 0) + item.get("v13", 0) == 0
    ]
    if empty_days:
        lines.extend(["", f"无入池交易日：{', '.join(empty_days)}"])
    lines.extend(["", "仅用于观察池研究，不构成投资建议；未放宽任何选股条件。"])
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": f"A股双模型本周票池涨幅周报｜{end.isoformat()}"},
            },
            "elements": [{"tag": "markdown", "content": "\n".join(lines)}],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Week date, defaults to today, YYYY-MM-DD")
    parser.add_argument("--start", help="Start date, YYYY-MM-DD")
    parser.add_argument("--end", help="End date, YYYY-MM-DD")
    parser.add_argument("--send", action="store_true", help="Send Feishu webhook card")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start and args.end:
        start = dt.date.fromisoformat(args.start)
        end = dt.date.fromisoformat(args.end)
    else:
        target = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now().astimezone().date()
        start, end = week_bounds(target)
    daily_summary, samples = collect_week_rows(start, end)
    enrich_performance(samples)
    samples.sort(key=lambda item: float(item.get("change_since_first") or -999), reverse=True)
    output_path = WEEKLY_ROOT / f"weekly-performance-{start.isoformat()}_{end.isoformat()}.html"
    render_html(output_path, start, end, daily_summary, samples)
    print(f"wrote {output_path}")
    print(f"samples={len(samples)}")
    for item in samples:
        print(
            f"{item['model_key']} {item['code']} {item['name']} "
            f"{fmt_price(item.get('first_close'))}->{fmt_price(item.get('current_close'))} "
            f"{fmt_pct(item.get('change_since_first'))}"
        )
    if args.send:
        response = send_feishu(feishu_card(start, end, output_path, daily_summary, samples))
        print(f"sent Feishu weekly report: {response}")


if __name__ == "__main__":
    main()
