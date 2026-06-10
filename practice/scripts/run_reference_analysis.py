from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    precision_score,
    recall_score,
    roc_auc_score,
    silhouette_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from course_utils.business import money, pct
from course_utils.data_loader import (
    API_BASE,
    api_status,
    get_metrics,
    get_quality_report,
    get_table_catalog,
    load_table,
    paid_orders,
    query_table,
)


OUT = ROOT / "reference_answers"
OUT.mkdir(exist_ok=True)


def line(text=""):
    print(text)


def md_table(df, max_rows=20):
    if df.empty:
        return "_无结果_"
    sample = df.head(max_rows).copy()
    sample = sample.replace({np.nan: ""})
    cols = list(sample.columns)
    rows = ["| " + " | ".join(map(str, cols)) + " |"]
    rows.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for _, row in sample.iterrows():
        rows.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(rows)


def save_report(name, content):
    path = OUT / name
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def chapter_1():
    metrics = get_metrics()["metrics"]
    quality = get_quality_report()
    catalog = get_table_catalog()
    funnel = metrics["funnel"]
    stages = ["view_home", "view_product", "add_to_cart", "checkout", "pay_success"]
    funnel_rows = []
    base = funnel[stages[0]]
    prev = None
    for s in stages:
        v = funnel[s]
        funnel_rows.append(
            {
                "stage": s,
                "events": v,
                "overall_rate": v / base,
                "step_rate": 1 if prev is None else v / prev,
            }
        )
        prev = v
    funnel_df = pd.DataFrame(funnel_rows)
    decision = (
        "数据资产完整，ETL 适合作为课程主数据源。漏斗最大绝对流失发生在首页到商品页、商品页到加购两个阶段，"
        "后续经营诊断应优先围绕流量承接和商品详情页转化展开。"
    )
    return {
        "title": "第 1 章 商业问题定义与 ETL 数据接入",
        "good": quality["summary"]["fail"] == 0 and catalog["total"] >= 20,
        "summary": {
            "api": api_status(),
            "tables": catalog["total"],
            "quality": quality["summary"],
            "gmv": metrics["gmv"]["value"],
            "orders": metrics["orderCount"]["value"],
            "buyers": metrics["buyerCount"]["value"],
            "aov": metrics["avgOrderValue"]["value"],
        },
        "tables": {"funnel": funnel_df},
        "decision": decision,
        "data_issue": "数据质量检查 0 项失败，可作为课程入口。若要更强教学冲突，可保留少量 warning 让学生练习质量判断。",
    }


def chapter_2():
    daily = load_table("daily_business_summary", limit=100000)
    date_col = "summary_date" if "summary_date" in daily.columns else "date_id"
    daily[date_col] = pd.to_datetime(daily[date_col], errors="coerce")
    daily = daily.dropna(subset=[date_col])
    daily["month"] = daily[date_col].dt.to_period("M").astype(str)
    monthly = daily.groupby("month").agg(
        gmv=("gmv", "sum"),
        orders=("orders", "sum"),
        buyers=("buyers", "sum"),
        discount=("discount_amount", "sum"),
        observed_days=(date_col, "nunique"),
    ).reset_index()
    monthly["aov"] = monthly["gmv"] / monthly["orders"]
    monthly_all = monthly.copy()
    monthly = monthly[monthly["observed_days"] >= 20].copy()
    monthly["mom_gmv"] = monthly["gmv"].pct_change()
    last = monthly.tail(6).copy()
    ch = daily.groupby("channel").agg(
        gmv=("gmv", "sum"),
        orders=("orders", "sum"),
        buyers=("buyers", "sum"),
        discount=("discount_amount", "sum"),
    ).reset_index()
    ch["aov"] = ch["gmv"] / ch["orders"]
    ch["gmv_share"] = ch["gmv"] / ch["gmv"].sum()
    top_ch = ch.sort_values("gmv", ascending=False)
    weak_month = monthly.loc[monthly["mom_gmv"].idxmin()]
    decision = (
        f"最近经营诊断应采用月度趋势加渠道拆解。最低环比月份为 {weak_month['month']}，"
        f"GMV 环比 {pct(weak_month['mom_gmv'])}。渠道上应优先关注贡献最高的 "
        f"{top_ch.iloc[0]['channel']}，因为它贡献 {pct(top_ch.iloc[0]['gmv_share'])} 的 GMV。"
    )
    return {
        "title": "第 2 章 经营健康诊断与数据探索",
        "good": len(monthly) >= 12 and top_ch["gmv_share"].max() > 0.2,
        "summary": {
            "months": len(monthly),
            "total_gmv": monthly["gmv"].sum(),
            "avg_aov": monthly["gmv"].sum() / monthly["orders"].sum(),
            "worst_mom_month": weak_month["month"],
            "worst_mom": weak_month["mom_gmv"],
        },
        "tables": {"last_6_complete_months": last, "all_months_quality": monthly_all.tail(8), "channel": top_ch},
        "decision": decision,
        "data_issue": "趋势与渠道差异存在，适合经营诊断教学。若希望课堂更有戏剧性，可在某月制造更明显的 GMV 下滑或渠道异常。",
    }


