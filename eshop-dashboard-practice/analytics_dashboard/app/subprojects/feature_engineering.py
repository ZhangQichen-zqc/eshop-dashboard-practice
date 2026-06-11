"""R3/R4 特征工程：用户宽表 + 商品宽表

构建用户行为宽表（RFM + 行为 + 时间窗口 + 优惠券 + 品类偏好）
用于后续 RFM 分群、复购预测、客户聚类。
"""

import logging
from datetime import date, datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from ..data_access import get_db_connection

logger = logging.getLogger("analytics.features")


# ============================================================
# 4.1 RFM 特征 (items 208-213)
# ============================================================

def compute_rfm(orders_df: pd.DataFrame, reference_date: Optional[str] = None) -> pd.DataFrame:
    """计算用户基础 RFM。

    Args:
        orders_df: 订单 DataFrame（需含 user_id, order_date, paid_amount, order_id）
        reference_date: 参考日期（默认取数据中最大日期）
    Returns:
        DataFrame: user_id, recency, frequency, monetary
    """
    paid = orders_df[orders_df["status"].isin(["paid", "completed"])].copy()
    paid["order_date"] = pd.to_datetime(paid["order_date"])

    if reference_date is None:
        reference_date = paid["order_date"].max()

    ref_date = pd.Timestamp(reference_date)

    rfm = paid.groupby("user_id").agg(
        recency=("order_date", lambda x: (ref_date - x.max()).days),
        frequency=("order_id", "nunique"),
        monetary=("paid_amount", "sum"),
    ).reset_index()

    rfm["monetary"] = rfm["monetary"].fillna(0).astype(float)
    return rfm


def compute_rfm_scores(rfm_df: pd.DataFrame) -> pd.DataFrame:
    """给 RFM 打分（1-5 分，按分位数）。"""
    df = rfm_df.copy()

    # Recency: 越小越好 → 分位数反转
    df["R_score"] = 5 - pd.qcut(df["recency"], q=5, labels=[1, 2, 3, 4, 5]).astype(int)

    # Frequency: 越大越好
    df["F_score"] = pd.qcut(df["frequency"], q=5, labels=[1, 2, 3, 4, 5], duplicates="drop").astype(int)

    # Monetary: 越大越好
    df["M_score"] = pd.qcut(df["monetary"], q=5, labels=[1, 2, 3, 4, 5], duplicates="drop").astype(int)

    return df


def compute_rfm_segment(rfm_df: pd.DataFrame) -> pd.DataFrame:
    """生成 8 类 RFM 分群标签。

    分类逻辑：
      R >= 4, F >= 4, M >= 4 → 核心价值客户
      R >= 4, F < 4        → 潜力客户
      R < 3, F >= 3        → 沉睡客户
      R < 2                → 流失客户
      其他                   → 一般客户
    """
    df = rfm_df.copy()
    conditions = [
        (df["R_score"] >= 4) & (df["F_score"] >= 4) & (df["M_score"] >= 4),
        (df["R_score"] >= 4) & (df["F_score"] < 4),
        (df["R_score"] >= 3) & (df["F_score"] < 3),
        (df["R_score"] < 3),
    ]
    choices = ["核心价值", "潜力客户", "一般维持", "流失风险"]

    # 精细化分群
    segments = []
    for _, row in df.iterrows():
        rs, fs, ms = row["R_score"], row["F_score"], row["M_score"]
        if rs >= 4 and fs >= 4 and ms >= 4:
            segments.append("核心价值")
        elif rs >= 4 and fs >= 4:
            segments.append("重要发展")
        elif rs >= 4 and fs < 3:
            segments.append("潜力客户")
        elif rs >= 3 and fs >= 3:
            segments.append("一般维持")
        elif rs >= 3:
            segments.append("一般挽留")
        elif rs < 2:
            segments.append("流失客户")
        elif rs < 3:
            segments.append("沉睡客户")
        else:
            segments.append("其他")

    df["rfm_segment"] = segments
    return df


# ============================================================
# 4.2 行为特征 (items 214-219)
# ============================================================

