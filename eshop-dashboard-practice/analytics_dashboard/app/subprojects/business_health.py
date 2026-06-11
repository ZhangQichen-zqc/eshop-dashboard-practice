"""R1 经营驾驶舱

计算核心 KPI、趋势、渠道/品类/会员拆解、异常检测。
"""

import logging
from datetime import date, datetime
from typing import List, Optional

import numpy as np
import pandas as pd

from ..data_access import get_db_connection

logger = logging.getLogger("analytics.r1")


def compute_kpi(conn) -> dict:
    """计算 8 个核心 KPI + 环比变化。"""
    # 当前值
    gmv = float(pd.read_sql(
        "SELECT SUM(paid_amount) FROM fact_order WHERE status IN ('paid','completed')", conn
    ).iloc[0, 0] or 0)

    refund = float(pd.read_sql(
        "SELECT SUM(amount) FROM fact_refund WHERE status='approved'", conn
    ).iloc[0, 0] or 0)

    net_sales = gmv - refund

    gross_profit = float(pd.read_sql("""
        SELECT SUM((oi.unit_price - oi.unit_cost) * oi.quantity - oi.discount_amount)
        FROM fact_order_item oi
        JOIN fact_order o ON oi.order_id = o.order_id
        WHERE o.status IN ('paid','completed')
    """, conn).iloc[0, 0] or 0)

    order_count = int(pd.read_sql(
        "SELECT COUNT(DISTINCT order_id) FROM fact_order WHERE status IN ('paid','completed')", conn
    ).iloc[0, 0])

    buyer_count = int(pd.read_sql(
        "SELECT COUNT(DISTINCT user_id) FROM fact_order WHERE status IN ('paid','completed')", conn
    ).iloc[0, 0])

    aov = gmv / order_count if order_count else 0
    gross_margin = gross_profit / gmv * 100 if gmv else 0

    total_orders = int(pd.read_sql("SELECT COUNT(*) FROM fact_order", conn).iloc[0, 0])
    refund_orders = int(pd.read_sql(
        "SELECT COUNT(DISTINCT order_id) FROM fact_refund WHERE status='approved'", conn
    ).iloc[0, 0])
    refund_rate = refund_orders / total_orders * 100 if total_orders else 0

    # 转化率
    total_sessions = int(pd.read_sql("SELECT COUNT(DISTINCT session_id) FROM fact_traffic", conn).iloc[0, 0])
    pay_sessions = int(pd.read_sql(
        "SELECT COUNT(DISTINCT session_id) FROM fact_traffic WHERE event_type='pay_success'", conn
    ).iloc[0, 0])
    conversion = pay_sessions / total_sessions * 100 if total_sessions else 0

    return {
        "gmv": round(gmv, 2),
        "net_sales": round(net_sales, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_margin": round(gross_margin, 2),
        "order_count": order_count,
        "buyer_count": buyer_count,
        "aov": round(aov, 2),
        "refund_rate": round(refund_rate, 2),
        "conversion_rate": round(conversion, 2),
    }


def compute_monthly_trends(conn) -> list:
    """月度趋势：GMV、订单数、客单价、毛利。"""
    df = pd.read_sql("""
        SELECT strftime('%Y-%m', order_date) as ym,
               SUM(paid_amount) as gmv,
               COUNT(DISTINCT order_id) as orders,
               ROUND(SUM(paid_amount) / COUNT(DISTINCT order_id), 2) as aov
        FROM fact_order
        WHERE status IN ('paid','completed')
        GROUP BY ym ORDER BY ym
    """, conn)

    # 计算环比
    df["gmv_mom"] = df["gmv"].pct_change()
    df["orders_mom"] = df["orders"].pct_change()
    df["aov_mom"] = df["aov"].pct_change()

    # 填充 NaN
    df = df.where(pd.notnull(df), None)

    return df.to_dict(orient="records")


def compute_channel_breakdown(conn) -> list:
    """渠道 GMV 贡献率和排名。"""
    df = pd.read_sql("""
        SELECT channel,
               SUM(paid_amount) as gmv,
               COUNT(DISTINCT order_id) as orders,
               COUNT(DISTINCT user_id) as buyers
        FROM fact_order
        WHERE status IN ('paid','completed')
        GROUP BY channel ORDER BY gmv DESC
    """, conn)

    total_gmv = df["gmv"].sum()
    df["share"] = df["gmv"] / total_gmv * 100
    df["share"] = df["share"].round(2)

    return df.to_dict(orient="records")


def compute_category_breakdown(conn) -> list:
    """类目 GMV 贡献率和排名。"""
    df = pd.read_sql("""
        SELECT dp.category_name,
               SUM(oi.unit_price * oi.quantity - oi.discount_amount) as gmv,
               COUNT(DISTINCT oi.order_id) as orders,
               COUNT(DISTINCT oi.sku_id) as sku_count
        FROM fact_order_item oi
        JOIN dim_product dp ON oi.sku_id = dp.sku_id
        GROUP BY dp.category_name ORDER BY gmv DESC
    """, conn)

    total_gmv = df["gmv"].sum()
    df["share"] = df["gmv"] / total_gmv * 100
    df["share"] = df["share"].round(2)

    return df.to_dict(orient="records")


def compute_member_contribution(conn) -> list:
    """会员等级贡献。"""
    df = pd.read_sql("""
        SELECT du.member_level,
               COUNT(DISTINCT fo.user_id) as buyers,
               COUNT(DISTINCT fo.order_id) as orders,
               SUM(fo.paid_amount) as gmv
        FROM fact_order fo
        JOIN dim_user du ON fo.user_id = du.user_id
        WHERE fo.status IN ('paid','completed')
        GROUP BY du.member_level ORDER BY gmv DESC
    """, conn)
    return df.to_dict(orient="records")


def compute_top_bottom_products(conn, top_n: int = 10) -> dict:
    """TOP / BOTTOM N 商品。"""
    df = pd.read_sql("""
        SELECT dp.sku_id, dp.product_name, dp.category_name,
               SUM(oi.quantity) as total_qty,
               SUM(oi.unit_price * oi.quantity - oi.discount_amount) as gmv
        FROM fact_order_item oi
        JOIN dim_product dp ON oi.sku_id = dp.sku_id
        GROUP BY dp.sku_id ORDER BY gmv DESC
    """, conn)

    return {
        "top": df.head(top_n).to_dict(orient="records"),
        "bottom": df.tail(top_n).to_dict(orient="records"),
    }


def compute_daily_aggregation(conn, start: str = None, end: str = None) -> list:
    """日粒度聚合。"""
    sql = """
        SELECT order_date, channel,
               SUM(paid_amount) as gmv,
               COUNT(DISTINCT order_id) as orders
        FROM fact_order
        WHERE status IN ('paid','completed')
    """
    if start:
        sql += f" AND order_date >= '{start}'"
    if end:
        sql += f" AND order_date <= '{end}'"
    sql += " GROUP BY order_date, channel ORDER BY order_date"

    df = pd.read_sql(sql, conn)
    return df.to_dict(orient="records")


def compute_mom_changes(conn) -> dict:
    """计算各维度环比增长。"""
    monthly = pd.read_sql("""
        SELECT strftime('%Y-%m', order_date) as ym,
               SUM(paid_amount) as gmv,
               COUNT(DISTINCT order_id) as orders,
               COUNT(DISTINCT user_id) as buyers,
               ROUND(SUM(paid_amount)/COUNT(DISTINCT order_id), 2) as aov
        FROM fact_order WHERE status IN ('paid','completed')
        GROUP BY ym ORDER BY ym
    """, conn)

    latest = monthly.iloc[-1]
    prev = monthly.iloc[-2]

    return {
        "current_month": latest["ym"],
        "previous_month": prev["ym"],
        "gmv_mom": round((latest["gmv"] - prev["gmv"]) / prev["gmv"] * 100, 2) if prev["gmv"] else None,
        "orders_mom": round((latest["orders"] - prev["orders"]) / prev["orders"] * 100, 2) if prev["orders"] else None,
        "buyers_mom": round((latest["buyers"] - prev["buyers"]) / prev["buyers"] * 100, 2) if prev["buyers"] else None,
        "aov_mom": round((latest["aov"] - prev["aov"]) / prev["aov"] * 100, 2) if prev["aov"] else None,
    }


def detect_anomalies(conn, threshold: float = 0.10) -> list:
    """检测异常月份（环比波动 > threshold）。"""
    monthly = pd.read_sql("""
        SELECT strftime('%Y-%m', order_date) as ym,
               SUM(paid_amount) as gmv,
               COUNT(DISTINCT order_id) as orders
        FROM fact_order WHERE status IN ('paid','completed')
        GROUP BY ym ORDER BY ym
    """, conn)

    monthly["gmv_mom"] = monthly["gmv"].pct_change()
    monthly["orders_mom"] = monthly["orders"].pct_change()

    anomalies = []
    for _, row in monthly.iterrows():
        if row["gmv_mom"] is not None and abs(row["gmv_mom"]) > threshold:
            anomalies.append({
                "month": row["ym"],
                "indicator": "GMV",
                "change_pct": round(row["gmv_mom"] * 100, 2),
                "direction": "up" if row["gmv_mom"] > 0 else "down",
                "gmv": round(row["gmv"], 2),
            })
        if row["orders_mom"] is not None and abs(row["orders_mom"]) > threshold:
            anomalies.append({
                "month": row["ym"],
                "indicator": "订单数",
                "change_pct": round(row["orders_mom"] * 100, 2),
                "direction": "up" if row["orders_mom"] > 0 else "down",
                "orders": int(row["orders"]),
            })

    return anomalies


# ============================================================
# 综合 API 数据包装
# ============================================================

def get_dashboard_data() -> dict:
    """一次性获取驾驶舱全部数据。"""
    conn = get_db_connection()
    try:
        return {
            "kpi": compute_kpi(conn),
            "monthly_trends": compute_monthly_trends(conn),
            "channel_breakdown": compute_channel_breakdown(conn),
            "category_breakdown": compute_category_breakdown(conn),
            "member_contribution": compute_member_contribution(conn),
            "top_bottom_products": compute_top_bottom_products(conn),
            "mom_changes": compute_mom_changes(conn),
            "anomalies": detect_anomalies(conn),
            "generated_at": datetime.now().isoformat(),
        }
    finally:
        conn.close()
