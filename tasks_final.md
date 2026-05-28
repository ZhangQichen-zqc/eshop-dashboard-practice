# IT 项目管理实践课：商城 FastAPI 仪表盘开发课堂演示步骤

适用目录：`Project/eshop-dashboard-practice`

课堂目标：学生从已有商城源码出发，完成混合编程项目。Node.js 保留为商城业务系统，Python/FastAPI 负责数据挖掘、仪表盘和经营辅助决策，最终使用 Git 管理过程，并用 Docker Compose 部署到 Ubuntu Linux。

## 0. 课程准备与目标说明

- [ ] 0.1 说明项目背景。
  - 教师说明：本实践不是单纯做页面，而是按软件项目流程完成“需求拆解、环境搭建、后端服务、数据挖掘子项目、仪表盘、测试、部署、版本管理”。
  - 学生需要理解：商城源码是业务系统，FastAPI 是新增的数据分析与决策服务。
  - 验收标准：能说清楚 Node 商城 API、React 商城前端、FastAPI 仪表盘、SQLite 数据库之间的关系。

- [ ] 0.2 检查本机工具。
  - 教师演示命令：
    ```bash
    git --version
    node --version
    npm --version
    python --version
    ```
  - Ubuntu 部署阶段再检查：
    ```bash
    docker --version
    docker compose version
    ```
  - 常见问题：如果 Git 提交时报 `Author identity unknown`，需要配置 `git config user.name` 和 `git config user.email`。

## 1. 从商城源码创建实践项目

- [ ] 1.1 在 `Project/` 下创建新项目目录。
  - 教师演示：
    ```bash
    cd C:\Users\zzz\Projects\eshop\Project
    mkdir eshop-dashboard-practice
    ```
  - 说明：新项目目录用于课堂实践，避免直接修改原始商城源码。

- [ ] 1.2 复制商城源码与教学数据。
  - 复制内容：
    ```text
    client/   React 商城前端源码
    server/   Node.js + Express 商城 API 与 SQLite 数据库
    docs/     商城教学文档
    exports/  课程导出 CSV 数据
    ```
  - 学生跟做：复制后确认目录存在。
    ```bash
    ls
    ```
  - 验收标准：新项目下存在 `client`、`server`、`docs`、`exports`。

- [ ] 1.3 清理不应进入 Git 的文件。
  - 清理对象：`node_modules/`、`client/dist/`、SQLite 临时文件 `*.sqlite-shm`、`*.sqlite-wal`、数据库备份目录。
  - 说明：这是软件开发规范的一部分，避免把依赖和运行产物提交到仓库。

## 2. 建立 Git 项目基线

- [ ] 2.1 初始化 Git 仓库。
  ```bash
  git init
  git branch -M main
  ```

- [ ] 2.2 配置仓库级提交身份。
  ```bash
  git config user.name "Course Student"
  git config user.email "student@example.edu"
  ```
  - 说明：课堂中建议使用仓库级配置，不强制修改学生全局配置。

- [ ] 2.3 提交源码基线。
  ```bash
  git add client server docs exports
  git commit -m "Initialize from course e-commerce source"
  ```
  - 验收命令：
    ```bash
    git log --oneline
    ```
  - 建议里程碑：`v0.1`，完成“从源码建立项目基线”。

## 3. 建立工程化基础

- [ ] 3.1 增加 `.gitignore`。
  - 内容应包含：
    ```text
    node_modules/
    dist/
    __pycache__/
    *.pyc
    *.log
    *.sqlite-shm
    *.sqlite-wal
    server/data/backups/
    ```
  - 说明：后续 Python 运行会产生 `__pycache__`，必须提前忽略。

- [ ] 3.2 增加 `.gitattributes`。
  - 目的：规范换行和二进制文件处理，减少 Windows/Linux 协作差异。
  - 示例：
    ```text
    * text=auto eol=lf
    *.sqlite binary
    ```

- [ ] 3.3 增加根目录 `package.json`。
  - 作用：统一管理 Node 商城服务、React 构建、FastAPI 启动和验证命令。
  - 关键脚本：
    ```json
    {
      "install:all": "npm install --prefix server && npm install --prefix client && python -m pip install -r analytics_dashboard/requirements.txt",
      "dev": "node scripts/dev.mjs",
      "start:dashboard": "python -m uvicorn app.main:app --app-dir analytics_dashboard --host 127.0.0.1 --port 8000",
      "test:dashboard": "python analytics_dashboard/tests/smoke_test.py",
      "build:mall-web": "npm run build --prefix client"
    }
    ```

- [ ] 3.4 提交工程基线。
  ```bash
  git add .gitignore .gitattributes package.json README.md scripts/dev.mjs
  git commit -m "Add project engineering baseline"
  ```

## 4. 安装并验证本地依赖

- [ ] 4.1 安装 Node 与 Python 依赖。
  ```bash
  npm run install:all
  ```
  - 说明：这一步会分别安装 `server`、`client` 和 `analytics_dashboard` 的依赖。
  - 常见问题：`npm audit` 提示不等于项目不能运行；课堂先记录风险，不直接做破坏性升级。