def compute_behavior_features(traffic_df: pd.DataFrame) -> pd.DataFrame:
    """从 traffic 数据统计用户行为特征。

    Returns:
        DataFrame: user_id, total_events, view_home, view_product, ..., active_days, avg_daily_events, mobile_ratio
    """
    df = traffic_df.copy()
    df["event_date"] = pd.to_datetime(df["event_date"])

    # 各事件类型计数
    event_counts = df.pivot_table(
        index="user_id", columns="event_type", values="event_id",
        aggfunc="count", fill_value=0
    ).reset_index()

    # 总行为数
    event_counts["total_events"] = event_counts.drop(columns=["user_id"]).sum(axis=1)

    # 活跃天数
    active_days = df.groupby("user_id")["event_date"].nunique().reset_index(name="active_days")

    # 设备占比
    device = df.pivot_table(
        index="user_id", columns="device", values="event_id",
        aggfunc="count", fill_value=0
    ).reset_index()
    device["mobile_ratio"] = device.get("mobile", 0) / (device.get("mobile", 0) + device.get("desktop", 1))

    # 搜索次数
    search_count = df[df["event_type"] == "search"].groupby("user_id").size().reset_index(name="search_count")

    # 合并
    result = event_counts.merge(active_days, on="user_id", how="left")
    result = result.merge(device[["user_id", "mobile_ratio"]], on="user_id", how="left")
    result = result.merge(search_count, on="user_id", how="left")

    result["search_count"] = result["search_count"].fillna(0)
    result["mobile_ratio"] = result["mobile_ratio"].fillna(0)
    result["avg_daily_events"] = result["total_events"] / result["active_days"].clip(lower=1)

    return result


# ============================================================
# 4.3 时间窗口行为特征 (items 220-223)
# ============================================================

def compute_time_window_features(traffic_df: pd.DataFrame, reference_date: str) -> pd.DataFrame:
    """计算最近 7/30/90 天行为特征（向量化版本）。

    Args:
        traffic_df: 含 event_date 和 event_type 列
        reference_date: 参考日期
    """
    df = traffic_df.copy()
    df["event_date"] = pd.to_datetime(df["event_date"])
    ref = pd.Timestamp(reference_date)

    windows = {"7d": 7, "30d": 30, "90d": 90}

    result_parts = []
    for name, days in windows.items():
        cutoff = ref - pd.Timedelta(days=days)
        w = df[df["event_date"] >= cutoff]

        # 总事件数
        events = w.groupby("user_id").size().reset_index(name=f"events_{name}")

        # 浏览数（view_home + view_product 等）
        is_view = w["event_type"].str.contains("view", na=False)
        views = w[is_view].groupby("user_id").size().reset_index(name=f"views_{name}")

        # 加购数
        cart = w[w["event_type"] == "add_to_cart"].groupby("user_id").size().reset_index(name=f"cart_{name}")

        # 活跃天数
        active = w.groupby("user_id")["event_date"].nunique().reset_index(name=f"active_days_{name}")

        # 合并
        part = events.merge(views, on="user_id", how="outer")
        part = part.merge(cart, on="user_id", how="outer")
        part = part.merge(active, on="user_id", how="outer")

        if result_parts:
            result_parts.append(part)
        else:
            result_parts = [part]

    # 合并所有窗口
    result = result_parts[0]
    for p in result_parts[1:]:
        result = result.merge(p, on="user_id", how="outer")

    # 填充 NaN 为 0
    for col in result.columns:
        if col != "user_id":
            result[col] = result[col].fillna(0).astype(int)

    return result


# ============================================================
# 4.4 优惠券特征 (items 224-229)
# ============================================================

