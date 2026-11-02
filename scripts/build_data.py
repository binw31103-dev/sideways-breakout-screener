#!/usr/bin/env python3
"""Build dashboard data from research reports and current A-share quotes.

This script produces a research/watchlist dataset only. It does not create
buy/sell instructions, position advice, or automated trading actions.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import ssl
import subprocess
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "data" / "stock-data.json"
CTX = ssl._create_unverified_context()
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}

REPORTS = [
    {
        "id": "market-baseline",
        "version": "样本基线",
        "file": "当前候选样本.md",
        "date": "2026-07-24",
        "family": "板块强度与反向样本",
        "summary": "先识别已拉升标的，建立低位观察池的排除边界。",
    },
    {
        "id": "round-1",
        "version": "第一轮",
        "file": "准备布局观察池-第一轮.md",
        "date": "2026-07-24",
        "family": "准备布局观察",
        "summary": "板块已有拉升标的，个股仍未明显补涨。",
    },
    {
        "id": "round-2",
        "version": "第二轮",
        "file": "准备布局观察池-RSI优化第二轮.md",
        "date": "2026-07-26",
        "family": "RSI优化",
        "summary": "加入周 RSI 当前值与 4 周、8 周趋势判断。",
    },
    {
        "id": "round-3",
        "version": "第三轮",
        "file": "低位低RSI观察池-第三轮.md",
        "date": "2026-07-26",
        "family": "低位低RSI",
        "summary": "寻找价格和周 RSI 同处低位的左侧研究样本。",
    },
    {
        "id": "round-4",
        "version": "第四轮",
        "file": "低位低RSI-MACD水下金叉观察池-第四轮.md",
        "date": "2026-07-26",
        "family": "RSI与MACD协同",
        "summary": "区分周 MACD 水下金叉、接近金叉和绿柱改善。",
    },
    {
        "id": "round-5",
        "version": "第五轮",
        "file": "低位低RSI-MACD水下改善观察池-第五轮.md",
        "date": "2026-07-26",
        "family": "低位动能改善",
        "summary": "低位、低 RSI、MACD 水下改善并结合板块活跃。",
    },
    {
        "id": "round-6",
        "version": "第六轮 / v1.3",
        "file": "图形规则优化观察池-第六轮.md",
        "date": "2026-07-26",
        "family": "图形确认",
        "summary": "增加 MA15/30 与二次确认，强调日线结构质量。",
    },
    {
        "id": "round-7",
        "version": "第七轮 / v1.4",
        "file": "未站回15-30日线左侧观察池-第七轮.md",
        "date": "2026-07-26",
        "family": "未站回15/30左侧",
        "summary": "更早、更低但确认不足的左侧预备层。",
    },
    {
        "id": "round-8",
        "version": "第八轮 / v1.6",
        "file": "v1.3口径扩展观察池-第八轮.md",
        "date": "2026-07-27",
        "family": "v1.3扩展",
        "summary": "跨行业扩展 MA15/30 图形确认样本。",
    },
    {
        "id": "round-9",
        "version": "第九轮 / v1.7",
        "file": "站上5-10日线早期修复观察池-第九轮.md",
        "date": "2026-07-27",
        "family": "5/10早期修复",
        "summary": "用 MA5/10 捕捉更早的日线修复阶段。",
    },
    {
        "id": "round-10",
        "version": "第十轮 / v1.8",
        "file": "站上5-10日线盈利过滤观察池-第十轮.md",
        "date": "2026-07-27",
        "family": "盈利过滤扩展",
        "summary": "增加归母净利润为正的硬开关并扩展样本。",
    },
]


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    raw = urllib.request.urlopen(req, timeout=20, context=CTX).read().decode("utf-8")
    return json.loads(raw.lstrip("\ufeff"))


def get_json_with_curl(url: str) -> dict:
    result = subprocess.run(
        ["curl", "-sS", "--max-time", "20", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout.lstrip("\ufeff"))


def fetch_financials() -> dict[str, dict]:
    records: dict[str, dict] = {}
    page = 1
    while True:
        params = {
            "reportName": "RPT_LICO_FN_CPD",
            "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,REPORTDATE,QDATE,PARENT_NETPROFIT,TOTAL_OPERATE_INCOME,BOARD_NAME,SECUCODE",
            "filter": '(ISNEW="1")',
            "pageNumber": page,
            "pageSize": 500,
            "sortColumns": "SECURITY_CODE",
            "sortTypes": "1",
            "source": "WEB",
            "client": "WEB",
        }
        result = get_json(
            "https://datacenter-web.eastmoney.com/api/data/v1/get?"
            + urllib.parse.urlencode(params)
        ).get("result") or {}
        rows = result.get("data") or []
        if not rows:
            break
        for row in rows:
            code = str(row.get("SECURITY_CODE") or "")
            if len(code) == 6:
                records[code] = row
        if page >= int(result.get("pages") or page):
            break
        page += 1
    return records


def market_symbol(code: str) -> str:
    return ("sh" if code.startswith("6") else "sz") + code


def fetch_kline(code: str) -> list[dict]:
    symbol = market_symbol(code)
    end_date = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
        f"param={symbol},day,2023-01-01,{end_date},900,qfq"
    )
    try:
        raw = urllib.request.urlopen(url, timeout=20, context=CTX).read().decode("utf-8")
        data = json.loads(raw)
        node = data.get("data", {}).get(symbol) or {}
        source = node.get("qfqday") or node.get("day") or []
        if source:
            return [
                {
                    "date": row[0],
                    "open": float(row[1]),
                    "close": float(row[2]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "volume": float(row[5]),
                }
                for row in source
            ]
    except Exception:
        pass

    fallback_url = (
        "https://quotes.sina.cn/cn/api/openapi.php/"
        "CN_MarketDataService.getKLineData?"
        f"symbol={symbol}&scale=240&ma=no&datalen=1023"
    )
    fallback = get_json_with_curl(fallback_url)
    source = (fallback.get("result") or {}).get("data") or []
    return [
        {
            "date": row["day"],
            "open": float(row["open"]),
            "close": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": float(row["volume"]),
        }
        for row in source
    ]


def ema(values: list[float], period: int) -> list[float]:
    factor = 2 / (period + 1)
    current = values[0]
    result = []
    for value in values:
        current = value if not result else value * factor + current * (1 - factor)
        result.append(current)
    return result


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    gains: list[float] = []
    losses: list[float] = []
    avg_gain = avg_loss = None
    for index in range(1, len(values)):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
        if index < period:
            continue
        if index == period:
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
        else:
            assert avg_gain is not None and avg_loss is not None
            avg_gain = (avg_gain * (period - 1) + gains[-1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[-1]) / period
        output[index] = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return output


def weekly(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in rows:
        date_value = dt.date.fromisoformat(row["date"])
        year, week, _ = date_value.isocalendar()
        groups[(year, week)].append(row)
    return [
        {
            "date": values[-1]["date"],
            "close": values[-1]["close"],
            "high": max(item["high"] for item in values),
            "low": min(item["low"] for item in values),
        }
        for _, values in sorted(groups.items())
    ]


def macd_status(values: list[float]) -> str:
    fast = ema(values, 12)
    slow = ema(values, 26)
    dif = [a - b for a, b in zip(fast, slow)]
    dea = ema(dif, 9)
    hist = [(a - b) * 2 for a, b in zip(dif, dea)]
    for index in range(max(1, len(dif) - 8), len(dif)):
        if dif[index - 1] < dea[index - 1] and dif[index] >= dea[index] and dif[index] < 0 and dea[index] < 0:
            return "A 水下金叉"
    gap = dif[-1] - dea[-1]
    old_gap = dif[-4] - dea[-4]
    improving = hist[-1] > hist[-4]
    if dif[-1] < 0 and dea[-1] < 0 and dif[-1] < dea[-1] and abs(gap) < abs(old_gap) and improving:
        return "B 水下接近金叉"
    if dif[-1] < 0 and dea[-1] < 0 and improving:
        return "C 绿柱改善"
    if dif[-1] < 0 and dea[-1] < 0:
        return "D 水下弱势"
    return "E 非水下"


def parse_report(report: dict) -> list[dict]:
    text = (ROOT / report["file"]).read_text(encoding="utf-8")
    rows: list[dict] = []
    header: list[str] | None = None
    for line in text.splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not header and "股票" in cells:
            header = cells
            continue
        if not header or all(re.fullmatch(r"[-: ]+", cell or "-") for cell in cells):
            continue
        match = re.search(r"(.+?)\s+(\d{6})", cells[0])
        if not match:
            continue
        mapped = {header[index]: cells[index] for index in range(min(len(header), len(cells)))}
        data_date = mapped.get("最新交易日") or mapped.get("最新日期") or report["date"]
        rows.append(
            {
                "code": match.group(2),
                "name": match.group(1).strip(),
                "direction": mapped.get("方向") or mapped.get("行业") or "待分类",
                "date": report["date"],
                "dataDate": data_date,
                "label": mapped.get("初步定位")
                or mapped.get("池子类型")
                or mapped.get("初步结论")
                or mapped.get("第一轮分类")
                or report["family"],
                "reportId": report["id"],
                "reportVersion": report["version"],
                "reportFile": report["file"],
            }
        )
    deduped = {}
    for row in rows:
        deduped[row["code"]] = row
    return list(deduped.values())


def pick_initial_row(rows: list[dict], date_value: str) -> dict:
    eligible = [row for row in rows if row["date"] <= date_value]
    return eligible[-1] if eligible else rows[0]


def classify_current(metrics: dict) -> str:
    if metrics["riseFromYearLow"] > 35 or metrics["weeklyRsi"] > 58:
        return "板块强度样本"
    if metrics["above15"] and metrics["above30"] and metrics["macdClass"].startswith(("A", "B")):
        return "图形确认"
    if metrics["above5"] and metrics["above10"]:
        return "5/10早期修复"
    if metrics["weeklyRsi"] <= 40:
        return "低位低RSI潜伏"
    return "弱观察"


def sector_state(direction: str) -> str:
    if any(word in direction for word in ["电网", "电力设备", "特高压", "智能电表", "输电", "电力数字化"]):
        return "通过"
    if any(word in direction for word in ["算力", "信创", "通信", "软件", "数据", "AI", "医疗", "军工", "装备"]):
        return "观察"
    return "待验证"


def make_reasons(metrics: dict, first: dict) -> list[str]:
    reasons = [f"首次按“{first['label']}”纳入研究"]
    if metrics["riseFromYearLow"] <= 25:
        reasons.append(f"距近一年低点 {metrics['riseFromYearLow']:.1f}%，仍在低位容忍区")
    if 30 <= metrics["weeklyRsi"] <= 45:
        reasons.append(f"周 RSI {metrics['weeklyRsi']:.1f}，处于低位修复区")
    if metrics["macdClass"].startswith(("A", "B")):
        reasons.append(f"周 MACD 为{metrics['macdClass']}，动能接近或完成拐点")
    if metrics["above5"] and metrics["above10"]:
        reasons.append("当前收盘仍在 MA5/MA10 上方")
    return reasons[:4]


def make_risks(metrics: dict, financial: dict) -> list[str]:
    risks = []
    if metrics["riseFromYearLow"] > 35:
        risks.append("已明显离开近一年低点，不再属于低位核心样本")
    if metrics["weeklyRsi"] < 30:
        risks.append("周 RSI 仍处超弱区，存在继续探底风险")
    if not metrics["above15"] or not metrics["above30"]:
        risks.append("尚未完整收复 MA15/MA30，图形确认不足")
    if metrics["macdClass"].startswith("D"):
        risks.append("周 MACD 水下弱势，动能修复尚未成立")
    profit = financial.get("PARENT_NETPROFIT")
    if profit is None:
        risks.append("最新归母净利润数据缺失，财务开关待复核")
    elif profit <= 0:
        risks.append("最新归母净利润为负，不通过盈利过滤")
    elif profit < 50_000_000:
        risks.append("归母净利润为正但金额较小，需继续核对扣非与现金流")
    if not risks:
        risks.append("仍需核对扣非净利、现金流、质押、减持与监管事项")
    return risks[:3]


def observation_action(metrics: dict) -> str:
    if metrics["riseFromYearLow"] > 35 or metrics["weeklyRsi"] > 58:
        return "转入板块强度跟踪，观察回踩后是否形成新的稳定平台。"
    if metrics["above15"] and metrics["above30"]:
        return "观察站回 MA15/30 后的回踩是否缩量、结构是否保持。"
    if metrics["above5"] and metrics["above10"]:
        return "观察能否从 MA5/10 早期修复升级为 MA15/30 图形确认。"
    return "观察是否止跌横盘并重新收复 MA5/10，当前只保留弱跟踪。"


def main() -> None:
    appearances: dict[str, list[dict]] = defaultdict(list)
    report_payload = []
    for report in REPORTS:
        selections = parse_report(report)
        report_payload.append({**report, "selections": [item["code"] for item in selections]})
        for selection in selections:
            appearances[selection["code"]].append(selection)

    financials = fetch_financials()
    stocks = []
    failures = []
    for code, history in appearances.items():
        history.sort(key=lambda item: (item["date"], item["reportId"]))
        first = history[0]
        try:
            rows = fetch_kline(code)
            if len(rows) < 160:
                raise ValueError("insufficient kline rows")
            initial = pick_initial_row(rows, first["date"])
            current = rows[-1]
            closes = [row["close"] for row in rows]
            weekly_rows = weekly(rows)
            weekly_closes = [row["close"] for row in weekly_rows]
            weekly_rsi = rsi(weekly_closes)[-1]
            daily_rsi = rsi(closes)[-1]
            if weekly_rsi is None or daily_rsi is None:
                raise ValueError("RSI unavailable")
            ma = {period: sum(closes[-period:]) / period for period in [5, 10, 15, 30, 60, 120]}
            one_year = rows[-250:]
            metrics = {
                "weeklyRsi": round(weekly_rsi, 1),
                "dailyRsi": round(daily_rsi, 1),
                "macdClass": macd_status(weekly_closes),
                "riseFromYearLow": round((current["close"] / min(row["low"] for row in one_year) - 1) * 100, 1),
                "change20d": round((current["close"] / rows[-21]["close"] - 1) * 100, 1),
                "change60d": round((current["close"] / rows[-61]["close"] - 1) * 100, 1),
                "range60d": round((max(row["high"] for row in rows[-60:]) / min(row["low"] for row in rows[-60:]) - 1) * 100, 1),
                "above5": current["close"] >= ma[5],
                "above10": current["close"] >= ma[10],
                "above15": current["close"] >= ma[15],
                "above30": current["close"] >= ma[30],
                "above60": current["close"] >= ma[60],
                "above120": current["close"] >= ma[120],
            }
            financial = financials.get(code, {})
            profit = financial.get("PARENT_NETPROFIT")
            if profit is None:
                financial_state = "待验证"
            elif profit <= 0:
                financial_state = "不通过"
            elif profit < 50_000_000:
                financial_state = "观察"
            else:
                financial_state = "通过"
            performance = round((current["close"] / initial["close"] - 1) * 100, 2)
            current_category = classify_current(metrics)
            stocks.append(
                {
                    "code": code,
                    "name": first["name"],
                    "industry": financial.get("BOARD_NAME") or first["direction"],
                    "direction": first["direction"],
                    "firstSelectedDate": first["date"],
                    "firstSelectedPrice": round(initial["close"], 2),
                    "currentDate": current["date"],
                    "currentPrice": round(current["close"], 2),
                    "performance": performance,
                    "trackedDays": (dt.date.fromisoformat(current["date"]) - dt.date.fromisoformat(first["date"])).days,
                    "firstCategory": first["label"],
                    "currentCategory": current_category,
                    "sectorState": sector_state(first["direction"]),
                    "financialState": financial_state,
                    "parentNetProfit": profit,
                    "profitPeriod": financial.get("QDATE") or "待更新",
                    "metrics": metrics,
                    "reasons": make_reasons(metrics, first),
                    "risks": make_risks(metrics, financial),
                    "action": observation_action(metrics),
                    "appearances": history,
                    "sparkline": [
                        {"date": row["date"], "close": round(row["close"], 2)}
                        for row in rows[-80:]
                    ],
                }
            )
        except Exception as exc:  # keep partial output useful when one quote fails
            failures.append({"code": code, "name": first["name"], "error": str(exc)})

    stocks.sort(key=lambda item: (item["firstSelectedDate"], item["code"]))
    stock_map = {item["code"]: item for item in stocks}
    for report in report_payload:
        cohort = [stock_map[code] for code in report["selections"] if code in stock_map]
        performances = [item["performance"] for item in cohort]
        report["stats"] = {
            "count": len(cohort),
            "averagePerformance": round(sum(performances) / len(performances), 2) if performances else 0,
            "positiveCount": sum(1 for value in performances if value > 0),
            "strengthCount": sum(1 for item in cohort if item["currentCategory"] == "板块强度样本"),
        }

    latest_date = max((item["currentDate"] for item in stocks), default="")
    payload = {
        "generatedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "asOf": latest_date,
        "methodologyVersion": "v1.8-dashboard",
        "disclaimer": "本页面用于选票框架研究与观察池跟踪，不构成个股推荐、买卖建议或交易指令。",
        "reports": report_payload,
        "stocks": stocks,
        "failures": failures,
        "sources": [
            "项目内各轮 Markdown 选股报告",
            "腾讯前复权日 K 线；不可用时回退到新浪日 K 线",
            "东方财富最新主要财务指标",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT} with {len(stocks)} stocks; failures={len(failures)}")


if __name__ == "__main__":
    main()
