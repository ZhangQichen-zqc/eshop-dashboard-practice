#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 08_marketing_attribution.ipynb 提取

--- 第 8 章 营销归因与预算优化 ---
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

ads = load_table("fact_ads_spend", limit=100000)
channel = ads.groupby("channel").agg(spend=("spend_amount", "sum"), impressions=("impressions", "sum"), clicks=("clicks", "sum"), conversions=("conversions", "sum")).reset_index()
channel["ctr"] = channel["clicks"] / channel["impressions"]
channel["cvr"] = channel["conversions"] / channel["clicks"]
channel["cpa"] = channel["spend"] / channel["conversions"]
channel["estimated_revenue"] = channel["conversions"] * 120
channel["roas"] = channel["estimated_revenue"] / channel["spend"]
channel.sort_values("roas", ascending=False)

#===========================================================

assert channel["spend"].sum() > 0
print("第 08 章验证通过")

print("\n" + "=" * 60)
print("✅ 第 08 章 08_marketing_attribution 代码全部执行完毕")