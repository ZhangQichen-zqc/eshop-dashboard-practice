"""FastAPI 仪表盘入口

启动方式:
    cd analytics_dashboard
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import CORS_ALLOWED_ORIGINS, SERVICE_HOST, SERVICE_PORT, LOG_LEVEL
from .data_access import (
    get_db_connection,
    query_table,
    query_table_schema,
    query_metrics,
    query_quality_report,
    query_daily_summary,
    load_dim_user,
    load_dim_product,
    load_dim_date,
    load_dim_campaign,
    load_fact_order,
    load_fact_order_item,
    load_fact_traffic,
    load_fact_coupon_use,
    load_fact_refund,
    load_fact_fulfillment,
    load_fact_inventory_movement,
    load_fact_product_review,
    load_fact_ads_spend,
    ETLClient,
)
from .subprojects import data_quality as r0
from .subprojects import business_health as r1
from .subprojects import traffic_funnel as r2
from .subprojects import inventory_strategy as r10
from .subprojects import fulfillment_analysis as r9
from .subprojects import marketing_attribution as r8
from .subprojects import sales_forecast as r7
from .subprojects import association_rules as r6
from .subprojects import customer_clustering as r5
from .subprojects import repurchase_prediction as r4
from .subprojects import rfm_user_ops as r3
from .subprojects import feature_engineering as fe
from .utils import to_json, to_native, setup_logging

# ---- 日志 ----
logger = setup_logging(LOG_LEVEL)

# ---- 缓存 ----
_cache: Dict[str, Any] = {}
_cache_time: Dict[str, float] = {}


def cached(key: str, ttl: int = 3600):
    """简易内存缓存装饰器，用于 API 响应缓存。"""
    now = time.time()
    if key in _cache and (now - _cache_time.get(key, 0)) < ttl:
        return _cache[key]
    return None


def set_cache(key: str, value: Any):
    _cache[key] = value
    _cache_time[key] = time.time()


# ---- 生命周期 ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭事件。"""
    logger.info("=" * 50)
    logger.info("Course eShop Dashboard 启动中...")
    # 预热缓存
    try:
        logger.info("预热指标缓存...")
        metrics = query_metrics()
        set_cache("metrics", metrics)
        logger.info(f"GMV: ¥{metrics['gmv']:,.0f} | 订单: {metrics['order_count']:,}")
    except Exception as e:
        logger.warning(f"缓存预热失败（数据库可能未就绪）: {e}")
    logger.info(f"服务地址: http://{SERVICE_HOST}:{SERVICE_PORT}")
    logger.info("=" * 50)
    yield
    logger.info("Dashboard 关闭，清理资源...")
    _cache.clear()


