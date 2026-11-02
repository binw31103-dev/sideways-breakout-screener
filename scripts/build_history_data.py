#!/usr/bin/env python3
"""Build front-end daily history data from saved daily screening outputs."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DAILY_ROOT = ROOT / "output" / "daily"
OUTPUT = ROOT / "src" / "data" / "daily-history.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pct_change(current: float, base: float) -> float:
    return round((current / base - 1) * 100, 2) if base else 0


def compact_item(item: dict[str, Any], model_key: str) -> dict[str, Any]:
    tracking = item.get("tracking") or {}
    first_close = float(tracking.get("firstClose") or item.get("close") or 0)
    close = float(item.get("close") or 0)
    sector = item.get("sector") or {}
    return {
        "key": f"{model_key}:{item.get('code')}",
        "model": model_key,
        "code": str(item.get("code") or ""),
        "name": str(item.get("name") or ""),
        "industry": str(item.get("industry") or ""),
        "date": str(item.get("date") or ""),
        "state": str(item.get("state") or ""),
        "close": round(close, 2),
        "firstSelectedDate": str(tracking.get("firstSelectedDate") or item.get("date") or ""),
        "firstClose": round(first_close, 2),
        "changeSinceFirst": pct_change(close, first_close),
        "selectedCount": int(tracking.get("selectedCount") or 1),
        "riseYearLow": round(float(item.get("riseYearLow") or 0), 1),
        "change20": round(float(item.get("change20") or 0), 1),
        "dailyRsi": round(float(item.get("dailyRsi") or 0), 1),
        "weeklyRsi": round(float(item.get("weeklyRsi") or 0), 1),
        "range20": round(float(item.get("range20") or 0), 1),
        "volumeRatio5v20": round(float(item.get("volumeRatio5v20") or 0), 2),
        "sectorState": str((item.get("conditionChecks") or {}).get("sector") or "待核"),
        "sectorLeader": str(sector.get("leader") or "待核"),
        "sectorLeaderGain": round(float(sector.get("leaderGain") or 0), 1),
        "financialState": str(item.get("financialState") or "待核"),
        "riskState": str(item.get("riskState") or "待核"),
    }


def build_day(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    date = path.parent.name
    v26_items = [compact_item(item, "v26") for item in (payload.get("v26") or {}).get("selected", [])]
    v13_items = [compact_item(item, "v13") for item in (payload.get("v13") or {}).get("selected", [])]
    items = v26_items + v13_items
    avg_change = round(sum(item["changeSinceFirst"] for item in items) / len(items), 2) if items else 0
    return {
        "date": date,
        "generatedAt": payload.get("generatedAt"),
        "dataThrough": payload.get("dataThrough") or date,
        "counts": {
            "total": len(items),
            "v26": len(v26_items),
            "v13": len(v13_items),
            "positive": sum(1 for item in items if item["changeSinceFirst"] > 0),
            "financialPass": sum(1 for item in items if item["financialState"] == "通过"),
        },
        "averageChangeSinceFirst": avg_change,
        "items": items,
    }


def main() -> None:
    daily_files = sorted(DAILY_ROOT.glob("20*/combined.json"))
    days = [build_day(path) for path in daily_files]
    all_items = [item for day in days for item in day["items"]]
    payload = {
        "generatedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "dateRange": {
            "start": days[0]["date"] if days else "",
            "end": days[-1]["date"] if days else "",
        },
        "days": days,
        "summary": {
            "dayCount": len(days),
            "recordCount": len(all_items),
            "uniqueStockCount": len({item["code"] for item in all_items}),
            "positiveRecordCount": sum(1 for item in all_items if item["changeSinceFirst"] > 0),
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT} with {len(days)} days and {len(all_items)} records")


if __name__ == "__main__":
    main()