def make_user_wide():
    users = load_table("dim_user", limit=100000)
    orders = paid_orders()
    traffic = load_table("fact_traffic", limit=100000)
    coupons = load_table("fact_coupon_use", limit=100000)
    snapshot = orders["order_date"].max() + pd.Timedelta(days=1)
    rfm = orders.groupby("user_id").agg(
        last_order_date=("order_date", "max"),
        order_count=("order_id", "nunique"),
        total_paid=("paid_amount", "sum"),
        avg_paid=("paid_amount", "mean"),
        first_order_date=("order_date", "min"),
    ).reset_index()
    rfm["recency_days"] = (snapshot - rfm["last_order_date"]).dt.days
    rfm["customer_age_days"] = (snapshot - rfm["first_order_date"]).dt.days
    behavior = traffic.groupby("user_id").agg(
        event_count=("event_id", "count"),
        active_days=("event_date", lambda s: s.dt.date.nunique()),
    ).reset_index()
    coupon_feature = coupons.groupby("user_id").agg(
        coupons_issued=("user_coupon_id", "count"),
        coupons_used=("is_used", "sum"),
    ).reset_index()
    wide = users[["user_id", "province", "register_channel", "member_level"]].merge(
        rfm, on="user_id", how="left"
    ).merge(behavior, on="user_id", how="left").merge(coupon_feature, on="user_id", how="left")
    wide = wide.fillna(
        {
            "order_count": 0,
            "total_paid": 0,
            "avg_paid": 0,
            "recency_days": 999,
            "customer_age_days": 0,
            "event_count": 0,
            "active_days": 0,
            "coupons_issued": 0,
            "coupons_used": 0,
        }
    )
    return wide


def chapter_3():
    wide = make_user_wide()
    coverage = {
        "users": len(wide),
        "buyers": int((wide["order_count"] > 0).sum()),
        "buyer_rate": float((wide["order_count"] > 0).mean()),
        "features": len(wide.columns),
        "duplicate_user": int(wide["user_id"].duplicated().sum()),
    }
    quant = wide[["order_count", "total_paid", "recency_days", "event_count", "coupons_used"]].quantile([0.25, 0.5, 0.75, 0.9]).reset_index()
    decision = (
        f"宽表覆盖 {coverage['users']} 个用户，其中购买用户占 {pct(coverage['buyer_rate'])}。"
        "RFM、行为活跃和优惠券字段足以支撑复购预测与分群。建议将该宽表作为第 4、5 章统一建模底座。"
    )
    return {
        "title": "第 3 章 用户建模宽表与特征工程",
        "good": coverage["duplicate_user"] == 0 and coverage["buyer_rate"] > 0.5,
        "summary": coverage,
        "tables": {"feature_quantiles": quant},
        "decision": decision,
        "data_issue": "特征覆盖较完整，适合作为建模练习。若要提升模型效果，可增加最近 7/30/90 天行为、品类偏好、价格敏感度等更强预测特征。",
    }


