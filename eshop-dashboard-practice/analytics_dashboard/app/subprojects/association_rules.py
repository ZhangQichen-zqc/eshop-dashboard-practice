"""R6 关联规则 —— 购物篮分析

Apriori 频繁项集挖掘 → 关联规则 → 捆绑推荐/凑单推荐/交叉销售。
"""

import logging
import warnings
from itertools import combinations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules as mlx_association_rules

from ..data_access import get_db_connection

warnings.filterwarnings("ignore")
logger = logging.getLogger("analytics.r6")


# ============================================================
# 10.1 购物篮构建
# ============================================================

def build_sku_basket(min_items: int = 2, top_n: int = 80) -> pd.DataFrame:
    """按 order_id 聚合 SKU，构建购物篮（one-hot 编码）。

    限制 TOP N 热门 SKU 以控制内存。
    """
    conn = get_db_connection()
    try:
        oi = pd.read_sql("SELECT order_id, sku_id FROM fact_order_item", conn)

        # 只用 TOP N 热门 SKU
        top_skus = oi["sku_id"].value_counts().head(top_n).index.tolist()
        oi = oi[oi["sku_id"].isin(top_skus)]

        # 筛选 2+ 商品的订单
        order_counts = oi.groupby("order_id")["sku_id"].count()
        valid_orders = order_counts[order_counts >= min_items].index
        oi = oi[oi["order_id"].isin(valid_orders)]

        # One-hot 编码
        basket = oi.groupby(["order_id", "sku_id"]).size().unstack(fill_value=0)
        basket = (basket > 0).astype(bool)  # 用 bool 节省内存
        logger.info(f"SKU 购物篮: {basket.shape[0]} 订单, {basket.shape[1]} SKU")
        return basket
    finally:
        conn.close()


def build_category_basket(min_items: int = 2) -> pd.DataFrame:
    """按类目构建购物篮。"""
    conn = get_db_connection()
    try:
        oi = pd.read_sql("""
            SELECT oi.order_id, dp.category_name
            FROM fact_order_item oi
            JOIN dim_product dp ON oi.sku_id = dp.sku_id
        """, conn)

        order_counts = oi.groupby("order_id")["category_name"].nunique()
        valid_orders = order_counts[order_counts >= min_items].index
        oi = oi[oi["order_id"].isin(valid_orders)]

        basket = oi.groupby(["order_id", "category_name"]).size().unstack(fill_value=0)
        basket = (basket > 0).astype(int)
        logger.info(f"类目购物篮: {basket.shape[0]} 订单, {basket.shape[1]} 类目")
        return basket
    finally:
        conn.close()


def build_priceband_basket(min_items: int = 2) -> pd.DataFrame:
    """按价格带构建购物篮。"""
    conn = get_db_connection()
    try:
        oi = pd.read_sql("""
            SELECT oi.order_id,
                   CASE WHEN oi.unit_price < 100 THEN 'low'
                        WHEN oi.unit_price <= 500 THEN 'mid'
                        ELSE 'high' END as price_band
            FROM fact_order_item oi
        """, conn)

        order_counts = oi.groupby("order_id")["price_band"].nunique()
        valid_orders = order_counts[order_counts >= min_items].index
        oi = oi[oi["order_id"].isin(valid_orders)]

        basket = oi.groupby(["order_id", "price_band"]).size().unstack(fill_value=0)
        basket = (basket > 0).astype(int)
        logger.info(f"价格带购物篮: {basket.shape[0]} 订单, {basket.shape[1]} 价格带")
        return basket
    finally:
        conn.close()


# ============================================================
# 10.2 Apriori 挖掘
# ============================================================

