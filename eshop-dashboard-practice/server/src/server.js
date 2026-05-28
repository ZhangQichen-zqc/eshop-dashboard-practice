import express from "express";
import cors from "cors";
import morgan from "morgan";
import { nanoid } from "nanoid";
import { initSchema, openDb } from "./db.js";

const app = express();
const db = openDb();
initSchema(db);

app.use(cors());
app.use(express.json({ limit: "1mb" }));
app.use(morgan("dev"));

const now = () => new Date().toISOString().slice(0, 19).replace("T", " ");
const id = (prefix) => `${prefix}_${nanoid(10)}`;
const money = (value) => Number(value.toFixed(2));

function rowToProduct(row) {
  return {
    skuId: row.sku_id,
    spuId: row.spu_id,
    categoryId: row.category_id,
    categoryName: row.category_name,
    brand: row.brand,
    productName: row.product_name,
    skuName: row.sku_name,
    spec: row.spec,
    price: row.price,
    cost: row.cost,
    priceBand: row.price_band,
    productStatus: row.product_status,
    imageUrl: row.image_url,
    stock: row.stock,
    description: row.description
  };
}

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, service: "eshop-course-api" });
});

app.get("/api/categories", (_req, res) => {
  const rows = db.prepare("SELECT category_id AS categoryId, name FROM categories ORDER BY name").all();
  res.json(rows);
});

app.get("/api/products", (req, res) => {
  const { categoryId, q } = req.query;
  const filters = ["sk.status = 'on_sale'", "sp.status = 'on_sale'"];
  const params = {};
  if (categoryId) {
    filters.push("sp.category_id = @categoryId");
    params.categoryId = categoryId;
  }
  if (q) {
    filters.push("(sp.name LIKE @q OR sp.brand LIKE @q OR c.name LIKE @q)");
    params.q = `%${q}%`;
  }
  const rows = db.prepare(`
    SELECT
      sk.sku_id, sp.spu_id, c.category_id, c.name AS category_name,
      sp.brand, sp.name AS product_name, sp.description, sk.sku_name, sk.spec,
      sk.price, sk.cost, sk.stock, sk.image_url, sp.status AS product_status,
      CASE WHEN sk.price < 100 THEN 'low' WHEN sk.price < 500 THEN 'mid' ELSE 'high' END AS price_band
    FROM sku sk
    JOIN spu sp ON sp.spu_id = sk.spu_id
    JOIN categories c ON c.category_id = sp.category_id
    WHERE ${filters.join(" AND ")}
    ORDER BY c.name, sp.name, sk.price
  `).all(params);
  res.json(rows.map(rowToProduct));
});

app.get("/api/products/:skuId", (req, res) => {
  const row = db.prepare(`
    SELECT
      sk.sku_id, sp.spu_id, c.category_id, c.name AS category_name,
      sp.brand, sp.name AS product_name, sp.description, sk.sku_name, sk.spec,
      sk.price, sk.cost, sk.stock, sk.image_url, sp.status AS product_status,
      CASE WHEN sk.price < 100 THEN 'low' WHEN sk.price < 500 THEN 'mid' ELSE 'high' END AS price_band
    FROM sku sk
    JOIN spu sp ON sp.spu_id = sk.spu_id
    JOIN categories c ON c.category_id = sp.category_id
    WHERE sk.sku_id = ?
  `).get(req.params.skuId);

  if (!row) return res.status(404).json({ message: "商品不存在" });
  res.json(rowToProduct(row));
});

app.post("/api/auth/login", (req, res) => {
  const { email, password } = req.body;
  const user = db.prepare(`
    SELECT user_id AS userId, name, email, segment, status
    FROM users
    WHERE email = ? AND password = ?
  `).get(email, password);

  if (!user || user.status !== "active") {
    return res.status(401).json({ message: "邮箱或密码错误" });
  }

  res.json(user);
});

