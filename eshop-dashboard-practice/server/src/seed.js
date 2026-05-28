import fs from "node:fs";
import Database from "better-sqlite3";
import { dbPath, initSchema, openDb } from "./db.js";

const seedVersion = "course_dataset_v2";
const dayMs = 24 * 60 * 60 * 1000;
const startDate = new Date("2024-04-01T00:00:00Z");
const endDate = new Date("2026-03-31T23:59:59Z");
const totalDays = Math.floor((endDate - startDate) / dayMs) + 1;

const config = {
  users: Number(process.env.SEED_USERS || 20000),
  spuPerCategory: Number(process.env.SEED_SPU_PER_CATEGORY || 24),
  abandonedSessions: Number(process.env.SEED_ABANDONED_SESSIONS || 120000),
  reviewRate: 0.24
};

const provinces = [
  ["广东", "广州", 1.18],
  ["浙江", "杭州", 1.08],
  ["江苏", "南京", 1.06],
  ["四川", "成都", 0.96],
  ["北京", "北京", 1.22],
  ["上海", "上海", 1.25],
  ["湖北", "武汉", 0.92],
  ["陕西", "西安", 0.88],
  ["福建", "厦门", 1.02],
  ["山东", "青岛", 0.91],
  ["河南", "郑州", 0.86],
  ["重庆", "重庆", 0.9]
];

const channels = [
  { id: "organic", weight: 0.28, conversionLift: 0.96 },
  { id: "search", weight: 0.24, conversionLift: 1.12 },
  { id: "social", weight: 0.2, conversionLift: 0.9 },
  { id: "email", weight: 0.14, conversionLift: 1.24 },
  { id: "affiliate", weight: 0.1, conversionLift: 0.98 },
  { id: "live", weight: 0.04, conversionLift: 1.35 }
];

const devices = [
  { id: "mobile", weight: 0.72 },
  { id: "desktop", weight: 0.2 },
  { id: "tablet", weight: 0.08 }
];

const categories = [
  ["c_beauty", "美妆个护", 120, 420, 1.08, 0.055],
  ["c_home", "家居生活", 80, 680, 0.92, 0.045],
  ["c_food", "食品饮料", 25, 260, 1.2, 0.025],
  ["c_digital", "数码配件", 59, 1800, 0.86, 0.07],
  ["c_sports", "运动户外", 99, 1200, 0.78, 0.06],
  ["c_books", "图书文创", 19, 220, 0.74, 0.018],
  ["c_baby", "母婴用品", 39, 480, 0.82, 0.035],
  ["c_pet", "宠物生活", 29, 360, 0.94, 0.032],
  ["c_appliance", "小家电", 139, 1600, 0.7, 0.075],
  ["c_fashion", "服饰鞋包", 49, 900, 1.02, 0.085],
  ["c_health", "健康护理", 35, 520, 0.88, 0.04],
  ["c_office", "办公学习", 15, 620, 0.72, 0.03]
];

const brandNames = ["Aurora", "Mellow", "NorthHome", "FreshBox", "山野集", "DailyTea", "VoltGo", "SoundBud", "RunPeak", "FitLoop", "DataPress", "CanvasLab", "PawGo", "BabyNest", "LiteChef", "UrbanWeave", "CarePlus", "DeskMate"];
const nameTokens = ["臻选", "轻享", "专业", "焕新", "经典", "智能", "便携", "家庭装", "会员款", "升级版"];
const productWords = ["套装", "礼盒", "补充装", "组合", "单品", "训练包", "收纳组", "体验装", "旗舰款", "经济装"];
const specs = ["标准款", "升级款", "家庭装"];
const carriers = ["顺丰", "京东物流", "中通", "圆通", "韵达"];
const refundReasons = ["七天无理由", "尺码不合适", "物流延迟", "商品破损", "描述不符", "质量问题", "错发漏发"];
const reviewTags = ["品质好", "性价比高", "物流快", "包装一般", "尺码偏差", "售后满意", "复购意愿高", "与描述不符"];

