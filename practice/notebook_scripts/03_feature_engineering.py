#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 03_feature_engineering.ipynb 提取

--- 第 3 章 用户建模宽表与特征工程 ---
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
users = load_table("dim_user", limit=100000)
orders = paid_orders()
traffic = load_table("fact_traffic", limit=100000)
coupons = load_table("fact_coupon_use", limit=100000)

snapshot = orders["order_date"].max() + pd.Timedelta(days=1)
rfm = orders.groupby("user_id").agg(
    last_order_date=("order_date", "max"),
    order_count=("order_id", "nunique"),
    total_paid=("paid_amount", "sum"),
    avg_paid=("paid_amount", "mean")
).reset_index()
rfm["recency_days"] = (snapshot - rfm["last_order_date"]).dt.days

behavior = traffic.groupby("user_id").agg(
    event_count=("event_id", "count"),
    active_days=("event_date", lambda s: s.dt.date.nunique())
).reset_index()

coupon_feature = coupons.groupby("user_id").agg(
    coupons_issued=("user_coupon_id", "count"),
    coupons_used=("is_used", "sum")
).reset_index()

wide = users[["user_id", "province", "register_channel", "member_level"]].merge(rfm, on="user_id", how="left").merge(behavior, on="user_id", how="left").merge(coupon_feature, on="user_id", how="left")
wide = wide.fillna({"order_count": 0, "total_paid": 0, "avg_paid": 0, "recency_days": 999, "event_count": 0, "active_days": 0, "coupons_issued": 0, "coupons_used": 0})
wide.head()

#===========================================================

out = COURSE_ROOT / "data_cache" / "user_modeling_wide_table.csv"
wide.to_csv(out, index=False, encoding="utf-8-sig")
print("已保存:", out)
assert wide["user_id"].is_unique
print("第 03 章验证通过")

print("\n" + "=" * 60)
print("✅ 第 03 章 03_feature_engineering 代码全部执行完毕")