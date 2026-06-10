import json
import os
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


COURSE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = COURSE_ROOT.parent
DB_PATH = PROJECT_ROOT / "server" / "data" / "eshop.sqlite"
API_BASE = os.environ.get("ESHOP_ETL_API_BASE", "http://192.168.31.47:38173/api/etl").rstrip("/")

DATE_COLUMNS = {
    "dim_date": ["date_id"],
    "dim_user": ["register_date"],
    "dim_campaign": ["start_date", "end_date"],
    "dim_product": ["listing_date"],
    "fact_order": ["order_date"],
    "fact_order_item": ["order_date"],
    "fact_traffic": ["event_date", "created_at"],
    "fact_coupon_use": ["issued_date", "used_date"],
    "fact_refund": ["refund_date"],
    "fact_fulfillment": ["order_date", "shipped_date", "delivered_date"],
    "fact_inventory_movement": ["movement_date", "created_at"],
    "fact_product_review": ["review_date"],
    "fact_ads_spend": ["spend_date"],
    "daily_business_summary": ["summary_date", "date_id"],
}


def _url(path, params=None):
    query = urllib.parse.urlencode(params or {})
    return f"{API_BASE}{path}" + (f"?{query}" if query else "")


def _get_json(path, params=None, timeout=3):
    with urllib.request.urlopen(_url(path, params), timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(resp.read().decode(charset))


def api_status():
    try:
        doc = _get_json("/help", timeout=2)
        return f"online: {doc.get('service', 'etl-api')}"
    except Exception as exc:
        return f"offline, fallback to local SQLite: {type(exc).__name__}"


def connect():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"找不到本地后备数据库: {DB_PATH}")
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def _parse_dates(df, table_name):
    for col in DATE_COLUMNS.get(table_name, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def get_table_catalog():
    try:
        return _get_json("/tables")
    except Exception:
        with connect() as con:
            rows = con.execute(
                "select name from sqlite_master where type in ('table','view') and name not like 'sqlite_%' order by name"
            ).fetchall()
            tables = []
            for (name,) in rows:
                count = con.execute(f'select count(*) from "{name}"').fetchone()[0]
                tables.append({"tableName": name, "recordCount": count, "type": "local", "description": "本地 SQLite 后备表或视图"})
        return {"tables": tables, "total": len(tables)}


def get_schema(table_name):
    try:
        return _get_json(f"/schema/{table_name}")
    except Exception:
        with connect() as con:
            rows = con.execute(f'pragma table_info("{table_name}")').fetchall()
        return {
            "tableName": table_name,
            "columns": [{"name": r[1], "type": r[2], "notNull": bool(r[3]), "defaultValue": r[4], "pk": bool(r[5])} for r in rows],
        }


def load_table(table_name, limit=50000):
    try:
        payload = _get_json(f"/export/{table_name}", {"format": "json", "limit": int(limit)})
        df = pd.DataFrame(payload.get("rows", []))
        return _parse_dates(df, table_name)
    except Exception:
        sql = f'select * from "{table_name}"'
        if limit is not None:
            sql += f" limit {int(limit)}"
        with connect() as con:
            df = pd.read_sql_query(sql, con)
        return _parse_dates(df, table_name)


def query_table(table_name, limit=5000, offset=0, order_by=None, order_dir="asc", **filters):
    params = {"limit": int(limit), "offset": int(offset)}
    if order_by:
        params["orderBy"] = order_by
        params["orderDir"] = order_dir
    params.update({k: v for k, v in filters.items() if v is not None})
    try:
        payload = _get_json(f"/query/{table_name}", params)
        df = pd.DataFrame(payload.get("rows", []))
        return _parse_dates(df, table_name)
    except Exception:
        conditions = []
        values = []
        for key, value in filters.items():
            if value is None:
                continue
            conditions.append(f'"{key}" = ?')
            values.append(value)
        sql = f'select * from "{table_name}"'
        if conditions:
            sql += " where " + " and ".join(conditions)
        if order_by:
            direction = "desc" if str(order_dir).lower() == "desc" else "asc"
            sql += f' order by "{order_by}" {direction}'
        sql += f" limit {int(limit)} offset {int(offset)}"
        with connect() as con:
            df = pd.read_sql_query(sql, con, params=values)
        return _parse_dates(df, table_name)


def get_metrics():
    try:
        return _get_json("/metrics")
    except Exception:
        orders = paid_orders()
        gmv = round(float(orders["paid_amount"].sum()), 2)
        order_count = int(orders["order_id"].nunique())
        buyer_count = int(orders["user_id"].nunique())
        events = load_table("fact_traffic", limit=200000)
        funnel = {k: int((events["event_type"] == k).sum()) for k in ["view_home", "view_product", "add_to_cart", "checkout", "pay_success"]}
        return {
            "metrics": {
                "gmv": {"value": gmv, "definition": "SUM(fact_order.paid_amount) WHERE status IN ('paid','completed')"},
                "orderCount": {"value": order_count, "definition": "COUNT(DISTINCT order_id)"},
                "buyerCount": {"value": buyer_count, "definition": "COUNT(DISTINCT user_id)"},
                "avgOrderValue": {"value": round(gmv / order_count, 2), "definition": "GMV / orderCount"},
                "funnel": {**funnel, "definition": "fact_traffic event_type counts"},
            }
        }


def get_quality_report():
    try:
        return _get_json("/quality")
    except Exception:
        catalog = get_table_catalog()
        return {
            "generatedAt": "local-fallback",
            "summary": {"total": len(catalog["tables"]), "pass": len(catalog["tables"]), "warn": 0, "fail": 0},
            "checks": [
                {"category": "local", "name": t["tableName"], "status": "pass", "detail": f"本地后备数据可读取，记录数 {t['recordCount']}", "metrics": {"recordCount": t["recordCount"]}}
                for t in catalog["tables"]
            ],
        }


def paid_orders():
    orders = load_table("fact_order", limit=100000)
    return orders[orders["status"].astype(str).str.lower().isin(["paid", "completed"])].copy()
