"""R2 流量漏斗诊断

漏斗计算、流失分析、再营销候选名单。
"""

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

from ..data_access import get_db_connection

logger = logging.getLogger("analytics.r2")

FUNNEL_STAGES = ["view_home", "view_product", "add_to_cart", "checkout", "pay_success"]
STAGE_LABELS = {"view_home": "首页浏览", "view_product": "商品页", "add_to_cart": "加购", "checkout": "结算", "pay_success": "支付成功"}


# ============================================================
# 6.1 漏斗计算
# ============================================================

def compute_overall_funnel(conn) -> dict:
    """计算整体 5 层漏斗各层 session 数和转化率。"""
    counts = {}
    for stage in FUNNEL_STAGES:
        cnt = pd.read_sql(
            f"SELECT COUNT(DISTINCT session_id) FROM fact_traffic WHERE event_type='{stage}'", conn
        ).iloc[0, 0]
        counts[stage] = int(cnt)

    # 各环节转化率
    rates = {}
    for i in range(1, len(FUNNEL_STAGES)):
        prev = counts[FUNNEL_STAGES[i - 1]]
        curr = counts[FUNNEL_STAGES[i]]
        rates[f"{FUNNEL_STAGES[i-1]}_to_{FUNNEL_STAGES[i]}"] = round(curr / prev * 100, 2) if prev else 0

    # 整体转化率
    total_sessions = counts["view_home"]
    pay_sessions = counts["pay_success"]
    rates["overall"] = round(pay_sessions / total_sessions * 100, 2) if total_sessions else 0

    return {
        "stages": [{"stage": s, "label": STAGE_LABELS[s], "sessions": counts[s]} for s in FUNNEL_STAGES],
        "rates": rates,
    }


def compute_funnel_by_channel(conn) -> list:
    """按渠道分组漏斗。"""
    results = []
    channels = pd.read_sql("SELECT DISTINCT channel FROM fact_traffic", conn)["channel"].tolist()

    for ch in channels:
        row = {"channel": ch}
        for stage in FUNNEL_STAGES:
            cnt = pd.read_sql(
                f"SELECT COUNT(DISTINCT session_id) FROM fact_traffic WHERE event_type='{stage}' AND channel='{ch}'",
                conn
            ).iloc[0, 0]
            row[stage] = int(cnt)
        row["conversion"] = round(row["pay_success"] / row["view_home"] * 100, 2) if row["view_home"] else 0
        results.append(row)

    return results


def compute_funnel_by_device(conn) -> list:
    """按设备分组漏斗。"""
    results = []
    devices = pd.read_sql("SELECT DISTINCT device FROM fact_traffic WHERE device IS NOT NULL", conn)["device"].tolist()

    for dev in devices:
        row = {"device": dev}
        for stage in FUNNEL_STAGES:
            cnt = pd.read_sql(
                f"SELECT COUNT(DISTINCT session_id) FROM fact_traffic WHERE event_type='{stage}' AND device='{dev}'",
                conn
            ).iloc[0, 0]
            row[stage] = int(cnt)
        row["conversion"] = round(row["pay_success"] / row["view_home"] * 100, 2) if row["view_home"] else 0
        results.append(row)

    return results


def compute_funnel_by_campaign(conn) -> list:
    """按活动分组漏斗。"""
    results = []
    campaigns = pd.read_sql(
        "SELECT DISTINCT campaign_id FROM fact_traffic WHERE campaign_id IS NOT NULL AND campaign_id != ''",
        conn
    )["campaign_id"].tolist()

    for camp in campaigns[:10]:  # 取前 10 个活动
        row = {"campaign_id": camp}
        for stage in FUNNEL_STAGES:
            cnt = pd.read_sql(
                f"SELECT COUNT(DISTINCT session_id) FROM fact_traffic WHERE event_type='{stage}' AND campaign_id='{camp}'",
                conn
            ).iloc[0, 0]
            row[stage] = int(cnt)
        row["conversion"] = round(row["pay_success"] / row["view_home"] * 100, 2) if row.get("view_home", 0) else 0
        results.append(row)

    return results


def compute_monthly_funnel_trend(conn) -> list:
    """按月漏斗转化率趋势。"""
    df = pd.read_sql("""
        SELECT strftime('%Y-%m', event_date) as ym, event_type,
               COUNT(DISTINCT session_id) as sessions
        FROM fact_traffic
        WHERE event_type IN ('view_home','add_to_cart','pay_success')
        GROUP BY ym, event_type ORDER BY ym
    """, conn)

    pivot = df.pivot_table(index="ym", columns="event_type", values="sessions", fill_value=0).reset_index()
    pivot["cart_rate"] = pivot["add_to_cart"] / pivot["view_home"].clip(lower=1) * 100
    pivot["pay_rate"] = pivot["pay_success"] / pivot["view_home"].clip(lower=1) * 100

    return pivot.to_dict(orient="records")


# ============================================================
# 6.2 流失诊断
# ============================================================

