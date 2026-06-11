"""R8 营销归因分析

活动 KPI → 优惠券分析 → 增量评估 → 预算建议。
"""

import logging
import warnings
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..data_access import get_db_connection

warnings.filterwarnings("ignore")
logger = logging.getLogger("analytics.r8")


# ============================================================
# 12.1 活动 KPI
# ============================================================

def compute_campaign_kpis() -> dict:
    """计算每个活动的曝光/点击/转化 + CTR/CVR/ROAS/ROI。"""
    conn = get_db_connection()
    try:
        # 广告花费 + 曝光点击
        ads = pd.read_sql("""
            SELECT campaign_id,
                   SUM(impressions) as impressions,
                   SUM(clicks) as clicks,
                   SUM(conversions) as conversions,
                   SUM(spend_amount) as spend
            FROM fact_ads_spend GROUP BY campaign_id
        """, conn)

        # 活动带来的 GMV（关联订单）
        order_gmv = pd.read_sql("""
            SELECT campaign_id, SUM(paid_amount) as gmv
            FROM fact_order WHERE status IN ('paid','completed') AND campaign_id IS NOT NULL
            GROUP BY campaign_id
        """, conn)

        # 活动信息
        camps = pd.read_sql("SELECT * FROM dim_campaign", conn)

        merged = camps.merge(ads, on="campaign_id", how="left")
        merged = merged.merge(order_gmv, on="campaign_id", how="left")

        # 重命名冲突列
        if "channel_x" in merged.columns:
            merged["channel"] = merged["channel_x"]
            merged = merged.drop(columns=["channel_x", "channel_y"])

        merged["impressions"] = merged["impressions"].fillna(0)
        merged["clicks"] = merged["clicks"].fillna(0)
        merged["conversions"] = merged["conversions"].fillna(0)
        merged["spend"] = merged["spend"].fillna(0)
        merged["gmv"] = merged["gmv"].fillna(0)

        # 计算指标
        merged["ctr"] = (merged["clicks"] / merged["impressions"] * 100).fillna(0).round(2)
        merged["cvr"] = (merged["conversions"] / merged["clicks"] * 100).fillna(0).round(2)
        merged["cpc"] = (merged["spend"] / merged["clicks"]).fillna(0).round(2)
        merged["cpm"] = (merged["spend"] / merged["impressions"] * 1000).fillna(0).round(2)
        merged["cpa"] = (merged["spend"] / merged["conversions"]).fillna(0).round(2)
        merged["roas"] = (merged["gmv"] / merged["spend"]).replace([np.inf, -np.inf], 0).fillna(0).round(2)
        merged["roi"] = ((merged["gmv"] - merged["spend"]) / merged["spend"] * 100).replace([np.inf, -np.inf], 0).fillna(0).round(1)

        campaigns = merged.to_dict(orient="records")

        # 按渠道汇总
        chan = merged.groupby("channel").agg(
            campaigns=("campaign_id", "nunique"),
            total_spend=("spend", "sum"),
            total_gmv=("gmv", "sum"),
        ).reset_index()
        chan["roas"] = (chan["total_gmv"] / chan["total_spend"]).replace([np.inf, -np.inf], 0).fillna(0).round(2)

        return {
            "campaigns": campaigns,
            "channel_summary": chan.to_dict(orient="records"),
            "total_spend": round(float(merged["spend"].sum()), 2),
            "total_gmv": round(float(merged["gmv"].sum()), 2),
            "overall_roas": round(float(merged["gmv"].sum() / merged["spend"].sum()), 2) if merged["spend"].sum() else 0,
        }
    finally:
        conn.close()


# ============================================================
# 12.2 优惠券分析
# ============================================================

def analyze_coupons() -> dict:
    """优惠券发放/核销/核销率 + ROAS。"""
    conn = get_db_connection()
    try:
        # coupons 源表自带 issued_count 和 used_count
        coupons = pd.read_sql("""
            SELECT coupon_id, name, campaign_id, threshold, discount,
                   issued_count, used_count
            FROM coupons
        """, conn)

        # 用券订单带来的 GMV
        coupon_gmv = pd.read_sql("""
            SELECT uc.coupon_id, SUM(o.paid_amount) as gmv
            FROM user_coupons uc
            JOIN fact_order o ON uc.order_id = o.order_id
            WHERE o.status IN ('paid','completed') AND uc.used_at IS NOT NULL
            GROUP BY uc.coupon_id
        """, conn)

        merged = coupons.merge(coupon_gmv, on="coupon_id", how="left")
        merged["gmv"] = merged["gmv"].fillna(0)
        merged["issued"] = merged["issued_count"]
        merged["redeemed"] = merged["used_count"]
        merged["redemption_rate"] = (merged["redeemed"] / merged["issued"] * 100).fillna(0).round(2)
        merged["coupon_cost"] = merged["redeemed"] * merged["discount"]
        merged["roas"] = (merged["gmv"] / merged["coupon_cost"]).replace([np.inf, -np.inf], 0).fillna(0).round(2)

        return {
            "coupons": merged.to_dict(orient="records"),
            "total_issued": int(merged["issued"].sum()),
            "total_redeemed": int(merged["redeemed"].sum()),
            "overall_rate": round(float(merged["redeemed"].sum() / merged["issued"].sum() * 100), 2) if merged["issued"].sum() else 0,
        }
    finally:
        conn.close()