app.post("/api/auth/register", (req, res) => {
  const { name, email, password } = req.body;
  if (!name || !email || !password) {
    return res.status(400).json({ message: "姓名、邮箱和密码必填" });
  }

  try {
    const userId = id("user");
    db.prepare(`
      INSERT INTO users (user_id, name, email, password, phone, province, city, register_channel, segment, status, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(userId, name, email, password, "", "未知", "未知", "organic", "new", "active", now());
    res.status(201).json({ userId, name, email, segment: "new", status: "active" });
  } catch (error) {
    res.status(409).json({ message: "邮箱已存在" });
  }
});

app.get("/api/coupons", (_req, res) => {
  const rows = db.prepare(`
    SELECT coupon_id AS couponId, campaign_id AS campaignId, code, name, threshold, discount, start_date AS startDate, end_date AS endDate
    FROM coupons
    WHERE status = 'active'
    ORDER BY discount DESC
  `).all();
  res.json(rows);
});

app.get("/api/orders", (req, res) => {
  const { userId } = req.query;
  if (!userId) return res.status(400).json({ message: "缺少 userId" });

  const orders = db.prepare(`
    SELECT order_id AS orderId, order_no AS orderNo, status, channel, subtotal, discount_amount AS discountAmount,
      shipping_fee AS shippingFee, paid_amount AS paidAmount, created_at AS createdAt
    FROM orders
    WHERE user_id = ?
    ORDER BY created_at DESC
    LIMIT 50
  `).all(userId);

  const itemStmt = db.prepare(`
    SELECT oi.quantity, oi.unit_price AS unitPrice, oi.line_amount AS lineAmount, sk.sku_name AS skuName, sk.image_url AS imageUrl
    FROM order_items oi
    JOIN sku sk ON sk.sku_id = oi.sku_id
    WHERE oi.order_id = ?
  `);

  res.json(orders.map((order) => ({ ...order, items: itemStmt.all(order.orderId) })));
});

app.post("/api/checkout", (req, res) => {
  const { userId, items, couponCode, channel = "organic" } = req.body;
  if (!userId || !Array.isArray(items) || items.length === 0) {
    return res.status(400).json({ message: "缺少用户或商品" });
  }

  const checkout = db.transaction(() => {
    const user = db.prepare("SELECT user_id FROM users WHERE user_id = ?").get(userId);
    if (!user) throw new Error("用户不存在");

    const productStmt = db.prepare("SELECT sku_id, spu_id, price, cost, stock FROM sku WHERE sku_id = ? AND status = 'on_sale'");
    const products = items.map((item) => {
      const product = productStmt.get(item.skuId);
      if (!product) throw new Error(`商品不存在：${item.skuId}`);
      const quantity = Number(item.quantity || 1);
      if (quantity < 1 || product.stock < quantity) throw new Error(`库存不足：${item.skuId}`);
      return { ...product, quantity };
    });

    const coupon = couponCode
      ? db.prepare("SELECT * FROM coupons WHERE code = ? AND status = 'active'").get(couponCode)
      : null;
    const subtotal = money(products.reduce((sum, product) => sum + product.price * product.quantity, 0));
    const discount = coupon && subtotal >= coupon.threshold ? money(coupon.discount) : 0;
    const shipping = subtotal >= 99 ? 0 : 8;
    const paid = money(subtotal - discount + shipping);
    const createdAt = now();
    const orderId = id("order");
    const orderNo = `NO${new Date().toISOString().slice(0, 10).replaceAll("-", "")}${nanoid(6).toUpperCase()}`;

    db.prepare(`
      INSERT INTO orders (order_id, user_id, campaign_id, order_no, status, channel, subtotal, discount_amount, shipping_fee, total_amount, paid_amount, created_at, paid_at, completed_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(orderId, userId, coupon?.campaign_id ?? null, orderNo, "paid", channel, subtotal, discount, shipping, paid, paid, createdAt, createdAt, null);

    products.forEach((product) => {
      const shareDiscount = subtotal ? money((product.price * product.quantity / subtotal) * discount) : 0;
      db.prepare(`
        INSERT INTO order_items (order_item_id, order_id, sku_id, spu_id, quantity, unit_price, unit_cost, discount_amount, line_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(id("oi"), orderId, product.sku_id, product.spu_id, product.quantity, product.price, product.cost, shareDiscount, money(product.price * product.quantity - shareDiscount));
      db.prepare("UPDATE sku SET stock = stock - ? WHERE sku_id = ?").run(product.quantity, product.sku_id);
      db.prepare(`
        INSERT INTO inventory_movements (movement_id, sku_id, movement_type, quantity, reason, related_order_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `).run(id("inv"), product.sku_id, "out", -product.quantity, "sale", orderId, createdAt);
    });

    db.prepare("INSERT INTO payments (payment_id, order_id, provider, amount, status, paid_at) VALUES (?, ?, ?, ?, ?, ?)")
      .run(id("pay"), orderId, "mock_pay", paid, "success", createdAt);

    db.prepare(`
      INSERT INTO shipments (shipment_id, order_id, carrier, province, promised_days, shipped_at, delivered_at, delivery_days, status)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(id("ship"), orderId, "教学物流", "未知", 5, createdAt, null, null, "shipping");

    if (coupon) {
      db.prepare(`
        INSERT INTO user_coupons (user_coupon_id, user_id, coupon_id, issued_at, used_at, order_id)
        VALUES (?, ?, ?, ?, ?, ?)
      `).run(id("uc"), userId, coupon.coupon_id, createdAt, createdAt, orderId);
      db.prepare("UPDATE coupons SET issued_count = issued_count + 1, used_count = used_count + 1 WHERE coupon_id = ?").run(coupon.coupon_id);
    }

    const sessionId = id("sess");
    for (const eventType of ["view", "add_to_cart", "checkout"]) {
      db.prepare(`
        INSERT INTO page_events (event_id, user_id, session_id, event_type, page, channel, campaign_id, sku_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(id("evt"), userId, sessionId, eventType, eventType === "view" ? "product_detail" : eventType, channel, coupon?.campaign_id ?? null, products[0].sku_id, createdAt);
    }

    return { orderId, orderNo, paidAmount: paid, discountAmount: discount };
  });

  try {
    res.status(201).json(checkout());
  } catch (error) {
    res.status(400).json({ message: error.message });
  }
});

app.get("/api/analytics/daily", (_req, res) => {
  const rows = db.prepare(`
    SELECT summary_date AS date, channel, orders, buyers, gmv, discount_amount AS discountAmount, avg_order_value AS avgOrderValue
    FROM daily_business_summary
    ORDER BY summary_date DESC, channel
    LIMIT 120
  `).all();
  res.json(rows);
});

app.get("/api/analytics/rfm", (_req, res) => {
  const rows = db.prepare(`
    SELECT
      u.user_id AS userId,
      u.name,
      u.segment,
      CAST(julianday('now') - julianday(MAX(o.created_at)) AS INTEGER) AS recencyDays,
      COUNT(o.order_id) AS frequency,
      ROUND(SUM(o.paid_amount), 2) AS monetary
    FROM users u
    JOIN orders o ON o.user_id = u.user_id
    WHERE o.status IN ('paid', 'completed')
    GROUP BY u.user_id, u.name, u.segment
    ORDER BY monetary DESC
    LIMIT 100
  `).all();
  res.json(rows);
});

/* ========== ETL Read-Only APIs for Data Mining Course ========== */

app.get("/api/etl/help", (_req, res) => {
  res.json({
    service: "eshop-course-etl-api",
    description: "电商经营数据 ETL 只读接口，供数据挖掘课程教学使用。所有接口仅执行 SELECT，不会修改数据。",
    baseUrl: "http://{host}:38173/api/etl",
    endpoints: [
      {
        path: "/api/etl/help",
        method: "GET",
        description: "本帮助文档",
        params: [],
        example: "/api/etl/help"
      },
      {
        path: "/api/etl/tables",
        method: "GET",
        description: "列出所有可用表（分析视图 + 源表），含记录数和中文说明",
        params: [],
        example: "/api/etl/tables"
      },
      {
        path: "/api/etl/schema/:table",
        method: "GET",
        description: "获取指定表的字段结构（名称、类型、是否非空、默认值、主键）",
        params: [
          { name: "table", type: "path", required: true, description: "表名，如 fact_order、dim_user" }
        ],
        example: "/api/etl/schema/fact_order"
      },
      {
        path: "/api/etl/query/:table",
        method: "GET",
        description: "分页查询指定表的数据，支持过滤、排序",
        params: [
          { name: "table", type: "path", required: true, description: "表名" },
          { name: "limit", type: "query", required: false, default: "100", description: "返回行数上限（最大 5000）" },
          { name: "offset", type: "query", required: false, default: "0", description: "偏移量" },
          { name: "orderBy", type: "query", required: false, description: "排序字段" },
          { name: "orderDir", type: "query", required: false, default: "asc", description: "排序方向：asc 或 desc" },
          { name: "<field>", type: "query", required: false, description: "任意字段名可作为精确过滤条件，如 ?status=completed" }
        ],
        example: "/api/etl/query/fact_order?limit=50&offset=0&orderBy=order_date&orderDir=desc&status=completed&channel=search"
      },
      {
        path: "/api/etl/export/:table",
        method: "GET",
        description: "导出指定表数据为 JSON 或 CSV",
        params: [
          { name: "table", type: "path", required: true, description: "表名" },
          { name: "format", type: "query", required: false, default: "json", description: "导出格式：json 或 csv" },
          { name: "limit", type: "query", required: false, default: "50000", description: "导出上限（最大 100000）" }
        ],
        example: "/api/etl/export/dim_product?format=csv&limit=10000"
      },
      {
        path: "/api/etl/quality",
        method: "GET",
        description: "数据质量检查报告（R0）。覆盖完整性、准确性、一致性、时效性、分布、业务逻辑 6 大类",
        params: [],
        example: "/api/etl/quality"
      },
      {
        path: "/api/etl/metrics",
        method: "GET",
        description: "核心经营指标及口径定义。返回 GMV、净销售额、毛利、订单数、买家数、客单价、退款率、流量漏斗",
        params: [],
        example: "/api/etl/metrics"
      }
    ],
    analyticsViews: [
      { name: "dim_date", description: "日期维度" },
      { name: "dim_product", description: "SKU 维度：类目、品牌、价格带、供应商" },
      { name: "dim_user", description: "用户维度：地区、注册渠道、生命周期、会员等级" },
      { name: "dim_campaign", description: "活动维度：渠道、类型、目标人群、对照组" },
      { name: "fact_order", description: "订单事实：GMV、客单价、复购、活动订单" },
      { name: "fact_order_item", description: "订单行事实：类目贡献、毛利、购物篮" },
      { name: "fact_traffic", description: "流量事实：漏斗、路径、渠道转化、未转化行为" },
      { name: "fact_coupon_use", description: "优惠券事实：发放率、核销率、券敏感度" },
      { name: "fact_refund", description: "退款事实：退款率、原因结构、售后风险" },
      { name: "fact_fulfillment", description: "履约事实：配送时效、延迟率" },
      { name: "fact_inventory_movement", description: "库存流水：补货、出库、动销" },
      { name: "fact_product_review", description: "评论事实：评分、情感、体验问题" },
      { name: "fact_ads_spend", description: "广告日消耗：ROAS、点击率、转化成本" },
      { name: "daily_business_summary", description: "经营日报：日期+渠道粒度" }
    ],
    notes: [
      "所有接口均为只读，不会修改数据库",
      "单次查询上限 5000 行，导出上限 100000 行",
      "表名需通过 /api/etl/tables 白名单校验，防止 SQL 注入",
      "后端监听所有网卡，局域网或外网域名均可访问"
    ]
  });
});

const ETL_TABLES = [
  // Analytics views
  "dim_date", "dim_product", "dim_user", "dim_campaign",
  "fact_order", "fact_order_item", "fact_traffic", "fact_coupon_use",
  "fact_refund", "fact_fulfillment", "fact_inventory_movement",
  "fact_product_review", "fact_ads_spend", "daily_business_summary",
  // Source tables
  "users", "addresses", "categories", "spu", "sku",
  "campaigns", "coupons", "user_coupons", "carts", "cart_items",
  "orders", "order_items", "payments", "refunds", "shipments",
  "inventory_movements", "product_reviews", "page_events", "ads_spend", "admin_action_logs"
];

const TABLE_META = {
  dim_date: { type: "dimension", description: "日期维度：月度、周末、时间序列" },
  dim_product: { type: "dimension", description: "SKU维度：类目、品牌、规格、价格带、成本、供应商" },
  dim_user: { type: "dimension", description: "用户维度：地区、注册渠道、生命周期、会员等级" },
  dim_campaign: { type: "dimension", description: "活动维度：渠道、类型、目标人群、对照组、预算" },
  fact_order: { type: "fact", description: "订单事实：GMV、客单价、复购、活动订单" },
  fact_order_item: { type: "fact", description: "订单行事实：类目贡献、毛利、购物篮、SKU长尾" },
  fact_traffic: { type: "fact", description: "流量事实：漏斗、路径、渠道转化、未转化行为" },
  fact_coupon_use: { type: "fact", description: "优惠券事实：发放率、核销率、券敏感度" },
  fact_refund: { type: "fact", description: "退款事实：退款率、原因结构、售后风险" },
  fact_fulfillment: { type: "fact", description: "履约事实：配送时效、延迟率" },
  fact_inventory_movement: { type: "fact", description: "库存流水：补货、出库、动销、缺货风险" },
  fact_product_review: { type: "fact", description: "评论事实：评分、情感、体验问题" },
  fact_ads_spend: { type: "fact", description: "广告日消耗：ROAS、点击率、转化成本" },
  daily_business_summary: { type: "summary", description: "经营日报：日期+渠道粒度" },
  users: { type: "source", description: "用户源表：注册渠道、地区、性别、年龄段、会员等级" },
  orders: { type: "source", description: "订单头源表：渠道、活动、金额、状态" },
  order_items: { type: "source", description: "订单行源表：SKU、数量、单价、成本、分摊优惠" },
  page_events: { type: "source", description: "行为事件源表：曝光/浏览/搜索/加购/结算/支付成功" },
  product_reviews: { type: "source", description: "评论源表：评分、情感、内容标签" },
  refunds: { type: "source", description: "退款源表：退款原因、金额、审核状态" },
  shipments: { type: "source", description: "履约包裹源表：承运商、承诺时效、实际时效" },
  inventory_movements: { type: "source", description: "库存流水源表：初始库存、补货、销售出库" },
  ads_spend: { type: "source", description: "广告日花费源表：曝光、点击、转化、消耗" },
  campaigns: { type: "source", description: "营销活动源表：渠道、类型、目标人群、对照组" },
  coupons: { type: "source", description: "优惠券模板源表：门槛、面额、发放与使用计数" },
  sku: { type: "source", description: "可售规格源表：价格、成本、供应商、库存" },
  spu: { type: "source", description: "标准商品源表：品牌、名称、描述" },
  categories: { type: "source", description: "商品类目源表：一级类目" },
  user_coupons: { type: "source", description: "用户券源表：发放、未使用、核销和订单关联" },
  payments: { type: "source", description: "支付流水源表：支付方式和支付结果" },
  addresses: { type: "source", description: "用户地址源表：收货地址与省市" },
  carts: { type: "source", description: "购物车源表" },
  cart_items: { type: "source", description: "购物车行源表" },
  admin_action_logs: { type: "source", description: "后台审计源表：运营动作日志" }
};

function validateTable(table) {
  if (!ETL_TABLES.includes(table)) {
    throw new Error(`非法表名: ${table}`);
  }
}

// 1. 列出所有可用表
app.get("/api/etl/tables", (_req, res) => {
  const rows = db.prepare(`
    SELECT name FROM sqlite_master
    WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
    ORDER BY type, name
  `).all();
  const result = rows.map((r) => {
    const meta = TABLE_META[r.name] || { type: "unknown", description: "" };
    const count = db.prepare(`SELECT COUNT(*) AS c FROM "${r.name}"`).get().c;
    return { tableName: r.name, recordCount: count, ...meta };
  });
  res.json({ tables: result, total: result.length });
});

// 2. 获取表结构
app.get("/api/etl/schema/:table", (req, res) => {
  try {
    const { table } = req.params;
    validateTable(table);
    const columns = db.prepare(`PRAGMA table_info("${table}")`).all();
    const meta = TABLE_META[table] || { type: "unknown", description: "" };
    res.json({
      tableName: table,
      columns: columns.map((c) => ({
        name: c.name,
        type: c.type,
        notNull: c.notnull === 1,
        defaultValue: c.dflt_value,
        pk: c.pk === 1
      })),
      ...meta
    });
  } catch (error) {
    res.status(400).json({ message: error.message });
  }
});

// 3. 分页查询数据
app.get("/api/etl/query/:table", (req, res) => {
  try {
    const { table } = req.params;
    validateTable(table);
    const limit = Math.min(Number(req.query.limit) || 100, 5000);
    const offset = Math.max(Number(req.query.offset) || 0, 0);
    const orderBy = req.query.orderBy;
    const orderDir = req.query.orderDir === "desc" ? "DESC" : "ASC";

    let sql = `SELECT * FROM "${table}"`;
    const params = [];

    // Simple WHERE support for exact match: ?field=value
    const conditions = [];
    for (const [key, value] of Object.entries(req.query)) {
      if (["limit", "offset", "orderBy", "orderDir"].includes(key)) continue;
      conditions.push(`"${key}" = ?`);
      params.push(value);
    }
    if (conditions.length > 0) {
      sql += ` WHERE ${conditions.join(" AND ")}`;
    }

    if (orderBy) {
      sql += ` ORDER BY "${orderBy}" ${orderDir}`;
    }
    sql += ` LIMIT ? OFFSET ?`;
    params.push(limit, offset);

    const rows = db.prepare(sql).all(...params);
    const countRow = db.prepare(`SELECT COUNT(*) AS c FROM "${table}"`).get();
    res.json({
      tableName: table,
      total: countRow.c,
      limit,
      offset,
      rows
    });
  } catch (error) {
    res.status(400).json({ message: error.message });
  }
});

// 4. 导出数据（JSON 或 CSV）
app.get("/api/etl/export/:table", (req, res) => {
  try {
    const { table } = req.params;
    const format = req.query.format || "json";
    validateTable(table);

    const limit = Math.min(Number(req.query.limit) || 50000, 100000);
    const rows = db.prepare(`SELECT * FROM "${table}" LIMIT ?`).all(limit);

    if (format === "csv") {
      if (rows.length === 0) {
        res.setHeader("Content-Type", "text/csv; charset=utf-8");
        return res.send("");
      }
      const headers = Object.keys(rows[0]);
      const csvEscape = (value) => {
        if (value == null) return "";
        const text = String(value);
        return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
      };
      const lines = [headers.join(",")];
      for (const row of rows) {
        lines.push(headers.map((h) => csvEscape(row[h])).join(","));
      }
      res.setHeader("Content-Type", "text/csv; charset=utf-8");
      res.setHeader("Content-Disposition", `attachment; filename="${table}.csv"`);
      return res.send(lines.join("\n"));
    }

    res.json({ tableName: table, count: rows.length, rows });
  } catch (error) {
    res.status(400).json({ message: error.message });
  }
});

// 5. 数据质量检查（R0）
app.get("/api/etl/quality", (_req, res) => {
  const report = { generatedAt: new Date().toISOString(), checks: [] };

  // Helper to push check result
  const addCheck = (category, name, status, detail, metrics = {}) => {
    report.checks.push({ category, name, status, detail, metrics });
  };

  // 5.1 表行数与预期
  const expectedRows = {
    users: 20000, orders: 100000, page_events: 700000,
    sku: 864, campaigns: 50
  };
  for (const [table, expected] of Object.entries(expectedRows)) {
    const count = db.prepare(`SELECT COUNT(*) AS c FROM ${table}`).get().c;
    const status = count >= expected * 0.8 ? "pass" : "warn";
    addCheck("完整性", `${table} 行数`, status,
      `实际 ${count.toLocaleString()} 行，预期约 ${expected.toLocaleString()} 行`,
      { actual: count, expected });
  }

  // 5.2 users 缺失值
  const userNulls = db.prepare(`
    SELECT
      SUM(CASE WHEN phone IS NULL OR phone = '' THEN 1 ELSE 0 END) AS phone_missing,
      SUM(CASE WHEN gender IS NULL OR gender = '' THEN 1 ELSE 0 END) AS gender_missing,
      SUM(CASE WHEN birth_year IS NULL THEN 1 ELSE 0 END) AS birth_year_missing,
      SUM(CASE WHEN province IS NULL OR province = '' THEN 1 ELSE 0 END) AS province_missing
    FROM users
  `).get();
  addCheck("完整性", "users 关键字段缺失值", "pass",
    `phone缺失 ${userNulls.phone_missing}, gender缺失 ${userNulls.gender_missing}, birth_year缺失 ${userNulls.birth_year_missing}, province缺失 ${userNulls.province_missing}`,
    userNulls);

  // 5.3 重复主键检查
  const dupUsers = db.prepare(`SELECT COUNT(*) AS c FROM (SELECT user_id FROM users GROUP BY user_id HAVING COUNT(*) > 1)`).get().c;
  const dupOrders = db.prepare(`SELECT COUNT(*) AS c FROM (SELECT order_id FROM orders GROUP BY order_id HAVING COUNT(*) > 1)`).get().c;
  const dupSku = db.prepare(`SELECT COUNT(*) AS c FROM (SELECT sku_id FROM sku GROUP BY sku_id HAVING COUNT(*) > 1)`).get().c;
  addCheck("完整性", "users 重复主键", dupUsers === 0 ? "pass" : "fail", `重复 user_id: ${dupUsers}`, { duplicateCount: dupUsers });
  addCheck("完整性", "orders 重复主键", dupOrders === 0 ? "pass" : "fail", `重复 order_id: ${dupOrders}`, { duplicateCount: dupOrders });
  addCheck("完整性", "sku 重复主键", dupSku === 0 ? "pass" : "fail", `重复 sku_id: ${dupSku}`, { duplicateCount: dupSku });

  // 5.4 订单金额异常
  const orderAmountAnomaly = db.prepare(`
    SELECT
      SUM(CASE WHEN paid_amount < 0 THEN 1 ELSE 0 END) AS negative_paid,
      SUM(CASE WHEN subtotal < 0 THEN 1 ELSE 0 END) AS negative_subtotal,
      SUM(CASE WHEN total_amount < 0 THEN 1 ELSE 0 END) AS negative_total,
      SUM(CASE WHEN paid_amount > total_amount * 1.5 THEN 1 ELSE 0 END) AS paid_over_total
    FROM orders
  `).get();
  const amountStatus = (orderAmountAnomaly.negative_paid + orderAmountAnomaly.negative_subtotal + orderAmountAnomaly.negative_total) === 0 ? "pass" : "fail";
  addCheck("准确性", "orders 金额异常", amountStatus,
    `负数 paid_amount: ${orderAmountAnomaly.negative_paid}, 负数 subtotal: ${orderAmountAnomaly.negative_subtotal}, 负数 total: ${orderAmountAnomaly.negative_total}, paid>total*1.5: ${orderAmountAnomaly.paid_over_total}`,
    orderAmountAnomaly);

  // 5.5 订单行金额 vs 订单金额一致性（使用 JOIN 避免相关子查询）
  const lineAmountCheck = db.prepare(`
    SELECT COUNT(*) AS mismatch
    FROM (
      SELECT o.order_id, o.paid_amount, SUM(oi.line_amount) AS line_sum
      FROM orders o
      JOIN order_items oi ON oi.order_id = o.order_id
      GROUP BY o.order_id
      HAVING ABS(o.paid_amount - line_sum) > 0.01
    )
  `).get();
  addCheck("一致性", "order_items 行金额与订单金额差异", lineAmountCheck.mismatch === 0 ? "pass" : "warn",
    `不一致订单数: ${lineAmountCheck.mismatch}`, { mismatchCount: lineAmountCheck.mismatch });

  // 5.6 订单状态分布
  const statusDist = db.prepare(`SELECT status, COUNT(*) AS c FROM orders GROUP BY status`).all();
  addCheck("分布", "orders 状态分布", "pass",
    statusDist.map((s) => `${s.status}: ${s.c}`).join(", "),
    Object.fromEntries(statusDist.map((s) => [s.status, s.c])));

  // 5.7 时间范围与新鲜度
  const dateRange = db.prepare(`
    SELECT MIN(date(created_at)) AS min_date, MAX(date(created_at)) AS max_date
    FROM orders
  `).get();
  const eventDateRange = db.prepare(`
    SELECT MIN(date(created_at)) AS min_date, MAX(date(created_at)) AS max_date
    FROM page_events
  `).get();
  addCheck("时效性", "orders 时间范围", "pass",
    `从 ${dateRange.min_date} 到 ${dateRange.max_date}`, { minDate: dateRange.min_date, maxDate: dateRange.max_date });
  addCheck("时效性", "page_events 时间范围", "pass",
    `从 ${eventDateRange.min_date} 到 ${eventDateRange.max_date}`, { minDate: eventDateRange.min_date, maxDate: eventDateRange.max_date });

  // 5.8 退款金额异常
  const refundAnomaly = db.prepare(`
    SELECT
      SUM(CASE WHEN amount < 0 THEN 1 ELSE 0 END) AS negative_amount,
      SUM(CASE WHEN amount > o.paid_amount THEN 1 ELSE 0 END) AS overpaid_refund
    FROM refunds r
    JOIN orders o ON o.order_id = r.order_id
  `).get();
  addCheck("准确性", "refunds 退款金额异常", (refundAnomaly.negative_amount + refundAnomaly.overpaid_refund) === 0 ? "pass" : "warn",
    `负数退款: ${refundAnomaly.negative_amount}, 超付退款: ${refundAnomaly.overpaid_refund}`, refundAnomaly);

  // 5.9 SKU 库存负数
  const negativeStock = db.prepare(`SELECT COUNT(*) AS c FROM sku WHERE stock < 0`).get().c;
  addCheck("准确性", "sku 负库存检查", negativeStock === 0 ? "pass" : "fail",
    `负库存 SKU 数: ${negativeStock}`, { negativeStockCount: negativeStock });

  // 5.10 匿名流量比例
  const anonTraffic = db.prepare(`
    SELECT
      SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) AS anonymous,
      COUNT(*) AS total
    FROM page_events
  `).get();
  const anonRatio = anonTraffic.total > 0 ? Number((anonTraffic.anonymous / anonTraffic.total).toFixed(4)) : 0;
  addCheck("完整性", "page_events 匿名流量比例", "pass",
    `匿名事件 ${anonTraffic.anonymous} / ${anonTraffic.total} (${(anonRatio * 100).toFixed(2)}%)`,
    { anonymous: anonTraffic.anonymous, total: anonTraffic.total, ratio: anonRatio });

  // 5.11 优惠券核销率
  const couponRate = db.prepare(`
    SELECT
      SUM(CASE WHEN used_count > 0 THEN 1 ELSE 0 END) AS used_coupons,
      COUNT(*) AS total_coupons
    FROM coupons
  `).get();
  addCheck("业务逻辑", "coupons 整体使用状态", "pass",
    `至少使用1次的优惠券模板: ${couponRate.used_coupons} / ${couponRate.total_coupons}`,
    { usedTemplates: couponRate.used_coupons, totalTemplates: couponRate.total_coupons });

  // Summary
  const passCount = report.checks.filter((c) => c.status === "pass").length;
  const warnCount = report.checks.filter((c) => c.status === "warn").length;
  const failCount = report.checks.filter((c) => c.status === "fail").length;
  report.summary = { total: report.checks.length, pass: passCount, warn: warnCount, fail: failCount };

  res.json(report);
});

// 6. 核心指标口径查询
app.get("/api/etl/metrics", (_req, res) => {
  const gmv = db.prepare(`SELECT ROUND(SUM(paid_amount), 2) AS gmv FROM orders WHERE status IN ('paid', 'completed')`).get().gmv;
  const orderCount = db.prepare(`SELECT COUNT(DISTINCT order_id) AS c FROM orders WHERE status IN ('paid', 'completed')`).get().c;
  const buyerCount = db.prepare(`SELECT COUNT(DISTINCT user_id) AS c FROM orders WHERE status IN ('paid', 'completed')`).get().c;
  const refundAmount = db.prepare(`SELECT ROUND(SUM(amount), 2) AS refund FROM refunds WHERE status = 'approved'`).get().refund;
  const netSales = money(Number(gmv || 0) - Number(refundAmount || 0));
  const grossProfit = db.prepare(`
    SELECT ROUND(SUM((oi.unit_price - oi.unit_cost) * oi.quantity - oi.discount_amount), 2) AS gp
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id
    WHERE o.status IN ('paid', 'completed')
  `).get().gp;
  const paidOrders = db.prepare(`SELECT COUNT(DISTINCT order_id) AS c FROM orders WHERE status IN ('paid', 'completed')`).get().c;
  const refundOrders = db.prepare(`SELECT COUNT(DISTINCT order_id) AS c FROM refunds WHERE status = 'approved'`).get().c;
  const refundRate = paidOrders > 0 ? Number((refundOrders / paidOrders).toFixed(4)) : 0;
  const avgOrderValue = orderCount > 0 ? Number((Number(gmv || 0) / orderCount).toFixed(2)) : 0;

  // Conversion funnel from traffic
  const funnel = db.prepare(`
    SELECT
      SUM(CASE WHEN event_type = 'view_home' THEN 1 ELSE 0 END) AS view_home,
      SUM(CASE WHEN event_type = 'view_product' THEN 1 ELSE 0 END) AS view_product,
      SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END) AS add_to_cart,
      SUM(CASE WHEN event_type = 'checkout' THEN 1 ELSE 0 END) AS checkout,
      SUM(CASE WHEN event_type = 'pay_success' THEN 1 ELSE 0 END) AS pay_success
    FROM page_events
  `).get();

  res.json({
    metrics: {
      gmv: { value: gmv, definition: "SUM(orders.paid_amount) WHERE status IN ('paid', 'completed')" },
      netSales: { value: netSales, definition: "GMV - SUM(refunds.amount) WHERE status = 'approved'" },
      grossProfit: { value: grossProfit, definition: "SUM((unit_price - unit_cost) * quantity - discount_amount)" },
      orderCount: { value: orderCount, definition: "COUNT(DISTINCT order_id) WHERE status IN ('paid', 'completed')" },
      buyerCount: { value: buyerCount, definition: "COUNT(DISTINCT user_id) WHERE status IN ('paid', 'completed')" },
      avgOrderValue: { value: avgOrderValue, definition: "GMV / 订单数" },
      refundRate: { value: refundRate, definition: "退款订单数 / 支付订单数" },
      funnel: {
        view_home: funnel.view_home,
        view_product: funnel.view_product,
        add_to_cart: funnel.add_to_cart,
        checkout: funnel.checkout,
        pay_success: funnel.pay_success,
        definition: "page_events 各 event_type 计数"
      }
    }
  });
});

const port = Number(process.env.PORT || 38173);
app.listen(port, () => {
  console.log(`Course eShop API listening on http://localhost:${port}`);
});