def compute_coupon_features(coupon_df: pd.DataFrame) -> pd.DataFrame:
    """统计每个用户的优惠券使用特征。

    Args:
        coupon_df: fact_coupon_use DataFrame
    """
    df = coupon_df.copy()
    df["issued_date"] = pd.to_datetime(df["issued_date"])
    df["used_date"] = pd.to_datetime(df["used_date"])

    result = df.groupby("user_id").agg(
        coupons_issued_count=("user_coupon_id", "count"),
        coupons_used_count=("is_used", lambda x: (x == 1).sum()),
        avg_coupon_discount=("discount", "mean"),
        total_coupon_savings=("discount", "sum"),
    ).reset_index()

    result["coupon_use_rate"] = result["coupons_used_count"] / result["coupons_issued_count"].clip(lower=1)

    # 距上次用券天数
    last_use = df[df["is_used"] == 1].groupby("user_id")["used_date"].max().reset_index(name="last_coupon_date")
    result = result.merge(last_use, on="user_id", how="left")
    result["days_since_last_coupon"] = (pd.Timestamp.now() - result["last_coupon_date"]).dt.days
    result["days_since_last_coupon"] = result["days_since_last_coupon"].fillna(999)

    result["avg_coupon_discount"] = result["avg_coupon_discount"].fillna(0)
    result["total_coupon_savings"] = result["total_coupon_savings"].fillna(0)

    return result


# ============================================================
# 4.5 品类偏好特征 (items 230-234)
# ============================================================

def compute_category_features(order_items_df: pd.DataFrame, product_df: pd.DataFrame) -> pd.DataFrame:
    """计算用户品类偏好特征。

    Args:
        order_items_df: fact_order_item
        product_df: dim_product (含 category_name, price_band 或 price)
    """
    merged = order_items_df.merge(product_df[["sku_id", "category_name"]], on="sku_id", how="left")

    # TOP 品类
    user_cat = merged.groupby(["user_id", "category_name"]).size().reset_index(name="cnt")
    top_cat = user_cat.loc[user_cat.groupby("user_id")["cnt"].idxmax()][["user_id", "category_name"]]
    top_cat.columns = ["user_id", "top_category"]

    # 品类多样性
    diversity = user_cat.groupby("user_id")["category_name"].nunique().reset_index(name="category_diversity")

    # 均价
    avg_price = merged.groupby("user_id")["unit_price"].mean().reset_index(name="avg_unit_price")

    # 高端/低端价格带占比（price > 500 = high, price < 100 = low）
    if "price" in product_df.columns:
        product_with_price = merged.merge(product_df[["sku_id", "price"]], on="sku_id", how="left")
        product_with_price["is_high"] = (product_with_price["price"] > 500).astype(int)
        product_with_price["is_low"] = (product_with_price["price"] < 100).astype(int)
        price_ratio = product_with_price.groupby("user_id").agg(
            high_price_ratio=("is_high", "mean"),
            low_price_ratio=("is_low", "mean"),
        ).reset_index()
    else:
        merged_copy = merged.copy()
        merged_copy["is_high"] = (merged_copy["unit_price"] > 500).astype(int)
        merged_copy["is_low"] = (merged_copy["unit_price"] < 100).astype(int)
        price_ratio = merged_copy.groupby("user_id").agg(
            high_price_ratio=("is_high", "mean"),
            low_price_ratio=("is_low", "mean"),
        ).reset_index()

    # 合并
    result = top_cat.merge(diversity, on="user_id", how="outer")
    result = result.merge(avg_price, on="user_id", how="outer")
    result = result.merge(price_ratio, on="user_id", how="outer")
    result["category_diversity"] = result["category_diversity"].fillna(0)

    return result


# ============================================================
# 4.6 购物行为特征 (items 235-241)
# ============================================================