def find_coupon_sensitive_users(threshold: float = 0.5) -> dict:
    """识别券敏感/不敏感用户。"""
    conn = get_db_connection()
    try:
        df = pd.read_sql("""
            SELECT user_id,
                   COUNT(used_at IS NOT NULL OR NULL) as used,
                   COUNT(*) as issued,
                   CAST(COUNT(used_at IS NOT NULL OR NULL) AS FLOAT) / COUNT(*) as use_rate
            FROM user_coupons GROUP BY user_id HAVING COUNT(*) >= 3
        """, conn)

        sensitive = df[df["use_rate"] >= threshold]
        insensitive = df[df["use_rate"] < 0.2]

        return {
            "sensitive_users": len(sensitive),
            "insensitive_users": len(insensitive),
            "sensitive_sample": sensitive.head(10).to_dict(orient="records"),
        }
    finally:
        conn.close()


# ============================================================
# 12.3 增量评估
# ============================================================

def compute_increment_analysis() -> dict:
    """对照组增量分析。"""
    conn = get_db_connection()
    try:
        # 筛选 has_control_group=1 的活动
        camps = pd.read_sql("SELECT * FROM dim_campaign WHERE has_control_group=1", conn)

        results = []
        for _, camp in camps.iterrows():
            cid = camp["campaign_id"]
            # 活动组 GMV
            test_gmv = pd.read_sql("""
                SELECT SUM(paid_amount) FROM fact_order
                WHERE campaign_id=? AND status IN ('paid','completed')
            """, conn, params=[cid]).iloc[0, 0] or 0

            # 对照组近似：同期其他渠道订单的均值
            start = camp["start_date"]
            end = camp["end_date"]
            control_gmv = pd.read_sql("""
                SELECT AVG(daily_gmv) FROM (
                    SELECT order_date, SUM(paid_amount) as daily_gmv
                    FROM fact_order WHERE order_date BETWEEN ? AND ?
                      AND status IN ('paid','completed') AND (campaign_id IS NULL OR campaign_id != ?)
                    GROUP BY order_date
                )
            """, conn, params=[start, end, cid]).iloc[0, 0] or 0

            days = max(1, (pd.Timestamp(end) - pd.Timestamp(start)).days + 1)

            results.append({
                "campaign_id": cid,
                "campaign_name": camp["name"],
                "channel": camp["channel"],
                "test_gmv": round(float(test_gmv), 2),
                "estimated_control_gmv": round(float(control_gmv * days), 2),
                "increment": round(float(test_gmv - control_gmv * days), 2),
                "increment_pct": round(float((test_gmv - control_gmv * days) / (control_gmv * days + 1) * 100), 1),
                "budget": float(camp["budget"]) if camp["budget"] else 0,
            })

        results.sort(key=lambda x: -x["increment"])
        return {"control_group_analysis": results}
    finally:
        conn.close()


# ============================================================
# 12.4 预算建议
# ============================================================

def compute_budget_optimization(migrate_pct: float = 20.0) -> dict:
    """渠道预算优化：ROAS 排名 + 模拟预算迁移。"""
    conn = get_db_connection()
    try:
        # 渠道效率
        chan = pd.read_sql("""
            SELECT channel,
                   SUM(spend_amount) as spend,
                   COUNT(DISTINCT campaign_id) as campaigns
            FROM fact_ads_spend GROUP BY channel
        """, conn)

        chan_gmv = pd.read_sql("""
            SELECT channel, SUM(paid_amount) as gmv
            FROM fact_order WHERE status IN ('paid','completed') AND campaign_id IS NOT NULL
            GROUP BY channel
        """, conn)

        merged = chan.merge(chan_gmv, on="channel", how="left")
        merged["gmv"] = merged["gmv"].fillna(0)
        merged["roas"] = (merged["gmv"] / merged["spend"]).replace([np.inf], 0).fillna(0).round(2)
        merged = merged.sort_values("roas", ascending=False)

        total_spend = merged["spend"].sum()
        # 模拟迁移：从最低 ROAS 渠道移 20% 预算到最高 ROAS 渠道
        if len(merged) >= 2:
            best_ch = merged.iloc[0]
            worst_ch = merged.iloc[-1]
            migrated = total_spend * migrate_pct / 100
            new_revenue = migrated * best_ch["roas"]
            old_revenue = migrated * worst_ch["roas"]
            gain = new_revenue - old_revenue
        else:
            migrated = gain = 0

        return {
            "channel_ranking": merged.to_dict(orient="records"),
            "total_spend": round(float(total_spend), 2),
            "suggestion": {
                "increase": merged.head(2)["channel"].tolist() if len(merged) >= 2 else [],
                "maintain": merged.iloc[2:4]["channel"].tolist() if len(merged) >= 4 else [],
                "decrease": merged.tail(2)["channel"].tolist() if len(merged) >= 2 else [],
            },
            "simulation": {
                "migrate_pct": migrate_pct,
                "migrated_amount": round(migrated, 2),
                "estimated_gain": round(gain, 2),
            },
        }
    finally:
        conn.close()