- [ ] 4.2 验证商城前端仍可构建。
  ```bash
  npm run build:mall-web
  ```
  - 验收标准：Vite build 成功。

## 5. 新建 Python/FastAPI 仪表盘子系统

- [ ] 5.1 创建目录结构。
  ```text
  analytics_dashboard/
    requirements.txt
    app/
      main.py
      data_access.py
      utils.py
      subprojects/
    static/
      index.html
      styles.css
      app.js
    tests/
      smoke_test.py
  ```
  - 说明：这是混合编程的关键。不要把数据挖掘逻辑塞进 Node 商城 API。

- [ ] 5.2 增加 Python 依赖。
  - `analytics_dashboard/requirements.txt`：
    ```text
    fastapi==0.115.6
    uvicorn[standard]==0.34.0
    ```

- [ ] 5.3 实现 SQLite 读取层。
  - 文件：`analytics_dashboard/app/data_access.py`
  - 关键要求：
    - 默认读取 `server/data/eshop.sqlite`。
    - 支持环境变量 `ESHOP_DB_PATH`，便于 Docker 容器部署。
    - 使用只读连接，避免仪表盘误改业务数据。

- [ ] 5.4 实现公共工具。
  - 文件：`analytics_dashboard/app/utils.py`
  - 包含：安全除法、金额格式、百分比、日期解析、分位数、标准化、均值与标准差。

## 6. 按数据挖掘知识点拆分子项目

- [ ] 6.1 子项目一：经营健康诊断 `business_health`。
  - 输入：`orders`、`refunds`、`page_events`
  - 方法：描述性统计、月度趋势、渠道拆解、转化漏斗。
  - 输出：GMV、订单数、购买用户、客单价、退款率、漏斗转化率。
  - 管理意义：定位经营问题优先级。

- [ ] 6.2 子项目二：用户建模宽表 `feature_engineering`。
  - 输入：`users`、`orders`、`page_events`
  - 方法：RFM、行为特征、缺失值处理、特征标准化。
  - 输出：用户宽表、recency、frequency、monetary、行为次数、RFM 分数。
  - 管理意义：给复购预测和客户分群提供统一特征底座。

- [ ] 6.3 子项目三：复购预测 `repurchase_prediction`。
  - 输入：用户宽表。
  - 方法：教学版可解释评分模型、阈值选择、Precision/Recall、ROI。
  - 输出：高潜用户名单、触达比例、预估 ROI。
  - 管理意义：控制营销成本，避免全量粗放发券。

- [ ] 6.4 子项目四：客户分群 `customer_clustering`。
  - 输入：RFM 特征。
  - 方法：RFM 分箱、规则分群、群体画像。
  - 输出：高价值高频客、近期活跃复购客、沉睡待召回客、未转化浏览客等群体。
  - 管理意义：不同群体匹配不同运营策略。

- [ ] 6.5 子项目五：关联规则 `association_rules`。
  - 输入：`order_items`、`sku`、`orders`
  - 方法：购物篮分析、支持度、置信度、提升度。
  - 输出：商品组合规则和凑单推荐候选。
  - 管理意义：组合销售、推荐位实验、客单价提升。

- [ ] 6.6 子项目六：销售预测 `sales_forecast`。
  - 输入：订单日期与 GMV。
  - 方法：最近 30 天移动平均、标准差、波动系数、安全库存。
  - 输出：日均 GMV、需求波动、安全库存金额、重点品类。
  - 管理意义：备货计划与库存风险控制。

- [ ] 6.7 子项目七：营销归因 `marketing_attribution`。
  - 输入：`ads_spend`、`orders`
  - 方法：CTR、CVR、CPA、ROAS。
  - 输出：渠道效率、预算动作建议。
  - 管理意义：预算加投、维持、压缩或实验化。

- [ ] 6.8 子项目八：综合决策板 `decision_board`。
  - 输入：前七个子项目结果。
  - 方法：把指标转化为业务动作。
  - 输出：P0/P1/P2 决策建议、证据、Git 项目路线。
  - 管理意义：用于答辩和经营复盘。

## 7. 开发 FastAPI 接口与页面

- [ ] 7.1 实现 FastAPI 入口。
  - 文件：`analytics_dashboard/app/main.py`
  - 必备接口：
    ```text
    GET /
    GET /health
    GET /api/summary
    GET /api/subprojects
    GET /api/subprojects/{subproject_id}
    GET /api/decision-board
    POST /api/reload
    ```

- [ ] 7.2 实现仪表盘静态页面。
  - 文件：
    ```text
    analytics_dashboard/static/index.html
    analytics_dashboard/static/styles.css
    analytics_dashboard/static/app.js
    ```
  - 页面板块：
    - 经营 KPI
    - 月度 GMV 趋势
    - 转化漏斗
    - 数据挖掘子项目卡片
    - 经营辅助决策
    - Git 版本演进

