#!/usr/bin/env python3
"""Broad-index 缩量/放量 on its own: what it says about the index's next moves.

Standalone market study, not tied to any stock-picking model. Pre-registered on
2026-10-23 before looking at any result; do not tune thresholds after seeing output.

Data: BaoStock daily bars with turnover (amount), 2005-01 ~ latest, cached in
output/cache/index_long (cross-checked with Sina: closes and volumes identical on the
1023 overlapping days). 两市 = 上证指数 + 深证成指 turnover, priced on 上证指数.
CSI 1000 before its 2014-10 launch is back-filled by the index provider.

Q1  Volume level, 5-day mean turnover / 60-day mean: 缩量 < 0.8 · 常态 · 放量 > 1.2.
Q2  Day type: day turnover / previous 20-day mean >= 1.2 (放量) or <= 0.8 (缩量),
    crossed with day return >= +1% (上涨) or <= -1% (下跌).
Q3  Extremes: 5-day turnover in the bottom 10% (地量) / top 10% (天量) of the past
    250 days (point-in-time percentile).
Q4  Today's pattern 放量探底回升: day ratio >= 1.2, low <= prev close -2%, close >= prev +1%.

Outcome: forward 5/20/60-day index return minus the unconditional mean of the same
period (so a rising market does not make every state look good), and the share of
positive 20-day returns. Days within 20 trading days of a previous qualifying day are
one "episode"; episode count is shown because overlapping windows overstate samples.

A state counts as a real signal only if its 20-day excess has the same sign in all
three periods (2005-2014 / 2015-2019 / 2020-latest) and on at least 4 of 6 indexes.

Usage: python3 scripts/research/index_volume_standalone.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "output" / "cache" / "index_long"
OUT = ROOT / "output" / "backtest" / "index-volume-standalone.md"
INDEXES = {"上证指数": "sh.000001", "沪深300": "sh.000300", "中证500": "sh.000905",
           "中证1000": "sh.000852", "创业板指": "sz.399006"}
PERIODS = (("2005-2014", lambda d: d < "2015"), ("2015-2019", lambda d: "2015" <= d < "2020"),
           ("2020-最新", lambda d: d >= "2020"))
HORIZONS = (5, 20, 60)
STATES = ("缩量", "常态", "放量", "放量上涨", "放量下跌", "缩量上涨", "缩量下跌", "地量", "天量", "放量探底回升")


def load(code: str) -> list[dict]:
    rows = json.loads((CACHE / f"{code}.json").read_text(encoding="utf-8"))["rows"]
    keys = ("date", "open", "high", "low", "close", "volume", "amount")
    out = [dict(zip(keys, [r[0], *map(float, r[1:])])) for r in rows if r[6]]
    return [r for r in out if r["amount"] > 0]


def market() -> list[dict]:
    sh, sz = load("sh.000001"), {r["date"]: r for r in load("sz.399001")}
    return [{**r, "amount": r["amount"] + sz[r["date"]]["amount"]} for r in sh if r["date"] in sz]


def tag(rows: list[dict]) -> list[dict]:
    amt = [r["amount"] for r in rows]
    ma5 = [None] * len(rows)
    for k in range(4, len(rows)):
        ma5[k] = statistics.mean(amt[k - 4:k + 1])
    for k in range(310, len(rows)):
        r, prev = rows[k], rows[k - 1]
        vr = ma5[k] / statistics.mean(amt[k - 59:k + 1])
        day = amt[k] / statistics.mean(amt[k - 20:k])
        ret = r["close"] / prev["close"] - 1
        pct = sum(m <= ma5[k] for m in ma5[k - 249:k + 1]) / 250
        s = {"缩量" if vr < 0.8 else "放量" if vr > 1.2 else "常态"}
        if day >= 1.2 and ret >= 0.01: s.add("放量上涨")
        if day >= 1.2 and ret <= -0.01: s.add("放量下跌")
        if day <= 0.8 and ret >= 0.01: s.add("缩量上涨")
        if day <= 0.8 and ret <= -0.01: s.add("缩量下跌")
        if pct <= 0.10: s.add("地量")
        if pct >= 0.90: s.add("天量")
        if day >= 1.2 and r["low"] <= prev["close"] * 0.98 and ret >= 0.01: s.add("放量探底回升")
        r.update(states=s, vr=vr, day=day, ret=ret, pct=pct)
        for n in HORIZONS:
            r[f"f{n}"] = rows[k + n]["close"] / r["close"] - 1 if k + n < len(rows) else None
    return rows[310:]


def summarize(rows: list[dict], state: str) -> dict:
    out = {}
    for name, test in (("全部", lambda d: True), *PERIODS):
        part = [r for r in rows if test(r["date"])]
        hit = [k for k, r in enumerate(part) if state in r["states"]]
        res = {"days": len(hit), "episodes": sum(1 for a, b in zip([-99] + hit, hit) if b - a > 20)}
        for n in HORIZONS:
            base = [r[f"f{n}"] for r in part if r[f"f{n}"] is not None]
            v = [part[k][f"f{n}"] for k in hit if part[k][f"f{n}"] is not None]
            res[n] = statistics.mean(v) - statistics.mean(base) if v and base else None
        v20 = [part[k]["f20"] for k in hit if part[k]["f20"] is not None]
        base20 = [r["f20"] for r in part if r["f20"] is not None]
        res["up"] = sum(x > 0 for x in v20) / len(v20) if v20 else None
        res["baseUp"] = sum(x > 0 for x in base20) / len(base20) if base20 else None
        out[name] = res
    return out


def pct(x: float | None) -> str:
    return "" if x is None else f"{x:+.1%}"


def main() -> None:
    data = {name: tag(load(code)) for name, code in INDEXES.items()}
    data["两市成交额"] = tag(market())
    lines = ["# 宽基缩量 / 放量的独立研究：对后续指数走势的含义", "",
             "口径见 `scripts/research/index_volume_standalone.py` 文件头（跑数前写定）。"
             "超额 = 该状态之后的指数涨跌 − 同期所有交易日的平均涨跌。", ""]

    lines += ["## 今天", "", "| 指数 | 日期 | 当日涨跌 | 当日额/前20日均额 | 5日/60日均额 | 5日均额250日分位 | 状态 |",
              "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for name, rows in data.items():
        r = rows[-1]
        lines.append(f"| {name} | {r['date']} | {r['ret']:+.2%} | {r['day']:.2f} | {r['vr']:.2f} | {r['pct']:.0%} | "
                     f"{'、'.join(s for s in STATES if s in r['states'])} |")

    verdicts = {}
    for state in STATES:
        lines += ["", f"## {state}", "",
                  "| 指数 | 期间 | 天数 | 独立段数 | 5日超额 | 20日超额 | 60日超额 | 20日上涨占比（基准） |",
                  "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
        signs = []
        for name, rows in data.items():
            s = summarize(rows, state)
            per = [s[p][20] for p, _ in PERIODS]
            if all(x is not None for x in per) and min(s[p]["episodes"] for p, _ in PERIODS) >= 3:
                signs.append(1 if all(x > 0 for x in per) else -1 if all(x < 0 for x in per) else 0)
            for p, v in s.items():
                up = f"{v['up']:.0%}（{v['baseUp']:.0%}）" if v["up"] is not None else ""
                lines.append(f"| {name} | {p} | {v['days']} | {v['episodes']} | {pct(v[5])} | {pct(v[20])} | {pct(v[60])} | {up} |")
        pos, neg = signs.count(1), signs.count(-1)
        verdicts[state] = ("稳定偏多" if pos >= 4 else "稳定偏空" if neg >= 4 else "不稳定") + f"（三段同向：多{pos}/空{neg}/共{len(signs)}个指数）"
    lines[4:4] = ["## 判定（20日超额在三段都同号、且至少4个指数一致）", "", "| 状态 | 判定 |", "| --- | --- |",
                  *[f"| {k} | {v} |" for k, v in verdicts.items()], ""]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
