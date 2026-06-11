"""R9 履约与售后分析

承运商绩效 / 退款分析 / 评论分析 / 风险清单。
"""

import logging
import warnings
from typing import Dict, List

import numpy as np
import pandas as pd

from ..data_access import get_db_connection

warnings.filterwarnings("ignore")
logger = logging.getLogger("analytics.r9")


# ============================================================
# 13.1 履约分析
# ============================================================

def analyze_fulfillment() -> dict:
    """承运商延迟率 + 省份延迟率。"""
    conn = get_db_connection()
    try:
        ff = pd.read_sql("SELECT * FROM fact_fulfillment", conn)

        # 按承运商
        carrier = ff.groupby("carrier").agg(
            shipments=("shipment_id", "nunique"),
            late_count=("is_late", "sum"),
            avg_delivery_days=("delivery_days", "mean"),
        ).reset_index()
        carrier["late_rate"] = (carrier["late_count"] / carrier["shipments"] * 100).round(2)
        carrier = carrier.sort_values("late_rate")

        # 按省份
        province = ff.groupby("province").agg(
            shipments=("shipment_id", "nunique"),
            late_count=("is_late", "sum"),
            avg_delivery_days=("delivery_days", "mean"),
        ).reset_index()
        province["late_rate"] = (province["late_count"] / province["shipments"] * 100).round(2)
        province = province.sort_values("late_rate", ascending=False)

        # 延迟对退款率的影响
        delayed = ff[ff["is_late"] == 1]
        ontime = ff[ff["is_late"] == 0]
        refunds = pd.read_sql("SELECT order_id FROM fact_refund WHERE status='approved'", conn)

        delayed_refund = len(set(delayed["order_id"]) & set(refunds["order_id"]))
        ontime_refund = len(set(ontime["order_id"]) & set(refunds["order_id"]))
        delayed_rate = delayed_refund / len(delayed) * 100 if len(delayed) else 0
        ontime_rate = ontime_refund / len(ontime) * 100 if len(ontime) else 0

        return {
            "carriers": carrier.to_dict(orient="records"),
            "provinces": province.to_dict(orient="records"),
            "late_vs_refund": {
                "delayed_refund_rate": round(delayed_rate, 2),
                "ontime_refund_rate": round(ontime_rate, 2),
                "impact": round(delayed_rate - ontime_rate, 2),
            },
            "total_shipments": len(ff),
            "overall_late_rate": round(float(ff["is_late"].mean() * 100), 2),
        }
    finally:
        conn.close()


# ============================================================
# 13.2 退款分析
# ============================================================

def analyze_refunds() -> dict:
    """月度退款率 + 原因分布 + 高退款商品/供应商。"""
    conn = get_db_connection()
    try:
        refunds = pd.read_sql("SELECT * FROM fact_refund WHERE status='approved'", conn)
        orders = pd.read_sql("SELECT * FROM fact_order", conn)

        # 月度退款率
        refunds["refund_date"] = pd.to_datetime(refunds["refund_date"])
        orders["order_date"] = pd.to_datetime(orders["order_date"])

        monthly_refunds = refunds.groupby(refunds["refund_date"].dt.strftime("%Y-%m")).size().reset_index(name="refunds")
        monthly_orders = orders.groupby(orders["order_date"].dt.strftime("%Y-%m")).size().reset_index(name="orders")
        monthly = monthly_orders.merge(monthly_refunds, left_on="order_date", right_on="refund_date", how="left")
        monthly["refunds"] = monthly["refunds"].fillna(0)
        monthly["refund_rate"] = (monthly["refunds"] / monthly["orders"] * 100).round(2)

        # 退款原因分布
        reasons = refunds.groupby("reason").size().sort_values(ascending=False).reset_index(name="count")
        reasons["share"] = (reasons["count"] / reasons["count"].sum() * 100).round(1)

        # 高退款商品（需要关联 order_items）
        oi = pd.read_sql("""
            SELECT r.order_id, oi.sku_id, dp.product_name, dp.category_name, dp.supplier
            FROM fact_refund r
            JOIN fact_order_item oi ON r.order_id = oi.order_id
            JOIN dim_product dp ON oi.sku_id = dp.sku_id
            WHERE r.status='approved'
        """, conn)

        top_sku = oi.groupby(["sku_id", "product_name", "category_name"]).size().sort_values(ascending=False).reset_index(name="refund_count").head(20)

        top_supplier = oi.groupby("supplier").size().sort_values(ascending=False).reset_index(name="refund_count").head(10)

        return {
            "monthly_trend": monthly.tail(12).to_dict(orient="records"),
            "reasons": reasons.to_dict(orient="records"),
            "top_refund_skus": top_sku.to_dict(orient="records"),
            "top_refund_suppliers": top_supplier.to_dict(orient="records"),
            "total_refunds": len(refunds),
            "total_amount": round(float(refunds["amount"].sum()), 2),
        }
    finally:
        conn.close()