def compute_shopping_features(orders_df: pd.DataFrame, refunds_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """计算购物行为特征。

    Returns:
        DataFrame: user_id, monthly_orders, avg_order_interval, first_order_days, lifecycle_days, weekend_ratio, has_refund, refund_count
    """
    df = orders_df.copy()
    df["order_date"] = pd.to_datetime(df["order_date"])
    now = pd.Timestamp.now()

    result = df.groupby("user_id").agg(
        first_order_date=("order_date", "min"),
        last_order_date=("order_date", "max"),
        order_count=("order_id", "nunique"),
    ).reset_index()

    # 月均购买频次
    result["lifecycle_days"] = (result["last_order_date"] - result["first_order_date"]).dt.days
    result["lifecycle_months"] = (result["lifecycle_days"] / 30).clip(lower=1)
    result["monthly_orders"] = result["order_count"] / result["lifecycle_months"]

    # 平均下单间隔
    result["avg_order_interval"] = result["lifecycle_days"] / result["order_count"].clip(lower=1)

    # 首次购买距今天数
    result["first_order_days_ago"] = (now - result["first_order_date"]).dt.days

    # 周末订单占比
    df["is_weekend"] = df["order_date"].dt.weekday.isin([5, 6]).astype(int)
    weekend_ratio = df.groupby("user_id")["is_weekend"].mean().reset_index(name="weekend_order_ratio")
    result = result.merge(weekend_ratio, on="user_id", how="left")

    # 退款特征
    if refunds_df is not None:
        refund_count = refunds_df.groupby("user_id").size().reset_index(name="refund_count")
        result = result.merge(refund_count, on="user_id", how="left")
        result["refund_count"] = result["refund_count"].fillna(0)
        result["has_refund"] = (result["refund_count"] > 0).astype(int)
    else:
        result["has_refund"] = 0
        result["refund_count"] = 0

    result["weekend_order_ratio"] = result["weekend_order_ratio"].fillna(0)

    return result.drop(columns=["first_order_date", "last_order_date"])


# ============================================================
# 4.7 合并用户宽表 (items 242-251)
# ============================================================

def build_user_wide_table(
    reference_date: Optional[str] = None,
    save_csv: bool = True,
) -> pd.DataFrame:
    """构建完整用户宽表。

    整合：dim_user + RFM + 行为 + 时间窗口 + 优惠券 + 品类偏好 + 购物行为

    Args:
        reference_date: 参考日期（默认数据最后一天）
        save_csv: 是否保存 CSV
    Returns:
        DataFrame: 用户宽表（一行一个 user_id）
    """
    conn = get_db_connection()
    logger.info("开始构建用户宽表...")

    try:
        # ---- 加载数据 ----
        logger.info("加载基础数据...")
        users = pd.read_sql("SELECT * FROM dim_user", conn)
        orders = pd.read_sql("SELECT * FROM fact_order", conn)
        order_items = pd.read_sql("SELECT * FROM fact_order_item", conn)
        traffic = pd.read_sql("SELECT * FROM fact_traffic WHERE user_id IS NOT NULL AND user_id != ''", conn)
        coupons = pd.read_sql("SELECT * FROM fact_coupon_use", conn)
        refunds = pd.read_sql("SELECT * FROM fact_refund", conn)
        products = pd.read_sql("SELECT * FROM dim_product", conn)

        if reference_date is None:
            reference_date = orders["order_date"].max()
        ref_date = str(reference_date)
        logger.info(f"参考日期: {ref_date}")

        # ---- 逐模块计算 ----
        logger.info("计算 RFM...")
        rfm = compute_rfm(orders, ref_date)
        rfm = compute_rfm_scores(rfm)
        rfm = compute_rfm_segment(rfm)

        logger.info("计算行为特征...")
        behavior = compute_behavior_features(traffic)

        logger.info("计算时间窗口特征...")
        time_window = compute_time_window_features(traffic, ref_date)

        logger.info("计算优惠券特征...")
        coupon_features = compute_coupon_features(coupons)

        logger.info("计算品类偏好...")
        category_features = compute_category_features(order_items, products)

        logger.info("计算购物行为...")
        shopping = compute_shopping_features(orders, refunds)

        # ---- 合并 ----
        logger.info("合并所有特征...")
        wide = users.copy()

        # 合并 RFM
        wide = wide.merge(rfm, on="user_id", how="left")

        # 合并行为
        wide = wide.merge(behavior, on="user_id", how="left")

        # 合并时间窗口
        wide = wide.merge(time_window, on="user_id", how="left")

        # 合并优惠券
        wide = wide.merge(coupon_features, on="user_id", how="left")

        # 合并品类偏好
        wide = wide.merge(category_features, on="user_id", how="left")

        # 合并购物行为
        wide = wide.merge(shopping, on="user_id", how="left")

        # ---- 填充无行为用户 ----
        # 数值列填 0
        num_cols = wide.select_dtypes(include=[np.number]).columns
        for col in num_cols:
            if col not in ["user_id", "birth_year"]:
                wide[col] = wide[col].fillna(0)

        # 类别列填默认值
        cat_cols = wide.select_dtypes(include=["object"]).columns
        for col in cat_cols:
            if col not in ["user_id", "name", "city", "register_date"]:
                wide[col] = wide[col].fillna("unknown")

        # RFM segment 特殊处理
        wide["rfm_segment"] = wide["rfm_segment"].fillna("无订单")
        wide["R_score"] = wide["R_score"].fillna(0)
        wide["F_score"] = wide["F_score"].fillna(0)
        wide["M_score"] = wide["M_score"].fillna(0)

        logger.info(f"用户宽表构建完成: {wide.shape}")

        # ---- 验证 ----
        assert wide["user_id"].nunique() == len(wide), "user_id 不唯一！"
        assert len(wide) == 20000, f"行数不符: {len(wide)} != 20000"
        logger.info("主键唯一性和行数验证通过 ✅")

        # ---- 保存 ----
        if save_csv:
            output_path = "user_wide_table.csv"
            wide.to_csv(output_path, index=False)
            logger.info(f"已保存: {output_path}")

        return wide
    finally:
        conn.close()


# ============================================================
# 4.8 特征重要性预分析 (items 252-256)
# ============================================================

def analyze_feature_importance(wide_df: pd.DataFrame, target_col: Optional[str] = None) -> dict:
    """特征重要性分析。

    如果提供了 target_col（如 'will_repurchase'），用随机森林计算重要性。
    否则只做相关性分析。
    """
    # 选数值列
    num_cols = wide_df.select_dtypes(include=[np.number]).columns.tolist()
    # 排除 ID 和 score 类
    exclude = ["user_id", "birth_year", "R_score", "F_score", "M_score"]
    features = [c for c in num_cols if c not in exclude and not c.startswith("_")]

    df_num = wide_df[features].copy()

    # 相关性矩阵
    corr_matrix = df_num.corr()

    # 高相关特征对 (r > 0.8)
    high_corr_pairs = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i + 1, len(corr_matrix.columns)):
            if abs(corr_matrix.iloc[i, j]) > 0.8:
                high_corr_pairs.append({
                    "feature1": corr_matrix.columns[i],
                    "feature2": corr_matrix.columns[j],
                    "correlation": round(corr_matrix.iloc[i, j], 4),
                })

    result = {"correlation_pairs": high_corr_pairs[:20]}

    # 如果有目标列，用随机森林计算重要性
    if target_col and target_col in wide_df.columns:
        y = wide_df[target_col].fillna(0).astype(int)
        X = df_num.fillna(0)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
        rf.fit(X_scaled, y)

        importances = pd.DataFrame({
            "feature": features,
            "importance": rf.feature_importances_,
        }).sort_values("importance", ascending=False)

        result["top_features"] = importances.head(15).to_dict(orient="records")

    return result


