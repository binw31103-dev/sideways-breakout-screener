#!/usr/bin/env python3
"""Revalidate a fixed red-zone watchlist against the current v2.2 conditions."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

from screen_red_zone_5 import (
    analyze,
    apply_manual_reviews,
    enrich_financial_risk,
    fetch_daily_quotes,
    fetch_financials,
    fetch_sector_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CODES = "300012,603855,603093,688128,688569"


def retry(callable_, attempts: int = 3):
    error = None
    for attempt in range(attempts):
        try:
            return callable_()
        except Exception as exc:  # Network sources occasionally fail transiently.
            error = exc
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
    raise error


def change_text(current: dict, previous: dict | None) -> str:
    if previous is None:
        return "无上轮基线"
    if current["date"] == previous["date"]:
        return "与上轮为同一收盘日"
    changes = []
    for label, key, unit in (
        ("距低点", "riseRecentLow", "%"),
        ("日RSI", "dailyRsi", ""),
        ("周RSI", "weeklyRsi", ""),
        ("量比", "volumeRatio5v20", ""),
    ):
        delta = float(current[key]) - float(previous[key])
        changes.append(f"{label}{delta:+.1f}{unit}")
    return "；".join(changes)


def source_text(current_source: str, previous: dict | None) -> str:
    previous_source = str((previous or {}).get("source") or "无")
    if current_source == previous_source:
        return "数据源相同"
    return f"数据源变化：{previous_source} → {current_source}"


def render_report(validated: list[dict], invalid: list[dict], baseline: dict[str, dict]) -> str:
    data_dates = sorted({item["date"] for item in validated})
    lines = [
        "# v2.2 当前5只条件复核",
        "",
        f"生成时间：{dt.datetime.now().astimezone().isoformat(timespec='seconds')}。",
        f"行情数据日：{', '.join(data_dates) if data_dates else '无有效行情'}。",
        "",
        "本次固定验证原观察池5只，不重新选股，不计算分数或排名。",
        "",
        "## 验证结论",
        "",
        "| 股票 | 量化硬条件 | 财务 | 公告风险 | 人工图形 | 与上轮比较 | 当前处理 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in validated:
        manual = item["manualReviewVerdict"]
        current_action = "继续保留" if manual == "通过" else "待确认" if manual == "观察" else manual
        lines.append(
            f"| {item['name']} {item['code']} | 满足 | {item['financialState']} | {item['riskState']} | "
            f"{manual} | {change_text(item, baseline.get(item['code']))}；"
            f"{source_text(item['source'], baseline.get(item['code']))} | {current_action} |"
        )
    for item in invalid:
        reasons = "；".join(item.get("reasons") or ["至少一项硬条件已失效"])
        previous = baseline.get(item["code"])
        lines.append(
            f"| {item['name']} {item['code']} | 不满足 | {item.get('financialState', '待复核')} | "
            f"{item.get('riskState', '待复核')} | {item.get('manualReviewVerdict', '待重新看图')} | "
            f"{reasons}；{source_text(item.get('source', '未知'), previous)} | 移出严格池，转边界观察 |"
        )

    lines.extend([
        "",
        "## 条件依据",
        "",
        "| 股票 | 距低点/低点年龄 | 5/10/20日 | 日/周RSI | MA阶段 | MACD | 平台 | 量能 | 板块拉升标的 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for item in validated:
        platform = "二次确认" if item["secondaryWithContext"] else "平台确认"
        lines.append(
            f"| {item['name']} {item['code']} | {item['riseRecentLow']:.1f}%/{item['lowAge']}日 | "
            f"{item['change5']:+.1f}%/{item['change10']:+.1f}%/{item['change20']:+.1f}% | "
            f"{item['dailyRsi']:.1f}/{item['weeklyRsi']:.1f} | MA15 {item['maDistance15']:+.1f}% / "
            f"MA30 {item['maDistance30']:+.1f}% | {item['dailyMacd']['state']} | {platform}，"
            f"{item['platformEvidenceCount']}/6项 | {item['volumeState']}，5/20={item['volumeRatio5v20']:.2f} | "
            f"{item['sector']['leader']} {item['sector']['leaderGain']:+.2f}% |"
        )

    lines.extend([
        "",
        "## 风险复核",
        "",
    ])
    for item in validated + invalid:
        if "financialRisk" not in item:
            continue
        financial = item["financialRisk"]
        manual_reason = (item.get("manualReviewReason") or "待重新看图确认").rstrip("。；")
        lines.extend([
            f"### {item['name']} {item['code']}",
            "",
            f"- 财务（{item['financialState']}）：{'；'.join(financial['financialNotes'])}。",
            f"- 公告风险（{item['riskState']}）：{'；'.join(financial['riskNotes'])}。",
            f"- 普通公司事项：{'；'.join(financial.get('eventNotes') or ['无'])}。",
            f"- 人工结论（{item.get('manualReviewVerdict', '待重新看图')}）："
            f"{manual_reason}。",
            "",
        ])
    lines.extend([
        "## 数据边界",
        "",
        "- 公告风险仍是最近100条公告标题关键词扫描，命中不等于风险已经成立。",
        "- 若行情数据日与上轮相同，本次只能证明条件计算和数据一致，不能代表出现了新的市场验证。",
        "- 本文件只用于观察池研究，不构成买卖建议。",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", default=DEFAULT_CODES)
    parser.add_argument("--baseline", type=Path, default=ROOT / "output" / "red-zone-v2.2-candidates.json")
    parser.add_argument("--manual-review", type=Path, default=ROOT / "output" / "red-zone-v2.1-manual-review.json")
    parser.add_argument("--output", type=Path, default=ROOT / "v2.2当前5只条件复核.md")
    parser.add_argument("--json-output", type=Path, default=ROOT / "output" / "red-zone-v2.2-validation.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    codes = [code.strip() for code in args.codes.split(",") if code.strip()]
    baseline_payload = json.loads(args.baseline.read_text(encoding="utf-8"))
    baseline = {item["code"]: item for item in baseline_payload["allCandidates"]}

    financials = retry(fetch_financials)
    snapshots = retry(fetch_sector_snapshot)
    quotes = retry(lambda: fetch_daily_quotes(financials.keys()))

    validated = []
    invalid = []
    failures = []
    for code in codes:
        financial = financials.get(code)
        if financial is None:
            previous = baseline.get(code, {})
            invalid.append({
                "code": code,
                "name": previous.get("name", code),
                "reasons": ["当前盈利基础池中缺失"],
            })
            continue
        try:
            diagnostics = []
            diagnostic_context = {}
            candidate = analyze(code, financial, snapshots, quotes, diagnostics, diagnostic_context)
            if candidate is None:
                previous = dict(baseline.get(code) or {})
                previous.update({
                    "code": code,
                    "name": financial.get("SECURITY_NAME_ABBR", code),
                    "source": diagnostic_context.get("source", "未知"),
                    "reasons": diagnostics or ["未知条件"],
                })
                try:
                    previous = enrich_financial_risk(previous)
                except Exception as exc:
                    failures.append({"code": code, "error": f"invalid-financial-risk: {exc}"})
                invalid.append(previous)
                continue
            candidate = enrich_financial_risk(candidate)
            if candidate["financialState"] == "不通过" or candidate["riskState"] == "不通过":
                invalid.append({
                    "code": code,
                    "name": candidate["name"],
                    "reasons": ["财务或风险开关不通过"],
                })
                continue
            validated.append(candidate)
        except Exception as exc:
            failures.append({"code": code, "error": str(exc)})

    apply_manual_reviews(validated, args.manual_review)
    for item in validated:
        previous = baseline.get(item["code"])
        if previous and previous["date"] != item["date"]:
            item["manualReviewVerdict"] = "待重新看图"
            item["manualReviewReason"] = "行情数据日已变化，需要按新图重新确认"

    args.output.write_text(render_report(validated, invalid, baseline), encoding="utf-8")
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(
            {
                "generatedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "selected": validated,
                "allCandidates": validated,
                "invalid": invalid,
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"validated={len(validated)} invalid={len(invalid)} failures={len(failures)}")
    for item in validated:
        print(item["code"], item["name"], item["date"], item["financialState"], item["riskState"], item["manualReviewVerdict"])


if __name__ == "__main__":
    main()
