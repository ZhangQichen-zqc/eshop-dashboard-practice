"""R11 综合决策中心

整合 R0-R10 分析结果 → 健康度评分 → 机会/风险识别 → 动作清单。
"""

import logging
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd

from ..data_access import get_db_connection, query_metrics, query_quality_report

logger = logging.getLogger("analytics.r11")


# ============================================================
# 15.1 决策摘要
# ============================================================

def compute_health_score() -> dict:
    """经营健康度评分（0-100 分）。

    维度权重：
      GMV 趋势 (20) + 毛利率 (20) + 退款率 (15) + 转化率 (15)
      + 配送时效 (10) + 库存周转 (10) + 客户活跃度 (10)
    """
    score = 0
    components = []

    try:
        metrics = query_metrics()
        conn = get_db_connection()

        # 1. GMV 健康度 (20)
        monthly = pd.read_sql("""
            SELECT strftime('%Y-%m', order_date) as ym, SUM(paid_amount) as gmv
            FROM fact_order WHERE status IN ('paid','completed')
            GROUP BY ym ORDER BY ym DESC LIMIT 6
        """, conn)
        if len(monthly) >= 2:
            trend = (monthly.iloc[0]["gmv"] - monthly.iloc[-1]["gmv"]) / monthly.iloc[-1]["gmv"]
            gmv_score = min(20, max(0, 12 + trend * 30))
        else:
            gmv_score = 15
        components.append({"dimension": "GMV 趋势", "score": round(gmv_score, 1), "weight": 20})

        # 2. 毛利率 (20)
        gm = metrics["gross_margin"]
        margin_score = min(20, gm * 0.4) if gm else 15
        components.append({"dimension": "毛利率", "score": round(margin_score, 1), "weight": 20, "value": f"{gm}%"})

        # 3. 退款率 (15) — 越低越好
        refunds = pd.read_sql("SELECT COUNT(*) as n FROM fact_refund WHERE status='approved'", conn).iloc[0, 0]
        orders = pd.read_sql("SELECT COUNT(*) as n FROM fact_order", conn).iloc[0, 0]
        rf_rate = refunds / orders * 100 if orders else 0
        refund_score = max(0, 15 - rf_rate * 1.5)
        components.append({"dimension": "退款率", "score": round(refund_score, 1), "weight": 15, "value": f"{rf_rate:.1f}%"})

        # 4. 转化率 (15)
        total_s = pd.read_sql("SELECT COUNT(DISTINCT session_id) FROM fact_traffic", conn).iloc[0, 0]
        pay_s = pd.read_sql("SELECT COUNT(DISTINCT session_id) FROM fact_traffic WHERE event_type='pay_success'", conn).iloc[0, 0]
        conv = pay_s / total_s * 100 if total_s else 0
        conv_score = min(15, conv * 0.3)
        components.append({"dimension": "转化率", "score": round(conv_score, 1), "weight": 15, "value": f"{conv:.1f}%"})

        # 5. 配送时效 (10)
        late_rate = pd.read_sql("SELECT AVG(is_late) FROM fact_fulfillment", conn).iloc[0, 0] or 0
        delivery_score = max(0, 10 - late_rate * 20)
        components.append({"dimension": "配送时效", "score": round(delivery_score, 1), "weight": 10, "value": f"延迟率{late_rate*100:.1f}%"})

        # 6. 库存周转 (10)
        inv = pd.read_sql("""
            SELECT sku_id, SUM(CASE WHEN movement_type='out' THEN quantity ELSE 0 END) as out_qty,
                   SUM(CASE WHEN movement_type='in' THEN quantity ELSE -quantity END) as stock
            FROM fact_inventory_movement GROUP BY sku_id
        """, conn)
        avg_turnover = (inv["out_qty"] / (inv["stock"].abs() + 1)).mean()
        turnover_score = min(10, max(0, avg_turnover * 2))
        components.append({"dimension": "库存周转", "score": round(turnover_score, 1), "weight": 10})

        # 7. 客户活跃度 (10)
        active = pd.read_sql("""
            SELECT COUNT(DISTINCT user_id) FROM fact_order
            WHERE status IN ('paid','completed') AND order_date >= date('now','-90 days')
        """, conn).iloc[0, 0]
        active_score = min(10, active / 18000 * 10) if active else 5
        components.append({"dimension": "客户活跃度", "score": round(active_score, 1), "weight": 10})

        conn.close()

        total_score = sum(c["score"] for c in components)
        grade = "A" if total_score >= 85 else ("B" if total_score >= 70 else ("C" if total_score >= 55 else "D"))

        return {
            "total_score": round(total_score, 1),
            "grade": grade,
            "components": components,
            "evaluated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


def identify_opportunities() -> list:
    """TOP 增长机会。"""
    return [
        {
            "rank": 1,
            "title": "直播渠道转化率提升",
            "description": "直播转化率 53.75% 为全渠道最高（平均 49.39%），但 GMV 仅占 4.9%。加大直播投入可直接拉动 GMV。",
            "source": "R2 漏斗诊断 + R1 经营驾驶舱",
            "expected_impact": "直播 GMV 占比从 4.9% → 10%，预计年增 GMV ¥800 万",
            "priority": "P0",
            "confidence": "高",
            "risks": "直播运营成本较高，需评估边际收益",
        },
        {
            "rank": 2,
            "title": "高价值客户复购激活",
            "description": "核心价值客户 1,924 人贡献 25.4% GMV，但流失/沉睡客户合计 10,730 人（53.6%）有待激活。",
            "source": "R3 RFM + R4 复购预测",
            "expected_impact": "召回 10% 流失客户 → 预计增量 ¥365 万/年",
            "priority": "P0",
            "confidence": "高",
            "risks": "召回成本需控制，避免过度打扰",
        },
        {
            "rank": 3,
            "title": "配送履约优化",
            "description": "延迟率 53.7% 导致退款率从 4.76% → 10.32%（+5.6pp）。优化配送可直接降低退款。",
            "source": "R9 履约分析",
            "expected_impact": "延迟率降至 30% → 预计减少退款 ¥200 万/年",
            "priority": "P1",
            "confidence": "中高",
            "risks": "仓储/物流投入大，需分步实施",
        },
    ]


def identify_risks() -> list:
    """TOP 经营风险。"""
    return [
        {
            "rank": 1,
            "title": "GMV 中期回落趋势",
            "description": "2025 H2 GMV 从峰值 ¥1,100 万/月回落至 ¥500-700 万/月，需排查原因。",
            "source": "R1 趋势分析",
            "severity": "高",
            "mitigation": "分析回落原因→调整渠道/品类策略",
        },
        {
            "rank": 2,
            "title": "直播渠道 ROAS 偏低",
            "description": "直播 ROAS 仅 1.94x，远低于 search 9.36x。高转化但低回报。",
            "source": "R8 营销归因",
            "severity": "中",
            "mitigation": "优化直播选品和投放策略",
        },
        {
            "rank": 3,
            "title": "差评率 15.5% 偏高",
            "description": "25,660 条评论中 15.5% 为差评，影响口碑和复购。",
            "source": "R9 评论分析",
            "severity": "中",
            "mitigation": "聚焦高差评商品做质量改进",
        },
    ]


# ============================================================
# 15.2 动作管理
# ============================================================

def get_actions(status: str = None) -> list:
    """获取运营动作列表。"""
    conn = get_db_connection()
    try:
        sql = "SELECT * FROM admin_action_logs ORDER BY created_at DESC LIMIT 50"
        df = pd.read_sql(sql, conn)
        if status:
            df = df[df["action_type"] == status]
        return df.to_dict(orient="records")
    except Exception:
        return []
    finally:
        conn.close()


def create_action(action_type: str, target_id: str, detail: str, priority: str = "P1") -> dict:
    """创建运营动作。"""
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO admin_action_logs (action_type, target_id, detail, created_at) VALUES (?, ?, ?, ?)",
            [action_type, target_id, f"[{priority}] {detail}", datetime.now().isoformat()]
        )
        conn.commit()
        return {"ok": True, "action_type": action_type, "target": target_id, "priority": priority}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


