# 商城仪表盘与经营辅助决策板块开发任务

项目目录：`Project/eshop-dashboard-practice`

说明：本任务清单记录实际执行过程。最终课堂演示版会根据实际完成路径整理为 `Project/tasks_final.md`。

## 阶段 0：复制源码与建立 Git 基线

- [x] 0.1 确认根目录已有商城源码：`client/`、`server/`、`docs/`、`exports/`。
- [x] 0.2 确认可参考的数据挖掘教学资料：`Data_Mining_Management_Decision_Course_20260228`、`Data_Mining_management_Decision_Course_V2`、`Data_Mining_management_Decision_Course_V3`。
- [x] 0.3 在 `Project/` 下创建新实践项目目录 `eshop-dashboard-practice`。
- [x] 0.4 复制商城源码到新项目：保留 Node 商城 API、React 商城前端、文档、导出数据。
- [x] 0.5 清理复制出的 `node_modules/`、`dist/`、SQLite 临时文件和数据库备份，避免污染教学仓库。
- [x] 0.6 初始化 Git 仓库，配置仓库级教学身份。
- [x] 0.7 提交源码基线：`Initialize from course e-commerce source`。

## 阶段 1：工程化与本地环境

- [x] 1.1 增加根目录 `.gitignore`，排除依赖、构建产物、日志、SQLite 运行临时文件。
- [x] 1.2 增加 `.gitattributes`，规范文本换行和二进制文件处理。
- [x] 1.3 增加根目录 `package.json`，统一 Node 商城服务与前端构建命令。
- [x] 1.4 增加根目录 `README.md`，说明课程目标、本地运行、验证和 Docker 部署方式。
- [x] 1.5 增加 `scripts/dev.mjs`，支持一条命令同时启动 Node API 与 React 前端。
- [x] 1.6 提交工程基线：`Add project engineering baseline`。
- [x] 1.7 安装 Node 商城 API 与 React 商城前端依赖，确认 lockfile 状态。
- [x] 1.8 增加 Python/FastAPI 依赖文件，建立 Python 数据挖掘服务运行环境。

## 阶段 2：FastAPI 数据挖掘子项目架构

- [x] 2.1 新建 `analytics_dashboard/`，作为 Python/FastAPI 仪表盘与决策服务。
- [x] 2.2 增加 FastAPI 应用入口 `app/main.py`。
- [x] 2.3 增加 SQLite 数据读取层，统一读取商城业务库。
- [x] 2.4 增加分析公共工具：金额格式、百分比、时间窗口、TopN、缺失值处理。
- [x] 2.5 按数据挖掘知识点建立子项目目录：
  - [x] 2.5.1 `business_health`：经营健康诊断。
  - [x] 2.5.2 `feature_engineering`：RFM 与用户宽表。
  - [x] 2.5.3 `repurchase_prediction`：复购预测与触达名单。
  - [x] 2.5.4 `customer_clustering`：客户分群。
  - [x] 2.5.5 `association_rules`：商品关联规则。
  - [x] 2.5.6 `sales_forecast`：销售预测与库存备货。
  - [x] 2.5.7 `marketing_attribution`：营销归因与预算建议。
  - [x] 2.5.8 `decision_board`：经营辅助决策汇总。

## 阶段 3：实现各数据挖掘子项目

- [x] 3.1 实现经营总览指标：GMV、订单数、购买用户、客单价、退款率。
- [x] 3.2 实现经营健康诊断：月度趋势、渠道贡献、转化漏斗。
- [x] 3.3 实现 RFM 与用户宽表：recency、frequency、monetary、渠道与会员字段。
- [x] 3.4 实现复购预测教学版：使用可解释评分模型输出高潜用户与触达 ROI。
- [x] 3.5 实现客户分群教学版：基于 RFM 的规则分群或轻量 K-Means。
- [x] 3.6 实现商品关联规则：支持度、置信度、提升度、组合销售建议。
- [x] 3.7 实现销售预测：移动平均、波动系数、安全库存金额。
- [x] 3.8 实现营销归因：渠道 GMV、广告花费、CPA、ROAS、预算动作建议。
- [x] 3.9 实现综合决策板：把前述分析转化为经营动作和课堂解释。

## 阶段 4：FastAPI 仪表盘页面与 API

- [x] 4.1 暴露 JSON API：`/api/summary`、`/api/subprojects`、`/api/decision-board`。
- [x] 4.2 使用 FastAPI 静态文件服务提供仪表盘页面。
- [x] 4.3 实现仪表盘首页：KPI、趋势、漏斗、渠道、决策建议。
- [x] 4.4 实现子项目页或卡片：每个数据挖掘子项目展示输入、方法、输出、管理含义。
- [x] 4.5 增加课堂项目管理板块：Git 分支路线、提交规范、验收命令、Docker 部署步骤。

## 阶段 5：验证、测试与 Git 管理

- [x] 5.1 增加 FastAPI smoke test，验证 API 与页面可访问。
- [x] 5.2 启动 FastAPI 服务并验证 `/health`、`/api/summary`、首页。
- [x] 5.3 构建 React 商城前端，确认原商城源码仍可构建。
- [x] 5.4 提交 FastAPI 数据挖掘服务。
- [x] 5.5 提交仪表盘页面与课堂项目管理板块。

## 阶段 6：Docker Compose 与 Ubuntu Linux 部署

- [x] 6.1 为 Node 商城 API 增加 Dockerfile。
- [x] 6.2 为 FastAPI 仪表盘增加 Dockerfile。
- [x] 6.3 增加根目录 `docker-compose.yml`，编排 `mall-api` 与 `dashboard`。
- [x] 6.4 配置卷挂载或镜像复制，使 FastAPI 能读取商城 SQLite 数据库。
- [x] 6.5 增加 Ubuntu 部署说明：安装 Docker、启动、查看日志、验收接口。
- [x] 6.6 本机无 Docker CLI，已用 Python 解析 `docker-compose.yml` 完成语法级验证；镜像构建需在 Ubuntu/Docker 环境执行。

## 阶段 7：倒推课堂演示版任务

- [x] 7.1 根据实际执行路径整理 `tasks_final.md`。
- [x] 7.2 每一步补充教师演示说明、学生跟做命令、验收标准、常见问题。
- [x] 7.3 标记建议 Git 提交点、分支名和课堂里程碑。
- [x] 7.4 形成最终 Git tag：`v1.0.0-fastapi-dashboard-practice`。