# ============================================================
# 13.3 评论分析
# ============================================================

def analyze_reviews() -> dict:
    """评分 + 差评率 + 情感 + 标签分布。"""
    conn = get_db_connection()
    try:
        reviews = pd.read_sql("SELECT * FROM fact_product_review", conn)
        products = pd.read_sql("SELECT * FROM dim_product", conn)

        # 按品类平均评分
        merged = reviews.merge(products[["sku_id", "category_name"]], on="sku_id")
        cat_rating = merged.groupby("category_name")["rating"].mean().round(2).sort_values(ascending=False).reset_index()

        # 按商品平均评分
        sku_rating = merged.groupby("sku_id")["rating"].agg(["mean", "count"]).round(2).reset_index()
        sku_rating.columns = ["sku_id", "avg_rating", "review_count"]

        # 差评率 (rating <= 2)
        bad = reviews[reviews["rating"] <= 2]
        bad_rate = len(bad) / len(reviews) * 100 if len(reviews) else 0
        good = reviews[reviews["rating"] >= 4]

        # 情感分布
        sentiment = reviews.groupby("sentiment").size().reset_index(name="count")
        sentiment["share"] = (sentiment["count"] / sentiment["count"].sum() * 100).round(1)

        # 评论标签分布
        tags = reviews.groupby("content_tag").size().sort_values(ascending=False).reset_index(name="count").head(15)

        return {
            "category_ratings": cat_rating.to_dict(orient="records"),
            "top_reviewed_skus": sku_rating.nlargest(10, "review_count").to_dict(orient="records"),
            "bad_rate": round(bad_rate, 2),
            "good_rate": round(len(good) / len(reviews) * 100, 2) if len(reviews) else 0,
            "total_reviews": len(reviews),
            "avg_rating": round(float(reviews["rating"].mean()), 2),
            "sentiment": sentiment.to_dict(orient="records"),
            "tags": tags.to_dict(orient="records"),
        }
    finally:
        conn.close()


# ============================================================
# 13.4 风险清单
# ============================================================

def generate_risk_list() -> dict:
    """综合风险清单。"""
    conn = get_db_connection()
    try:
        risks = []

        # 高退款商品
        oi = pd.read_sql("""
            SELECT oi.sku_id, dp.product_name, dp.category_name,
                   COUNT(*) as refunds
            FROM fact_refund r
            JOIN fact_order_item oi ON r.order_id = oi.order_id
            JOIN dim_product dp ON oi.sku_id = dp.sku_id
            WHERE r.status='approved'
            GROUP BY oi.sku_id HAVING refunds >= 5
            ORDER BY refunds DESC LIMIT 10
        """, conn)

        for _, row in oi.iterrows():
            risks.append({
                "type": "高退款商品",
                "target": f"{row['product_name']}({row['sku_id']})",
                "evidence": f"{row['refunds']} 次退款，品类 {row['category_name']}",
                "action": "排查质量或描述不符问题，考虑优化详情页",
                "severity": "high" if row["refunds"] > 15 else "medium",
            })

        # 高延迟地区
        ff = pd.read_sql("""
            SELECT province, COUNT(*) as total, SUM(is_late) as late
            FROM fact_fulfillment GROUP BY province HAVING CAST(SUM(is_late) AS FLOAT)/COUNT(*) > 0.1
            ORDER BY CAST(SUM(is_late) AS FLOAT)/COUNT(*) DESC LIMIT 5
        """, conn)

        for _, row in ff.iterrows():
            rate = row["late"] / row["total"] * 100 if row["total"] else 0
            risks.append({
                "type": "高延迟地区",
                "target": row["province"],
                "evidence": f"延迟率 {rate:.1f}%（{int(row['late'])}/{int(row['total'])}）",
                "action": "增加该地区仓储覆盖或切换承运商",
                "severity": "high" if rate > 15 else "medium",
            })

        return {"risks": risks}
    finally:
        conn.close()
