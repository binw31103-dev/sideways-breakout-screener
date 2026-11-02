#!/usr/bin/env python3
"""Does broad-index volume (缩量/放量) tell us anything for v1.3 / v2.6?

Pre-registered on 2026-10-23 before looking at any result. Do not tune the thresholds
after seeing the output.

Volume = index daily volume (shares) from Sina, for CSI 1000 (our stocks' size) and
SSE + SZSE composite (whole market). Shares, not turnover: fine for 5/20/60-day ratios.

Q1  Level: VR = 5-day mean volume / 60-day mean volume on the signal day.
    缩量 VR < 0.8 · 常态 0.8–1.2 · 放量 VR > 1.2.
Q2  Q1 crossed with the existing switch (CSI 1000 below MA120 = 弱势).
Q3  Event days, today-like: day volume / previous 20-day mean >= 1.2 and
    放量大涨 day return >= +1.5% · 放量大跌 day return <= -1.5% ·
    放量探底回升 low <= prev close -2% and close >= prev close +1% (today 2026-10-23).
    Measured as forward CSI 1000 returns, and as signals in the 5 trading days after.

Pass mark per bucket (same as combo_v13_v26): excess > 0 in 2023-07~2024-12 and
2025-01~2026-06, > 0 after dropping the best 3 months, positive months > 50%.
A volume rule is only "useful" if the bucket ordering is the same in both periods.

Usage: python3 scripts/research/index_volume_regime.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "research"))

from backtest_bottom_base import (  # noqa: E402
    HEADER, PERIODS, _curl_json, annotate_market, benchmark_index, row, stats, v26,
)
from combo_v13_v26 import load_v13, pick, verdict  # noqa: E402

BACKTEST = ROOT / "output" / "backtest"
SINA = ("https://quotes.sina.cn/cn/api/openapi.php/CN_MarketDataService.getKLineData?"
        "symbol={}&scale=240&ma=no&datalen=1023")


def sina_bars(symbol: str) -> dict[str, dict]:
    data = ((_curl_json(SINA.format(symbol)) or {}).get("result") or {}).get("data") or []
    if not data:
        raise RuntimeError(f"Sina {symbol} unavailable")
    return {r["day"]: {k: float(r[k]) for k in ("open", "high", "low", "close", "volume")} for r in data}


def market_bars() -> dict[str, dict]:
    sh, sz = sina_bars("sh000001"), sina_bars("sz399001")
    return {d: {**sh[d], "volume": sh[d]["volume"] + sz[d]["volume"]} for d in sh if d in sz}


def features(bars: dict[str, dict]) -> dict[str, dict]:
    dates = sorted(bars)
    vol = [bars[d]["volume"] for d in dates]
    out = {}
    for k in range(60, len(dates)):
        d, prev = dates[k], bars[dates[k - 1]]
        b = bars[d]
        vr = statistics.mean(vol[k - 4:k + 1]) / statistics.mean(vol[k - 59:k + 1])
        day_vr = vol[k] / statistics.mean(vol[k - 20:k])
        ret = b["close"] / prev["close"] - 1
        event = None
        if day_vr >= 1.2:
            if b["low"] <= prev["close"] * 0.98 and ret >= 0.01:
                event = "放量探底回升"
            elif ret >= 0.015:
                event = "放量大涨"
            elif ret <= -0.015:
                event = "放量大跌"
        out[d] = {"vr": vr, "dayVr": day_vr, "ret": ret, "event": event,
                  "level": "缩量" if vr < 0.8 else "放量" if vr > 1.2 else "常态"}
    return out


def forward(close: dict[str, float], date: str, n: int) -> float | None:
    dates = sorted(close)
    k = dates.index(date)
    return close[dates[k + n]] / close[date] - 1 if k + n < len(dates) else None


def main() -> None:
    keep = lambda s: s["date"] >= "2023-07-01" and not s["date"].startswith("2024-09")  # noqa: E731
    index = benchmark_index()
    v26_all = [s for s in json.loads((BACKTEST / "signals.json").read_text(encoding="utf-8")) if keep(s) and v26(s)]
    v13_all = [s for s in load_v13(False) if keep(s)]
    annotate_market(v26_all, index)
    annotate_market(v13_all, index)

    csi = sina_bars("sh000852")
    feats = {"中证1000": features(csi), "沪深两市": features(market_bars())}
    close = {d: b["close"] for d, b in csi.items()}
    dates = sorted(close)
    today = dates[-1]
    lines = ["# 宽基缩量/放量对策略的影响（预先登记，2026-10-23）", "",
             "口径见 `scripts/research/index_volume_regime.py` 文件头。信号 2023-07 起、剔除 2024-09；基准中证1000；"
             "v1.3 用全部信号（未加盈利过滤）。", ""]

    lines += ["## 今天的量能位置", "", "| 指数 | 当日涨跌 | 当日量/前20日均量 | 5日/60日均量 | 档位 | 事件 | 5/60量比历史分位 |",
              "| --- | ---: | ---: | ---: | --- | --- | ---: |"]
    for name, f in feats.items():
        t = f[today]
        pct = sum(x["vr"] <= t["vr"] for x in f.values()) / len(f)
        lines.append(f"| {name} | {t['ret']:+.2%} | {t['dayVr']:.2f} | {t['vr']:.2f} | {t['level']} | {t['event'] or '-'} | {pct:.0%} |")

    # Index base rates: forward CSI 1000 returns after each state (overlapping windows).
    lines += ["", "## 指数自身：之后 5/10/20 日中证1000涨跌（2022-11 起，窗口重叠，仅作参考）", "",
              "| 口径 | 状态 | 天数 | 5日 | 10日 | 20日 | 20日上涨占比 |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, f in feats.items():
        groups: dict[str, list[str]] = {}
        for d, x in f.items():
            groups.setdefault(x["level"], []).append(d)
            if x["event"]:
                groups.setdefault(x["event"], []).append(d)
        for state in ("缩量", "常态", "放量", "放量大涨", "放量大跌", "放量探底回升"):
            ds = [d for d in groups.get(state, []) if d in close]
            cells = []
            for n in (5, 10, 20):
                v = [r for r in (forward(close, d, n) for d in ds) if r is not None]
                cells.append(f"{statistics.mean(v):+.1%}" if v else "")
            v20 = [r for r in (forward(close, d, 20) for d in ds) if r is not None]
            up = f"{sum(r > 0 for r in v20) / len(v20):.0%}" if v20 else ""
            lines.append(f"| {name} | {state} | {len(ds)} | {' | '.join(cells)} | {up} |")
        lines.append(f"| {name} | 全部 | {len(f)} | | | | |")

    # Strategy: tag every signal with the state on its signal day and in the 5 days before.
    pos = {d: k for k, d in enumerate(dates)}
    for s in v13_all + v26_all:
        k = pos.get(s["date"])
        for name, f in feats.items():
            x = f.get(s["date"])
            s[name] = x["level"] if x else None
            recent = [f.get(dates[j], {}).get("event") for j in range(max(0, k - 4), k + 1)] if k is not None else []
            s[name + "事件"] = {e for e in recent if e}
        s["weak"] = bool(s.get("m") and s["m"]["belowMa120"])

    for exit_name, label in (("hold10", "持有10日"), ("stop40", "40日+止损")):
        for model, items in (("v1.3", v13_all), ("v2.6", v26_all)):
            variants = {f"{model} 全部": lambda s: True}
            for name in feats:
                for lv in ("缩量", "常态", "放量"):
                    variants[f"{model} {name}{lv}"] = lambda s, n=name, lv=lv: s[n] == lv
                for regime, wk in (("弱势", True), ("强势", False)):
                    for lv in ("缩量", "放量"):
                        variants[f"{model} {regime}+{name}{lv}"] = (
                            lambda s, n=name, lv=lv, wk=wk: s["weak"] == wk and s[n] == lv)
                for ev in ("放量大涨", "放量大跌", "放量探底回升"):
                    variants[f"{model} 近5日{name}{ev}"] = lambda s, n=name, ev=ev: ev in s[n + "事件"]
            results = {k: pick(items, p, exit_name, index) for k, p in variants.items()}
            lines += ["", f"## {model} · {label}", "", "| 方案 | 判定 |", "| --- | --- |"]
            lines += [f"| {k} | {verdict(t)} |" for k, t in results.items()]
            for period, test in (("全部（截至最新）", lambda d: True), *PERIODS):
                lines += ["", f"### {model} · {label} · {period}", "", *HEADER]
                lines += [row(k, stats([x for x in t if test(x["date"])])) for k, t in results.items()]
    lines += ["", "局限：成交量为股数；指数数据仅新浪一源（价格已与东财交叉校验于 benchmark_index）；"
              "未扣交易成本；仅当前在市股票。"]
    out = BACKTEST / "index-volume-regime.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
