# 核心指标口径定义

> 所有口径遵循课程标准，与 ETL API `/api/etl/metrics` 保持一致。

## 1. GMV（商品交易总额）

- **公式**: `SUM(paid_amount) WHERE status IN ('paid', 'completed')`
- **来源表**: `fact_order` / `orders`
- **计算值**: ¥156,024,869.93
- **说明**: 只统计已支付和已完成的订单，排除 pending、cancelled、refunded 状态的订单中的未支付部分。

## 2. 净销售额（Net Sales）

- **公式**: `GMV - SUM(refunds.amount) WHERE status = 'approved'`
- **来源表**: `fact_order` + `fact_refund`
- **计算值**: ¥145,715,683.69
- **退款总额**: ¥10,309,186.24
- **说明**: 扣除已批准退款后的实际收入。

## 3. 毛利（Gross Profit）

- **公式**: `SUM((unit_price - unit_cost) * quantity - discount_amount)`
- **来源表**: `fact_order_item` JOIN `fact_order`（限定 status IN ('paid','completed')）
- **计算值**: ¥79,232,068.28
- **毛利率**: 50.8%
- **说明**: 从订单行逐行计算，扣除折扣金额。

## 4. 订单数（Order Count）

- **公式**: `COUNT(DISTINCT order_id) WHERE status IN ('paid', 'completed')`
- **来源表**: `fact_order`
- **计算值**: 108,040 笔
- **说明**: 去重计数已支付/已完成订单。

## 5. 买家数（Buyer Count）

- **公式**: `COUNT(DISTINCT user_id) WHERE status IN ('paid', 'completed')`
- **来源表**: `fact_order`
- **计算值**: 18,118 人
- **说明**: 有实际支付行为的独立用户数。

## 6. 客单价（AOV）

- **公式**: `GMV / 订单数`
- **计算值**: ¥1,444.14
- **说明**: 每笔订单的平均交易金额。

## 7. 退款率（Refund Rate）

- **公式**: `COUNT(DISTINCT refund_order_id WHERE status='approved') / COUNT(*) FROM orders`
- **来源表**: `fact_refund` + `fact_order`
- **计算值**: 7.75%
- **说明**: 已批准退款订单占总订单的比例。

## 8. 转化率（Conversion Rate）

- **公式**: `pay_success session 数 / 总 session 数`
- **来源表**: `fact_traffic`
- **计算值**: 49.39%
- **说明**: 产生支付的 session 占全部 session 比例（含未登录匿名流量）。

## 月度环比（MoM）

- **公式**: `(本月值 - 上月值) / 上月值 * 100%`
- **注意**: 排除不完整月份（如当前月未结束）。

## 年度同比（YoY）

- **公式**: `(本月值 - 去年同月值) / 去年同月值 * 100%`
