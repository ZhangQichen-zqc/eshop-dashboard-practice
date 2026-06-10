#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 02_business_health_diagnosis.ipynb 提取

--- 第 2 章 经营健康诊断与数据探索 ---
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
daily = load_table("daily_business_summary", limit=100000)
print(daily.head())
if "gmv" not in daily.columns:
    orders = paid_orders()
    daily = orders.groupby("order_date").agg(gmv=("paid_amount", "sum"), orders=("order_id", "nunique"), buyers=("user_id", "nunique")).reset_index()
date_source = daily["summary_date"] if "summary_date" in daily.columns else daily.get("date_id", daily.get("order_date"))
daily["analysis_date"] = pd.to_datetime(date_source, errors="coerce")
daily = daily.dropna(subset=["analysis_date"])
daily["month"] = daily["analysis_date"].dt.to_period("M").astype(str)
monthly = daily.groupby("month").agg(gmv=("gmv", "sum"), orders=("orders", "sum")).reset_index()
monthly["aov"] = monthly["gmv"] / monthly["orders"]
monthly.tail()

#===========================================================

import matplotlib.pyplot as plt
monthly.plot(x="month", y=["gmv", "orders"], secondary_y="orders", figsize=(10, 4), title="Monthly GMV and Orders")
plt.xticks(rotation=45)
plt.tight_layout()

#===========================================================

assert len(monthly) > 0
print("第 02 章验证通过")

print("\n" + "=" * 60)
print("✅ 第 02 章 02_business_health_diagnosis 代码全部执行完毕")