def mine_association_rules(
    basket: pd.DataFrame,
    min_support: float = 0.01,
    min_confidence: float = 0.3,
    min_lift: float = 1.2,
) -> dict:
    """执行 Apriori 频繁项集挖掘并生成关联规则。

    Returns:
        dict: 频繁项集 + 关联规则列表
    """
    # 频繁项集
    frequent_itemsets = apriori(basket, min_support=min_support, use_colnames=True, max_len=3)
    freq_list = []
    for _, row in frequent_itemsets.iterrows():
        freq_list.append({
            "itemset": list(row["itemsets"]),
            "support": round(row["support"], 6),
            "length": len(row["itemsets"]),
        })

    # 关联规则
    if len(frequent_itemsets) < 2:
        return {"frequent_itemsets": freq_list, "rules": [], "message": "频繁项集不足，降低 min_support 试试"}

    rules = mlx_association_rules(frequent_itemsets, metric="confidence", min_threshold=min_confidence)
    rules["lift"] = rules["lift"].round(4)
    rules["leverage"] = rules["leverage"].round(6)
    rules["conviction"] = rules["conviction"].round(4)

    # 计算提升度过滤
    rules = rules[rules["lift"] > min_lift]
    rules = rules.sort_values("lift", ascending=False)

    # 转 dict
    rule_list = []
    for _, r in rules.iterrows():
        rule_list.append({
            "antecedents": list(r["antecedents"]),
            "consequents": list(r["consequents"]),
            "support": round(r["support"], 6),
            "confidence": round(r["confidence"], 4),
            "lift": round(r["lift"], 4),
            "leverage": round(r["leverage"], 6),
            "conviction": round(r["conviction"], 4),
        })

    return {
        "frequent_itemsets": freq_list[:50],
        "rules": rule_list[:100],
        "total_rules": len(rule_list),
    }


# ============================================================
# 10.3 推荐生成
# ============================================================

def generate_bundle_recommendations(rules: List[dict]) -> List[dict]:
    """捆绑销售建议：高 lift + 高 confidence。"""
    bundles = [r for r in rules if r["lift"] >= 1.5 and r["confidence"] >= 0.4]
    return sorted(bundles, key=lambda x: -x["lift"])[:20]


def generate_cross_sell_recommendations(rules: List[dict], categories: List[str] = None) -> List[dict]:
    """交叉销售建议：跨类目 + 高 lift。"""
    if categories is None:
        cats = set()
        for r in rules:
            cats.update(r["antecedents"])
        categories = list(cats)

    cross_sell = []
    for r in rules:
        antecedents = set(r["antecedents"])
        consequents = set(r["consequents"])
        # 判断是否跨类目（antecedents 和 consequents 不在同一类目）
        if not antecedents.intersection(consequents) and len(antecedents) >= 1:
            cross_sell.append(r)
    return sorted(cross_sell, key=lambda x: -x["lift"])[:20]


def generate_addon_recommendations(rules: List[dict]) -> List[dict]:
    """凑单推荐：仅按高提升度和高置信度生成。"""
    return sorted(rules, key=lambda x: (-x["lift"], -x["confidence"]))[:20]


def filter_business_unsuitable(rules: List[dict]) -> List[dict]:
    """筛选数学好但业务不适合的规则（至少 5 条）。

    标准：lift > 2 但 support 极低（< 0.005），实际业务价值有限。
    """
    unsuitable = [
        r for r in rules
        if r["lift"] > 2 and r["support"] < 0.005
    ]
    return unsuitable[:10]


def get_product_recommendations(sku_id: str, rules: List[dict]) -> List[dict]:
    """给定 SKU，找推荐商品。"""
    recommendations = []
    for r in rules:
        if sku_id in r["antecedents"]:
            recommendations.append({
                "recommend": r["consequents"],
                "confidence": r["confidence"],
                "lift": r["lift"],
            })
    return sorted(recommendations, key=lambda x: -x["lift"])[:10]


# ============================================================
# 一站式分析
# ============================================================

def run_full_association_analysis() -> dict:
    """运行完整关联规则分析流程。"""
    logger.info("=== R6 关联规则分析开始 ===")

    # SKU 篮
    sku_basket = build_sku_basket(min_items=2)
    sku_result = mine_association_rules(sku_basket, min_support=0.0005, min_confidence=0.15, min_lift=1.05)

    # 类目篮
    cat_basket = build_category_basket(min_items=2)
    cat_result = mine_association_rules(cat_basket, min_support=0.01, min_confidence=0.15, min_lift=1.05)

    # 推荐
    bundles = generate_bundle_recommendations(sku_result["rules"])
    cross_sell = generate_cross_sell_recommendations(cat_result["rules"])
    addons = generate_addon_recommendations(sku_result["rules"])
    unsuitable = filter_business_unsuitable(sku_result["rules"])

    return {
        "sku_rules": sku_result,
        "category_rules": cat_result,
        "bundles": bundles[:10],
        "cross_sell": cross_sell[:10],
        "addon_recommendations": addons[:10],
        "business_unsuitable": unsuitable,
        "generated_at": pd.Timestamp.now().isoformat(),
    }
