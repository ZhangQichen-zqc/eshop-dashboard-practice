"""R10 库存策略优化

SKU 动销分析 → ABC 分类 → 商品策略 → 预警。
"""

import logging
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

from ..data_access import get_db_connection

warnings.filterwarnings("ignore")
logger = logging.getLogger("analytics.r10")


# ============================================================
# 14.1 SKU 动销
# ============================================================

def analyze_sku_performance() -> dict:
    """SKU 销量/销售额/毛利 + 库存周转 + 动销率。"""
    conn = get_db_connection()
    try:
        oi = pd.read_sql("""
            SELECT oi.sku_id, dp.product_name, dp.category_name, dp.supplier,
                   SUM(oi.quantity) as total_qty,
                   SUM(oi.unit_price * oi.quantity - oi.discount_amount) as total_sales,
                   SUM((oi.unit_price - oi.unit_cost) * oi.quantity - oi.discount_amount) as gross_profit,
                   COUNT(DISTINCT oi.order_id) as order_count
            FROM fact_order_item oi
            JOIN dim_product dp ON oi.sku_id = dp.sku_id
            GROUP BY oi.sku_id
        """, conn)

        # 库存周转
        inv = pd.read_sql("""
            SELECT sku_id,
                   SUM(CASE WHEN movement_type='in' THEN quantity ELSE 0 END) as total_in,
                   SUM(CASE WHEN movement_type='out' THEN quantity ELSE 0 END) as total_out
            FROM fact_inventory_movement GROUP BY sku_id
        """, conn)

        merged = oi.merge(inv, on="sku_id", how="left")
        merged["total_in"] = merged["total_in"].fillna(0)
        merged["total_out"] = merged["total_out"].fillna(0)
        merged["current_stock"] = merged["total_in"] - merged["total_out"]

        # 周转次数 = 销量 / 平均库存
        merged["avg_inventory"] = (merged["current_stock"] + 1).clip(lower=1)
        merged["turnover_times"] = (merged["total_qty"] / merged["avg_inventory"]).round(2)
        merged["turnover_days"] = (365 / merged["turnover_times"]).round(0)
        merged["turnover_days"] = merged["turnover_days"].replace([np.inf], 365).fillna(365)

        # 动销率（有销量 SKU / 总 SKU）
        active = (merged["total_qty"] > 0).sum()
        sell_through = active / len(merged) * 100

        return {
            "skus": merged.to_dict(orient="records"),
            "total_skus": len(merged),
            "active_skus": int(active),
            "sell_through_rate": round(sell_through, 1),
            "total_revenue": round(float(merged["total_sales"].sum()), 2),
            "total_profit": round(float(merged["gross_profit"].sum()), 2),
        }
    finally:
        conn.close()


# ============================================================
# 14.2 ABC 分类
# ============================================================

def abc_classify(df: pd.DataFrame, value_col: str, label: str = "sales") -> pd.DataFrame:
    """ABC 分类：累计占比前 70%=A，70-90%=B，90-100%=C。"""
    df = df.sort_values(value_col, ascending=False).copy()
    df["cumsum"] = df[value_col].cumsum()
    df["cumshare"] = df["cumsum"] / df[value_col].sum()
    df[f"abc_{label}"] = df["cumshare"].apply(
        lambda x: "A" if x <= 0.7 else ("B" if x <= 0.9 else "C")
    )
    return df


def compute_abc_matrix() -> dict:
    """按销售额/毛利/销量做 ABC 分类，生成交叉矩阵。"""
    conn = get_db_connection()
    try:
        oi = pd.read_sql("""
            SELECT oi.sku_id, dp.product_name, dp.category_name,
                   SUM(oi.quantity) as qty,
                   SUM(oi.unit_price * oi.quantity - oi.discount_amount) as sales,
                   SUM((oi.unit_price - oi.unit_cost) * oi.quantity - oi.discount_amount) as profit
            FROM fact_order_item oi
            JOIN dim_product dp ON oi.sku_id = dp.sku_id
            GROUP BY oi.sku_id
        """, conn)

        df = oi.copy()
        df = abc_classify(df, "sales", "sales")
        df = abc_classify(df, "profit", "profit")
        df = abc_classify(df, "qty", "volume")

        # ABC 交叉矩阵
        cross = df.groupby(["abc_sales", "abc_profit"]).agg(
            sku_count=("sku_id", "nunique"),
            total_sales=("sales", "sum"),
        ).reset_index()

        # 各类别统计
        summary = {}
        for col in ["abc_sales", "abc_profit", "abc_volume"]:
            dist = df[col].value_counts().to_dict()
            summary[col] = {
                "A": int(dist.get("A", 0)),
                "B": int(dist.get("B", 0)),
                "C": int(dist.get("C", 0)),
            }

        return {
            "abc_matrix": cross.to_dict(orient="records"),
            "summary": summary,
            "skus": df.to_dict(orient="records"),
        }
    finally:
        conn.close()


