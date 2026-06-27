FROM python:3.12-slim-bookworm

WORKDIR /app

# 安装系统依赖（编译 scikit-learn 等需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libsqlite3-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 缓存层
COPY analytics_dashboard/requirements.txt .
# 使用清华 pip 镜像加速
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制源代码
COPY analytics_dashboard/ ./analytics_dashboard/

# 暴露端口
ENV SERVICE_HOST=0.0.0.0
ENV SERVICE_PORT=8000
ENV DATA_SOURCE_MODE=etl
# ETL API 地址 — docker-compose 中通过 service name 访问
ENV ETL_API_BASE_URL=http://mall-api:38173/api/etl

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "analytics_dashboard", "--host", "0.0.0.0", "--port", "8000"]