def chapter_4():
    orders = paid_orders()
    traffic = load_table("fact_traffic", limit=100000)
    cutoff = pd.Timestamp("2026-01-01")
    history = orders[orders["order_date"] < cutoff]
    future = orders[(orders["order_date"] >= cutoff) & (orders["order_date"] < cutoff + pd.Timedelta(days=60))]
    feat = history.groupby("user_id").agg(
        order_count=("order_id", "nunique"),
        total_paid=("paid_amount", "sum"),
        avg_paid=("paid_amount", "mean"),
        last_order_date=("order_date", "max"),
    ).reset_index()
    feat["recency_days"] = (cutoff - feat["last_order_date"]).dt.days
    recent_events = traffic[(traffic["event_date"] >= cutoff - pd.Timedelta(days=60)) & (traffic["event_date"] < cutoff)]
    behavior = recent_events.groupby("user_id").agg(
        recent_events=("event_id", "count"),
        recent_active_days=("event_date", lambda s: s.dt.date.nunique()),
    ).reset_index()
    feat = feat.merge(behavior, on="user_id", how="left").fillna({"recent_events": 0, "recent_active_days": 0})
    feat["label_repurchase"] = feat["user_id"].isin(future["user_id"].unique()).astype(int)
    feat = feat.drop(columns=["last_order_date"]).fillna(0)
    feature_cols = ["order_count", "total_paid", "avg_paid", "recency_days", "recent_events", "recent_active_days"]
    X = feat[feature_cols]
    y = feat["label_repurchase"]
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
    model = RandomForestClassifier(n_estimators=180, random_state=42, n_jobs=-1, min_samples_leaf=5)
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_val)[:, 1]
    auc = roc_auc_score(y_val, proba)
    rows = []
    for q in np.arange(0.05, 0.55, 0.05):
        threshold = np.quantile(proba, 1 - q)
        pred = (proba >= threshold).astype(int)
        touched = int(pred.sum())
        precision = precision_score(y_val, pred, zero_division=0)
        recall = recall_score(y_val, pred, zero_division=0)
        expected_margin = touched * precision * 80
        touch_cost = touched * 8
        roi = (expected_margin - touch_cost) / max(touch_cost, 1)
        rows.append([q, threshold, touched, precision, recall, roi])
    roi = pd.DataFrame(rows, columns=["top_ratio", "threshold", "touch_users", "precision", "recall", "expected_roi"])
    best = roi.sort_values("expected_roi", ascending=False).iloc[0]
    decision = (
        f"模型 AUC={auc:.3f}，可作为教学中的中等强度预测模型。按验证集 Top {pct(best['top_ratio'])} 触达，"
        f"Precision={pct(best['precision'])}，Recall={pct(best['recall'])}，预估 ROI={best['expected_roi']:.2f}。"
        "建议将其作为发券名单参考，但不要宣称为高精度生产模型。"
    )
    return {
        "title": "第 4 章 复购预测与触达名单",
        "good": auc >= 0.65 and best["expected_roi"] > 3,
        "summary": {
            "samples": len(feat),
            "positive_rate": y.mean(),
            "auc": auc,
            "best_top_ratio": best["top_ratio"],
            "best_precision": best["precision"],
            "best_recall": best["recall"],
            "best_roi": best["expected_roi"],
        },
        "tables": {"roi": roi.sort_values("expected_roi", ascending=False)},
        "decision": decision,
        "data_issue": "模型效果中等，教学可用。若希望形成更强“数据挖掘成果”，建议修改模拟数据：让近期浏览、加购、优惠券使用、会员等级与未来复购有更明确关系。",
    }


def chapter_5():
    wide = make_user_wide()
    customer = wide[wide["order_count"] > 0].copy()
    cols = ["order_count", "total_paid", "avg_paid", "recency_days", "event_count", "coupons_used"]
    Xs = StandardScaler().fit_transform(customer[cols])
    scores = []
    labels_by_k = {}
    for k in range(2, 7):
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(Xs)
        labels_by_k[k] = labels
        scores.append((k, silhouette_score(Xs, labels)))
    score_df = pd.DataFrame(scores, columns=["k", "silhouette"])
    best_k = int(score_df.sort_values("silhouette", ascending=False).iloc[0]["k"])
    customer["cluster"] = labels_by_k[best_k]
    profile = customer.groupby("cluster").agg(
        users=("user_id", "count"),
        avg_orders=("order_count", "mean"),
        avg_total_paid=("total_paid", "mean"),
        avg_aov=("avg_paid", "mean"),
        avg_recency=("recency_days", "mean"),
        avg_events=("event_count", "mean"),
        avg_coupon_used=("coupons_used", "mean"),
    ).reset_index().sort_values("avg_total_paid", ascending=False)
    decision = (
        f"最佳 k={best_k}，轮廓系数={score_df['silhouette'].max():.3f}。分群画像有明显消费金额与活跃差异，"
        "适合作为差异化运营参考：高价值高活跃客做会员权益，低活跃老客做召回，低价值群控制触达成本。"
    )
    return {
        "title": "第 5 章 客户分群与差异化运营",
        "good": score_df["silhouette"].max() >= 0.25 and profile["avg_total_paid"].max() / profile["avg_total_paid"].min() > 2,
        "summary": {"best_k": best_k, "best_silhouette": score_df["silhouette"].max()},
        "tables": {"scores": score_df, "profile": profile},
        "decision": decision,
        "data_issue": "分群差异可见，教学可用。若想让分群更像真实运营画像，可在模拟数据中强化新客、沉睡客、高价值客、券敏感客的生成规则。",
    }