function random(seed) {
  let value = seed % 2147483647;
  return () => {
    value = (value * 16807) % 2147483647;
    return (value - 1) / 2147483646;
  };
}

const rnd = random(20260427);
const money = (value) => Number(value.toFixed(2));
const iso = (date) => date.toISOString().slice(0, 19).replace("T", " ");
const dateOnly = (date) => date.toISOString().slice(0, 10);
const addDays = (date, days) => new Date(date.getTime() + days * dayMs);
const randInt = (min, max) => min + Math.floor(rnd() * (max - min + 1));
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

function weightedPick(items, weightKey = "weight") {
  const total = items.reduce((sum, item) => sum + item[weightKey], 0);
  let cursor = rnd() * total;
  for (const item of items) {
    cursor -= item[weightKey];
    if (cursor <= 0) return item;
  }
  return items.at(-1);
}

function resetDb() {
  try {
    for (const suffix of ["", "-wal", "-shm"]) {
      const file = `${dbPath}${suffix}`;
      if (fs.existsSync(file)) fs.rmSync(file);
    }
  } catch (error) {
    if (error.code !== "EBUSY") throw error;
    const db = new Database(dbPath);
    db.pragma("foreign_keys = OFF");
    const objects = db.prepare(`
      SELECT type, name
      FROM sqlite_master
      WHERE type IN ('view', 'table') AND name NOT LIKE 'sqlite_%'
      ORDER BY CASE type WHEN 'view' THEN 0 ELSE 1 END
    `).all();
    for (const object of objects) {
      db.exec(`DROP ${object.type.toUpperCase()} IF EXISTS ${object.name}`);
    }
    db.close();
  }
}

