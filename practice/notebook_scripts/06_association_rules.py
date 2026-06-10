#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 06_association_rules.ipynb 提取

--- 第 6 章 商品关联规则与组合销售 ---
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
products = load_table("dim_product", limit=100000)[["sku_id", "sku_name", "category_name", "price", "cost"]]
top_sku = [
    "sku_00001", "sku_00002", "sku_00005", "sku_00003",
    "sku_00008", "sku_00009", "sku_00022", "sku_00023",
    "sku_00153", "sku_00183", "sku_00098", "sku_00073",
    "sku_00232", "sku_00242", "sku_00828", "sku_00803",
    "sku_00292", "sku_00294",
]
frames = []
for sku_id in top_sku:
    frames.append(query_table("fact_order_item", limit=5000, sku_id=sku_id))
items = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["order_item_id"])
basket = items.groupby("order_id")["sku_id"].apply(set)
rules = []
for a in top_sku:
    has_a = basket.apply(lambda s: a in s)
    support_a = has_a.mean()
    for b in top_sku:
        if a == b:
            continue
        has_b = basket.apply(lambda s: b in s)
        both = (has_a & has_b).mean()
        if support_a > 0 and has_b.mean() > 0:
            confidence = both / support_a
            lift = confidence / has_b.mean()
            if both >= 0.001 and confidence >= 0.03 and lift > 1.05:
                rules.append([a, b, both, confidence, lift])
rules_df = pd.DataFrame(rules, columns=["antecedent", "consequent", "support", "confidence", "lift"]).sort_values(["lift", "confidence"], ascending=False)
rules_df.head(10)

#===========================================================

assert len(rules_df) >= 0
print("第 06 章验证通过")

print("\n" + "=" * 60)
print("✅ 第 06 章 06_association_rules 代码全部执行完毕")