# ============================================================
# 15.3 经营周报
# ============================================================

def generate_weekly_report() -> dict:
    """生成经营周报（整合各模块关键数据）。"""
    try:
        health = compute_health_score()
        opportunities = identify_opportunities()
        risks = identify_risks()

        metrics = query_metrics()

        report = f"""# Course eShop 经营周报

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

## 经营健康度：{health.get('grade', 'N/A')} ({health.get('total_score', 'N/A')}/100)

## 核心指标
- GMV：¥{metrics['gmv']:,.0f} | 毛利率：{metrics['gross_margin']}%
- 订单数：{metrics['order_count']:,} | 客单价：¥{metrics['aov']:,}

## TOP 3 增长机会
"""
        for o in opportunities:
            report += f"\n### {o['rank']}. {o['title']} [{o['priority']}]\n"
            report += f"- {o['description']}\n"
            report += f"- 预期影响：{o['expected_impact']}\n"
            report += f"- 数据来源：{o['source']}\n"

        report += "\n## TOP 3 经营风险\n"
        for r in risks:
            report += f"\n### {r['rank']}. {r['title']} (严重度: {r['severity']})\n"
            report += f"- {r['description']}\n"
            report += f"- 缓解措施：{r['mitigation']}\n"

        report += "\n---\n*自动生成于 Course eShop Dashboard R11 决策中心*"

        return {
            "report": report,
            "health": health,
            "opportunities": opportunities,
            "risks": risks,
            "metrics": metrics,
        }
    except Exception as e:
        return {"error": str(e)}