function makePrepared(db) {
  return {
    category: db.prepare("INSERT INTO categories (category_id, name) VALUES (?, ?)"),
    spu: db.prepare("INSERT INTO spu (spu_id, category_id, brand, name, description, image_url, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"),
    sku: db.prepare("INSERT INTO sku (sku_id, spu_id, sku_name, spec, price, cost, supplier, listing_date, stock, image_url, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
    user: db.prepare("INSERT INTO users (user_id, name, email, password, phone, province, city, register_channel, segment, gender, birth_year, member_level, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
    address: db.prepare("INSERT INTO addresses (address_id, user_id, receiver, phone, province, city, detail, is_default) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"),
    campaign: db.prepare("INSERT INTO campaigns (campaign_id, name, channel, campaign_type, target_segment, has_control_group, start_date, end_date, budget, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
    coupon: db.prepare("INSERT INTO coupons (coupon_id, campaign_id, code, name, threshold, discount, start_date, end_date, total_limit, issued_count, used_count, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
    userCoupon: db.prepare("INSERT INTO user_coupons (user_coupon_id, user_id, coupon_id, issued_at, used_at, order_id) VALUES (?, ?, ?, ?, ?, ?)"),
    order: db.prepare("INSERT INTO orders (order_id, user_id, campaign_id, order_no, status, channel, subtotal, discount_amount, shipping_fee, total_amount, paid_amount, created_at, paid_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
    orderItem: db.prepare("INSERT INTO order_items (order_item_id, order_id, sku_id, spu_id, quantity, unit_price, unit_cost, discount_amount, line_amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"),
    payment: db.prepare("INSERT INTO payments (payment_id, order_id, provider, amount, status, paid_at) VALUES (?, ?, ?, ?, ?, ?)"),
    refund: db.prepare("INSERT INTO refunds (refund_id, order_id, amount, reason, status, created_at) VALUES (?, ?, ?, ?, ?, ?)"),
    shipment: db.prepare("INSERT INTO shipments (shipment_id, order_id, carrier, province, promised_days, shipped_at, delivered_at, delivery_days, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"),
    inventory: db.prepare("INSERT INTO inventory_movements (movement_id, sku_id, movement_type, quantity, reason, related_order_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)"),
    review: db.prepare("INSERT INTO product_reviews (review_id, order_id, user_id, sku_id, rating, sentiment, content_tag, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"),
    event: db.prepare("INSERT INTO page_events (event_id, user_id, session_id, event_type, page, channel, device, campaign_id, sku_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
    ad: db.prepare("INSERT INTO ads_spend (spend_id, campaign_id, spend_date, channel, impressions, clicks, conversions, spend_amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"),
    adminLog: db.prepare("INSERT INTO admin_action_logs (log_id, admin_name, action_type, entity_type, entity_id, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)")
  };
}

function buildCampaigns() {
  const types = [
    ["满减券", "coupon"],
    ["会员复购礼", "member"],
    ["直播专场", "live"],
    ["新品冷启动", "new_product"],
    ["清仓促销", "clearance"]
  ];
  const targetSegments = ["all", "new", "active", "high_value", "coupon_sensitive", "at_risk"];
  const result = [];
  let idx = 1;
  for (let month = 0; month < 24; month += 1) {
    const base = new Date(Date.UTC(2024, 3 + month, 1));
    const count = month % 3 === 1 ? 3 : 2;
    for (let j = 0; j < count; j += 1) {
      const [label, type] = types[(month + j) % types.length];
      const channel = channels[(month + j * 2) % channels.length].id;
      const startOffset = j === 0 ? 4 : 16 + j;
      const start = addDays(base, startOffset);
      const duration = type === "live" ? 4 : type === "clearance" ? 18 : 10 + (month % 5);
      const end = addDays(start, duration);
      const seasonalLift = [5, 10, 11].includes(start.getUTCMonth()) ? 1.8 : 1;
      result.push({
        campaignId: `camp_${String(idx).padStart(3, "0")}`,
        couponId: `coupon_${String(idx).padStart(3, "0")}`,
        name: `${start.getUTCFullYear()}-${String(start.getUTCMonth() + 1).padStart(2, "0")}${label}`,
        channel,
        type,
        targetSegment: targetSegments[(month + j) % targetSegments.length],
        hasControlGroup: idx % 3 === 0 ? 1 : 0,
        startDate: dateOnly(start),
        endDate: dateOnly(end),
        budget: money((18000 + rnd() * 90000) * seasonalLift),
        threshold: [99, 199, 299, 499][idx % 4],
        discount: [10, 25, 40, 80][idx % 4],
        orderConversions: 0
      });
      idx += 1;
    }
  }
  return result;
}

function campaignForDate(campaigns, date, channel, segment) {
  const day = dateOnly(date);
  const active = campaigns.filter((campaign) => (
    campaign.startDate <= day &&
    campaign.endDate >= day &&
    (campaign.channel === channel || rnd() < 0.12) &&
    (campaign.targetSegment === "all" || campaign.targetSegment === segment || rnd() < 0.2)
  ));
  if (active.length === 0) return null;
  return active[Math.floor(rnd() * active.length)];
}

function buildCatalog(stmt) {
  const skus = [];
  let spuIndex = 1;
  let skuIndex = 1;
  for (const [categoryId, categoryName, minPrice, maxPrice, demandLift, refundBase] of categories) {
    stmt.category.run(categoryId, categoryName);
    for (let i = 1; i <= config.spuPerCategory; i += 1) {
      const brand = brandNames[(spuIndex + i) % brandNames.length];
      const productName = `${brand}${nameTokens[(i + spuIndex) % nameTokens.length]}${categoryName}${productWords[i % productWords.length]}`;
      const spuId = `spu_${String(spuIndex).padStart(4, "0")}`;
      const imageText = encodeURIComponent(productName.slice(0, 24));
      const imageUrl = `https://placehold.co/640x480/png?text=${imageText}`;
      const created = addDays(startDate, randInt(0, totalDays - 90));
      stmt.spu.run(spuId, categoryId, brand, productName, `${categoryName}教学样例商品，用于选品、价格带、毛利和长尾分析。`, imageUrl, "on_sale", iso(created));

      for (let s = 0; s < specs.length; s += 1) {
        const base = minPrice + rnd() * (maxPrice - minPrice);
        const price = money(base * (1 + s * 0.22));
        const costRate = 0.42 + rnd() * 0.23;
        const skuId = `sku_${String(skuIndex).padStart(5, "0")}`;
        const supplier = `供应商${String((spuIndex % 18) + 1).padStart(2, "0")}`;
        const initialStock = 400 + randInt(0, 2400);
        stmt.sku.run(skuId, spuId, `${productName} ${specs[s]}`, specs[s], price, money(price * costRate), supplier, dateOnly(created), initialStock, imageUrl, "on_sale");
        stmt.inventory.run(`inv_init_${skuIndex}`, skuId, "in", initialStock, "initial_stock", null, iso(created));
        skus.push({
          skuId,
          spuId,
          categoryId,
          categoryName,
          price,
          cost: money(price * costRate),
          demandWeight: Math.pow(1 / skuIndex, 0.35) * demandLift * (0.75 + rnd() * 0.7),
          refundBase
        });
        skuIndex += 1;
      }
      spuIndex += 1;
    }
  }
  return skus;
}

function pickSku(skus, preferredCategoryId) {
  const pool = preferredCategoryId && rnd() < 0.72 ? skus.filter((sku) => sku.categoryId === preferredCategoryId) : skus;
  const total = pool.reduce((sum, sku) => sum + sku.demandWeight, 0);
  let cursor = rnd() * total;
  for (const sku of pool) {
    cursor -= sku.demandWeight;
    if (cursor <= 0) return sku;
  }
  return pool.at(-1);
}

function buildUsers(stmt) {
  const users = [];
  const segments = [
    { id: "high_value", weight: 0.08, orderMin: 10, orderMax: 24, aovLift: 1.32 },
    { id: "active", weight: 0.24, orderMin: 5, orderMax: 12, aovLift: 1.05 },
    { id: "coupon_sensitive", weight: 0.22, orderMin: 4, orderMax: 10, aovLift: 0.92 },
    { id: "at_risk", weight: 0.16, orderMin: 1, orderMax: 5, aovLift: 0.86 },
    { id: "new", weight: 0.2, orderMin: 0, orderMax: 3, aovLift: 0.8 },
    { id: "sleeping", weight: 0.1, orderMin: 0, orderMax: 2, aovLift: 0.72 }
  ];
  for (let i = 1; i <= config.users; i += 1) {
    const province = weightedPick(provinces.map(([name, city, weight]) => ({ name, city, weight })));
    const channel = weightedPick(channels).id;
    const segment = weightedPick(segments);
    const created = addDays(startDate, randInt(0, totalDays - 30));
    const userId = `user_${String(i).padStart(6, "0")}`;
    const gender = rnd() < 0.52 ? "female" : "male";
    const birthYear = randInt(1968, 2005);
    const memberLevel = segment.id === "high_value" ? "vip" : segment.id === "active" ? "plus" : "normal";
    stmt.user.run(userId, `教学用户${i}`, `user${i}@example.edu`, "demo123456", `138${String(10000000 + i).slice(-8)}`, province.name, province.city, channel, segment.id, gender, birthYear, memberLevel, "active", iso(created));
    stmt.address.run(`addr_${String(i).padStart(6, "0")}`, userId, `教学用户${i}`, `138${String(10000000 + i).slice(-8)}`, province.name, province.city, `教学样例地址${i}号`, 1);
    users.push({
      userId,
      created,
      province: province.name,
      city: province.city,
      provinceLift: province.weight,
      channel,
      segment: segment.id,
      targetOrders: randInt(segment.orderMin, segment.orderMax),
      aovLift: segment.aovLift,
      preferredCategoryId: categories[randInt(0, categories.length - 1)][0]
    });
  }
  return users;
}

function createEvents(stmt, context, eventTypes) {
  const { userId, sessionId, channel, device, campaignId, skuId, baseTime } = context;
  eventTypes.forEach((eventType, index) => {
    const page = eventType === "view_home" ? "home"
      : eventType === "search" ? "search"
      : eventType === "view_category" ? "category"
      : eventType === "view_product" ? "product_detail"
      : eventType === "add_to_cart" ? "cart"
      : eventType === "checkout" ? "checkout"
      : eventType === "pay_success" ? "payment_success"
      : "other";
    stmt.event.run(`evt_${context.eventStart + index}`, userId, sessionId, eventType, page, channel, device, campaignId, skuId, iso(new Date(baseTime.getTime() + index * randInt(35, 220) * 1000)));
  });
}

function seed() {
  resetDb();
  const db = openDb();
  db.pragma("synchronous = OFF");
  db.pragma("temp_store = MEMORY");
  initSchema(db);
  const stmt = makePrepared(db);

  const campaigns = buildCampaigns();
  const ordersByCampaign = new Map();
  let counters = {
    order: 1,
    orderItem: 1,
    payment: 1,
    refund: 1,
    shipment: 1,
    movement: 1,
    review: 1,
    event: 1,
    userCoupon: 1,
    spend: 1
  };

  const tx = db.transaction(() => {
    const skus = buildCatalog(stmt);
    const users = buildUsers(stmt);

    for (const campaign of campaigns) {
      stmt.campaign.run(campaign.campaignId, campaign.name, campaign.channel, campaign.type, campaign.targetSegment, campaign.hasControlGroup, campaign.startDate, campaign.endDate, campaign.budget, "active");
      stmt.coupon.run(campaign.couponId, campaign.campaignId, campaign.campaignId.toUpperCase(), `${campaign.name}优惠券`, campaign.threshold, campaign.discount, campaign.startDate, campaign.endDate, 200000, 0, 0, "active");
    }

    const userOrders = [];
    for (const user of users) {
      for (let i = 0; i < user.targetOrders; i += 1) {
        const earliest = Math.max(0, Math.floor((user.created - startDate) / dayMs));
        const day = randInt(earliest, totalDays - 1);
        userOrders.push({ user, day, repeatIndex: i });
      }
    }
    userOrders.sort((a, b) => a.day - b.day);

    for (const item of userOrders) {
      const { user, day } = item;
      const orderDate = addDays(startDate, day);
      const hour = clamp(Math.floor(10 + rnd() * 12 + (user.segment === "high_value" ? 1 : 0)), 0, 23);
      const createdAt = new Date(orderDate.getTime() + hour * 60 * 60 * 1000 + randInt(0, 3599) * 1000);
      const baseChannel = rnd() < 0.55 ? user.channel : weightedPick(channels).id;
      const campaign = campaignForDate(campaigns, createdAt, baseChannel, user.segment);
      const channel = campaign ? campaign.channel : baseChannel;
      const device = weightedPick(devices).id;
      const skuCount = user.segment === "high_value" ? randInt(1, 4) : randInt(1, 3);
      const selected = [];
      for (let i = 0; i < skuCount; i += 1) {
        selected.push(pickSku(skus, i === 0 ? user.preferredCategoryId : null));
      }
      const quantities = selected.map(() => (rnd() < 0.82 ? 1 : randInt(2, 4)));
      const subtotal = money(selected.reduce((sum, sku, index) => sum + sku.price * quantities[index] * user.aovLift * user.provinceLift, 0));
      const couponEligible = campaign && subtotal >= campaign.threshold && (user.segment === "coupon_sensitive" || rnd() < 0.48);
      const discount = couponEligible ? money(Math.min(campaign.discount, subtotal * 0.18)) : 0;
      const shipping = subtotal >= 99 ? 0 : 8;
      const paid = money(subtotal - discount + shipping);
      const orderId = `order_${String(counters.order).padStart(7, "0")}`;
      const paidAt = new Date(createdAt.getTime() + randInt(1, 35) * 60 * 1000);
      const shipmentDelay = randInt(8, 42) / 24;
      const shippedAt = addDays(paidAt, shipmentDelay);
      const promisedDays = ["北京", "上海", "广东", "浙江", "江苏"].includes(user.province) ? 3 : 5;
      const deliveryDays = money(clamp(1.2 + rnd() * 5.8 + (rnd() < 0.08 ? 3.5 : 0), 1, 12));
      const deliveredAt = addDays(shippedAt, deliveryDays);
      const refundRisk = selected.reduce((sum, sku) => sum + sku.refundBase, 0) / selected.length + (deliveryDays > promisedDays ? 0.055 : 0);
      const isRefunded = rnd() < refundRisk;
      const isRecent = createdAt > addDays(endDate, -8);
      const status = isRefunded ? "refunded" : isRecent && rnd() < 0.35 ? "paid" : "completed";
      const completedAt = status === "completed" ? iso(deliveredAt) : null;

      stmt.order.run(orderId, user.userId, campaign?.campaignId ?? null, `NO${dateOnly(createdAt).replaceAll("-", "")}${String(counters.order).padStart(7, "0")}`, status, channel, subtotal, discount, shipping, paid, paid, iso(createdAt), iso(paidAt), completedAt);
      stmt.payment.run(`pay_${String(counters.payment++).padStart(8, "0")}`, orderId, weightedPick([{ id: "wechat", weight: 0.48 }, { id: "alipay", weight: 0.34 }, { id: "mock_card", weight: 0.18 }]).id, paid, "success", iso(paidAt));
      stmt.shipment.run(`ship_${String(counters.shipment++).padStart(8, "0")}`, orderId, carriers[randInt(0, carriers.length - 1)], user.province, promisedDays, iso(shippedAt), status === "paid" ? null : iso(deliveredAt), status === "paid" ? null : deliveryDays, status === "paid" ? "shipping" : "delivered");

      selected.forEach((sku, index) => {
        const quantity = quantities[index];
        const grossLine = sku.price * quantity * user.aovLift * user.provinceLift;
        const shareDiscount = subtotal ? money((grossLine / subtotal) * discount) : 0;
        stmt.orderItem.run(`oi_${String(counters.orderItem++).padStart(8, "0")}`, orderId, sku.skuId, sku.spuId, quantity, money(sku.price * user.aovLift * user.provinceLift), sku.cost, shareDiscount, money(grossLine - shareDiscount));
        stmt.inventory.run(`inv_${String(counters.movement++).padStart(9, "0")}`, sku.skuId, "out", -quantity, "sale", orderId, iso(createdAt));
      });

      if (couponEligible) {
        stmt.userCoupon.run(`uc_${String(counters.userCoupon++).padStart(8, "0")}`, user.userId, campaign.couponId, iso(new Date(createdAt.getTime() - randInt(1, 72) * 60 * 60 * 1000)), iso(paidAt), orderId);
      } else if (campaign && rnd() < 0.22) {
        stmt.userCoupon.run(`uc_${String(counters.userCoupon++).padStart(8, "0")}`, user.userId, campaign.couponId, iso(new Date(createdAt.getTime() - randInt(1, 72) * 60 * 60 * 1000)), null, null);
      }

      if (isRefunded) {
        stmt.refund.run(`refund_${String(counters.refund++).padStart(8, "0")}`, orderId, money(paid * (0.45 + rnd() * 0.55)), refundReasons[randInt(0, refundReasons.length - 1)], "approved", iso(addDays(deliveredAt, randInt(1, 10))));
      }

      if (status === "completed" && rnd() < config.reviewRate) {
        const firstSku = selected[0];
        const ratingBase = deliveryDays > promisedDays ? 3 : 4;
        const rating = clamp(ratingBase + (rnd() < 0.7 ? 1 : randInt(-2, 0)), 1, 5);
        stmt.review.run(`review_${String(counters.review++).padStart(8, "0")}`, orderId, user.userId, firstSku.skuId, rating, rating >= 4 ? "positive" : rating === 3 ? "neutral" : "negative", reviewTags[randInt(0, reviewTags.length - 1)], iso(addDays(deliveredAt, randInt(1, 18))));
      }

      const sessionId = `sess_order_${String(counters.order).padStart(7, "0")}`;
      const eventStart = counters.event;
      createEvents(stmt, {
        userId: user.userId,
        sessionId,
        channel,
        device,
        campaignId: campaign?.campaignId ?? null,
        skuId: selected[0].skuId,
        baseTime: new Date(createdAt.getTime() - randInt(8, 35) * 60 * 1000),
        eventStart
      }, ["view_home", rnd() < 0.5 ? "search" : "view_category", "view_product", "add_to_cart", "checkout", "pay_success"]);
      counters.event += 6;
      if (campaign) {
        ordersByCampaign.set(campaign.campaignId, (ordersByCampaign.get(campaign.campaignId) || 0) + 1);
      }
      counters.order += 1;
    }

    for (let i = 1; i <= config.abandonedSessions; i += 1) {
      const user = rnd() < 0.65 ? users[randInt(0, users.length - 1)] : null;
      const day = randInt(0, totalDays - 1);
      const visitedAt = addDays(startDate, day);
      const channel = weightedPick(channels).id;
      const device = weightedPick(devices).id;
      const segment = user?.segment ?? "anonymous";
      const campaign = campaignForDate(campaigns, visitedAt, channel, segment);
      const sku = pickSku(skus, user?.preferredCategoryId);
      const sessionId = `sess_abandon_${String(i).padStart(7, "0")}`;
      const pathRoll = rnd();
      const events = pathRoll < 0.38
        ? ["view_home", "view_category"]
        : pathRoll < 0.72
          ? ["view_home", "search", "view_product"]
          : pathRoll < 0.92
            ? ["view_home", "view_product", "add_to_cart"]
            : ["view_home", "search", "view_product", "add_to_cart", "checkout"];
      createEvents(stmt, {
        userId: user?.userId ?? null,
        sessionId,
        channel,
        device,
        campaignId: campaign?.campaignId ?? null,
        skuId: sku.skuId,
        baseTime: new Date(visitedAt.getTime() + randInt(8, 23) * 60 * 60 * 1000),
        eventStart: counters.event
      }, events);
      counters.event += events.length;
    }

    for (const campaign of campaigns) {
      const start = new Date(`${campaign.startDate}T00:00:00Z`);
      const end = new Date(`${campaign.endDate}T00:00:00Z`);
      const days = Math.max(1, Math.floor((end - start) / dayMs) + 1);
      const conversions = ordersByCampaign.get(campaign.campaignId) || 0;
      for (let day = 0; day < days; day += 1) {
        const current = addDays(start, day);
        const impressions = randInt(2500, 38000);
        const clicks = Math.floor(impressions * (0.018 + rnd() * 0.052));
        const spend = money(campaign.budget / days * (0.72 + rnd() * 0.62));
        stmt.ad.run(`spend_${String(counters.spend++).padStart(7, "0")}`, campaign.campaignId, dateOnly(current), campaign.channel, impressions, clicks, Math.floor(conversions / days * (0.5 + rnd())), spend);
      }
    }

    for (const sku of skus) {
      for (let m = 0; m < 24; m += 1) {
        if (rnd() < 0.45) {
          const date = new Date(Date.UTC(2024, 3 + m, randInt(1, 26)));
          stmt.inventory.run(`inv_${String(counters.movement++).padStart(9, "0")}`, sku.skuId, "in", randInt(50, 500), "restock", null, iso(date));
        }
      }
    }

    db.prepare("UPDATE coupons SET issued_count = (SELECT COUNT(*) FROM user_coupons WHERE user_coupons.coupon_id = coupons.coupon_id)").run();
    db.prepare("UPDATE coupons SET used_count = (SELECT COUNT(*) FROM user_coupons WHERE user_coupons.coupon_id = coupons.coupon_id AND used_at IS NOT NULL)").run();
    stmt.adminLog.run("log_seed_v2", "teacher", "seed", "dataset", seedVersion, "初始化课程级电商数据挖掘数据集：大规模用户、订单、行为、履约、库存、评论与活动对照", iso(new Date("2026-04-01T10:00:00Z")));
  });

  tx();
  console.log(`Seeded ${seedVersion} at ${dbPath}`);
  console.log(JSON.stringify({
    users: config.users,
    categories: categories.length,
    skus: categories.length * config.spuPerCategory * specs.length,
    abandonedSessions: config.abandonedSessions
  }));
}

seed();
