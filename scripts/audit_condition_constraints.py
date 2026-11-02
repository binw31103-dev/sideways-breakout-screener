#!/usr/bin/env python3
"""Audit v2.2 candidate constraints and market-cap concentration."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import math
from pathlib import Path

from screen_red_zone_5 import fetch_daily_quotes


ROOT = Path(__file__).resolve().parents[1]


def yi(value: float) -> float:
    return value / 100_000_000


def cap_bucket(value: float) -> str:
    value_yi = yi(value)
    if value_yi < 30:
        return "<30亿"
    if value_yi < 50:
        return "30-50亿"
    if value_yi < 100:
        return "50-100亿"
    if value_yi < 300:
        return "100-300亿"
    return ">=300亿"


def render(candidates: list[dict], quotes: dict[str, dict]) -> str:
    enriched = []
    for item in candidates:
        quote = quotes.get(item["code"], {})
        sparkline = item.get("sparkline") or []
        volume_scale = 1.0
        if sparkline and sparkline[-1]["volume"] > 0 and quote.get("volume", 0) > 0:
            observed_ratio = quote["volume"] / sparkline[-1]["volume"]
            volume_scale = min(
                (0.01, 1.0, 100.0),
                key=lambda value: abs(math.log(max(observed_ratio, 1e-9) / value)),
            )
        average_amount20 = (
            sum(row["close"] * row["volume"] * volume_scale for row in sparkline[-20:]) / 20
            if len(sparkline) >= 20
            else 0
        )
        enriched.append({
            **item,
            "totalCap": float(quote.get("totalMarketCap") or 0),
            "floatCap": float(quote.get("floatMarketCap") or 0),
            "amount": float(quote.get("amount") or 0),
            "averageAmount20": average_amount20,
            "turnoverRate": float(quote.get("turnoverRate") or 0),
        })

    cap_counts = collections.Counter(cap_bucket(item["totalCap"]) for item in enriched)
    failure_counts = collections.Counter(
        reason.split("（", 1)[0]
        for item in enriched
        for reason in item.get("failedConditions", [])
    )
    lines = [
        "# v2.2 条件约束与市值偏差审计",
        "",
        f"生成时间：{dt.datetime.now().astimezone().isoformat(timespec='seconds')}。",
        "",
        "本报告审计当前边界候选的市值、流动性和失败条件，不计算分数，也不提供交易建议。",
        "",
        "## 市值分布",
        "",
        "| 总市值区间 | 数量 |",
        "| --- | ---: |",
    ]
    for bucket in ("<30亿", "30-50亿", "50-100亿", "100-300亿", ">=300亿"):
        lines.append(f"| {bucket} | {cap_counts[bucket]} |")

    lines.extend([
        "",
        "## 候选明细",
        "",
        "| 股票 | 行业 | 总市值 | 流通市值 | 20日估算均额 | 当日成交额 | 换手率 | 不满足项 | 财务 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ])
    for item in sorted(enriched, key=lambda row: row["totalCap"]):
        lines.append(
            f"| {item['name']} {item['code']} | {item['industry']} | {yi(item['totalCap']):.1f}亿 | "
            f"{yi(item['floatCap']):.1f}亿 | {yi(item['averageAmount20']):.2f}亿 | "
            f"{yi(item['amount']):.2f}亿 | {item['turnoverRate']:.2f}% | "
            f"{'；'.join(item.get('failedConditions') or ['无'])} | {item['financialState']} |"
        )

    lines.extend([
        "",
        "## 门槛敏感性",
        "",
        "| 条件组合 | 保留数量 |",
        "| --- | ---: |",
    ])
    combinations = (
        ("总市值>=30亿", lambda x: x["totalCap"] >= 3_000_000_000),
        ("总市值>=50亿", lambda x: x["totalCap"] >= 5_000_000_000),
        ("总市值>=80亿", lambda x: x["totalCap"] >= 8_000_000_000),
        ("总市值>=100亿", lambda x: x["totalCap"] >= 10_000_000_000),
        ("总市值>=80亿且流通>=50亿", lambda x: x["totalCap"] >= 8_000_000_000 and x["floatCap"] >= 5_000_000_000),
        ("上项且20日均额>=1亿", lambda x: x["totalCap"] >= 8_000_000_000 and x["floatCap"] >= 5_000_000_000 and x["averageAmount20"] >= 100_000_000),
        ("上项且20日均额>=1.5亿", lambda x: x["totalCap"] >= 8_000_000_000 and x["floatCap"] >= 5_000_000_000 and x["averageAmount20"] >= 150_000_000),
        ("总市值>=50亿、流通>=30亿、20日均额>=0.5亿", lambda x: x["totalCap"] >= 5_000_000_000 and x["floatCap"] >= 3_000_000_000 and x["averageAmount20"] >= 50_000_000),
    )
    for label, predicate in combinations:
        lines.append(f"| {label} | {sum(1 for item in enriched if predicate(item))} |")

    lines.extend([
        "",
        "## 失败条件分布",
        "",
        "| 条件 | 数量 |",
        "| --- | ---: |",
    ])
    for reason, count in failure_counts.most_common():
        lines.append(f"| {reason} | {count} |")

    lines.extend([
        "",
        "## 审计结论",
        "",
        "- 当前模型缺少市值和流动性条件，容易把低成交的小市值股票识别为缩量平台。",
        "- 市值应作为独立分类条件，不参与评分；核心池和弹性池应分开输出。",
        "- RSI边界继续严格判断，但轻微超界只进入边界观察，不修改严格阈值。",
        "- 周MACD协同条件需要区分核心池和更左侧潜伏池，避免把二者混成同一结论。",
        "- 行业启动需要增加领涨标的流动性或板块多股扩散约束，降低小票单点脉冲影响。",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "output" / "red-zone-v2.2-new-boundary-candidates.json",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "v2.2条件约束与市值偏差审计.md")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    quotes = fetch_daily_quotes(item["code"] for item in payload["allCandidates"])
    args.output.write_text(render(payload["allCandidates"], quotes), encoding="utf-8")
    print(f"wrote {args.output} candidates={len(payload['allCandidates'])}")


if __name__ == "__main__":
    main()
