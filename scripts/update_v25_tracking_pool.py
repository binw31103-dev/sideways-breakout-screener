#!/usr/bin/env python3
"""Maintain the v2.5 strict-trigger and right-edge tracking ledger.

The script records state transitions only. It does not rank candidates or
produce trading instructions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FAIL_STATES = {"不满足", "不通过", "剔除"}
STRICT_STATES = {"满足", "严格满足"}


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def payload_date(payload: dict[str, Any]) -> str:
    if payload.get("dataThrough"):
        return str(payload["dataThrough"])
    dates = [str(item.get("date")) for item in payload.get("results", []) if item.get("date")]
    if dates:
        return max(dates)
    generated = str(payload.get("generatedAt") or "")
    return generated[:10]


def is_strict(item: dict[str, Any]) -> bool:
    return (
        item.get("status") in STRICT_STATES
        or item.get("conditionVerdict") == "满足量化条件"
    )


def passed_switch(value: Any) -> bool:
    return value not in FAIL_STATES


def as_number(item: dict[str, Any], key: str) -> float | None:
    value = item.get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def right_edge_checks(item: dict[str, Any]) -> dict[str, bool] | None:
    required = {
        key: as_number(item, key)
        for key in (
            "riseRecentLow",
            "riseYearLow",
            "change5",
            "change10",
            "change20",
            "dailyRsi",
            "weeklyRsi",
            "maDistance15",
            "maDistance30",
            "volumeRatio5v20",
        )
    }
    if any(value is None for value in required.values()):
        return None

    macd = item.get("dailyMacd") or {}
    if not isinstance(macd, dict):
        return None
    platform = bool(item.get("stablePlatform")) or bool(item.get("secondaryWithContext"))
    return {
        "low_position": required["riseRecentLow"] <= 10 and required["riseYearLow"] <= 15,
        "not_launched": (
            required["change5"] <= 8
            and required["change10"] <= 10
            and required["change20"] <= 12
        ),
        "rsi": 28 <= required["dailyRsi"] <= 50 and 24 <= required["weeklyRsi"] <= 45,
        "ma_stage": required["maDistance15"] <= 3 and required["maDistance30"] <= 2,
        "platform": platform,
        "volume": required["volumeRatio5v20"] <= 1,
        "macd": bool(macd.get("underwater")) and bool(macd.get("improving")),
        "financial": passed_switch(item.get("financialState")),
        "risk": passed_switch(item.get("riskState")),
    }


def explicit_breakdown(item: dict[str, Any]) -> bool:
    text = "；".join(item.get("reasons") or item.get("failedConditions") or [])
    return any(token in text for token in ("持续创新低", "平台破位", "严重风险", "退市"))


def explicit_launch(item: dict[str, Any]) -> bool:
    text = "；".join(item.get("reasons") or item.get("failedConditions") or [])
    return any(
        token in text
        for token in ("已经站上MA30", "明显站上MA15", "距低点涨幅", "涨幅超过红框上限")
    )


def classify(item: dict[str, Any], recent_strict: bool) -> tuple[str, list[str]]:
    if is_strict(item):
        return "当前严格", []
    if explicit_breakdown(item):
        return "破位失效", list(item.get("reasons") or item.get("failedConditions") or [])
    checks = right_edge_checks(item)
    if recent_strict and checks is not None and all(checks.values()):
        return "红框右沿", []
    if checks is None:
        if explicit_launch(item):
            return "启动确认", list(item.get("reasons") or item.get("failedConditions") or [])
        return "数据待复核", list(item.get("reasons") or item.get("failedConditions") or [])
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        if "financial" in failed or "risk" in failed:
            return "破位失效", failed
        return "启动确认", failed
    if not recent_strict:
        return "未登记触发", ["最近三次观察中没有严格触发记录"]
    return "数据待复核", []


def update_tracking_dates(record: dict[str, Any], current_date: str) -> None:
    dates = record.setdefault("trackingDates", [])
    if current_date and current_date not in dates:
        dates.append(current_date)
        dates.sort()


def has_recent_strict(
    record: dict[str, Any],
    current_item: dict[str, Any],
    lookback_days: int = 3,
) -> bool:
    if is_strict(current_item):
        return True
    dates = record.get("trackingDates", [])
    eligible_dates = dates[-(lookback_days + 1):]
    return record.get("lastStrictDate") in eligible_dates


def render_report(registry: dict[str, Any], current_date: str) -> str:
    records = list(registry.get("records", {}).values())
    records.sort(key=lambda item: (item.get("state", ""), item.get("code", "")))
    lines = [
        "# v2.5 红框状态跟踪",
        "",
        f"状态日期：{current_date}。",
        "",
        "本报告只维护选股研究状态，不计算评分，不提供交易指令。",
        "",
        "| 股票 | 首次严格触发 | 最近严格触发 | 当前状态 | 已观察日 | 状态依据 |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for item in records:
        reasons = "；".join(item.get("stateReasons") or ["条件满足"])
        lines.append(
            f"| {item.get('name', '')} {item['code']} | {item.get('firstSelectedDate', '')} | "
            f"{item.get('lastStrictDate', '')} | {item.get('state', '')} | "
            f"{len(item.get('trackingDates', []))} | {reasons} |"
        )
    lines.extend([
        "",
        "## 口径",
        "",
        "- 当前严格：当日完整满足严格公式。",
        "- 红框右沿：最近三次观察内曾严格触发，当前仍满足 v2.5 右沿边界。",
        "- 启动确认：已经超过右沿边界，只保留为形态验证样本。",
        "- 数据待复核：关键行情、财务或市值字段缺失，不作满足结论。",
        "- 连续运行本脚本时，以实际记录的不同状态日期计数；满 10 个观察交易日后可以归档。",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-snapshot", type=Path, action="append", required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "output" / "v25-tracking-pool.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "v2.5红框状态跟踪.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.registry.exists():
        registry = load_payload(args.registry)
    else:
        registry = {"version": "2.5", "records": {}}

    records = registry.setdefault("records", {})
    for path in args.strict_snapshot:
        payload = load_payload(path)
        date = payload_date(payload)
        for item in payload.get("results", []):
            if not is_strict(item):
                continue
            code = str(item["code"])
            record = records.setdefault(code, {"code": code, "name": item.get("name", code)})
            record["name"] = item.get("name", record.get("name", code))
            record.setdefault("firstSelectedDate", date)
            record["lastStrictDate"] = max(str(record.get("lastStrictDate") or date), date)
            update_tracking_dates(record, date)

    current = load_payload(args.current)
    current_date = payload_date(current)
    current_items = {str(item["code"]): item for item in current.get("results", [])}
    for code, item in current_items.items():
        if not is_strict(item):
            continue
        record = records.setdefault(code, {"code": code, "name": item.get("name", code)})
        record["name"] = item.get("name", record.get("name", code))
        record.setdefault("firstSelectedDate", current_date)
        record["lastStrictDate"] = current_date
        update_tracking_dates(record, current_date)

    for code, record in records.items():
        item = current_items.get(code)
        if item is None:
            record["state"] = "数据待复核"
            record["stateReasons"] = ["当前快照缺少该股票"]
            continue
        update_tracking_dates(record, current_date)
        recent_strict = has_recent_strict(record, item)
        state, reasons = classify(item, recent_strict)
        if len(record.get("trackingDates", [])) > 10 and state not in {"当前严格", "破位失效"}:
            state = "到期"
            reasons = ["已超过10个实际观察交易日"]
        record["state"] = state
        record["stateDate"] = current_date
        record["stateReasons"] = reasons
        history = record.setdefault("history", [])
        event = {
            "date": current_date,
            "state": state,
            "reasons": reasons,
        }
        if history and history[-1].get("date") == current_date:
            history[-1] = event
        else:
            history.append(event)

    registry["updatedAt"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    registry["dataThrough"] = current_date
    args.registry.parent.mkdir(parents=True, exist_ok=True)
    args.registry.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    args.report.write_text(render_report(registry, current_date), encoding="utf-8")
    print(f"records={len(records)} date={current_date} registry={args.registry} report={args.report}")


if __name__ == "__main__":
    main()
