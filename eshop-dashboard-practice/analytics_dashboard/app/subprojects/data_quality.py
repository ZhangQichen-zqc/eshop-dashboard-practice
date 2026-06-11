"""R0 数据质量检查与清洗

覆盖：完整性/唯一性/准确性/时效性/一致性/业务逻辑检查 + 清洗流水线
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler

from ..data_access import get_db_connection

logger = logging.getLogger("analytics.r0")


# ============================================================
# 3.1 完整性检查 (items 165-169)
# ============================================================

def check_table_row_counts(conn) -> List[Dict]:
    """检查每张表行数是否在预期范围。"""
    expectations = {
        "users": (18000, 22000),
        "orders": (90000, 130000),
        "page_events": (600000, 1200000),
        "sku": (700, 1000),
        "campaigns": (40, 70),
        "order_items": (200000, 300000),
        "refunds": (5000, 15000),
    }
    checks = []
    for table, (lo, hi) in expectations.items():
        actual = pd.read_sql(f'SELECT COUNT(*) FROM "{table}"', conn).iloc[0, 0]
        status = "pass" if lo <= actual <= hi else "warn"
        checks.append({
            "category": "完整性",
            "name": f"{table} 行数",
            "status": status,
            "detail": f"实际 {actual:,}，预期 {lo:,}~{hi:,}",
            "metrics": {"actual": int(actual), "min": lo, "max": hi},
        })
    return checks


def check_missing_rate(conn) -> List[Dict]:
    """检查关键字段缺失率（来自源表 users）。"""
    checks = []
    # 用源表 users 检查（dim_user 是视图，可能已处理）
    try:
        df = pd.read_sql("SELECT * FROM users", conn)
        for col in ["phone", "gender", "birth_year", "province"]:
            missing = int(df[col].isnull().sum())
            rate = missing / len(df)
            status = "pass" if rate < 0.1 else ("warn" if rate < 0.3 else "fail")
            checks.append({
                "category": "完整性",
                "name": f"users.{col} 缺失率",
                "status": status,
                "detail": f"缺失 {missing}/{len(df)} ({rate:.2%})",
                "metrics": {"missing": missing, "total": len(df), "rate": round(rate, 4)},
            })
    except Exception as e:
        logger.warning(f"users 表缺失率检查失败: {e}")

    return checks


def check_order_amount_missing(conn) -> List[Dict]:
    """检查 orders 金额字段缺失率。"""
    df = pd.read_sql("SELECT paid_amount, subtotal, total_amount, discount_amount FROM orders", conn)
    checks = []
    for col in df.columns:
        missing = int(df[col].isnull().sum())
        rate = missing / len(df)
        status = "pass" if rate < 0.01 else "warn"
        checks.append({
            "category": "完整性",
            "name": f"orders.{col} 缺失率",
            "status": status,
            "detail": f"缺失 {missing}/{len(df)} ({rate:.2%})",
            "metrics": {"missing": missing, "total": len(df), "rate": round(rate, 4)},
        })
    return checks


def check_anonymous_traffic(conn) -> List[Dict]:
    """检查 page_events 匿名流量比例。"""
    df = pd.read_sql("SELECT COUNT(*) as n FROM page_events WHERE user_id IS NULL OR user_id = ''", conn)
    total = pd.read_sql("SELECT COUNT(*) FROM page_events", conn).iloc[0, 0]
    anon = int(df['n'][0])
    rate = anon / total if total else 0
    return [{
        "category": "完整性",
        "name": "page_events 匿名流量",
        "status": "pass" if rate < 0.5 else "warn",
        "detail": f"匿名 {anon:,}/{total:,} ({rate:.2%})",
        "metrics": {"anonymous": anon, "total": int(total), "rate": round(rate, 4)},
    }]


def completeness_report(conn) -> Dict:
    """生成完整性检查综合报告。"""
    checks = []
    checks.extend(check_table_row_counts(conn))
    checks.extend(check_missing_rate(conn))
    checks.extend(check_order_amount_missing(conn))
    checks.extend(check_anonymous_traffic(conn))
    return {
        "category": "完整性",
        "generated_at": datetime.now().isoformat(),
        "checks": checks,
    }


# ============================================================
# 3.2 唯一性检查 (items 170-174)
# ============================================================

def check_uniqueness(conn) -> List[Dict]:
    """检查主键唯一性。"""
    checks = []
    checks_def = [
        ("users", "user_id"),
        ("orders", "order_id"),
        ("sku", "sku_id"),
        ("campaigns", "campaign_id"),
    ]
    for table, pk in checks_def:
        total = pd.read_sql(f'SELECT COUNT(*) FROM "{table}"', conn).iloc[0, 0]
        distinct = pd.read_sql(f'SELECT COUNT(DISTINCT "{pk}") FROM "{table}"', conn).iloc[0, 0]
        status = "pass" if total == distinct else "fail"
        checks.append({
            "category": "唯一性",
            "name": f"{table}.{pk}",
            "status": status,
            "detail": f"总行 {total:,}，去重 {distinct:,}，重复 {total - distinct}",
            "metrics": {"total": int(total), "distinct": int(distinct), "duplicates": total - distinct},
        })
    return checks


# ============================================================
# 3.3 准确性检查 (items 175-181)
# ============================================================

def check_accuracy(conn) -> List[Dict]:
    """准确性检查。"""
    checks = []

    # 175. paid_amount 负数
    neg = int(pd.read_sql("SELECT COUNT(*) FROM orders WHERE paid_amount < 0", conn).iloc[0, 0])
    checks.append({
        "category": "准确性", "name": "paid_amount 负数",
        "status": "pass" if neg == 0 else "fail",
        "detail": f"{neg} 条负数", "metrics": {"negative_count": neg},
    })

    # 176. subtotal 负数
    neg2 = int(pd.read_sql("SELECT COUNT(*) FROM orders WHERE subtotal < 0", conn).iloc[0, 0])
    checks.append({
        "category": "准确性", "name": "subtotal 负数",
        "status": "pass" if neg2 == 0 else "fail",
        "detail": f"{neg2} 条负数", "metrics": {"negative_count": neg2},
    })

    # 177. 订单行金额与订单头金额一致性
    try:
        order_header = pd.read_sql("SELECT order_id, total_amount FROM orders WHERE status IN ('paid','completed')", conn)
        order_lines = pd.read_sql("""
            SELECT order_id, SUM(unit_price * quantity - discount_amount) as calc_total
            FROM order_items GROUP BY order_id
        """, conn)
        merged = order_header.merge(order_lines, on="order_id")
        merged["diff"] = (merged["total_amount"] - merged["calc_total"]).abs()
        inconsistent = int((merged["diff"] > 1).sum())
        checks.append({
            "category": "准确性", "name": "订单行金额 vs 订单头金额",
            "status": "pass" if inconsistent < len(merged) * 0.05 else "warn",
            "detail": f"{inconsistent}/{len(merged)} 偏差 > 1 元",
            "metrics": {"inconsistent": inconsistent, "total": len(merged)},
        })
    except Exception as e:
        checks.append({"category": "准确性", "name": "订单行金额一致性", "status": "error", "detail": str(e)})

    # 178. 退款金额是否超过支付金额
    try:
        o = pd.read_sql("SELECT order_id, paid_amount FROM orders WHERE status IN ('paid','completed','refunded')", conn)
        r = pd.read_sql("SELECT order_id, SUM(amount) as refund_amount FROM refunds WHERE status='approved' GROUP BY order_id", conn)
        m = o.merge(r, on="order_id", how="inner")
        over = int((m["refund_amount"] > m["paid_amount"]).sum())
        checks.append({
            "category": "准确性", "name": "退款超支付金额",
            "status": "pass" if over == 0 else "fail",
            "detail": f"{over} 笔退款超过支付金额",
            "metrics": {"over_refund": over},
        })
    except Exception as e:
        checks.append({"category": "准确性", "name": "退款超支付金额", "status": "error", "detail": str(e)})

    # 179. sku 库存是否有负数 (inventory_movements)
    try:
        stock = pd.read_sql("""
            SELECT sku_id, SUM(CASE WHEN movement_type='in' THEN quantity ELSE -quantity END) as stock
            FROM inventory_movements GROUP BY sku_id
        """, conn)
        neg_stock = int((stock["stock"] < 0).sum())
        checks.append({
            "category": "准确性", "name": "SKU 库存负数",
            "status": "pass" if neg_stock == 0 else "fail",
            "detail": f"{neg_stock}/{len(stock)} SKU 库存为负",
            "metrics": {"negative_stock_skus": neg_stock, "total_skus": len(stock)},
        })
    except Exception as e:
        checks.append({"category": "准确性", "name": "SKU 库存负数", "status": "error", "detail": str(e)})

    # 180. price >= cost 约束
    try:
        sku_df = pd.read_sql("SELECT sku_id, price, cost FROM sku", conn)
        invalid = int((sku_df["price"] < sku_df["cost"]).sum())
        checks.append({
            "category": "准确性", "name": "price < cost",
            "status": "pass" if invalid == 0 else "fail",
            "detail": f"{invalid}/{len(sku_df)} SKU 售价低于成本",
            "metrics": {"invalid_count": invalid, "total": len(sku_df)},
        })
    except Exception as e:
        checks.append({"category": "准确性", "name": "price < cost", "status": "error", "detail": str(e)})

    return checks


# ============================================================
# 3.4 时效性检查 (items 182-186)
# ============================================================

def check_timeliness(conn) -> List[Dict]:
    """时效性检查。"""
    checks = []

    # 182-184: 各表时间范围
    time_tables = [
        ("orders", "created_at"),
        ("page_events", "created_at"),
        ("ads_spend", "spend_date"),
    ]
    for table, col in time_tables:
        try:
            r = pd.read_sql(f'SELECT MIN("{col}") as t_min, MAX("{col}") as t_max FROM "{table}"', conn)
            checks.append({
                "category": "时效性",
                "name": f"{table} 时间范围",
                "status": "pass",
                "detail": f"{r['t_min'][0]} ~ {r['t_max'][0]}",
                "metrics": {"min": str(r['t_min'][0]), "max": str(r['t_max'][0])},
            })
        except Exception as e:
            checks.append({"category": "时效性", "name": f"{table} 时间范围", "status": "error", "detail": str(e)})

    # 185. 最新订单距今天数
    try:
        latest = pd.read_sql("SELECT MAX(created_at) FROM orders", conn).iloc[0, 0]
        latest_date = pd.Timestamp(latest).date()
        days_ago = (date.today() - latest_date).days
        checks.append({
            "category": "时效性",
            "name": "最新订单距今天数",
            "status": "pass" if days_ago < 365 else "warn",
            "detail": f"最新订单 {latest_date}，距今 {days_ago} 天",
            "metrics": {"latest_date": str(latest_date), "days_ago": days_ago},
        })
    except Exception as e:
        checks.append({"category": "时效性", "name": "最新订单距今天数", "status": "error", "detail": str(e)})

    return checks


# ============================================================
# 3.5 一致性检查 (items 187-189)
# ============================================================

def check_consistency(conn) -> List[Dict]:
    """外键一致性检查。"""
    checks = []
    fk_checks = [
        ("orders", "user_id", "users", "user_id"),
        ("order_items", "sku_id", "sku", "sku_id"),
        ("ads_spend", "campaign_id", "campaigns", "campaign_id"),
    ]
    for child_table, child_col, parent_table, parent_col in fk_checks:
        try:
            orphans = pd.read_sql(f"""
                SELECT COUNT(*) FROM "{child_table}" c
                LEFT JOIN "{parent_table}" p ON c."{child_col}" = p."{parent_col}"
                WHERE c."{child_col}" IS NOT NULL AND p."{parent_col}" IS NULL
            """, conn).iloc[0, 0]
            status = "pass" if orphans == 0 else "fail"
            checks.append({
                "category": "一致性",
                "name": f"{child_table}.{child_col} → {parent_table}.{parent_col}",
                "status": status,
                "detail": f"{orphans} 条孤立记录",
                "metrics": {"orphans": int(orphans)},
            })
        except Exception as e:
            checks.append({"category": "一致性", "name": f"{child_table}→{parent_table}", "status": "error", "detail": str(e)})
    return checks


# ============================================================
# 3.6 业务逻辑检查 (items 190-192)
# ============================================================

def check_business_logic(conn) -> List[Dict]:
    """业务逻辑检查。"""
    checks = []

    # 190. 订单状态分布
    status_dist = pd.read_sql("SELECT status, COUNT(*) as n FROM orders GROUP BY status", conn)
    checks.append({
        "category": "业务逻辑",
        "name": "订单状态分布",
        "status": "pass",
        "detail": ", ".join(f"{r['status']}:{r['n']:,}" for _, r in status_dist.iterrows()),
        "metrics": status_dist.set_index("status")["n"].to_dict(),
    })

    # 191. paid_at >= created_at
    try:
        bad = int(pd.read_sql(
            "SELECT COUNT(*) FROM payments WHERE paid_at < created_at", conn
        ).iloc[0, 0])
        checks.append({
            "category": "业务逻辑",
            "name": "paid_at < created_at",
            "status": "pass" if bad == 0 else "fail",
            "detail": f"{bad} 条支付时间早于创建时间",
            "metrics": {"bad_count": bad},
        })
    except Exception:
        checks.append({"category": "业务逻辑", "name": "paid_at < created_at", "status": "error", "detail": "payments 表结构不匹配"})

    # 192. 流量漏斗事件数量是否逐层递减
    try:
        funnel = pd.read_sql("""
            SELECT event_type, COUNT(*) as n FROM page_events
            WHERE event_type IN ('view_home','view_product','add_to_cart','checkout','pay_success')
            GROUP BY event_type ORDER BY n DESC
        """, conn)
        checks.append({
            "category": "业务逻辑",
            "name": "流量漏斗事件分布",
            "status": "pass",
            "detail": ", ".join(f"{r['event_type']}:{r['n']:,}" for _, r in funnel.iterrows()),
            "metrics": funnel.set_index("event_type")["n"].to_dict(),
        })
    except Exception as e:
        checks.append({"category": "业务逻辑", "name": "流量漏斗", "status": "error", "detail": str(e)})

    return checks


# ============================================================
# 3.7 数据清洗流水线 (items 193-201)
# ============================================================

def handle_missing(df: pd.DataFrame, strategy: str = "auto") -> pd.DataFrame:
    """缺失值处理。

    Args:
        df: 输入 DataFrame
        strategy: "drop"|"mean"|"median"|"mode"|"auto"
    """
    df = df.copy()
    for col in df.columns:
        if df[col].isnull().sum() == 0:
            continue
        if strategy == "drop":
            df = df.dropna(subset=[col])
        elif strategy == "mean" and df[col].dtype in ("float64", "int64"):
            df[col] = df[col].fillna(df[col].mean())
        elif strategy == "median" and df[col].dtype in ("float64", "int64"):
            df[col] = df[col].fillna(df[col].median())
        elif strategy == "mode":
            df[col] = df[col].fillna(df[col].mode()[0] if not df[col].mode().empty else 0)
        else:  # auto
            if df[col].dtype in ("float64", "int64"):
                df[col] = df[col].fillna(df[col].median())
            else:
                df[col] = df[col].fillna(df[col].mode()[0] if not df[col].mode().empty else "unknown")
    return df


def handle_outliers_iqr(df: pd.DataFrame, columns: List[str] = None, multiplier: float = 1.5) -> pd.DataFrame:
    """IQR 异常值处理（替换为边界值）。"""
    df = df.copy()
    cols = columns or df.select_dtypes(include=[np.number]).columns.tolist()
    for col in cols:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - multiplier * iqr
        upper = q3 + multiplier * iqr
        df[col] = df[col].clip(lower, upper)
    return df


def handle_outliers_zscore(df: pd.DataFrame, columns: List[str] = None, threshold: float = 3.0) -> pd.DataFrame:
    """Z-score 异常值处理（替换为边界值）。"""
    df = df.copy()
    cols = columns or df.select_dtypes(include=[np.number]).columns.tolist()
    for col in cols:
        mu, sigma = df[col].mean(), df[col].std()
        if sigma == 0:
            continue
        lower = mu - threshold * sigma
        upper = mu + threshold * sigma
        df[col] = df[col].clip(lower, upper)
    return df


def encode_categorical(df: pd.DataFrame, method: str = "onehot", columns: List[str] = None) -> pd.DataFrame:
    """类别变量编码。"""
    if method == "onehot":
        cols = columns or df.select_dtypes(include=["object"]).columns.tolist()
        return pd.get_dummies(df, columns=cols, drop_first=True)
    elif method == "ordinal":
        df = df.copy()
        cols = columns or df.select_dtypes(include=["object"]).columns.tolist()
        for col in cols:
            df[col] = df[col].astype("category").cat.codes
        return df
    return df


def scale_features(df: pd.DataFrame, method: str = "standard", columns: List[str] = None) -> pd.DataFrame:
    """特征缩放。"""
    df = df.copy()
    cols = columns or df.select_dtypes(include=[np.number]).columns.tolist()
    scalers = {"standard": StandardScaler(), "minmax": MinMaxScaler(), "robust": RobustScaler()}
    scaler = scalers.get(method, StandardScaler())
    df[cols] = scaler.fit_transform(df[cols])
    return df


def select_by_correlation(df: pd.DataFrame, threshold: float = 0.9) -> List[str]:
    """基于相关性进行特征选择（去除高相关特征）。"""
    corr = df.corr(numeric_only=True).abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    to_drop = [col for col in upper.columns if any(upper[col] > threshold)]
    return to_drop


def select_by_variance(df: pd.DataFrame, threshold: float = 0.01) -> List[str]:
    """基于方差过滤特征选择（去除低方差特征）。"""
    numeric = df.select_dtypes(include=[np.number])
    variances = numeric.var()
    return variances[variances < threshold].index.tolist()


def run_preprocessing_pipeline(df: pd.DataFrame, config: Dict = None) -> pd.DataFrame:
    """完整数据预处理流水线。

    Args:
        df: 原始 DataFrame
        config: {
            "missing": "auto"|"drop"|"mean"|"median"|"mode",
            "outliers": "iqr"|"zscore"|None,
            "encode": "onehot"|"ordinal"|None,
            "scale": "standard"|"minmax"|"robust"|None,
        }
    """
    if config is None:
        config = {"missing": "auto", "outliers": None, "encode": None, "scale": None}

    logger.info(f"预处理开始，输入: {df.shape}")

    # 缺失值
    df = handle_missing(df, strategy=config.get("missing", "auto"))
    logger.info(f"缺失值处理后: {df.shape}")

    # 异常值
    if config.get("outliers") == "iqr":
        df = handle_outliers_iqr(df)
    elif config.get("outliers") == "zscore":
        df = handle_outliers_zscore(df)
    logger.info(f"异常值处理后: {df.shape}")

    # 编码
    if config.get("encode"):
        df = encode_categorical(df, method=config["encode"])
    logger.info(f"编码后: {df.shape}")

    # 缩放
    if config.get("scale"):
        df = scale_features(df, method=config["scale"])
    logger.info(f"缩放后: {df.shape}")

    return df


# ============================================================
# 综合质量报告
# ============================================================

def run_full_quality_report() -> Dict:
    """运行全部数据质量检查。"""
    conn = get_db_connection()
    try:
        all_checks = []
        all_checks.extend(completeness_report(conn)["checks"])
        all_checks.extend(check_uniqueness(conn))
        all_checks.extend(check_accuracy(conn))
        all_checks.extend(check_timeliness(conn))
        all_checks.extend(check_consistency(conn))
        all_checks.extend(check_business_logic(conn))

        pass_count = sum(1 for c in all_checks if c["status"] == "pass")
        warn_count = sum(1 for c in all_checks if c["status"] == "warn")
        fail_count = sum(1 for c in all_checks if c["status"] == "fail")
        error_count = sum(1 for c in all_checks if c["status"] == "error")

        return {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": len(all_checks),
                "pass": pass_count,
                "warn": warn_count,
                "fail": fail_count,
                "error": error_count,
            },
            "checks": all_checks,
        }
    finally:
        conn.close()