def chapter_6():
    seed_items = load_table("fact_order_item", limit=100000)
    products = load_table("dim_product", limit=100000)[["sku_id", "sku_name", "category_name", "price", "cost"]]
    top_sku = list(seed_items["sku_id"].value_counts().head(60).index)
    # Pull each candidate SKU with filtered ETL queries so late inserted teaching rows are included.
    sku_frames = []
    for sku_id in top_sku:
        sku_frames.append(query_table("fact_order_item", limit=5000, sku_id=sku_id))
    items = pd.concat(sku_frames, ignore_index=True).drop_duplicates(subset=["order_item_id"])
    basket = items.groupby("order_id")["sku_id"].apply(set)
    rules = []
    for a in top_sku:
        has_a = basket.apply(lambda s: a in s)
        support_a = has_a.mean()
        for b in top_sku:
            if a == b:
                continue
            has_b = basket.apply(lambda s: b in s)
            support_b = has_b.mean()
            both = (has_a & has_b).mean()
            if support_a > 0 and support_b > 0:
                confidence = both / support_a
                lift = confidence / support_b
                if both >= 0.001 and confidence >= 0.03 and lift > 1.05:
                    rules.append([a, b, both, confidence, lift])
    rules_df = pd.DataFrame(rules, columns=["antecedent", "consequent", "support", "confidence", "lift"])
    if not rules_df.empty:
        rules_df = rules_df.sort_values(["lift", "confidence"], ascending=False)
        rules_named = rules_df.merge(products, left_on="antecedent", right_on="sku_id", how="left").rename(
            columns={"sku_name": "antecedent_name", "category_name": "antecedent_category"}
        ).drop(columns=["sku_id"])
        rules_named = rules_named.merge(products, left_on="consequent", right_on="sku_id", how="left").rename(
            columns={"sku_name": "consequent_name", "category_name": "consequent_category"}
        ).drop(columns=["sku_id"])
    else:
        rules_named = rules_df
    decision = (
        "关联规则结果偏弱但可解释。可选取 lift 高且支持度不太低的组合做凑单推荐，"
        "但不建议把当前规则直接作为强套餐策略，因为规则支持度整体较低。"
    )
    return {
        "title": "第 6 章 商品关联规则与组合销售",
        "good": len(rules_df) >= 10 and (not rules_df.empty and rules_df["lift"].max() > 1.2),
        "summary": {
            "orders_sample": basket.shape[0],
            "rules": len(rules_df),
            "max_lift": 0 if rules_df.empty else rules_df["lift"].max(),
            "max_confidence": 0 if rules_df.empty else rules_df["confidence"].max(),
        },
        "tables": {"rules": rules_named.head(20)},
        "decision": decision,
        "data_issue": "当前关联规则商业力度偏弱。建议修改模拟数据：人为设置若干品类搭配关系，例如手机+保护壳、咖啡+杯具、课程+资料包，并提高同单购买概率。",
    }


def chapter_7():
    orders = paid_orders()
    daily = orders.groupby("order_date").agg(
        sales=("paid_amount", "sum"),
        orders=("order_id", "nunique"),
    ).sort_index()
    daily = daily.asfreq("D").fillna(0)
    daily["ma7"] = daily["sales"].rolling(7).mean()
    daily["ma30"] = daily["sales"].rolling(30).mean()
    recent = daily.tail(30)
    forecast = recent["sales"].mean()
    safety = recent["sales"].std() * 1.65
    cv = recent["sales"].std() / recent["sales"].mean()
    # category demand
    items = load_table("fact_order_item", limit=100000)
    products = load_table("dim_product", limit=100000)[["sku_id", "category_name"]]
    items = items.merge(products, on="sku_id", how="left")
    cat = items.groupby("category_name").agg(
        qty=("quantity", "sum"),
        sales=("line_amount", "sum"),
        profit=("gross_profit", "sum"),
    ).reset_index().sort_values("sales", ascending=False)
    decision = (
        f"最近 30 天日销售基准预测为 {money(forecast)}，安全库存金额建议约 {money(safety)}。"
        f"需求波动系数 CV={cv:.2f}，说明备货需要保留缓冲。优先保障销售额最高的品类。"
    )
    return {
        "title": "第 7 章 销售预测与库存备货",
        "good": forecast > 100000 and 0.05 < cv < 1,
        "summary": {"forecast_daily_sales": forecast, "safety_stock_value": safety, "cv": cv},
        "tables": {"top_categories": cat.head(12)},
        "decision": decision,
        "data_issue": "销售预测结果有经营含义，教学可用。若要讲季节性或促销峰值，可在模拟数据中加入更明显的节假日/大促冲击。",
    }


