"""R4 复购预测模型

样本准备 → 特征工程 → 多模型训练 → 评估 → 落地触达名单 + ROI 模拟。
"""

import logging
import warnings
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score, precision_score, recall_score, f1_score,
    roc_curve, precision_recall_curve, confusion_matrix,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.tree import DecisionTreeClassifier

from ..data_access import get_db_connection
from ..subprojects.feature_engineering import build_user_wide_table

warnings.filterwarnings("ignore")
logger = logging.getLogger("analytics.r4")

MODELS = {}
BEST_MODEL = None
SCALER = None
FEATURE_COLS = None


# ============================================================
# 8.1 样本准备
# ============================================================

def prepare_samples(reference_date: str = "2025-12-31", observation_days: int = 365, prediction_days: int = 60) -> dict:
    """构造训练样本，确保无数据泄漏。

    Args:
        reference_date: 参考日期（分割线）
        observation_days: 观察窗口（特征使用此窗口内的数据）
        prediction_days: 预测窗口（标签：此窗口内是否复购）
    """
    ref = pd.Timestamp(reference_date)
    obs_start = ref - pd.Timedelta(days=observation_days)
    pred_end = ref + pd.Timedelta(days=prediction_days)

    logger.info(f"观察窗口: {obs_start.date()} ~ {ref.date()}")
    logger.info(f"预测窗口: {ref.date()} ~ {pred_end.date()}")

    conn = get_db_connection()
    try:
        # 标签：在预测窗口内有购买的标记为 1
        label_orders = pd.read_sql("""
            SELECT DISTINCT user_id FROM fact_order
            WHERE order_date > ? AND order_date <= ?
              AND status IN ('paid','completed')
        """, conn, params=[str(ref.date()), str(pred_end.date())])

        # 特征用户：观察窗口内至少有一个订单
        feature_users = pd.read_sql("""
            SELECT DISTINCT user_id FROM fact_order
            WHERE order_date >= ? AND order_date <= ?
              AND status IN ('paid','completed')
        """, conn, params=[str(obs_start.date()), str(ref.date())])

        # 合并
        all_users = feature_users.copy()
        all_users["will_repurchase"] = all_users["user_id"].isin(label_orders["user_id"]).astype(int)

        pos = all_users["will_repurchase"].sum()
        neg = len(all_users) - pos

        logger.info(f"样本: {len(all_users)} 人 | 正例: {pos} ({pos/len(all_users)*100:.1f}%) | 负例: {neg} ({neg/len(all_users)*100:.1f}%)")

        return {
            "user_ids": all_users["user_id"].tolist(),
            "labels": all_users["will_repurchase"].tolist(),
            "reference_date": reference_date,
            "obs_window": f"{obs_start.date()} ~ {ref.date()}",
            "pred_window": f"{ref.date()} ~ {pred_end.date()}",
            "positive": int(pos),
            "negative": int(neg),
            "ratio": round(pos / len(all_users), 4),
        }
    finally:
        conn.close()


# ============================================================
# 8.2 特征准备与训练
# ============================================================

def prepare_features():
    """从用户宽表选取特征，编码和标准化。"""
    global SCALER, FEATURE_COLS

    wide = build_user_wide_table(save_csv=False)

    # 选数值特征
    exclude = ["user_id", "name", "city", "register_date", "rfm_segment", "top_category",
               "R_score", "F_score", "M_score", "last_coupon_date", "province",
               "gender", "member_level", "register_channel", "segment", "status"]
    num_cols = wide.select_dtypes(include=[np.number]).columns.tolist()
    FEATURE_COLS = [c for c in num_cols if c not in exclude and c in wide.columns]

    X = wide[FEATURE_COLS].fillna(0)
    user_ids = wide["user_id"].tolist()

    SCALER = StandardScaler()
    X_scaled = SCALER.fit_transform(X)
    X_scaled = pd.DataFrame(X_scaled, columns=FEATURE_COLS)

    return X_scaled, user_ids


