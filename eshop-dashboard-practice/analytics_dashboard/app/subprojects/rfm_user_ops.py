"""R3 RFM 用户运营

RFM 分层、Cohort 留存、用户画像、运营动作。
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..data_access import get_db_connection
from ..subprojects.feature_engineering import (
    compute_rfm, compute_rfm_scores, compute_rfm_segment,
    build_user_wide_table,
)

logger = logging.getLogger("analytics.r3")

SEGMENT_STRATEGIES = {
    "核心价值": {
        "description": "高频高消费近期活跃，平台最优质客户",
        "strategy": "VIP 专属服务 + 新品优先体验 + 高端商品推荐",
        "action": "发高端品专属券，不扰动价格体系",
    },
    "重要发展": {
        "description": "高频高消费但近期活跃度略低",
        "strategy": "大促召回 + 会员升级引导 + 积分激励",
        "action": "发大额满减券，引导升 platinum",
    },
    "潜力客户": {
        "description": "近期活跃但消费力待提升",
        "strategy": "客单价提升 + 品类拓展 + 首单升级",
        "action": "发跨品类券，推荐高关联商品",
    },
    "一般维持": {
        "description": "中等活跃度和消费力",
        "strategy": "维持活跃 + 提升频次 + 小额激励",
        "action": "发小额无门槛券，签到积分",
    },
    "一般挽留": {
        "description": "消费力尚可但活跃度下降",
        "strategy": "流失预警 + 定向召回 + 大促触达",
        "action": "发限时大额券，push 消息触达",
    },
    "流失风险": {
        "description": "曾经消费但已长时间未购买",
        "strategy": "强召回 + 高折扣 + 首单优惠",
        "action": "发新人级大额券，短信/邮件触达",
    },
    "沉睡客户": {
        "description": "近期沉默，历史消费一般",
        "strategy": "内容唤醒 + 低价爆款 + 限时秒杀",
        "action": "发低价引流品券，参加秒杀活动",
    },
    "流失客户": {
        "description": "长期未购买或低频低消费",
        "strategy": "低成本召回 + 品牌再教育 + 转介绍激励",
        "action": "发极低门槛券，邀请有礼活动",
    },
}


# ============================================================
# 7.1 RFM 分层
# ============================================================

def compute_rfm_layers() -> dict:
    """RFM 分群总览：每类的人数、GMV、毛利、策略。"""
    wide = build_user_wide_table(save_csv=False)

    segments = wide.groupby("rfm_segment").agg(
        user_count=("user_id", "nunique"),
        total_gmv=("monetary", "sum"),
        avg_recency=("recency", "mean"),
        avg_frequency=("frequency", "mean"),
        avg_monetary=("monetary", "mean"),
    ).reset_index()

    segments["gmv_share"] = segments["total_gmv"] / segments["total_gmv"].sum() * 100
    segments["gmv_share"] = segments["gmv_share"].round(2)

    result = []
    for _, row in segments.iterrows():
        seg = row["rfm_segment"]
        strategy = SEGMENT_STRATEGIES.get(seg, {})
        result.append({
            "segment": seg,
            "user_count": int(row["user_count"]),
            "total_gmv": round(float(row["total_gmv"]), 2),
            "gmv_share": round(float(row["gmv_share"]), 2),
            "avg_recency": round(float(row["avg_recency"]), 1),
            "avg_frequency": round(float(row["avg_frequency"]), 1),
            "avg_monetary": round(float(row["avg_monetary"]), 2),
            "description": strategy.get("description", ""),
            "strategy": strategy.get("strategy", ""),
            "action": strategy.get("action", ""),
        })

    result.sort(key=lambda x: -x["user_count"])
    return {"segments": result}


# ============================================================
# 7.2 Cohort 留存
# ============================================================

def compute_cohort_retention() -> dict:
    """按注册月份分 Cohort，计算第 1/2/3/6/12 月留存率。"""
    conn = get_db_connection()
    try:
        users = pd.read_sql("""
            SELECT user_id, strftime('%Y-%m', register_date) as cohort_month
            FROM dim_user WHERE register_date IS NOT NULL
        """, conn)

        orders = pd.read_sql("""
            SELECT user_id, strftime('%Y-%m', order_date) as order_month
            FROM fact_order WHERE status IN ('paid','completed')
        """, conn)

        orders["order_month"] = pd.to_datetime(orders["order_month"])
        users["cohort_month"] = pd.to_datetime(users["cohort_month"])

        # 合并 cohort 信息
        merged = orders.merge(users, on="user_id", how="inner")
        merged["month_diff"] = (
            (merged["order_month"].dt.year - merged["cohort_month"].dt.year) * 12 +
            (merged["order_month"].dt.month - merged["cohort_month"].dt.month)
        )

        # 每个 cohort 的用户总数
        cohort_size = users.groupby("cohort_month")["user_id"].nunique()

        # 生成留存矩阵
        retention_data = []
        for cohort, size in cohort_size.items():
            row = {"cohort": str(cohort)[:7], "size": int(size)}
            for m in [1, 2, 3, 6, 12]:
                active = merged[
                    (merged["cohort_month"] == cohort) & (merged["month_diff"] == m)
                ]["user_id"].nunique()
                row[f"month_{m}"] = int(active)
                row[f"retention_{m}"] = round(active / size * 100, 2) if size else 0
            retention_data.append(row)

        # 热力图数据：按 cohort × month 的留存率
        heatmap = []
        for r in retention_data:
            for m in [1, 2, 3, 6, 12]:
                heatmap.append({
                    "cohort": r["cohort"],
                    "month": m,
                    "rate": r.get(f"retention_{m}", 0),
                })

        return {"matrix": retention_data, "heatmap": heatmap}
    finally:
        conn.close()


# ============================================================
# 7.3 用户画像
# ============================================================

def get_user_profile(user_id: str) -> dict:
    """单个用户完整画像。"""
    conn = get_db_connection()
    try:
        user = pd.read_sql("SELECT * FROM dim_user WHERE user_id=?", conn, params=[user_id])
        if user.empty:
            return {"error": f"用户不存在: {user_id}"}

        orders = pd.read_sql("""
            SELECT * FROM fact_order WHERE user_id=? AND status IN ('paid','completed')
            ORDER BY order_date DESC
        """, conn, params=[user_id])

        traffic = pd.read_sql("""
            SELECT event_type, COUNT(*) as cnt FROM fact_traffic
            WHERE user_id=? GROUP BY event_type ORDER BY cnt DESC LIMIT 10
        """, conn, params=[user_id])

        coupons = pd.read_sql("""
            SELECT COUNT(*) as issued, SUM(is_used) as used
            FROM fact_coupon_use WHERE user_id=?
        """, conn, params=[user_id])

        refunds = pd.read_sql("""
            SELECT COUNT(*) as cnt, SUM(amount) as total
            FROM fact_refund WHERE user_id=? AND status='approved'
        """, conn, params=[user_id])

        return {
            "user": user.iloc[0].to_dict(),
            "order_summary": {
                "total_orders": len(orders),
                "total_spent": round(float(orders["paid_amount"].sum()), 2),
                "first_order": str(orders["order_date"].min()),
                "last_order": str(orders["order_date"].max()),
            },
            "top_events": traffic.set_index("event_type")["cnt"].to_dict(),
            "coupons": {
                "issued": int(coupons["issued"].iloc[0]),
                "used": int(coupons["used"].iloc[0]),
            },
            "refunds": {
                "count": int(refunds["cnt"].iloc[0]),
                "amount": round(float(refunds["total"].iloc[0] or 0), 2),
            },
        }
    finally:
        conn.close()


def get_segment_comparison() -> dict:
    """分群对比雷达图数据（6 维度：人数/GMV/客单价/频次/近度/退款率）。"""
    wide = build_user_wide_table(save_csv=False)
    segments = wide.groupby("rfm_segment").agg(
        user_count=("user_id", "nunique"),
        total_gmv=("monetary", "sum"),
        avg_aov=("monetary", lambda x: x.sum() / x.count() if x.count() else 0),
        avg_frequency=("frequency", "mean"),
        avg_recency=("recency", "mean"),
        refund_rate=("has_refund", "mean"),
    ).reset_index()

    return {
        "labels": ["人数", "GMV", "客单价", "频次", "近度(越小越好)", "退款率(越小越好)"],
        "segments": segments.to_dict(orient="records"),
    }


def search_users(keyword: str = "", segment: str = "", limit: int = 50) -> list:
    """用户搜索和筛选。"""
    conn = get_db_connection()
    try:
        # 先查用户宽表获取分群信息
        wide = build_user_wide_table(save_csv=False)
        wide = wide[["user_id", "name", "province", "member_level", "rfm_segment",
                      "recency", "frequency", "monetary"]]

        if segment:
            wide = wide[wide["rfm_segment"] == segment]
        if keyword:
            mask = wide["name"].str.contains(keyword, na=False) | wide["user_id"].str.contains(keyword, na=False)
            wide = wide[mask]

        wide = wide.head(limit)
        return wide.to_dict(orient="records")
    finally:
        conn.close()


# ============================================================
# 7.4 运营动作
# ============================================================

def batch_tag_users(user_ids: List[str], tag: str) -> dict:
    """批量打标签。"""
    # 写入 admin_action_logs（如果表结构支持）
    conn = get_db_connection()
    try:
        for uid in user_ids[:100]:  # 限制批量大小
            conn.execute(
                "INSERT INTO admin_action_logs (action_type, target_id, detail, created_at) VALUES (?, ?, ?, ?)",
                ["tag_user", uid, tag, datetime.now().isoformat()]
            )
        conn.commit()
        return {"ok": True, "tagged": min(len(user_ids), 100), "tag": tag}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def export_user_list(segment: str = "", format: str = "json") -> list:
    """导出用户名单。"""
    wide = build_user_wide_table(save_csv=False)
    if segment:
        wide = wide[wide["rfm_segment"] == segment]
    cols = ["user_id", "name", "province", "member_level", "rfm_segment", "recency", "frequency", "monetary"]
    return wide[cols].to_dict(orient="records")


def generate_coupon_suggestions(segment: str) -> dict:
    """根据分群生成优惠券发放建议。"""
    strategy = SEGMENT_STRATEGIES.get(segment, {})
    wide = build_user_wide_table(save_csv=False)
    users = wide[wide["rfm_segment"] == segment]

    return {
        "segment": segment,
        "user_count": len(users),
        "strategy": strategy.get("strategy", ""),
        "action": strategy.get("action", ""),
        "suggested_coupon": {
            "核心价值": "专属券 9 折，上限 ¥200",
            "重要发展": "满 ¥500 减 ¥80",
            "潜力客户": "跨品类券 满 ¥200 减 ¥30",
            "一般维持": "无门槛 ¥10 券",
            "一般挽留": "限时满 ¥300 减 ¥60",
            "流失风险": "大额满 ¥200 减 ¥50",
            "沉睡客户": "秒杀资格券 + ¥5 无门槛",
            "流失客户": "新人券 满 ¥100 减 ¥30",
        }.get(segment, "通用 满 ¥100 减 ¥10"),
    }


def log_admin_action(action_type: str, target_id: str, detail: str) -> dict:
    """记录运营动作。"""
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO admin_action_logs (action_type, target_id, detail, created_at) VALUES (?, ?, ?, ?)",
            [action_type, target_id, detail, datetime.now().isoformat()]
        )
        conn.commit()
        return {"ok": True, "action": action_type}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()
