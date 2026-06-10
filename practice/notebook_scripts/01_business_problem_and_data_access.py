#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 1 章 商业问题定义与 ETL 数据接入

从 student_notebooks/01_business_problem_and_data_access.ipynb 提取

本章商业问题：商城经营数据从哪里来，
如何把老板的问题翻译成可分析、可验证、可行动的问题？

本章所有代码默认优先读取真实 ETL 接口 http://192.168.31.47:38173/api/etl
如果接口暂时不可用，会自动回退到本地 SQLite 后备数据。
"""

# ============================================================
# 0. 先建立商业问题意识
# 在商业课里，代码不是第一步。第一步是判断：
# 这个问题影响收入、成本、用户体验、库存风险，还是营销效率？
# 只有先说清楚商业目标，后面的数据选择和模型选择才不会跑偏。
# ============================================================

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

print("\n" + "=" * 60)

# ============================================================
# 1. 查看 ETL 数据资产
# 下面先查看 ETL 接口暴露了哪些表。
# 注意 dim_ 开头的是维度表，通常描述对象；
# fact_ 开头的是事实表，通常记录业务事件。
# ============================================================

catalog = get_table_catalog()
tables = catalog["tables"]
print("可用表数量:", catalog.get("total", len(tables)))
for t in tables[:12]:
    print(t["tableName"], t.get("recordCount"), t.get("type"), t.get("description", ""))

print("\n" + "=" * 60)

# ============================================================
# 2. 指标口径不是细节，而是管理共识
# 同样叫 GMV，不同公司可能有不同口径。
# 本课程要求每个指标都能说清楚定义。
# ============================================================

metrics = get_metrics()["metrics"]
for key in ["gmv", "orderCount", "buyerCount", "avgOrderValue"]:
    print(key, metrics[key]["value"], "| 口径:", metrics[key]["definition"])

funnel = metrics["funnel"]
stages = ["view_home", "view_product", "add_to_cart", "checkout", "pay_success"]
print("\n流量漏斗:")
for s in stages:
    print(s, funnel.get(s))

print("\n" + "=" * 60)

# ============================================================
# 3. 数据质量检查
# 数据质量检查对应商业上的可信度。
# 如果订单主键重复、金额异常、日期缺失，
# 后面的模型再漂亮也不值得信。
# ============================================================

quality = get_quality_report()
print("检查总数:", quality["summary"]["total"])
print("通过:", quality["summary"]["pass"], "警告:", quality["summary"]["warn"], "失败:", quality["summary"]["fail"])
for item in quality["checks"][:5]:
    print(item["category"], item["name"], item["status"], item["detail"])

print("\n" + "=" * 60)

# ============================================================
# 4. 查看 fact_order 表结构 — 了解有哪些字段可分析
# ============================================================

schema = get_schema("fact_order")
print("fact_order 字段:")
for col in schema["columns"]:
    print(col["name"], col["type"])
assert any(c["name"] == "paid_amount" for c in schema["columns"])
print("第 01 章验证通过")

print("\n" + "=" * 60)
print("✅ 第 1 章 ETL 数据接入代码全部执行完毕")
