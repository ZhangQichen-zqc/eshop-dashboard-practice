import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const defaultDbPath = path.resolve(__dirname, "../data/eshop.sqlite");

export const dbPath = process.env.DATABASE_URL?.startsWith("file:")
  ? process.env.DATABASE_URL.replace("file:", "")
  : defaultDbPath;

export function openDb() {
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  return db;
}

export function initSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      user_id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE,
      password TEXT NOT NULL,
      phone TEXT,
      province TEXT,
      city TEXT,
      register_channel TEXT NOT NULL,
      segment TEXT NOT NULL DEFAULT 'new',
      gender TEXT,
      birth_year INTEGER,
      member_level TEXT NOT NULL DEFAULT 'normal',
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS addresses (
      address_id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL REFERENCES users(user_id),
      receiver TEXT NOT NULL,
      phone TEXT NOT NULL,
      province TEXT NOT NULL,
      city TEXT NOT NULL,
      detail TEXT NOT NULL,
      is_default INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS categories (
      category_id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      parent_id TEXT REFERENCES categories(category_id)
    );

    CREATE TABLE IF NOT EXISTS spu (
      spu_id TEXT PRIMARY KEY,
      category_id TEXT NOT NULL REFERENCES categories(category_id),
      brand TEXT NOT NULL,
      name TEXT NOT NULL,
      description TEXT NOT NULL,
      image_url TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'on_sale',
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sku (
      sku_id TEXT PRIMARY KEY,
      spu_id TEXT NOT NULL REFERENCES spu(spu_id),
      sku_name TEXT NOT NULL,
      spec TEXT NOT NULL,
      price REAL NOT NULL,
      cost REAL NOT NULL,
      supplier TEXT,
      listing_date TEXT,
      stock INTEGER NOT NULL,
      image_url TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'on_sale'
    );

    CREATE TABLE IF NOT EXISTS campaigns (
      campaign_id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      channel TEXT NOT NULL,
      campaign_type TEXT NOT NULL DEFAULT 'promotion',
      target_segment TEXT NOT NULL DEFAULT 'all',
      has_control_group INTEGER NOT NULL DEFAULT 0,
      start_date TEXT NOT NULL,
      end_date TEXT NOT NULL,
      budget REAL NOT NULL,
      status TEXT NOT NULL DEFAULT 'active'
    );

    CREATE TABLE IF NOT EXISTS coupons (
      coupon_id TEXT PRIMARY KEY,
      campaign_id TEXT REFERENCES campaigns(campaign_id),
      code TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      threshold REAL NOT NULL,
      discount REAL NOT NULL,
      start_date TEXT NOT NULL,
      end_date TEXT NOT NULL,
      total_limit INTEGER NOT NULL,
      issued_count INTEGER NOT NULL DEFAULT 0,
      used_count INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'active'
    );

    CREATE TABLE IF NOT EXISTS user_coupons (
      user_coupon_id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL REFERENCES users(user_id),
      coupon_id TEXT NOT NULL REFERENCES coupons(coupon_id),
      issued_at TEXT NOT NULL,
      used_at TEXT,
      order_id TEXT
    );

    CREATE TABLE IF NOT EXISTS carts (
      cart_id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL REFERENCES users(user_id),
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS cart_items (
      cart_item_id TEXT PRIMARY KEY,
      cart_id TEXT NOT NULL REFERENCES carts(cart_id),
      sku_id TEXT NOT NULL REFERENCES sku(sku_id),
      quantity INTEGER NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS orders (
      order_id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL REFERENCES users(user_id),
      campaign_id TEXT REFERENCES campaigns(campaign_id),
      order_no TEXT NOT NULL UNIQUE,
      status TEXT NOT NULL,
      channel TEXT NOT NULL,
      subtotal REAL NOT NULL,
      discount_amount REAL NOT NULL,
      shipping_fee REAL NOT NULL,
      total_amount REAL NOT NULL,
      paid_amount REAL NOT NULL,
      created_at TEXT NOT NULL,
      paid_at TEXT,
      completed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS order_items (
      order_item_id TEXT PRIMARY KEY,
      order_id TEXT NOT NULL REFERENCES orders(order_id),
      sku_id TEXT NOT NULL REFERENCES sku(sku_id),
      spu_id TEXT NOT NULL REFERENCES spu(spu_id),
      quantity INTEGER NOT NULL,
      unit_price REAL NOT NULL,
      unit_cost REAL NOT NULL,
      discount_amount REAL NOT NULL,
      line_amount REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS payments (
      payment_id TEXT PRIMARY KEY,
      order_id TEXT NOT NULL REFERENCES orders(order_id),
      provider TEXT NOT NULL,
      amount REAL NOT NULL,
      status TEXT NOT NULL,
      paid_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS refunds (
      refund_id TEXT PRIMARY KEY,
      order_id TEXT NOT NULL REFERENCES orders(order_id),
      amount REAL NOT NULL,
      reason TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS shipments (
      shipment_id TEXT PRIMARY KEY,
      order_id TEXT NOT NULL REFERENCES orders(order_id),
      carrier TEXT NOT NULL,
      province TEXT NOT NULL,
      promised_days INTEGER NOT NULL,
      shipped_at TEXT,
      delivered_at TEXT,
      delivery_days REAL,
      status TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS inventory_movements (
      movement_id TEXT PRIMARY KEY,
      sku_id TEXT NOT NULL REFERENCES sku(sku_id),
      movement_type TEXT NOT NULL,
      quantity INTEGER NOT NULL,
      reason TEXT NOT NULL,
      related_order_id TEXT,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS product_reviews (
      review_id TEXT PRIMARY KEY,
      order_id TEXT NOT NULL REFERENCES orders(order_id),
      user_id TEXT NOT NULL REFERENCES users(user_id),
      sku_id TEXT NOT NULL REFERENCES sku(sku_id),
      rating INTEGER NOT NULL,
      sentiment TEXT NOT NULL,
      content_tag TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS page_events (
      event_id TEXT PRIMARY KEY,
      user_id TEXT REFERENCES users(user_id),
      session_id TEXT NOT NULL,
      event_type TEXT NOT NULL,
      page TEXT NOT NULL,
      channel TEXT NOT NULL,
      device TEXT NOT NULL DEFAULT 'mobile',
      campaign_id TEXT REFERENCES campaigns(campaign_id),
      sku_id TEXT REFERENCES sku(sku_id),
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS ads_spend (
      spend_id TEXT PRIMARY KEY,
      campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
      spend_date TEXT NOT NULL,
      channel TEXT NOT NULL,
      impressions INTEGER NOT NULL,
      clicks INTEGER NOT NULL,
      conversions INTEGER NOT NULL DEFAULT 0,
      spend_amount REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS admin_action_logs (
      log_id TEXT PRIMARY KEY,
      admin_name TEXT NOT NULL,
      action_type TEXT NOT NULL,
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      detail TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE VIEW IF NOT EXISTS dim_product AS
      SELECT
        sk.sku_id,
        sp.spu_id,
        c.category_id,
        c.name AS category_name,
        sp.brand,
        sp.name AS product_name,
        sk.sku_name,
        sk.spec,
        sk.price,
        sk.cost,
        sk.supplier,
        sk.listing_date,
        CASE
          WHEN sk.price < 100 THEN 'low'
          WHEN sk.price < 500 THEN 'mid'
          ELSE 'high'
        END AS price_band,
        sp.status AS product_status
      FROM sku sk
      JOIN spu sp ON sp.spu_id = sk.spu_id
      JOIN categories c ON c.category_id = sp.category_id;

    CREATE VIEW IF NOT EXISTS dim_user AS
      SELECT
        user_id,
        name,
        province,
        city,
        register_channel,
        segment,
        gender,
        birth_year,
        member_level,
        status,
        date(created_at) AS register_date
      FROM users;

    CREATE VIEW IF NOT EXISTS dim_campaign AS
      SELECT campaign_id, name, channel, campaign_type, target_segment, has_control_group, start_date, end_date, budget, status
      FROM campaigns;

    CREATE VIEW IF NOT EXISTS dim_date AS
      SELECT DISTINCT
        d AS date_id,
        CAST(strftime('%Y', d) AS INTEGER) AS year,
        CAST(strftime('%m', d) AS INTEGER) AS month,
        strftime('%Y-%m', d) AS year_month,
        CAST(strftime('%w', d) AS INTEGER) AS weekday,
        CASE WHEN strftime('%w', d) IN ('0', '6') THEN 1 ELSE 0 END AS is_weekend
      FROM (
        SELECT date(created_at) AS d FROM orders
        UNION
        SELECT date(created_at) AS d FROM page_events
        UNION
        SELECT spend_date AS d FROM ads_spend
        UNION
        SELECT date(created_at) AS d FROM refunds
      )
      WHERE d IS NOT NULL;

    CREATE VIEW IF NOT EXISTS fact_order AS
      SELECT
        order_id,
        user_id,
        campaign_id,
        date(created_at) AS order_date,
        channel,
        status,
        subtotal,
        discount_amount,
        shipping_fee,
        total_amount,
        paid_amount
      FROM orders;

    CREATE VIEW IF NOT EXISTS fact_order_item AS
      SELECT
        oi.order_item_id,
        oi.order_id,
        o.user_id,
        o.campaign_id,
        date(o.created_at) AS order_date,
        oi.sku_id,
        oi.spu_id,
        oi.quantity,
        oi.unit_price,
        oi.unit_cost,
        oi.discount_amount,
        oi.line_amount,
        (oi.unit_price - oi.unit_cost) * oi.quantity - oi.discount_amount AS gross_profit
      FROM order_items oi
      JOIN orders o ON o.order_id = oi.order_id;

    CREATE VIEW IF NOT EXISTS fact_traffic AS
      SELECT
        event_id,
        user_id,
        session_id,
        event_type,
        page,
        channel,
        device,
        campaign_id,
        sku_id,
        date(created_at) AS event_date,
        created_at
      FROM page_events;

    CREATE VIEW IF NOT EXISTS fact_ads_spend AS
      SELECT spend_id, campaign_id, spend_date, channel, impressions, clicks, conversions, spend_amount
      FROM ads_spend;

    CREATE VIEW IF NOT EXISTS fact_coupon_use AS
      SELECT
        uc.user_coupon_id,
        uc.user_id,
        uc.coupon_id,
        c.campaign_id,
        uc.order_id,
        date(uc.issued_at) AS issued_date,
        date(uc.used_at) AS used_date,
        c.threshold,
        c.discount,
        CASE WHEN uc.used_at IS NULL THEN 0 ELSE 1 END AS is_used
      FROM user_coupons uc
      JOIN coupons c ON c.coupon_id = uc.coupon_id;

    CREATE VIEW IF NOT EXISTS fact_refund AS
      SELECT
        r.refund_id,
        r.order_id,
        o.user_id,
        o.campaign_id,
        date(r.created_at) AS refund_date,
        r.amount,
        r.reason,
        r.status
      FROM refunds r
      JOIN orders o ON o.order_id = r.order_id;

    CREATE VIEW IF NOT EXISTS fact_fulfillment AS
      SELECT
        s.shipment_id,
        s.order_id,
        o.user_id,
        date(o.created_at) AS order_date,
        date(s.shipped_at) AS shipped_date,
        date(s.delivered_at) AS delivered_date,
        s.carrier,
        s.province,
        s.promised_days,
        s.delivery_days,
        CASE WHEN s.delivery_days > s.promised_days THEN 1 ELSE 0 END AS is_late,
        s.status
      FROM shipments s
      JOIN orders o ON o.order_id = s.order_id;

    CREATE VIEW IF NOT EXISTS fact_inventory_movement AS
      SELECT
        movement_id,
        sku_id,
        movement_type,
        quantity,
        reason,
        related_order_id,
        date(created_at) AS movement_date,
        created_at
      FROM inventory_movements;

    CREATE VIEW IF NOT EXISTS fact_product_review AS
      SELECT
        review_id,
        order_id,
        user_id,
        sku_id,
        rating,
        sentiment,
        content_tag,
        date(created_at) AS review_date
      FROM product_reviews;

    CREATE VIEW IF NOT EXISTS daily_business_summary AS
      SELECT
        date(o.created_at) AS summary_date,
        o.channel,
        COUNT(DISTINCT o.order_id) AS orders,
        COUNT(DISTINCT o.user_id) AS buyers,
        ROUND(SUM(o.paid_amount), 2) AS gmv,
        ROUND(SUM(o.discount_amount), 2) AS discount_amount,
        ROUND(AVG(o.paid_amount), 2) AS avg_order_value
      FROM orders o
      WHERE o.status IN ('paid', 'completed')
      GROUP BY date(o.created_at), o.channel;
  `);
}
