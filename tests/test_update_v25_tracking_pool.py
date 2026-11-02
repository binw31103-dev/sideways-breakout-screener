from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from update_v25_tracking_pool import classify, has_recent_strict  # noqa: E402


class V25TrackingCaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(
            (ROOT / "output" / "tdx-selection-2026-07-29-intraday.json").read_text(
                encoding="utf-8"
            )
        )
        cls.items = {item["code"]: item for item in payload["results"]}

    def test_expected_strict_and_right_edge_states(self) -> None:
        expected = {
            "688128": "当前严格",
            "000420": "红框右沿",
            "002085": "红框右沿",
            "002312": "红框右沿",
        }
        for code, state in expected.items():
            with self.subTest(code=code):
                self.assertEqual(classify(self.items[code], recent_strict=True)[0], state)

    def test_clear_edge_exits_are_not_kept_in_right_edge(self) -> None:
        for code in ("002683", "002801", "300775"):
            with self.subTest(code=code):
                self.assertEqual(classify(self.items[code], recent_strict=True)[0], "启动确认")

    def test_missing_market_cap_snapshot_is_data_pending(self) -> None:
        self.assertEqual(
            classify(self.items["002985"], recent_strict=True)[0],
            "数据待复核",
        )

    def test_right_edge_cannot_be_a_fresh_entry(self) -> None:
        state, reasons = classify(self.items["000420"], recent_strict=False)
        self.assertEqual(state, "未登记触发")
        self.assertTrue(reasons)

    def test_trigger_remains_valid_through_third_following_day(self) -> None:
        record = {
            "lastStrictDate": "2026-07-28",
            "trackingDates": [
                "2026-07-28",
                "2026-07-29",
                "2026-07-30",
                "2026-07-31",
            ],
        }
        self.assertTrue(has_recent_strict(record, self.items["000420"]))
        record["trackingDates"].append("2026-08-03")
        self.assertFalse(has_recent_strict(record, self.items["000420"]))


if __name__ == "__main__":
    unittest.main()