def find_high_exposure_low_cart(conn, top_n: int = 20) -> list:
    """高曝光低加购商品（浏览多但加购少）。"""
    df = pd.read_sql("""
        SELECT sku_id,
               SUM(CASE WHEN event_type='view_product' THEN 1 ELSE 0 END) as views,
               SUM(CASE WHEN event_type='add_to_cart' THEN 1 ELSE 0 END) as carts
        FROM fact_traffic
        WHERE sku_id IS NOT NULL
        GROUP BY sku_id HAVING views >= 10
        ORDER BY (CAST(carts AS FLOAT) / views) ASC
        LIMIT ?
    """, conn, params=[top_n])

    df["cart_rate"] = df["carts"] / df["views"] * 100
    df["cart_rate"] = df["cart_rate"].round(2)
    return df.to_dict(orient="records")


def find_high_cart_low_checkout(conn, top_n: int = 20) -> list:
    """高加购低结算商品（加购多但结算少）。"""
    df = pd.read_sql("""
        SELECT sku_id,
               SUM(CASE WHEN event_type='add_to_cart' THEN 1 ELSE 0 END) as carts,
               SUM(CASE WHEN event_type='checkout' THEN 1 ELSE 0 END) as checkouts
        FROM fact_traffic
        WHERE sku_id IS NOT NULL
        GROUP BY sku_id HAVING carts >= 5
        ORDER BY (CAST(checkouts AS FLOAT) / carts) ASC
        LIMIT ?
    """, conn, params=[top_n])

    df["checkout_rate"] = df["checkouts"] / df["carts"] * 100
    df["checkout_rate"] = df["checkout_rate"].round(2)
    return df.to_dict(orient="records")


def find_biggest_dropoff(conn) -> dict:
    """定位最大流失环节。"""
    funnel = compute_overall_funnel(conn)
    stages = funnel["stages"]

    drops = []
    for i in range(1, len(stages)):
        prev = stages[i - 1]
        curr = stages[i]
        loss = prev["sessions"] - curr["sessions"]
        loss_rate = round(loss / prev["sessions"] * 100, 2) if prev["sessions"] else 0
        drops.append({
            "from": prev["label"],
            "to": curr["label"],
            "loss": loss,
            "loss_rate": loss_rate,
        })

    biggest = max(drops, key=lambda x: x["loss"]) if drops else {}
    return {"drops": drops, "biggest_dropoff": biggest}


# ============================================================
# 6.3 再营销
# ============================================================

def _get_max_date(conn) -> str:
    """获取数据中的最大日期。"""
    return pd.read_sql("SELECT MAX(event_date) FROM fact_traffic", conn).iloc[0, 0]


def find_browse_no_order_users(conn, days: int = 90) -> list:
    """最近 N 天浏览但无订单的用户。"""
    max_date = _get_max_date(conn)
    ref = (pd.Timestamp(max_date) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql("""
        SELECT DISTINCT t.user_id
        FROM fact_traffic t
        WHERE t.event_date >= ? AND t.event_type IN ('view_product','add_to_cart')
          AND t.user_id NOT IN (
            SELECT DISTINCT user_id FROM fact_order WHERE order_date >= ? AND status IN ('paid','completed')
          )
        LIMIT 200
    """, conn, params=[ref, ref])
    return df["user_id"].tolist()


def find_cart_abandon_users(conn, days: int = 90) -> list:
    """最近 N 天加购未支付用户。"""
    max_date = _get_max_date(conn)
    ref = (pd.Timestamp(max_date) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql("""
        SELECT DISTINCT t.user_id
        FROM fact_traffic t
        WHERE t.event_date >= ? AND t.event_type = 'add_to_cart'
          AND t.user_id NOT IN (
            SELECT DISTINCT user_id FROM fact_order WHERE order_date >= ? AND status IN ('paid','completed')
          )
        LIMIT 200
    """, conn, params=[ref, ref])
    return df["user_id"].tolist()


def find_checkout_abandon_users(conn, days: int = 90) -> list:
    """最近 N 天结算放弃用户。"""
    max_date = _get_max_date(conn)
    ref = (pd.Timestamp(max_date) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql("""
        SELECT DISTINCT t.user_id
        FROM fact_traffic t
        WHERE t.event_date >= ? AND t.event_type = 'checkout'
          AND t.user_id NOT IN (
            SELECT DISTINCT user_id FROM fact_order WHERE order_date >= ?
          )
        LIMIT 200
    """, conn, params=[ref, ref])
    return df["user_id"].tolist()


def generate_remarketing_list(conn) -> dict:
    """生成综合再营销候选名单。"""
    return {
        "browse_no_order": find_browse_no_order_users(conn),
        "cart_abandon": find_cart_abandon_users(conn),
        "checkout_abandon": find_checkout_abandon_users(conn),
        "generated_at": datetime.now().isoformat(),
    }


# ============================================================
# 综合数据
# ============================================================

def get_funnel_data() -> dict:
    """一次性获取漏斗全部数据。"""
    conn = get_db_connection()
    try:
        return {
            "funnel": compute_overall_funnel(conn),
            "by_channel": compute_funnel_by_channel(conn),
            "by_device": compute_funnel_by_device(conn),
            "by_campaign": compute_funnel_by_campaign(conn),
            "monthly_trend": compute_monthly_funnel_trend(conn),
            "biggest_dropoff": find_biggest_dropoff(conn),
            "high_exposure_low_cart": find_high_exposure_low_cart(conn),
            "high_cart_low_checkout": find_high_cart_low_checkout(conn),
            "remarketing": generate_remarketing_list(conn),
        }
    finally:
        conn.close()