- [ ] 7.3 启动 FastAPI。
  ```bash
  npm run start:dashboard
  ```
  - 浏览器访问：
    ```text
    http://127.0.0.1:8000
    ```
  - 注意：首次请求会计算用户宽表、关联规则和决策板，可能需要等待；后续请求使用进程缓存。

## 8. 测试与验证

- [ ] 8.1 增加 FastAPI smoke test。
  - 文件：`analytics_dashboard/tests/smoke_test.py`
  - 验证内容：
    - `/health` 可访问。
    - `/api/summary` 返回 KPI 和决策建议。
    - `/api/subprojects` 返回多个数据挖掘子项目。

- [ ] 8.2 执行 smoke test。
  ```bash
  npm run test:dashboard
  ```
  - 验收标准：输出 `FastAPI dashboard smoke test passed`。

- [ ] 8.3 浏览器验收。
  - 检查页面是否展示：
    - GMV、订单数、购买用户、客单价、退款率。
    - 趋势图和漏斗图。
    - 数据挖掘子项目卡片。
    - 经营辅助决策建议。

- [ ] 8.4 提交 FastAPI 服务。
  ```bash
  git add analytics_dashboard package.json scripts/dev.mjs README.md
  git commit -m "Add FastAPI data mining dashboard service"
  ```
  - 如果误提交 `__pycache__`，立即补充 `.gitignore` 并用 `git rm --cached` 移除。

## 9. Docker Compose 部署

- [ ] 9.1 为 Node 商城 API 增加 `server/Dockerfile`。
  - 目标：容器内启动 `server/src/server.js`，暴露 38173 端口。

- [ ] 9.2 为 FastAPI 仪表盘增加 `analytics_dashboard/Dockerfile`。
  - 目标：安装 Python 依赖，启动 Uvicorn，暴露 8000 端口。
  - 关键环境变量：
    ```text
    ESHOP_DB_PATH=/data/eshop.sqlite
    ```

- [ ] 9.3 增加根目录 `docker-compose.yml`。
  - 服务：
    ```text
    mall-api   Node 商城 API
    dashboard  Python/FastAPI 仪表盘
    ```
  - 关键点：`dashboard` 使用只读卷挂载 `./server/data:/data:ro`。

- [ ] 9.4 增加 `.dockerignore`。
  - 排除：`.git/`、`node_modules/`、`dist/`、`__pycache__/`、日志、SQLite 临时文件。

- [ ] 9.5 增加 Ubuntu 部署文档。
  - 文件：`docs/ubuntu-docker-compose-guide.md`
  - 内容：安装 Docker、上传项目、构建启动、查看日志、接口验收、端口冲突处理。

- [ ] 9.6 验证 Compose 配置。
  - 有 Docker 的环境：
    ```bash
    docker compose config
    docker compose up --build -d
    docker compose ps
    ```
  - 无 Docker 的教学机：至少用 YAML 解析验证语法，并在报告中说明未执行镜像构建。

- [ ] 9.7 提交 Docker 部署。
  ```bash
  git add .dockerignore docker-compose.yml server/Dockerfile analytics_dashboard/Dockerfile docs/ubuntu-docker-compose-guide.md README.md
  git commit -m "Add Docker Compose deployment for mixed stack"
  ```

## 10. Git 项目管理演示要求

- [ ] 10.1 查看项目历史。
  ```bash
  git log --oneline --decorate --graph --all
  ```

- [ ] 10.2 建议课堂分支路线。
  ```text
  main
  feature/engineering-baseline
  feature/fastapi-dashboard
  feature/data-mining-subprojects
  feature/docker-compose
  release/classroom-demo
  ```

- [ ] 10.3 建议提交粒度。
  ```text
  Initialize from course e-commerce source
  Add project engineering baseline
  Add FastAPI data access layer
  Add business health analysis subproject
  Add RFM feature engineering subproject
  Add repurchase prediction and ROI analysis
  Add customer clustering strategy board
  Add association rules and sales forecast
  Add marketing attribution decision module
  Add FastAPI dashboard page
  Add Docker Compose deployment for mixed stack
  ```

- [ ] 10.4 打课程验收标签。
  ```bash
  git tag -a v1.0.0-fastapi-dashboard-practice -m "FastAPI dashboard classroom practice release"
  git tag
  ```

## 11. 最终验收清单

- [ ] 11.1 本地 FastAPI 仪表盘可访问：`http://127.0.0.1:8000`。
- [ ] 11.2 `/api/summary` 返回经营 KPI 和辅助决策。
- [ ] 11.3 `/api/subprojects` 返回至少 7 个数据挖掘子项目。
- [ ] 11.4 React 商城前端可构建：`npm run build:mall-web`。
- [ ] 11.5 FastAPI smoke test 通过：`npm run test:dashboard`。
- [ ] 11.6 Git 历史能体现版本演进。
- [ ] 11.7 Docker Compose 文件存在并可在 Ubuntu/Docker 环境执行。
- [ ] 11.8 学生能解释每个数据挖掘子项目的输入、方法、输出和管理含义。
