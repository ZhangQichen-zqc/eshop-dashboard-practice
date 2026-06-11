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


@app.get("/api/subprojects")
async def list_subprojects():
    """子项目列表。"""
    return {
        "subprojects": [
            {"id": "r0", "name": "数据质量检查", "status": "completed"},
            {"id": "r1", "name": "经营驾驶舱", "status": "pending"},
            {"id": "r2", "name": "流量漏斗诊断", "status": "pending"},
            {"id": "r3", "name": "RFM 用户运营", "status": "pending"},
            {"id": "r4", "name": "复购预测模型", "status": "pending"},
            {"id": "r5", "name": "客户聚类分群", "status": "pending"},
            {"id": "r6", "name": "关联规则分析", "status": "pending"},
            {"id": "r7", "name": "时间序列预测", "status": "pending"},
            {"id": "r8", "name": "营销归因分析", "status": "pending"},
            {"id": "r9", "name": "履约售后分析", "status": "pending"},
            {"id": "r10", "name": "库存策略优化", "status": "pending"},
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
