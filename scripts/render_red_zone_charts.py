#!/usr/bin/env python3
"""Render compact review charts for strict red-zone candidates."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from screen_red_zone_5 import ema, rsi


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "output" / "red-zone-candidates.json"
OUTPUT = ROOT / "output" / "red-zone-review.png"

CARD_W = 640
CARD_H = 590
COLS = 3
MARGIN = 16


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size=size, index=1 if bold and path.endswith(".ttc") else 0)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_13 = font(13)
FONT_14 = font(14)
FONT_17 = font(17, bold=True)


def scale(value: float, low: float, high: float, top: int, bottom: int) -> float:
    if math.isclose(high, low):
        return (top + bottom) / 2
    return bottom - (value - low) / (high - low) * (bottom - top)


def draw_candidate(draw: ImageDraw.ImageDraw, item: dict, left: int, top: int, rank: int) -> None:
    right = left + CARD_W - MARGIN
    bottom = top + CARD_H - MARGIN
    draw.rounded_rectangle((left, top, right, bottom), radius=7, fill="#fbfcfe", outline="#cbd5e1", width=1)

    title = f"{rank:02d}  {item['name']} {item['code']}  {item['industry']}"
    draw.text((left + 12, top + 9), title, fill="#0f172a", font=FONT_17)
    subtitle = (
        f"低点+{item['riseRecentLow']:.1f}% / {item['lowAge']}日  "
        f"RSI 日{item['dailyRsi']:.1f} 周{item['weeklyRsi']:.1f}  "
        f"平台条件{item.get('platformEvidenceCount', item.get('platformScore', 0))}/6  "
        f"量{item.get('volumeState', '待核')}  {item['dailyMacd']['state']}"
    )
    draw.text((left + 12, top + 34), subtitle, fill="#475569", font=FONT_13)

    rows = item["sparkline"][-80:]
    closes = [float(row["close"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    price_top = top + 62
    price_bottom = top + 300
    chart_left = left + 12
    chart_right = right - 12
    price_low = min(lows) * 0.985
    price_high = max(highs) * 1.015
    step = (chart_right - chart_left) / len(rows)
    body_w = max(2, min(5, step * 0.62))

    red_zone_start = chart_left + (len(rows) - 20) * step
    draw.rectangle((red_zone_start, price_top, chart_right, price_bottom), fill="#fff1f2")
    draw.text((red_zone_start + 4, price_top + 3), "当前红框复核20日", fill="#be123c", font=FONT_13)

    for index, row in enumerate(rows):
        x = chart_left + (index + 0.5) * step
        y_high = scale(float(row["high"]), price_low, price_high, price_top, price_bottom)
        y_low = scale(float(row["low"]), price_low, price_high, price_top, price_bottom)
        y_open = scale(float(row["open"]), price_low, price_high, price_top, price_bottom)
        y_close = scale(float(row["close"]), price_low, price_high, price_top, price_bottom)
        color = "#dc2626" if row["close"] >= row["open"] else "#0891b2"
        draw.line((x, y_high, x, y_low), fill=color, width=1)
        draw.rectangle((x - body_w / 2, min(y_open, y_close), x + body_w / 2, max(y_open, y_close) + 1), fill=color)

    ma_colors = {5: "#f59e0b", 10: "#2563eb", 15: "#a855f7", 30: "#ef4444"}
    for period, color in ma_colors.items():
        points = []
        for index in range(period - 1, len(closes)):
            value = sum(closes[index - period + 1:index + 1]) / period
            x = chart_left + (index + 0.5) * step
            y = scale(value, price_low, price_high, price_top, price_bottom)
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=color, width=2)

    low_index = min(range(len(rows)), key=lambda index: rows[index]["low"])
    low_x = chart_left + (low_index + 0.5) * step
    draw.line((low_x, price_top, low_x, price_bottom), fill="#94a3b8", width=1)

    secondary = item.get("secondaryConfirmation") or {}
    for label, date_key, color in (("低1", "firstDate", "#7c3aed"), ("低2", "secondDate", "#db2777")):
        target_date = secondary.get(date_key)
        if not target_date:
            continue
        match = next((index for index, row in enumerate(rows) if row["date"] == target_date), None)
        if match is None:
            continue
        x = chart_left + (match + 0.5) * step
        y = scale(float(rows[match]["low"]), price_low, price_high, price_top, price_bottom)
        draw.line((x, price_top + 20, x, price_bottom), fill=color, width=1)
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)
        draw.text((x + 3, y - 17), label, fill=color, font=FONT_13)

    volumes = [float(row["volume"]) for row in rows]
    volume_top = top + 313
    volume_bottom = top + 370
    volume_high = max(volumes) * 1.08
    for index, row in enumerate(rows):
        x = chart_left + (index + 0.5) * step
        y = scale(float(row["volume"]), 0, volume_high, volume_top, volume_bottom)
        color = "#fca5a5" if row["close"] >= row["open"] else "#67e8f9"
        draw.rectangle((x - body_w / 2, y, x + body_w / 2, volume_bottom), fill=color)
    volume_ma20 = []
    for index in range(19, len(volumes)):
        value = sum(volumes[index - 19:index + 1]) / 20
        x = chart_left + (index + 0.5) * step
        y = scale(value, 0, volume_high, volume_top, volume_bottom)
        volume_ma20.append((x, y))
    if len(volume_ma20) > 1:
        draw.line(volume_ma20, fill="#7c3aed", width=2)
    draw.text(
        (chart_left, volume_top),
        f"VOL 5/20={item.get('volumeRatio5v20', 0):.2f} 中位={item.get('medianVolumeRatio5v20', 0):.2f}",
        fill="#475569",
        font=FONT_13,
    )

    fast = ema(closes, 12)
    slow = ema(closes, 26)
    dif = [a - b for a, b in zip(fast, slow)]
    dea = ema(dif, 9)
    hist = [(a - b) * 2 for a, b in zip(dif, dea)]
    macd_top = top + 383
    macd_bottom = top + 454
    macd_abs = max(max(abs(value) for value in dif + dea + hist), 1e-9)
    zero_y = scale(0, -macd_abs, macd_abs, macd_top, macd_bottom)
    draw.line((chart_left, zero_y, chart_right, zero_y), fill="#cbd5e1", width=1)
    for index, value in enumerate(hist):
        x = chart_left + (index + 0.5) * step
        y = scale(value, -macd_abs, macd_abs, macd_top, macd_bottom)
        color = "#dc2626" if value >= 0 else "#0891b2"
        draw.line((x, zero_y, x, y), fill=color, width=max(1, int(body_w / 2)))
    draw.line(
        [(chart_left + (index + 0.5) * step, scale(value, -macd_abs, macd_abs, macd_top, macd_bottom)) for index, value in enumerate(dif)],
        fill="#111827",
        width=2,
    )
    draw.line(
        [(chart_left + (index + 0.5) * step, scale(value, -macd_abs, macd_abs, macd_top, macd_bottom)) for index, value in enumerate(dea)],
        fill="#eab308",
        width=2,
    )

    rsi_values = rsi(closes)
    rsi_top = top + 468
    rsi_bottom = top + 512
    for level, color in ((30, "#16a34a"), (50, "#94a3b8"), (70, "#dc2626")):
        y = scale(level, 0, 100, rsi_top, rsi_bottom)
        draw.line((chart_left, y, chart_right, y), fill=color, width=1)
    rsi_points = [
        (chart_left + (index + 0.5) * step, scale(float(value), 0, 100, rsi_top, rsi_bottom))
        for index, value in enumerate(rsi_values)
        if value is not None
    ]
    if len(rsi_points) > 1:
        draw.line(rsi_points, fill="#2563eb", width=2)

    sector = item["sector"]
    footer = (
        f"5/10/20日 {item['change5']:+.1f}%/{item['change10']:+.1f}%/{item['change20']:+.1f}%  "
        f"MA15 {item['maDistance15']:+.1f}% MA30 {item['maDistance30']:+.1f}%  站5/10 {item['aboveDays']}日"
    )
    draw.text((left + 12, top + 524), footer, fill="#334155", font=FONT_13)
    precheck = item.get("manualPrecheck") or {}
    pending_count = sum(not bool(value) for value in precheck.values())
    footer2 = (
        f"市值 {item.get('market', {}).get('totalMarketCap', 0) / 100_000_000:.0f}亿  "
        f"20日均额 {item.get('market', {}).get('averageAmount20', 0) / 100_000_000:.2f}亿  "
        f"预检 {'满足' if pending_count == 0 else f'待{pending_count}项'}  "
        f"结论 {item.get('manualReviewVerdict', '待人工复核')}"
    )
    draw.text((left + 12, top + 545), footer2, fill="#334155", font=FONT_13)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    candidates = payload["allCandidates"]
    rows = math.ceil(len(candidates) / COLS)
    image = Image.new("RGB", (CARD_W * COLS, CARD_H * rows), "#e2e8f0")
    draw = ImageDraw.Draw(image)
    for index, item in enumerate(candidates):
        col = index % COLS
        row = index // COLS
        draw_candidate(draw, item, col * CARD_W + MARGIN // 2, row * CARD_H + MARGIN // 2, index + 1)
    image.save(args.output, quality=95)
    print(f"wrote {args.output} ({len(candidates)} charts)")


if __name__ == "__main__":
    main()
