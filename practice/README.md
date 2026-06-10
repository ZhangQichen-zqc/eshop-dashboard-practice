# 数据挖掘与管理决策实训教程 V3

V3 版已升级为 **ETL API 驱动** 的课程包。默认数据入口：

```text
http://192.168.31.47:38173/api/etl
```

Notebook 会优先请求真实 ETL 接口；如果课堂网络或后端服务暂时不可用，会自动回退到本地 SQLite 后备数据，保证教学不中断。

## 课程文件

- `lectures/`：每章 50 分钟详细讲稿，含商业逻辑、代码讲解、课堂提问、作业要求
- `notebooks/`：可直接运行的教师示例 Notebook
- `student_notebooks/`：学生版 Notebook
- `teacher_notebooks/`：教师版 Notebook
- `slides/`：PPTX 与每章 PPT Markdown 源稿
- `course_utils/`：ETL API 取数与本地回退工具

## 章节与数据

| 章 | 主题 | 主要数据 | 方法 |
|---:|---|---|---|
| 1 | 商业问题定义与 ETL 数据接入 | dim_user、fact_order、fact_traffic、/metrics、/quality | CRISP-DM、数据字典、指标口径、API 取数 |
| 2 | 经营健康诊断与数据探索 | daily_business_summary、fact_order、fact_refund、fact_traffic | 描述性统计、漏斗分析、趋势分析、分组对比 |
| 3 | 用户建模宽表与特征工程 | dim_user、fact_order、fact_traffic、fact_coupon_use | RFM、时间窗口、行为特征、缺失值处理 |
| 4 | 复购预测与触达名单 | fact_order、dim_user、fact_traffic | 分类模型、AUC、Precision、Recall、阈值与 ROI |
| 5 | 客户分群与差异化运营 | dim_user、fact_order、fact_traffic | 标准化、K-Means、轮廓系数、群体画像 |
| 6 | 商品关联规则与组合销售 | fact_order_item、dim_product | 购物篮、支持度、置信度、提升度 |
| 7 | 销售预测与库存备货 | daily_business_summary、fact_order_item、dim_product | 时间序列、移动平均、误差、安全库存 |
| 8 | 营销归因与预算优化 | fact_ads_spend、dim_campaign、fact_order | CTR、CVR、CPA、ROAS、对照组意识 |
| 9 | 综合经营决策项目 | 前八章全部核心数据表 | 问题定义、数据证据、模型分析、管理建议、答辩表达 |

## 验证

```powershell
cd C:\Users\zzz\Projects\eshop\Data_Mining_management_Decision_Course_V3
python scripts\validate_notebooks.py
python scripts\execute_notebooks.py
```