def train_models(samples: dict, X_df: pd.DataFrame, user_ids: list) -> dict:
    """训练多种分类模型并返回评估结果。"""
    global MODELS, BEST_MODEL

    # 合并标签
    labels_map = dict(zip(samples["user_ids"], samples["labels"]))
    y = np.array([labels_map.get(uid, 0) for uid in user_ids])
    X = X_df.values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)

    models = {
        "逻辑回归": LogisticRegression(max_iter=1000, random_state=42),
        "决策树": DecisionTreeClassifier(max_depth=8, random_state=42),
        "随机森林": RandomForestClassifier(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1),
        "梯度提升": GradientBoostingClassifier(n_estimators=100, max_depth=5, random_state=42),
    }

    results = {}
    best_auc = 0
    for name, model in models.items():
        logger.info(f"训练 {name}...")
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]

        auc = roc_auc_score(y_test, y_proba)
        precision = precision_score(y_test, y_pred)
        recall = recall_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)

        MODELS[name] = model

        results[name] = {
            "auc": round(auc, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

        if auc > best_auc:
            best_auc = auc
            BEST_MODEL = model
            BEST_MODEL.name = name

        # ROC 曲线数据
        fpr, tpr, _ = roc_curve(y_test, y_proba)
        results[name]["roc"] = {
            "fpr": [round(x, 4) for x in fpr.tolist()],
            "tpr": [round(x, 4) for x in tpr.tolist()],
        }

        # 混淆矩阵
        cm = confusion_matrix(y_test, y_pred)
        results[name]["confusion_matrix"] = cm.tolist()

        # Top N% 的 Precision/Recall
        for pct in [5, 10, 20]:
            n = max(1, int(len(y_test) * pct / 100))
            top_idx = np.argsort(y_proba)[-n:]
            top_y_true = y_test[top_idx]
            top_y_pred = (y_proba[top_idx] >= 0.5).astype(int)
            results[name][f"top{pct}_precision"] = round(precision_score(top_y_true, top_y_pred, zero_division=0), 4)
            results[name][f"top{pct}_recall"] = round(recall_score(top_y_true, top_y_pred, zero_division=0), 4)

    # 特征重要性（随机森林）
    rf = MODELS.get("随机森林")
    if rf and hasattr(rf, "feature_importances_"):
        importances = sorted(
            zip(FEATURE_COLS, rf.feature_importances_),
            key=lambda x: -x[1]
        )[:15]
        results["feature_importance"] = [
            {"feature": f, "importance": round(v, 6)} for f, v in importances
        ]

    logger.info(f"最佳模型: {BEST_MODEL.name} (AUC={best_auc:.4f})")
    return results


# ============================================================
# 8.3 模型落地
# ============================================================

def score_all_users() -> dict:
    """用最优模型为全部用户打分。"""
    if BEST_MODEL is None:
        prepare_and_train()

    X_df, user_ids = prepare_features()
    X = X_df.values
    scores = BEST_MODEL.predict_proba(X)[:, 1]

    result_df = pd.DataFrame({
        "user_id": user_ids,
        "score": scores,
    }).sort_values("score", ascending=False)

    return {
        "model": BEST_MODEL.name,
        "total_users": len(result_df),
        "top_users": result_df.head(100).to_dict(orient="records"),
        "thresholds": {
            "top5": round(float(result_df["score"].quantile(0.95)), 4),
            "top10": round(float(result_df["score"].quantile(0.90)), 4),
            "top20": round(float(result_df["score"].quantile(0.80)), 4),
        },
    }


def generate_contact_list(threshold: float = None, top_pct: float = 5.0) -> dict:
    """生成触达名单（按概率/阈值筛选）。"""
    scored = score_all_users()
    users = pd.DataFrame(scored["top_users"])
    # need to re-score all users
    X_df, user_ids = prepare_features()
    scores = BEST_MODEL.predict_proba(X_df.values)[:, 1]
    result = pd.DataFrame({"user_id": user_ids, "repurchase_score": scores.round(4)})

    if threshold is not None:
        result = result[result["repurchase_score"] >= threshold]
    else:
        cutoff = result["repurchase_score"].quantile(1 - top_pct / 100)
        result = result[result["repurchase_score"] >= cutoff]

    result = result.sort_values("repurchase_score", ascending=False)

    # ROI 估算：假设触达成本 ¥5/人，复购客单价约 ¥1,444
    contact_count = len(result)
    contact_cost = contact_count * 5
    expected_repurchasers = int(contact_count * float(result["repurchase_score"].mean()))
    expected_revenue = expected_repurchasers * 1444
    roi = (expected_revenue - contact_cost) / contact_cost if contact_cost else 0

    return {
        "contact_list": result.head(200).to_dict(orient="records"),
        "threshold": round(float(cutoff) if threshold is None else threshold, 4),
        "contact_count": contact_count,
        "contact_cost": contact_cost,
        "expected_repurchasers": expected_repurchasers,
        "expected_revenue": round(expected_revenue),
        "roi": round(roi, 2),
    }


def simulate_roi(threshold: float) -> dict:
    """阈值调节 + ROI 实时计算。"""
    return generate_contact_list(threshold=threshold)


# ============================================================
# 一站式训练
# ============================================================

def prepare_and_train(reference_date: str = "2025-12-31") -> dict:
    """一键完成样本准备 → 特征准备 → 训练 → 评估。"""
    logger.info("=== R4 复购预测开始 ===")

    samples = prepare_samples(reference_date)
    X_df, user_ids = prepare_features()
    train_results = train_models(samples, X_df, user_ids)

    return {
        "samples": samples,
        "model_results": train_results,
        "best_model": BEST_MODEL.name if BEST_MODEL else None,
        "feature_count": len(FEATURE_COLS) if FEATURE_COLS else 0,
        "generated_at": datetime.now().isoformat(),
    }
