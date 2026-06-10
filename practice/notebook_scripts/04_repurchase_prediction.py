#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 04_repurchase_prediction.ipynb 提取

--- 第 4 章 复购预测与触达名单 ---
"""

from pathlib import Path
import sys

COURSE_ROOT = Path.cwd()
if COURSE_ROOT.name in ["notebooks", "student_notebooks", "teacher_notebooks"]:
    COURSE_ROOT = COURSE_ROOT.parent
elif not (COURSE_ROOT / "course_utils").exists():
    COURSE_ROOT = Path("..").resolve()

sys.path.insert(0, str(COURSE_ROOT))

from course_utils.data_loader import (
    API_BASE, load_table, get_metrics, get_quality_report,
    get_table_catalog, get_schema, paid_orders, api_status, query_table
)
from course_utils.business import money, pct, section

try:
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
except Exception:
    pass

print("课程目录:", COURSE_ROOT)
print("ETL API:", API_BASE)
print("API 状态:", api_status())

#===========================================================

catalog = get_table_catalog()
tables = catalog["tables"]
print("可用表数量:", catalog.get("total", len(tables)))
for t in tables[:12]:
    print(t["tableName"], t.get("recordCount"), t.get("type"), t.get("description", ""))

#===========================================================

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, precision_score, recall_score

orders = paid_orders()
cutoff = pd.Timestamp("2026-01-01")
history = orders[orders["order_date"] < cutoff]
future = orders[(orders["order_date"] >= cutoff) & (orders["order_date"] < cutoff + pd.Timedelta(days=60))]

feat = history.groupby("user_id").agg(
    order_count=("order_id", "nunique"),
    total_paid=("paid_amount", "sum"),
    avg_paid=("paid_amount", "mean"),
    last_order_date=("order_date", "max")
).reset_index()
feat["recency_days"] = (cutoff - feat["last_order_date"]).dt.days
feat["label_repurchase"] = feat["user_id"].isin(future["user_id"].unique()).astype(int)
feat = feat.drop(columns=["last_order_date"]).fillna(0)
feat["label_repurchase"].mean()

#===========================================================

X = feat[["order_count", "total_paid", "avg_paid", "recency_days"]]
y = feat["label_repurchase"]
X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
model = RandomForestClassifier(n_estimators=120, random_state=42, n_jobs=-1, min_samples_leaf=5)
model.fit(X_train, y_train)
proba = model.predict_proba(X_val)[:, 1]
auc = roc_auc_score(y_val, proba)
print("AUC:", round(auc, 3))

#===========================================================

rows = []
for threshold in np.arange(0.1, 0.9, 0.1):
    pred = (proba >= threshold).astype(int)
    touched = int(pred.sum())
    if touched == 0:
        continue
    precision = precision_score(y_val, pred, zero_division=0)
    recall = recall_score(y_val, pred, zero_division=0)
    expected_margin = touched * precision * 80
    touch_cost = touched * 8
    roi = (expected_margin - touch_cost) / max(touch_cost, 1)
    rows.append([threshold, touched, precision, recall, roi])
roi_table = pd.DataFrame(rows, columns=["threshold", "touch_users", "precision", "recall", "expected_roi"])
roi_table.sort_values("expected_roi", ascending=False)

#===========================================================

assert auc >= 0.5
print("第 04 章验证通过")

print("\n" + "=" * 60)
print("✅ 第 04 章 04_repurchase_prediction 代码全部执行完毕")