def chapter_8():
    ads = load_table("fact_ads_spend", limit=100000)
    ch = ads.groupby("channel").agg(
        spend=("spend_amount", "sum"),
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        conversions=("conversions", "sum"),
    ).reset_index()
    ch["ctr"] = ch["clicks"] / ch["impressions"]
    ch["cvr"] = ch["conversions"] / ch["clicks"]
    ch["cpa"] = ch["spend"] / ch["conversions"]
    ch["estimated_revenue"] = ch["conversions"] * 120
    ch["roas"] = ch["estimated_revenue"] / ch["spend"]
    ch = ch.sort_values("roas", ascending=False)
    best = ch.iloc[0]
    worst = ch.iloc[-1]
    decision = (
        f"按估算 ROAS，最佳渠道为 {best['channel']}，ROAS={best['roas']:.2f}；最低渠道为 {worst['channel']}，ROAS={worst['roas']:.2f}。"
        "建议加投高 ROAS 渠道、压缩低 ROAS 渠道，并在下次活动中保留对照组验证增量。"
    )
    return {
        "title": "第 8 章 营销归因与预算优化",
        "good": ch["roas"].max() / ch["roas"].min() > 1.5 and ch["spend"].sum() > 0,
        "summary": {
            "channels": len(ch),
            "total_spend": ch["spend"].sum(),
            "best_channel": best["channel"],
            "best_roas": best["roas"],
            "worst_channel": worst["channel"],
            "worst_roas": worst["roas"],
        },
        "tables": {"channel_roas": ch},
        "decision": decision,
        "data_issue": "渠道差异存在，适合教学。若要更严谨地讲归因，建议模拟 campaign control group 的真实订单转化和自然流量抢占。",
    }


def chapter_9(results):
    score = sum(1 for r in results if r["good"])
    risk = [r["title"] for r in results if not r["good"]]
    decision = (
        f"8 个分析章节中有 {score}/8 个达到较好教学效果。总体可作为参考答案基础。"
        "经营建议主线是：先保障数据质量和指标口径，再围绕转化、复购、分群、备货和广告预算做分场景决策。"
    )
    return {
        "title": "第 9 章 综合经营决策项目",
        "good": score >= 6,
        "summary": {"good_chapters": score, "need_attention": risk},
        "tables": {},
        "decision": decision,
        "data_issue": "综合项目可用，但第 6 章关联规则和第 4 章预测效果还可以通过模拟数据机制进一步增强。",
    }


def render_result(r):
    parts = [f"# {r['title']}", "", "## 是否适合作为参考答案", ""]
    parts.append("结论：**适合**" if r["good"] else "结论：**需要谨慎，建议优化模拟数据或降低教学目标**")
    parts += ["", "## 关键结果", ""]
    for k, v in r["summary"].items():
        if isinstance(v, float):
            parts.append(f"- {k}: {v:.4f}")
        else:
            parts.append(f"- {k}: {v}")
    parts += ["", "## 商业决策", "", r["decision"], "", "## 数据质量与模拟数据建议", "", r["data_issue"]]
    for name, df in r["tables"].items():
        parts += ["", f"## 参考表：{name}", "", md_table(df)]
    return "\n".join(parts)


def main():
    results = []
    for fn in [chapter_1, chapter_2, chapter_3, chapter_4, chapter_5, chapter_6, chapter_7, chapter_8]:
        r = fn()
        results.append(r)
        path = save_report(f"{len(results):02d}_reference_answer.md", render_result(r))
        line(f"WROTE {path.name}: {'GOOD' if r['good'] else 'CHECK'}")
    r9 = chapter_9(results)
    path = save_report("09_reference_answer.md", render_result(r9))
    line(f"WROTE {path.name}: {'GOOD' if r9['good'] else 'CHECK'}")
    summary_rows = []
    for i, r in enumerate(results + [r9], start=1):
        summary_rows.append({"chapter": i, "title": r["title"], "good": r["good"], "decision": r["decision"]})
    summary_df = pd.DataFrame(summary_rows)
    save_report(
        "00_reference_summary.md",
        "# V3 参考答案总览\n\n"
        f"- ETL API: {API_BASE}\n"
        f"- API 状态: {api_status()}\n"
        f"- 生成目录: `{OUT}`\n\n"
        + md_table(summary_df, max_rows=20),
    )
    line("DONE")


if __name__ == "__main__":
    main()
