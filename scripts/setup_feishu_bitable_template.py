#!/usr/bin/env python3
"""Create/update Feishu Bitable fields for the daily stock-screen sync."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import sync_feishu_bitable as sync


TEXT = 1
NUMBER = 2


def field_type(name: str) -> int:
    return NUMBER if name in sync.NUMBER_FIELDS else TEXT


def field_defs(fields: list[str]) -> list[dict[str, Any]]:
    return [{"field_name": name, "type": field_type(name)} for name in fields]


def list_tables(app_token: str, token: str) -> dict[str, str]:
    result = sync.request_json("GET", f"/open-apis/bitable/v1/apps/{app_token}/tables", token=token)
    return {
        item["name"]: item["table_id"]
        for item in result.get("data", {}).get("items", [])
    }


def create_table(app_token: str, table_name: str, fields: list[dict[str, Any]], token: str) -> str:
    result = sync.request_json(
        "POST",
        f"/open-apis/bitable/v1/apps/{app_token}/tables",
        token=token,
        body={
            "table": {
                "name": table_name,
                "default_view_name": "默认视图",
                "fields": fields,
            }
        },
    )
    table_id = result.get("data", {}).get("table_id") or result.get("data", {}).get("table", {}).get("table_id")
    if not table_id:
        raise RuntimeError(f"created table but table_id is missing: {result}")
    return table_id


def create_field(app_token: str, table_id: str, field: dict[str, Any], token: str) -> None:
    sync.request_json(
        "POST",
        f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
        token=token,
        body=field,
    )


def rename_table(app_token: str, table_id: str, table_name: str, token: str) -> None:
    sync.request_json(
        "PATCH",
        f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}",
        token=token,
        body={"name": table_name},
    )


def ensure_fields(app_token: str, table_id: str, fields: list[dict[str, Any]], token: str) -> int:
    existing = sync.remote_fields(app_token, table_id, token)
    created = 0
    for field in fields:
        if field["field_name"] in existing:
            continue
        create_field(app_token, table_id, field, token)
        created += 1
        time.sleep(0.1)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(sync.CONFIG_PATH))
    parser.add_argument("--env", default=str(sync.ROOT / ".env"))
    args = parser.parse_args()

    sync.load_dotenv(Path(args.env))
    app_id, app_secret = sync.feishu_credentials()
    if not app_id or not app_secret:
        raise SystemExit("FEISHU_APP_ID/FEISHU_APP_SECRET missing.")

    config_path = Path(args.config)
    config = sync.load_json(config_path, {})
    app_token = config.get("app_token", "")
    if not app_token:
        raise SystemExit(f"app_token missing in {config_path}")

    token = sync.tenant_access_token(app_id, app_secret)
    tables = config.setdefault("tables", {})
    existing_tables = list_tables(app_token, token)

    v26_board = tables.setdefault("01 v2.6统一观察每日票池", {})
    v26_board_table_id = (
        v26_board.get("table_id")
        or existing_tables.get("01 v2.6统一观察每日票池")
        or tables.get("每日入选明细", {}).get("table_id")
        or existing_tables.get("每日入选明细")
        or tables.get("01 每日看板", {}).get("table_id")
        or existing_tables.get("01 每日看板")
    )
    if not sync.configured_table_id(v26_board_table_id):
        v26_board_table_id = create_table(app_token, "01 v2.6统一观察每日票池", field_defs(sync.CLEAN_DAILY_FIELDS), token)
        print(f"[setup] created 01 v2.6统一观察每日票池: {v26_board_table_id}")
    else:
        rename_table(app_token, v26_board_table_id, "01 v2.6统一观察每日票池", token)
        created = ensure_fields(app_token, v26_board_table_id, field_defs(sync.CLEAN_DAILY_FIELDS), token)
        print(f"[setup] updated 01 v2.6统一观察每日票池: {v26_board_table_id}, new_fields={created}")
    v26_board.update({"table_id": v26_board_table_id, "mode": "replace", "key_fields": ["同步主键"]})
    legacy_daily_table_id = tables.get("01 每日看板", {}).get("table_id") or existing_tables.get("01 每日看板")
    if sync.configured_table_id(legacy_daily_table_id) and legacy_daily_table_id != v26_board_table_id:
        rename_table(app_token, legacy_daily_table_id, "99 旧版每日看板（停用）", token)
    tables.pop("01 每日看板", None)
    tables.pop("每日入选明细", None)

    clean_performance = tables.setdefault("03 表现看板", {})
    clean_performance_table_id = (
        clean_performance.get("table_id")
        or existing_tables.get("03 表现看板")
        or tables.get("02 表现看板", {}).get("table_id")
        or existing_tables.get("02 表现看板")
    )
    if not sync.configured_table_id(clean_performance_table_id):
        clean_performance_table_id = create_table(app_token, "03 表现看板", field_defs(sync.CLEAN_PERFORMANCE_FIELDS), token)
        print(f"[setup] created 03 表现看板: {clean_performance_table_id}")
    else:
        rename_table(app_token, clean_performance_table_id, "03 表现看板", token)
        created = ensure_fields(app_token, clean_performance_table_id, field_defs(sync.CLEAN_PERFORMANCE_FIELDS), token)
        print(f"[setup] updated 03 表现看板: {clean_performance_table_id}, new_fields={created}")
    clean_performance.update({"table_id": clean_performance_table_id, "mode": "replace", "key_fields": ["样本ID"]})
    tables.pop("02 表现看板", None)

    v13_board = tables.setdefault("02 v1.3右侧启动每日票池", {})
    v13_board_table_id = (
        v13_board.get("table_id")
        or existing_tables.get("02 v1.3右侧启动每日票池")
        or tables.get("03 风范模式每日票池", {}).get("table_id")
        or existing_tables.get("03 风范模式每日票池")
    )
    if not sync.configured_table_id(v13_board_table_id):
        v13_board_table_id = create_table(app_token, "02 v1.3右侧启动每日票池", field_defs(sync.V13_BOARD_FIELDS), token)
        print(f"[setup] created 02 v1.3右侧启动每日票池: {v13_board_table_id}")
    else:
        rename_table(app_token, v13_board_table_id, "02 v1.3右侧启动每日票池", token)
        created = ensure_fields(app_token, v13_board_table_id, field_defs(sync.V13_BOARD_FIELDS), token)
        print(f"[setup] updated 02 v1.3右侧启动每日票池: {v13_board_table_id}, new_fields={created}")
    v13_board.update({"table_id": v13_board_table_id, "mode": "replace", "key_fields": ["同步主键"]})
    tables.pop("03 风范模式每日票池", None)

    daily_change = tables.setdefault("04 股票每日涨跌跟踪", {})
    daily_change_table_id = daily_change.get("table_id") or existing_tables.get("04 股票每日涨跌跟踪")
    if not sync.configured_table_id(daily_change_table_id):
        daily_change_table_id = create_table(app_token, "04 股票每日涨跌跟踪", field_defs(sync.DAILY_CHANGE_FIELDS), token)
        print(f"[setup] created 04 股票每日涨跌跟踪: {daily_change_table_id}")
    else:
        created = ensure_fields(app_token, daily_change_table_id, field_defs(sync.DAILY_CHANGE_FIELDS), token)
        print(f"[setup] updated 04 股票每日涨跌跟踪: {daily_change_table_id}, new_fields={created}")
    daily_change.update({"table_id": daily_change_table_id, "mode": "replace", "key_fields": ["同步主键"]})

    legacy_performance_table_id = tables.get("样本表现跟踪", {}).get("table_id") or existing_tables.get("样本表现跟踪")
    if sync.configured_table_id(legacy_performance_table_id):
        rename_table(app_token, legacy_performance_table_id, "99 原始样本表现明细（备用）", token)
        print(f"[setup] renamed 样本表现跟踪 -> 99 原始样本表现明细（备用）: {legacy_performance_table_id}")
    tables.pop("样本表现跟踪", None)

    sync.write_json(config_path, config)
    print(f"[setup] wrote {config_path}")


if __name__ == "__main__":
    main()