# ---- FastAPI 应用 ----
app = FastAPI(
    title="Course eShop Dashboard",
    description="电商经营仪表盘 API — 数据挖掘课程期末项目",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
import os
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")


# ---- 中间件 ----
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志 + 耗时记录。"""
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration:.3f}s)")
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理。"""
    logger.error(f"未捕获异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "path": str(request.url.path)},
    )


# ============================================================
# 路由
# ============================================================

@app.get("/")
async def root():
    """API 根信息。"""
    return {
        "service": "Course eShop Dashboard API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    """健康检查。"""
    ok = True
    db_ok = False
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        ok = False

    return {
        "ok": ok,
        "database": db_ok,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/summary")
async def get_summary():
    """经营概览（核心 KPI）。"""
    cached_result = cached("metrics", ttl=300)
    if cached_result:
        return cached_result

    try:
        metrics = query_metrics()
        set_cache("metrics", metrics)
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取指标失败: {e}")


@app.get("/api/tables")
async def get_tables():
    """数据表列表。"""
    try:
        conn = get_db_connection()
        tables = []
        for row in conn.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name"
        ):
            count = conn.execute(f'SELECT COUNT(*) FROM "{row[0]}"').fetchone()[0]
            tables.append({"name": row[0], "type": row[1], "rows": count})
        conn.close()
        return {"tables": tables, "total": len(tables)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tables/{name}")
async def get_table_schema(name: str):
    """表结构查询。"""
    try:
        schema = query_table_schema(name)
        if schema.empty:
            raise HTTPException(status_code=404, detail=f"表不存在: {name}")
        return {"table": name, "columns": schema.to_dict(orient="records")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/query/{table_name}")
async def query_data(
    table_name: str,
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    order_by: Optional[str] = None,
):
    """数据查询（分页）。"""
    try:
        df = query_table(table_name, limit=limit, offset=offset, order_by=order_by)
        return {
            "table": table_name,
            "limit": limit,
            "offset": offset,
            "count": len(df),
            "data": df.to_dict(orient="records"),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/quality")
async def get_quality():
    """数据质量快速报告。"""
    try:
        checks = query_quality_report()
        return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "checks": checks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r0/quality-report")
async def get_r0_full_report():
    """R0 完整数据质量报告（6 大维度）。"""
    try:
        cached_result = cached("r0_quality", ttl=600)
        if cached_result:
            return to_native(cached_result)
        report = r0.run_full_quality_report()
        set_cache("r0_quality", report)
        return to_native(report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/r0/preprocess")
async def r0_preprocess(config: Optional[Dict] = None):
    """数据预处理流水线（示例用 fact_order）。"""
    try:
        from .data_access import load_fact_order
        df = load_fact_order()
        result = r0.run_preprocessing_pipeline(df, config or {})
        return to_native({
            "ok": True,
            "input_shape": list(df.shape),
            "output_shape": list(result.shape),
            "sample": result.head(3).to_dict(orient="records"),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R3/R4 特征工程路由
# ============================================================

@app.get("/api/r3/build-user-wide")
async def build_user_wide():
    """构建用户宽表（RFM + 行为 + 优惠券 + 品类偏好）。"""
    try:
        wide = fe.build_user_wide_table(save_csv=True)
        # 返回概要信息
        num_cols = wide.select_dtypes(include=[np.number]).columns.tolist()
        return to_native({
            "ok": True,
            "shape": list(wide.shape),
            "columns": wide.columns.tolist(),
            "numeric_columns": num_cols,
            "segments": wide["rfm_segment"].value_counts().to_dict(),
            "sample": wide.head(5).to_dict(orient="records"),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r3/product-wide")
async def build_product_wide():
    """构建商品宽表。"""
    try:
        wide = fe.build_product_wide_table(save_csv=True)
        return to_native({
            "ok": True,
            "shape": list(wide.shape),
            "columns": wide.columns.tolist(),
            "sample": wide.head(5).to_dict(orient="records"),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r3/feature-importance")
async def get_feature_importance(target: Optional[str] = None):
    """特征重要性预分析。"""
    try:
        wide = fe.build_user_wide_table(save_csv=False)
        result = fe.analyze_feature_importance(wide, target)
        result["shape"] = list(wide.shape)
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R1 经营驾驶舱路由
# ============================================================

@app.get("/api/r1/dashboard")
async def get_r1_dashboard():
    """经营驾驶舱全部数据（KPI + 趋势 + 拆解 + 异常）。"""
    try:
        data = r1.get_dashboard_data()
        return to_native(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r1/kpi")
async def get_r1_kpi():
    """8 个核心指标卡。"""
    try:
        conn = get_db_connection()
        kpi = r1.compute_kpi(conn)
        mom = r1.compute_mom_changes(conn)
        conn.close()
        return to_native({"kpi": kpi, "mom": mom})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r1/trends")
async def get_r1_trends():
    """月度趋势数据。"""
    try:
        conn = get_db_connection()
        trends = r1.compute_monthly_trends(conn)
        conn.close()
        return to_native({"trends": trends})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r1/channel-breakdown")
async def get_r1_channels():
    """渠道拆解。"""
    try:
        conn = get_db_connection()
        data = r1.compute_channel_breakdown(conn)
        conn.close()
        return to_native({"channels": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r1/category-breakdown")
async def get_r1_categories():
    """品类拆解。"""
    try:
        conn = get_db_connection()
        data = r1.compute_category_breakdown(conn)
        conn.close()
        return to_native({"categories": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r1/top-products")
async def get_r1_top_products():
    """TOP/BOTTOM 商品。"""
    try:
        conn = get_db_connection()
        data = r1.compute_top_bottom_products(conn)
        conn.close()
        return to_native(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r1/anomaly-alerts")
async def get_r1_anomalies():
    """异常告警。"""
    try:
        conn = get_db_connection()
        data = r1.detect_anomalies(conn)
        conn.close()
        return to_native({"anomalies": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R2 流量漏斗路由
# ============================================================

@app.get("/api/r2/funnel")
async def get_r2_funnel(group_by: Optional[str] = None):
    """漏斗数据（可选按 channel/device/campaign 分组）。"""
    try:
        conn = get_db_connection()
        if group_by == "channel":
            data = r2.compute_funnel_by_channel(conn)
        elif group_by == "device":
            data = r2.compute_funnel_by_device(conn)
        elif group_by == "campaign":
            data = r2.compute_funnel_by_campaign(conn)
        else:
            data = r2.compute_overall_funnel(conn)
        conn.close()
        return to_native(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r2/dropoff-analysis")
async def get_r2_dropoff():
    """流失诊断 + 高曝光低加购/高加购低结算商品。"""
    try:
        conn = get_db_connection()
        dropoff = r2.find_biggest_dropoff(conn)
        high_exposure = r2.find_high_exposure_low_cart(conn)
        high_cart = r2.find_high_cart_low_checkout(conn)
        conn.close()
        return to_native({"dropoff": dropoff, "high_exposure_low_cart": high_exposure, "high_cart_low_checkout": high_cart})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r2/remarketing-list")
async def get_r2_remarketing():
    """再营销候选名单。"""
    try:
        conn = get_db_connection()
        data = r2.generate_remarketing_list(conn)
        conn.close()
        return to_native(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R3 RFM 用户运营路由
# ============================================================

@app.get("/api/r3/rfm-layers")
async def get_r3_rfm_layers():
    """RFM 分群数据。"""
    try:
        data = r3.compute_rfm_layers()
        return to_native(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r3/cohort-retention")
async def get_r3_cohort():
    """Cohort 留存数据。"""
    try:
        data = r3.compute_cohort_retention()
        return to_native(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r3/user-profile/{user_id}")
async def get_r3_user_profile(user_id: str):
    """用户画像。"""
    try:
        data = r3.get_user_profile(user_id)
        return to_native(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r3/segment-comparison")
async def get_r3_segment_comparison():
    """分群对比数据。"""
    try:
        data = r3.get_segment_comparison()
        return to_native(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r3/search-users")
async def get_r3_search(keyword: str = "", segment: str = "", limit: int = 50):
    """用户搜索。"""
    try:
        data = r3.search_users(keyword, segment, limit)
        return to_native({"users": data, "count": len(data)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/r3/batch-tag")
async def post_r3_batch_tag(user_ids: List[str], tag: str):
    """批量打标签。"""
    try:
        result = r3.batch_tag_users(user_ids, tag)
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R4 复购预测路由
# ============================================================

@app.get("/api/r4/train")
async def get_r4_train():
    """训练复购预测模型（样本准备 + 特征 + 多模型训练 + 评估）。"""
    try:
        result = r4.prepare_and_train()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r4/prediction-list")
async def get_r4_prediction_list():
    """预测名单（全部用户打分）。"""
    try:
        result = r4.score_all_users()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/r4/adjust-threshold")
async def post_r4_threshold(threshold: float = 0.5):
    """调节阈值 + ROI 模拟。"""
    try:
        result = r4.simulate_roi(threshold)
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/r4/roi-simulation")
async def post_r4_roi(top_pct: float = 5.0):
    """ROI 模拟（按百分比触达）。"""
    try:
        result = r4.generate_contact_list(top_pct=top_pct)
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R5 聚类分析路由
# ============================================================

@app.get("/api/r5/user-clusters")
async def get_r5_user_clusters(k: int = 5):
    """用户聚类。"""
    try:
        result = r5.cluster_users(k=k)
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r5/product-clusters")
async def get_r5_product_clusters(k: int = 5):
    """商品聚类。"""
    try:
        result = r5.cluster_products(k=k)
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r5/cluster-profile/{cluster_id}")
async def get_r5_cluster_profile(cluster_id: int):
    """簇画像（占位，由前端从 user-clusters 提取）。"""
    return {"cluster_id": cluster_id, "note": "请使用 /api/r5/user-clusters 获取完整分群数据"}


@app.get("/api/r5/algorithm-compare")
async def get_r5_algorithm_compare():
    """三种聚类算法对比。"""
    try:
        result = r5.compare_algorithms()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R6 关联规则路由
# ============================================================

@app.get("/api/r6/association-rules")
async def get_r6_rules():
    """关联规则列表。"""
    try:
        result = r6.run_full_association_analysis()
        # 只返回精简版避免过大
        return to_native({
            "category_rules": result["category_rules"]["rules"][:30],
            "sku_rules_count": len(result["sku_rules"]["rules"]),
            "bundles": result["bundles"],
            "cross_sell": result["cross_sell"],
            "business_unsuitable": result["business_unsuitable"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r6/frequent-itemsets")
async def get_r6_frequent_itemsets(basket_type: str = "sku"):
    """频繁项集。"""
    try:
        if basket_type == "category":
            basket = r6.build_category_basket()
        else:
            basket = r6.build_sku_basket()
        result = r6.mine_association_rules(basket)
        return to_native({"itemsets": result["frequent_itemsets"][:50]})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r6/bundle-recommendations")
async def get_r6_bundles():
    """捆绑推荐。"""
    try:
        basket = r6.build_sku_basket()
        result = r6.mine_association_rules(basket, min_support=0.005)
        bundles = r6.generate_bundle_recommendations(result["rules"])
        return to_native({"bundles": bundles})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r6/product-recommendations/{sku_id}")
async def get_r6_product_recs(sku_id: str):
    """单品推荐。"""
    try:
        basket = r6.build_sku_basket()
        result = r6.mine_association_rules(basket, min_support=0.003)
        recs = r6.get_product_recommendations(sku_id, result["rules"])
        return to_native({"sku_id": sku_id, "recommendations": recs})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R7 时间序列预测路由
# ============================================================

@app.get("/api/r7/gmv-forecast")
async def get_r7_gmv_forecast(periods: int = 30):
    """GMV 预测（多模型对比 + 未来 N 天预测）。"""
    try:
        result = r7.forecast_gmv(periods=periods)
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r7/category-forecast/{category_name}")
async def get_r7_category_forecast(category_name: str, periods: int = 30):
    """品类销量预测。"""
    try:
        result = r7.forecast_category(category_name, periods=periods)
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r7/safety-stock")
async def get_r7_safety_stock():
    """安全库存与补货建议。"""
    try:
        result = r7.compute_safety_stock()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r7/replenishment-list")
async def get_r7_replenishment():
    """补货清单（紧急补货 + 库存过剩）。"""
    try:
        result = r7.compute_safety_stock()
        return to_native({
            "urgent": result["urgent_replenishment"],
            "excess": result["excess_inventory"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R8 营销归因路由
# ============================================================

@app.get("/api/r8/campaign-kpis")
async def get_r8_campaign_kpis():
    """活动 KPI。"""
    try:
        result = r8.compute_campaign_kpis()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r8/coupon-analysis")
async def get_r8_coupon_analysis():
    """优惠券分析。"""
    try:
        result = r8.analyze_coupons()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r8/channel-efficiency")
async def get_r8_channel_efficiency():
    """渠道效率排名。"""
    try:
        result = r8.compute_budget_optimization()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r8/increment-analysis")
async def get_r8_increment():
    """增量分析。"""
    try:
        result = r8.compute_increment_analysis()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r8/budget-optimization")
async def get_r8_budget(migrate_pct: float = 20.0):
    """预算优化模拟。"""
    try:
        result = r8.compute_budget_optimization(migrate_pct=migrate_pct)
        return to_native({
            "channel_ranking": result["channel_ranking"],
            "suggestion": result["suggestion"],
            "simulation": result["simulation"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R9 履约售后路由
# ============================================================

@app.get("/api/r9/fulfillment")
async def get_r9_fulfillment():
    """履约分析。"""
    try:
        result = r9.analyze_fulfillment()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r9/refund-analysis")
async def get_r9_refunds():
    """退款分析。"""
    try:
        result = r9.analyze_refunds()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r9/review-analysis")
async def get_r9_reviews():
    """评论分析。"""
    try:
        result = r9.analyze_reviews()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r9/risk-list")
async def get_r9_risks():
    """风险清单。"""
    try:
        result = r9.generate_risk_list()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# R10 库存策略路由
# ============================================================

@app.get("/api/r10/sku-performance")
async def get_r10_sku_perf():
    """SKU 动销绩效。"""
    try:
        result = r10.analyze_sku_performance()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r10/abc-classification")
async def get_r10_abc():
    """ABC 分类矩阵。"""
    try:
        result = r10.compute_abc_matrix()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r10/strategies")
async def get_r10_strategies():
    """商品策略建议。"""
    try:
        result = r10.generate_product_strategies()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/r10/alerts")
async def get_r10_alerts():
    """库存预警。"""
    try:
        result = r10.generate_inventory_alerts()
        return to_native(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/subprojects")
async def list_subprojects():
    """子项目列表。"""
    return {
        "subprojects": [
            {"id": "r0", "name": "数据质量检查", "status": "completed"},
            {"id": "r1", "name": "经营驾驶舱", "status": "completed"},
            {"id": "r2", "name": "流量漏斗诊断", "status": "completed"},
            {"id": "r3", "name": "RFM 用户运营", "status": "completed"},
            {"id": "r4", "name": "复购预测模型", "status": "completed"},
            {"id": "r5", "name": "客户聚类分群", "status": "completed"},
            {"id": "r6", "name": "关联规则分析", "status": "completed"},
            {"id": "r7", "name": "时间序列预测", "status": "completed"},
            {"id": "r8", "name": "营销归因分析", "status": "completed"},
            {"id": "r9", "name": "履约售后分析", "status": "completed"},
            {"id": "r10", "name": "库存策略优化", "status": "completed"},
            {"id": "r11", "name": "综合决策中心", "status": "pending"},
        ]
    }


@app.get("/api/subprojects/{subproject_id}")
async def get_subproject(subproject_id: str):
    """子项目详情（占位）。"""
    return {"id": subproject_id, "status": "pending", "message": "子项目尚未实现，将在后续阶段开发。"}


@app.post("/api/reload")
async def reload_cache():
    """手动刷新缓存。"""
    _cache.clear()
    try:
        metrics = query_metrics()
        set_cache("metrics", metrics)
        return {"ok": True, "message": "缓存已刷新", "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export/{table_name}")
async def export_table(table_name: str, format: str = Query("json")):
    """数据导出（JSON 格式，可用于下载）。"""
    try:
        df = query_table(table_name, limit=10000)
        if format == "csv":
            from fastapi.responses import StreamingContent
            import io
            stream = io.StringIO()
            df.to_csv(stream, index=False)
            return Response(
                content=stream.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={table_name}.csv"},
            )
        return {"table": table_name, "count": len(df), "data": df.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
