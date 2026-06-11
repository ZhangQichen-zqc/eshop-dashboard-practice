"""R5 客户聚类与商品聚类

K-Means 用户分群 + 商品分群 + 层次聚类/DBSCAN 对比。
"""

import logging
import warnings
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
from sklearn.metrics import silhouette_score, calinski_harabasz_score
from sklearn.preprocessing import StandardScaler

from ..data_access import get_db_connection
from ..subprojects.feature_engineering import build_user_wide_table, build_product_wide_table

warnings.filterwarnings("ignore")
logger = logging.getLogger("analytics.r5")

CLUSTER_NAMES = {
    0: "高价值活跃型",
    1: "中等消费型",
    2: "低频低消型",
    3: "高频低消型",
    4: "近期流失型",
    5: "价格敏感型",
    6: "品类探索型",
    7: "忠实高消型",
    8: "边缘用户型",
    9: "潜力增长型",
}


# ============================================================
# 9.1 用户聚类
# ============================================================

def cluster_users(k: int = 5) -> dict:
    """K-Means 用户聚类。

    Returns:
        dict: 肘部法/轮廓系数/CH 指数 + 聚类标签 + 各簇画像
    """
    wide = build_user_wide_table(save_csv=False)

    # 选取聚类特征
    feature_cols = [
        "recency", "frequency", "monetary", "total_events", "active_days",
        "category_diversity", "avg_unit_price", "high_price_ratio",
        "monthly_orders", "avg_order_interval", "lifecycle_days",
        "coupons_used_count", "coupon_use_rate",
    ]
    available = [c for c in feature_cols if c in wide.columns]
    X = wide[available].fillna(0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 肘部法 (K=2~10)
    elbow = []
    for k_val in range(2, 11):
        km = KMeans(n_clusters=k_val, random_state=42, n_init=10)
        km.fit(X_scaled)
        elbow.append({"k": k_val, "inertia": round(km.inertia_, 2)})

    # 最佳 K 评估
    best_k = k
    sil_scores = {}
    ch_scores = {}
    for k_val in [3, 4, 5, 6, 7, 8]:
        km = KMeans(n_clusters=k_val, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        sil_scores[k_val] = round(silhouette_score(X_scaled, labels), 4)
        ch_scores[k_val] = round(calinski_harabasz_score(X_scaled, labels), 2)

    # 最终聚类
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    wide["cluster"] = km.fit_predict(X_scaled)

    # 各簇画像
    profiles = []
    for c in range(k):
        cluster_data = wide[wide["cluster"] == c]
        profiles.append({
            "cluster_id": c,
            "name": CLUSTER_NAMES.get(c, f"分群{c}"),
            "size": len(cluster_data),
            "share": round(len(cluster_data) / len(wide) * 100, 1),
            "avg_recency": round(float(cluster_data["recency"].mean()), 1),
            "avg_frequency": round(float(cluster_data["frequency"].mean()), 1),
            "avg_monetary": round(float(cluster_data["monetary"].mean()), 2),
            "avg_events": round(float(cluster_data["total_events"].mean()), 0) if "total_events" in cluster_data else 0,
            "category_diversity": round(float(cluster_data["category_diversity"].mean()), 1) if "category_diversity" in cluster_data else 0,
            "top_member_level": cluster_data["member_level"].mode()[0] if not cluster_data["member_level"].mode().empty else "unknown",
        })

    return {
        "elbow": elbow,
        "silhouette_scores": sil_scores,
        "calinski_harabasz_scores": ch_scores,
        "best_k": k,
        "best_silhouette": sil_scores.get(k, 0),
        "clusters": profiles,
    }


# ============================================================
# 9.2 商品聚类
# ============================================================

def cluster_products(k: int = 5) -> dict:
    """K-Means 商品聚类。"""
    wide = build_product_wide_table(save_csv=False)

    feature_cols = [
        "total_quantity", "total_sales", "total_gross_profit",
        "avg_rating", "refund_rate", "turnover_rate", "avg_order_price",
    ]
    available = [c for c in feature_cols if c in wide.columns]

    # 去掉可能全为 0 的列
    valid_cols = [c for c in available if wide[c].std() > 0]
    X = wide[valid_cols].fillna(0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 肘部法
    elbow = []
    for kv in range(2, 11):
        km = KMeans(n_clusters=kv, random_state=42, n_init=10)
        km.fit(X_scaled)
        elbow.append({"k": kv, "inertia": round(km.inertia_, 2)})

    # 轮廓系数
    sil_scores = {}
    for kv in [3, 4, 5, 6, 7]:
        km = KMeans(n_clusters=kv, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        sil_scores[kv] = round(silhouette_score(X_scaled, labels), 4)

    # 最终聚类
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    wide["cluster"] = km.fit_predict(X_scaled)

    # 商品簇命名
    product_cluster_names = {
        0: "利润款",
        1: "引流款",
        2: "长尾款",
        3: "风险款",
        4: "清仓款",
    }

    profiles = []
    for c in range(k):
        cd = wide[wide["cluster"] == c]
        profiles.append({
            "cluster_id": c,
            "name": product_cluster_names.get(c, f"商品分群{c}"),
            "size": len(cd),
            "share": round(len(cd) / len(wide) * 100, 1),
            "avg_sales": round(float(cd["total_sales"].mean()), 2) if "total_sales" in cd else 0,
            "avg_profit": round(float(cd["total_gross_profit"].mean()), 2) if "total_gross_profit" in cd else 0,
            "avg_rating": round(float(cd["avg_rating"].mean()), 2) if "avg_rating" in cd else 0,
            "avg_refund_rate": round(float(cd["refund_rate"].mean()), 4) if "refund_rate" in cd else 0,
            "avg_turnover": round(float(cd["turnover_rate"].mean()), 2) if "turnover_rate" in cd else 0,
        })

    return {
        "elbow": elbow,
        "silhouette_scores": sil_scores,
        "best_k": k,
        "clusters": profiles,
        "sample_products": wide[["sku_id", "cluster"] + valid_cols].head(10).to_dict(orient="records"),
    }


# ============================================================
# 9.3 算法对比
# ============================================================

def compare_algorithms() -> dict:
    """对比三种聚类算法（K-Means / 层次聚类 / DBSCAN）。"""
    wide = build_user_wide_table(save_csv=False)
    feature_cols = ["recency", "frequency", "monetary", "total_events", "active_days", "category_diversity"]
    available = [c for c in feature_cols if c in wide.columns]
    X = wide[available].fillna(0)

    # 采样加速
    sample = X.sample(n=3000, random_state=42)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(sample)

    results = {}

    # K-Means
    km = KMeans(n_clusters=5, random_state=42, n_init=10)
    km_labels = km.fit_predict(Xs)
    results["kmeans"] = {
        "silhouette": round(silhouette_score(Xs, km_labels), 4),
        "ch_score": round(calinski_harabasz_score(Xs, km_labels), 2),
        "clusters": len(set(km_labels)),
    }

    # 层次聚类
    hc = AgglomerativeClustering(n_clusters=5)
    hc_labels = hc.fit_predict(Xs)
    results["hierarchical"] = {
        "silhouette": round(silhouette_score(Xs, hc_labels), 4),
        "ch_score": round(calinski_harabasz_score(Xs, hc_labels), 2),
        "clusters": len(set(hc_labels)),
    }

    # DBSCAN
    db = DBSCAN(eps=1.0, min_samples=50)
    db_labels = db.fit_predict(Xs)
    n_clusters = len(set(db_labels)) - (1 if -1 in db_labels else 0)
    # Silhouette only if we have >1 cluster and not all noise
    if n_clusters >= 2:
        mask = db_labels != -1
        db_sil = round(silhouette_score(Xs[mask], db_labels[mask]), 4) if mask.sum() > 1 else 0
    else:
        db_sil = 0
    results["dbscan"] = {
        "silhouette": db_sil,
        "clusters": n_clusters,
        "noise_points": int((db_labels == -1).sum()),
    }

    # 排名
    best = max(results.items(), key=lambda x: x[1].get("silhouette", 0))
    results["best_method"] = best[0]

    return results