# ============================================================
# 4.9 商品建模宽表 (items 257-261)
# ============================================================

def build_product_wide_table(save_csv: bool = True) -> pd.DataFrame:
    """构建商品宽表（一行一个 SKU）。

    特征：总销量、总销售额、总毛利、平均评分、退款率、库存周转率、销售趋势。
    """
    conn = get_db_connection()
    logger.info("开始构建商品宽表...")

    try:
        products = pd.read_sql("SELECT * FROM dim_product", conn)
        order_items = pd.read_sql("SELECT * FROM fact_order_item", conn)
        orders = pd.read_sql("SELECT * FROM fact_order WHERE status IN ('paid','completed')", conn)
        reviews = pd.read_sql("SELECT * FROM fact_product_review", conn)
        refunds = pd.read_sql("SELECT * FROM fact_refund WHERE status='approved'", conn)
        inventory = pd.read_sql("SELECT * FROM fact_inventory_movement", conn)

        # 关联有效订单
        oi = order_items.merge(orders[["order_id"]], on="order_id")

        # 毛利 = SUM((unit_price - unit_cost) * quantity - discount_amount)
        oi["gross_profit"] = (oi["unit_price"] - oi["unit_cost"]) * oi["quantity"] - oi["discount_amount"]
        profit = oi.groupby("sku_id")["gross_profit"].sum().reset_index(name="total_gross_profit")

        # 每个 SKU 统计
        sku_stats = oi.groupby("sku_id").agg(
            total_quantity=("quantity", "sum"),
            total_sales=("line_amount", "sum"),
            avg_order_price=("unit_price", "mean"),
        ).reset_index()
        sku_stats = sku_stats.merge(profit, on="sku_id", how="left")
        sku_stats["total_gross_profit"] = sku_stats["total_gross_profit"].fillna(0)

        # 平均评分
        avg_rating = reviews.groupby("sku_id")["rating"].mean().reset_index(name="avg_rating")
        sku_stats = sku_stats.merge(avg_rating, on="sku_id", how="left")
        sku_stats["avg_rating"] = sku_stats["avg_rating"].fillna(0)

        # 退款率（按 SKU 从 order_items + refunds 关联）
        refund_skus = refunds.merge(
            order_items[["order_id", "sku_id"]], on="order_id", how="inner"
        ).groupby("sku_id").size().reset_index(name="refund_count")
        sku_stats = sku_stats.merge(refund_skus, on="sku_id", how="left")
        sku_stats["refund_count"] = sku_stats["refund_count"].fillna(0)
        sku_stats["refund_rate"] = sku_stats["refund_count"] / sku_stats["total_quantity"].clip(lower=1)

        # 库存周转率（近似：销量 / 平均库存）
        stock = inventory.groupby("sku_id").agg(
            total_in=("quantity", lambda x: x[inventory["movement_type"] == "in"].sum()),
            total_out=("quantity", lambda x: x[inventory["movement_type"] == "out"].sum()),
        ).reset_index()
        stock["avg_inventory"] = (stock["total_in"] - stock["total_out"]).clip(lower=1)
        stock["turnover_rate"] = stock["total_out"] / stock["avg_inventory"]
        sku_stats = sku_stats.merge(stock[["sku_id", "turnover_rate"]], on="sku_id", how="left")
        sku_stats["turnover_rate"] = sku_stats["turnover_rate"].fillna(0)

        # 销售趋势（简单版：近 3 月 vs 前 3 月）
        oi["order_date"] = pd.to_datetime(oi["order_date"])
        max_date = oi["order_date"].max()
        recent_cutoff = max_date - pd.Timedelta(days=90)
        older_cutoff = max_date - pd.Timedelta(days=180)

        recent = oi[oi["order_date"] >= recent_cutoff].groupby("sku_id")["quantity"].sum().reset_index(name="recent_qty")
        older = oi[(oi["order_date"] >= older_cutoff) & (oi["order_date"] < recent_cutoff)].groupby("sku_id")["quantity"].sum().reset_index(name="older_qty")
        trend = recent.merge(older, on="sku_id", how="left")
        trend["sales_trend"] = (trend["recent_qty"] - trend["older_qty"]) / trend["older_qty"].clip(lower=1)
        sku_stats = sku_stats.merge(trend[["sku_id", "sales_trend"]], on="sku_id", how="left")
        sku_stats["sales_trend"] = sku_stats["sales_trend"].fillna(0).clip(-1, 5)

        # 合并产品属性
        result = products.merge(sku_stats, on="sku_id", how="left")

        logger.info(f"商品宽表构建完成: {result.shape}")

        if save_csv:
            output_path = "product_wide_table.csv"
            result.to_csv(output_path, index=False)
            logger.info(f"已保存: {output_path}")

        return result
    finally:
        conn.close()
