"""应用配置模块

通过环境变量覆盖默认值，支持本地开发和容器化部署。
"""

import os
from pathlib import Path

# ---- 项目路径 ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # eshop-dashboard-practice/
APP_DIR = Path(__file__).resolve().parent  # app/

# ---- 数据库配置 ----
SQLITE_DB_PATH = os.environ.get(
    "ESHOP_DB_PATH",
    str(PROJECT_ROOT / "server" / "data" / "eshop.sqlite")
)

# ---- ETL API 配置 ----
ETL_API_BASE_URL = os.environ.get(
    "ETL_API_BASE_URL",
    "http://127.0.0.1:38173/api/etl"
)

# ---- 缓存配置 ----
CACHE_DIR = os.environ.get(
    "CACHE_DIR",
    str(PROJECT_ROOT / ".cache")
)
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL", "3600"))  # 默认 1 小时

# ---- 服务配置 ----
SERVICE_HOST = os.environ.get("SERVICE_HOST", "127.0.0.1")
SERVICE_PORT = int(os.environ.get("SERVICE_PORT", "8000"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# ---- CORS 配置 ----
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173"
).split(",")

# ---- 数据源模式 ----
# "etl":   通过 ETL API (http://127.0.0.1:38173/api/etl) 获取数据（教学标准模式）
# "sqlite": 直连 SQLite（降级方案）
DATA_SOURCE_MODE = os.environ.get("DATA_SOURCE_MODE", "etl")
