# 数据字典 course_dataset_v2

`course_dataset_v2` 的目标不是演示商城功能，而是提供可用于数据挖掘教学的经营数据环境。数据由 `server/src/seed.js` 按固定随机种子生成，包含用户生命周期、商品长尾、未转化流量、订单、营销、广告、库存、履约、退款和评论。

## 数据规模目标

- 用户：约 20,000
- 商品：12 个类目，约 288 个 SPU、864 个 SKU
- 订单：约 100,000，覆盖 24 个月
- 行为事件：约 700,000，包含成交和未转化会话
- 活动：约 56 个，包含渠道、活动类型、目标人群与对照组标记
- 退款、履约、库存、评论：用于售后、供应链和用户体验分析

## OLTP 源系统表

| 表 | 粒度 | 说明 |
|---|---|---|
| `users` | 用户 | 注册渠道、地区、性别、年龄段、会员等级、生命周期分群 |
| `addresses` | 用户地址 | 演示收货地址与省市 |
| `categories` | 商品类目 | 一级类目 |
| `spu` | 标准商品 | 品牌、名称、描述、图片 |
| `sku` | 可售规格 | 价格、成本、供应商、上架日期、库存 |
| `campaigns` | 营销活动 | 渠道、类型、目标人群、是否有对照组、预算 |
| `coupons` | 优惠券模板 | 门槛、券面额、发放与使用计数 |
| `user_coupons` | 用户券 | 发放、未使用、核销和订单关联 |
| `orders` | 订单头 | 渠道、活动、金额、状态、支付时间 |
| `order_items` | 订单行 | SKU、数量、单价、成本、分摊优惠 |
| `payments` | 支付流水 | 模拟支付方式和支付结果 |
| `shipments` | 履约包裹 | 承运商、承诺时效、实际时效、是否延迟的基础 |
| `refunds` | 退款记录 | 退款原因、金额、审核状态 |
| `page_events` | 行为事件 | 曝光/浏览/搜索/加购/结算/支付成功，含未转化会话 |
| `ads_spend` | 广告日花费 | campaign、曝光、点击、转化、消耗 |
| `inventory_movements` | 库存流水 | 初始库存、补货、销售出库 |
| `product_reviews` | 评论 | 评分、情感、内容标签 |
| `admin_action_logs` | 后台审计 | 学生管理端应写入或兼容该表 |

## 分析视图

| 视图 | 粒度 | 典型用途 |
|---|---|---|
| `dim_date` | 日期 | 月度、周末、时间序列 |
| `dim_product` | SKU | 类目、品牌、规格、价格带、成本、供应商 |
| `dim_user` | 用户 | 地区、注册渠道、生命周期、会员等级 |
| `dim_campaign` | 活动 | 渠道、活动类型、目标人群、对照组、预算 |
| `fact_order` | 订单 | GMV、客单价、复购、活动订单 |
| `fact_order_item` | 订单行 | 类目贡献、毛利、购物篮、SKU长尾 |
| `fact_traffic` | 页面事件 | 漏斗、路径、渠道转化、未转化行为 |
| `fact_coupon_use` | 用户券 | 发放率、核销率、券敏感度 |
| `fact_refund` | 退款 | 退款率、原因结构、售后风险 |
| `fact_fulfillment` | 履约 | 配送时效、延迟率、履约对退款/复购影响 |
| `fact_inventory_movement` | 库存流水 | 补货、出库、动销、缺货风险 |
| `fact_product_review` | 评论 | 评分、情感、体验问题 |
| `fact_ads_spend` | 活动日消耗 | ROAS、点击率、转化成本 |
| `daily_business_summary` | 日期 + 渠道 | 经营日报、趋势图 |

## 核心指标口径

- GMV：`SUM(fact_order.paid_amount)`，通常限定订单状态为 `paid` 或 `completed`。
- 净销售额：GMV 减去已退款金额。
- 订单数：`COUNT(DISTINCT order_id)`。
- 客单价：`GMV / 订单数`。
- 毛利：`SUM((unit_price - unit_cost) * quantity - discount_amount)`，来自 `fact_order_item`。
- 漏斗转化：同一 `session_id` 中，从 `view_home`/`view_product` 到 `add_to_cart`、`checkout`、`pay_success` 的转化率。
- 券核销率：`SUM(is_used) / COUNT(user_coupon_id)`。
- 活动 ROAS：活动 GMV / `fact_ads_spend.spend_amount`。
- 退款率：退款订单数 / 支付订单数，或退款金额 / GMV。
- 延迟率：`fact_fulfillment.is_late = 1` 的包裹占比。
- RFM：
  - Recency：距最近一次订单的天数；
  - Frequency：订单次数；
  - Monetary：累计支付金额。

## 推荐挖掘任务

- 用户：RFM、cohort、复购预测、流失预警、LTV 分层。
- 商品：类目贡献、毛利矩阵、长尾分析、价格带弹性、关联规则。
- 流量：渠道漏斗、路径流失、设备差异、活动落地页质量。
- 营销：券敏感度、活动增量、对照组分析、ROAS 与预算迁移。
- 履约售后：延迟对退款/评论的影响，供应商和承运商治理。
- 库存：动销、滞销、补货节奏、缺货风险。

## 商品与图片来源

商品名称、品牌、类目和价格为教学样例合成数据；图片 URL 使用 `placehold.co` 动态占位图。数据集不来自商业平台爬取，不包含真实用户隐私。
