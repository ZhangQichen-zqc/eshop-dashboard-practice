#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 07_sales_forecast.ipynb 提取

--- 第 7 章 销售预测与库存备货 ---
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
orders = paid_orders()
daily = orders.groupby("order_date").agg(sales=("paid_amount", "sum"), orders=("order_id", "nunique")).reset_index().sort_values("order_date")
daily = daily.set_index("order_date").asfreq("D").fillna(0)
daily["ma7"] = daily["sales"].rolling(7).mean()
daily["ma30"] = daily["sales"].rolling(30).mean()
daily.tail()

#===========================================================

import matplotlib.pyplot as plt
daily[["sales", "ma7", "ma30"]].tail(120).plot(figsize=(11, 4), title="Recent Sales and Moving Average")
plt.tight_layout()

#===========================================================

recent = daily["sales"].tail(30)
base_forecast = recent.mean()
safety = recent.std() * 1.65
print("基准日销售预测:", money(base_forecast))
print("安全库存金额建议:", money(safety))

#===========================================================

assert len(daily) > 30
print("第 07 章验证通过")

print("\n" + "=" * 60)
print("✅ 第 07 章 07_sales_forecast 代码全部执行完毕")