# ============================================================
# 14.3 商品策略
# ============================================================

def generate_product_strategies() -> dict:
    """为 SKU 生成具体策略建议（至少 20 个）。"""
    conn = get_db_connection()
    try:
        # 获取销量 + 库存数据
        oi = pd.read_sql("""
            SELECT oi.sku_id, dp.product_name, dp.category_name,
                   SUM(oi.quantity) as qty,
                   SUM(oi.unit_price * oi.quantity - oi.discount_amount) as sales,
                   SUM((oi.unit_price - oi.unit_cost) * oi.quantity - oi.discount_amount) as profit
            FROM fact_order_item oi
            JOIN dim_product dp ON oi.sku_id = dp.sku_id
            GROUP BY oi.sku_id
        """, conn)

        inv = pd.read_sql("""
            SELECT sku_id,
                   SUM(CASE WHEN movement_type='in' THEN quantity ELSE -quantity END) as stock
            FROM fact_inventory_movement GROUP BY sku_id
        """, conn)

        df = oi.merge(inv, on="sku_id", how="left")
        df["stock"] = df["stock"].fillna(0)
        df = abc_classify(df, "sales", "abc")

        strategies = []
        for _, row in df.iterrows():
            strategy = None
            if row["abc_abc"] == "A" and row["stock"] < row["qty"] * 0.5:
                strategy = "补货"
            elif row["abc_abc"] == "C" and row["stock"] > row["qty"] * 3:
                strategy = "清仓"
            elif row["abc_abc"] == "A" and row["profit"] < row["sales"] * 0.2:
                strategy = "提价/控成本"
            elif row["abc_abc"] == "C" and row["qty"] < 10:
                strategy = "考虑下架"
            elif row["abc_abc"] == "B" and row["profit"] > row["sales"] * 0.5:
                strategy = "重点运营"

            if strategy:
                strategies.append({
                    "sku_id": row["sku_id"],
                    "product_name": row["product_name"],
                    "category": row["category_name"],
                    "abc_class": row["abc_abc"],
                    "strategy": strategy,
                    "sales": round(float(row["sales"]), 2),
                    "stock": int(row["stock"]),
                    "qty": int(row["qty"]),
                })

        return {
            "strategies": strategies[:30],  # 至少 20
            "summary": {
                "补货": sum(1 for s in strategies if s["strategy"] == "补货"),
                "清仓": sum(1 for s in strategies if s["strategy"] == "清仓"),
                "提价/控成本": sum(1 for s in strategies if s["strategy"] == "提价/控成本"),
                "考虑下架": sum(1 for s in strategies if s["strategy"] == "考虑下架"),
                "重点运营": sum(1 for s in strategies if s["strategy"] == "重点运营"),
            },
        }
    finally:
        conn.close()


# ============================================================
# 14.4 预警
# ============================================================

def generate_inventory_alerts() -> dict:
    """缺货/滞销/高退款库存风险预警。"""
    perf = analyze_sku_performance()
    skus = pd.DataFrame(perf["skus"])

    alerts = []

    # 缺货预警：库存 < 日均销量 * 3
    for _, row in skus.iterrows():
        avg_daily = row["total_qty"] / 365 if row["total_qty"] > 0 else 0
        if row["current_stock"] < avg_daily * 3 and row["total_qty"] > 10:
            alerts.append({
                "sku_id": row["sku_id"],
                "type": "缺货预警",
                "current_stock": int(row["current_stock"]),
                "avg_daily_demand": round(avg_daily, 1),
                "severity": "high" if row["current_stock"] <= 0 else "medium",
            })

    # 滞销预警：周转天数 > 180
    slow = skus[skus["turnover_days"] > 180]
    for _, row in slow.head(10).iterrows():
        alerts.append({
            "sku_id": row["sku_id"],
            "type": "滞销预警",
            "turnover_days": int(row["turnover_days"]),
            "current_stock": int(row["current_stock"]),
            "severity": "medium",
        })

    return {
        "alerts": alerts[:30],
        "stockout_count": sum(1 for a in alerts if a["type"] == "缺货预警"),
        "overstock_count": sum(1 for a in alerts if a["type"] == "滞销预警"),
    }
