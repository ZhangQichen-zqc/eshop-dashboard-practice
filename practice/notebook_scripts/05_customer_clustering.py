#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 05_customer_clustering.ipynb 提取

--- 第 5 章 客户分群与差异化运营 ---
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

from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
orders = paid_orders()
customer = orders.groupby("user_id").agg(order_count=("order_id", "nunique"), total_paid=("paid_amount", "sum"), avg_paid=("paid_amount", "mean")).reset_index()
X = customer[["order_count", "total_paid", "avg_paid"]]
Xs = StandardScaler().fit_transform(X)
scores = []
for k in range(2, 7):
    labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(Xs)
    scores.append((k, silhouette_score(Xs, labels)))
scores

#===========================================================

k = max(scores, key=lambda x: x[1])[0]
customer["cluster"] = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(Xs)
profile = customer.groupby("cluster").agg(users=("user_id", "count"), avg_orders=("order_count", "mean"), avg_total_paid=("total_paid", "mean"), avg_order_value=("avg_paid", "mean")).reset_index()
profile

#===========================================================

assert profile["users"].sum() == len(customer)
print("第 05 章验证通过")

print("\n" + "=" * 60)
print("✅ 第 05 章 05_customer_clustering 代码全部执行完毕")