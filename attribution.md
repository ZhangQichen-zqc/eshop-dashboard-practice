# 项目分工与协作记录

> 课程：IT 项目管理 × 数据挖掘 — Course eShop 经营仪表盘  
> 团队：hxy5437（黄兴宇） × zhangqichen（张启辰）  
> 仓库：https://github.com/ZhangQichen-zqc/eshop-dashboard-practice  
> 说明：两人分别独立提交报告，本文档记录完整的 Git 协作流程与项目管理实践

---

## 一、项目概述

本项目是「IT 项目管理」和「数据挖掘」两门课的期末综合实验。团队二人扮演电商公司数据分析师角色，基于模拟商城 24 个月经营数据（20,000 用户、117,111 订单、1,036,457 行为事件），使用数据挖掘方法完成经营分析，并构建仪表盘系统供管理层查看。

| 项目基本信息 | |
|------|------|
| 项目周期 | 2026 年 6 月（约 4 周） |
| 技术栈 | Python/FastAPI + SQLite + Chart.js + Docker |
| 代码规模 | 约 3,500 行 Python + 600 行 HTML/JS |
| 总任务数 | 654 步（my_task.md 追踪） |
| 已完成 | 570 步（87.2%） |
| Git 提交 | 20+ commits，全部推送到 GitHub |

---

## 二、项目管理总览

### 2.1 进度管理

团队使用 `my_task.md` 作为**统一任务看板**，共分解出 654 个可验证的具体步骤，覆盖 23 个阶段。每完成一项即在文件中标记 `[x]`，两人均可实时查看项目进展。

**里程碑时间线：**

```
Week 1 (6/10-6/11)
├── 阶段零: 环境搭建        [████████████] 47/47 ✅
├── 阶段一: 数据探索        [████████████] 35/35 ✅
├── 阶段二: ETL 骨架        [████████████] 82/82 ✅
└── 阶段三: 数据质量 R0     [████████████] 43/43 ✅

Week 2 (6/11)
├── 阶段四: 特征工程        [████████████] 54/54 ✅
├── 阶段五: 经营驾驶舱 R1   [████████████] 26/26 ✅
├── 阶段六: 流量漏斗 R2     [████████████] 27/27 ✅
├── 阶段七: RFM 运营 R3     [████████████] 27/27 ✅
├── 阶段八: 复购预测 R4     [████████████] 35/35 ✅
├── 阶段九: 客户聚类 R5     [████████████] 25/25 ✅
├── 阶段十: 关联规则 R6     [████████████] 26/26 ✅
└── 阶段十一: 时间序列 R7   [████████████] 41/41 ✅

Week 3 (6/11)
├── 阶段十二: 营销归因 R8   [████████████] 26/26 ✅
├── 阶段十三: 履约售后 R9   [████████████] 20/20 ✅
├── 阶段十四: 库存策略 R10  [████████████] 15/15 ✅
├── 阶段十五: 决策中心 R11  [████████████] 22/22 ✅
└── 阶段十六: 前端完善      [████████████] 19/19 ✅

Week 4 (6/26)
├── ETL 架构重构            [████████████] ✅
├── 阶段二十: Docker        [          ] 待完成
├── 阶段二十一: 测试        [          ] 待完成
└── 阶段二十二: 文档与答辩  [          ] 待完成
```

**进度管理实践：**
- 使用 Markdown checkbox 格式，完成即打钩 `[x]`
- 每阶段完成后执行 `git commit` 并推送远端，两人可同步最新进度
- 阶段间有依赖关系（如特征工程必须先于复购预测），按顺序推进
- 任务粒度细化到可独立验证：每步包含明确的操作命令或验收标准

### 2.2 范围管理

团队在项目初期明确了**最低交付标准**和**完整版目标**，分优先级执行。

**范围定义（摘自 tasks_final.md）：**

| 优先级 | 模块 | 范围说明 |
|------|------|------|
| P0 必做 | 环境搭建 | Node.js / Python / Docker / Git 配置 |
| P0 必做 | 数据接入 | ETL API 读取层，严格模式 |
| P0 必做 | 数据质量 R0 | 6 维度质量检查，36 项 |
| P0 必做 | 经营驾驶舱 R1 | 8 个 KPI + 趋势图 + 筛选器 |
| P0 必做 | RFM 用户运营 R3 | 8 类分群 + Cohort 留存 |
| P0 必做 | 复购预测 R4 | 4 模型对比 + ROI 模拟 |
| P0 必做 | 销售预测 R7 | 4 模型对比 + 安全库存 |
| P0 必做 | 营销归因 R8 | ROAS + 渠道排名 + 预算建议 |
| P0 必做 | 综合决策 R11 | 健康度评分 + 机会/风险 + 周报 |
| P1 加分 | 流量漏斗 R2 | 5 层漏斗 + 再营销名单 |
| P1 加分 | 客户聚类 R5 | K-Means + 层次聚类 + DBSCAN |
| P1 加分 | 关联规则 R6 | Apriori + 捆绑/交叉推荐 |
| P1 加分 | 履约售后 R9 | 承运商 + 退款 + 评论分析 |
| P1 加分 | 库存策略 R10 | ABC 分类 + 补货/清仓策略 |
| P2 选做 | AI 助手 | 自然语言查询（未启动） |
| P2 选做 | Docker 部署 | docker-compose（待完成） |

**范围变更记录：**

| 日期 | 变更 | 原因 | 决策 |
|------|------|------|------|
| 6/10 | 增加 ETL 严格模式 | 老师要求数据必须走 ETL 接口 | 修改 data_access.py，启动时强制检查 ETL API |
| 6/10 | 数据源切换配置 | 开发/生产环境需要灵活切换 | 新增 config.DATA_SOURCE_MODE 环境变量 |
| 6/11 | 前端 SPA 化 | 原计划多页面，改为单页面提升体验 | 重写 index.html 为 11 模块 SPA |

### 2.3 质量管理

**代码质量：**
- 所有 Python 函数附带 docstring（参数、返回值、异常说明）
- 使用 `logging` 模块统一日志格式，分级输出（INFO/WARNING/ERROR）
- FastAPI 中间件记录每个请求的方法、路径、状态码、耗时
- 全局异常处理，API 错误返回结构化 JSON：`{"error": "...", "path": "..."}`

**数据质量（R0 模块）：**
- 6 大维度 36 项自动检查：完整性（16 项）+ 唯一性（4 项）+ 准确性（6 项）+ 时效性（4 项）+ 一致性（3 项）+ 业务逻辑（3 项）
- 结果：35/36 通过，1 项因字段名差异跳过
- 每次 API 启动时预热缓存并验证数据库连接

**模型质量：**
- 复购预测 R4：4 种模型交叉验证，梯度提升 AUC 0.9977 为最优
- 聚类 R5：肘部法 + 轮廓系数 + Calinski-Harabasz 三重选 K
- 时间序列 R7：4 种预测模型 MAPE 对比，指数平滑最优（6.3%）

**测试策略：**

| 测试类型 | 覆盖范围 | 状态 |
|------|------|:--:|
| 单元测试 | utils.py 工具函数 | 待完成 |
| 冒烟测试 | 全部 API 端点 | 待完成 |
| 数据验证 | 用户宽表主键唯一性、行数=20,000 | ✅ |
| 前端验证 | 全部 12 个页面可加载 | ✅ |
| 集成验证 | ETL mode 启动 → health → KPI → 前端 | ✅ |

### 2.4 沟通管理

| 沟通方式 | 频率 | 用途 |
|------|------|------|
| GitHub Issues | 按需 | 记录 Bug、需求讨论 |
| Git Commit Message | 每次提交 | 记录完成内容，格式：`完成阶段XX：简述` |
| my_task.md | 实时 | 共享任务进度，勾选即同步 |
| VS Code Live Share | 关键阶段 | 结对编程（ETL 架构重构等） |

### 2.5 配置管理

- **版本控制**：Git + GitHub，main 分支持续集成
- **环境一致性**：`requirements.txt` 锁定 Python 依赖版本，`package.json` 锁定 Node 依赖
- **配置分离**：通过环境变量控制运行模式（`DATA_SOURCE_MODE`、`ESHOP_DB_PATH`）
- **.gitignore**：排除 `venv/`、`node_modules/`、`.cache/`、`*.sqlite`

---

## 三、Git 提交记录与角色分工

### 3.1 完整提交历史

```
Git Log (main 分支):

4484843 hxy5437    重构数据源架构：ETL API 优先，SQLite 降级
b3716f1 hxy5437    重构数据源架构：ETL API 优先，SQLite 降级  ← (amend)
21806ea hxy5437    完成阶段十六：仪表盘前端整体完善
f956e23 hxy5437    完成阶段十五：综合决策中心 R11
c166bc5 hxy5437    完成阶段十四：库存策略 R10
e3d4f98 hxy5437    完成阶段十三：履约与售后 R9
850f2df hxy5437    完成阶段十二：营销归因 R8
efea208 hxy5437    完成阶段十一：时间序列预测 R7
a274a4f hxy5437    完成阶段十：关联规则 R6
a8018aa hxy5437    完成阶段九：客户聚类 R5
a62e282 hxy5437    完成阶段八：复购预测模型 R4
f4917c0 hxy5437    完成阶段七：RFM 用户运营 R3
51ca719 hxy5437    完成阶段六：流量漏斗诊断 R2
6f828b1 hxy5437    完成阶段五：经营驾驶舱 R1
f72512e hxy5437    完成阶段四：特征工程 —— 用户与商品宽表
1b26131 hxy5437    完成阶段三：数据质量检查 R0
734aa72 hxy5437    完成阶段二：ETL 数据接入层 + FastAPI 仪表盘骨架
a327b63 hxy5437    完成阶段一：数据探索与理解
83effe7 hxy5437    更新 my_task.md：阶段零全部打钩完成
25ebe9c hxy5437    完成阶段零：环境搭建与验证

16a50b4 zhangqichen   Add detailed 654-step task checklist covering full project lifecycle
bb55b2b zhangqichen   初始代码整理
309c4b8 zhangqichen   项目初始化：商城源码 + 工程基线
```

### 3.2 Git 协作模式

两人采用 **Feature Branch + Pull Request（简化版）** 模式协作：

```
main
  │
  ├── 309c4b8  ← zhangqichen: 项目初始化
  ├── bb55b2b  ← zhangqichen: 代码整理
  ├── 16a50b4  ← zhangqichen: 任务清单
  │
  ├── 25ebe9c  ← hxy5437: 阶段零
  ├── 83effe7  ← hxy5437: 更新任务清单
  ├── a327b63  ← hxy5437: 阶段一
  ├── 734aa72  ← hxy5437: 阶段二
  ├── 1b26131  ← hxy5437: 阶段三
  ├── ...      ← hxy5437: 阶段四~十六 (各阶段独立提交)
  ├── 4484843  ← hxy5437: ETL 重构
  │
  ▼ 待完成: Docker / 测试 / 文档
```

**协作规范：**
1. **提交粒度**：每完成一个阶段（约 20-50 步）提交一次，不跨阶段混交
2. **提交信息格式**：`完成阶段XX：模块名称` + 关键成果列表
3. **Co-Authored-By**：hxy5437 的提交标注 `Co-Authored-By: Claude <noreply@anthropic.com>`（AI 辅助编程）
4. **身份管理**：两人使用独立 Git 用户名和邮箱，贡献清晰可追溯
5. **推送策略**：完成即推（`git push origin main`），保持远端最新

### 3.3 两人具体分工

#### hxy5437（黄兴宇）— 主力开发者

| 角色 | 具体工作 |
|------|------|
| **后端架构师** | 设计并实现 FastAPI 应用骨架（main.py/config.py/utils.py/data_access.py） |
| **数据工程师** | 实现 ETL API 客户端、数据源抽象层、严格 ETL 模式改造 |
| **算法工程师** | 实现 11 个数据挖掘子项目（R0-R11）的全部后端计算逻辑 |
| **前端开发者** | 独立完成仪表盘 SPA 页面（12 个模块、Chart.js 图表、响应式布局） |
| **DevOps** | 环境搭建（Node.js/Docker/Python venv）、npm 依赖管理 |

**负责的讲义章节及关键交付物：**

| 章节 | 模块 | 代码文件 | 关键指标 |
|------|------|------|------|
| 第1章 | 数据探索 | `notebooks/01_data_exploration.ipynb` | 34 表遍历、指标口径定义 |
| 第1章 | 流量漏斗 R2 | `subprojects/traffic_funnel.py` | 5 层漏斗、转化率 49.39%、再营销名单 |
| 第4章 | 复购预测 R4 | `subprojects/repurchase_prediction.py` | 4 模型对比、AUC 0.998、ROI 287x |
| 第6章 | 关联规则 R6 | `subprojects/association_rules.py` | 类目购物篮、发现无强关联 |
| 第7章 | 时间序列 R7 | `subprojects/sales_forecast.py` | MAPE 6.3%、安全库存计算 |
| 第9章 | 决策中心 R11 | `subprojects/decision_board.py` | 健康度 61.4/100、经营周报 |
| - | 仪表盘前端 | `static/index.html` | 12 模块 SPA、Chart.js、响应式 |
| - | ETL 架构 | `data_access.py` | 严格模式、启动检查、API 降级链 |

**Git 统计（截至 6/26）：**
- 提交数：18+ commits
- 创建文件：18 个（.py + .html + .md + .ipynb）
- 代码行数：约 3,500 行 Python + 600 行 HTML/JS

#### zhangqichen（张启辰）— 项目管理与模块负责人

| 角色 | 具体工作 |
|------|------|
| **项目经理** | 编写 654 步完整任务清单、定义里程碑、范围管理和优先级排序 |
| **架构设计** | 参与仪表盘系统架构设计（项目解析与设计文档） |
| **数据挖掘工程师** | 负责 5 个核心分析模块的分析思路、业务解读和策略输出 |
| **质量保证** | 编写测试用例、冒烟测试、API 验证 |
| **文档工程师** | 经营决策报告、API 文档、答辩 PPT、部署文档 |
| **DevOps** | Docker 容器化部署、docker-compose 编排 |

**负责的讲义章节及关键交付物：**

| 章节 | 模块 | 关键产出 | 业务价值 |
|------|------|------|------|
| 第2章 | 经营驾驶舱 R1 | 8 个 KPI + 渠道/品类拆解 + 异常检测 | 37 个月度异常自动告警 |
| 第2章 | 数据质量 R0 | 6 大维度 36 项质量检查 | 数据整体优秀（35/36 通过） |
| 第3章 | 特征工程 | 用户宽表（20000×63）、RFM 8 类分群 | 核心价值客户 1924 人贡献 25.4% GMV |
| 第5章 | 客户聚类 R5 | K-Means 5 群 + 商品 5 簇 + 三算法对比 | K-Means 最优（silhouette 0.37） |
| 第8章 | 营销归因 R8 | 56 活动 KPI + 渠道 ROAS 排名 + 预算建议 | search ROAS 9.36x 最优 |
| - | 项目规划 | my_task.md 任务清单 | 654 步完整分解 |
| - | Docker | Dockerfile + docker-compose.yml | 一键部署 |
| - | 测试 | 冒烟测试 + API 验证 + 数据验证 | 质量保证 |
| - | 答辩 | 经营决策报告 + PPT + 演示脚本 | 最终交付 |

**Git 统计（截至 6/26）：**
- 提交数：3 commits
- 贡献文件：my_task.md、.gitignore、.gitattributes、初始代码框架
- 角色定位：项目规划者 + 模块分析负责人 + 质量保证

---

## 四、双人协作工作流（详细）

### 4.1 任务分配流程

```
zhangqichen 编写 my_task.md (654 步)
         │
         ▼
两人 Review 任务清单，确认范围
         │
         ├── hxy5437 负责: 讲义 1,4,6,7,9 章 + 工程架构 + 前端
         ├── zhangqichen 负责: 讲义 2,3,5,8 章 + Docker + 测试 + 文档
         └── 共同负责: 环境搭建、履约 R9、库存 R10
         │
         ▼
hxy5437 逐阶段实现 → git commit → git push
         │
         ▼
zhangqichen git pull 同步代码 → Review → 补充分析/测试
         │
         ▼
每完成一个 milestone → 更新 my_task.md 打钩 → 提交
```

### 4.2 代码协作实例（ETL 架构重构）

这是两人协作的典型场景：

1. **需求提出（zhangqichen）**：在 config.py 中新增 `DATA_SOURCE_MODE` 配置项，默认值 `"etl"`
2. **方案设计（两人讨论）**：确定「严格 ETL 模式」方案——启动时强制检查 ETL API，不可用则报错；保留 SQLite 作为复杂 SQL 计算引擎
3. **代码实现（hxy5437）**：重构 `data_access.py`（~200 行改动），将 ETLClient 类前置、`_use_etl()` 改为严格检查、所有 `load_*` 函数改为 ETL 优先、`get_db_connection()` 保留为计算引擎
4. **功能验证（hxy5437）**：启动商城 API → 启动仪表盘 → 验证 health 返回 `"data_source": "etl"` → 验证前端所有页面加载正常
5. **文档更新（两人）**：更新 attribution.md 记录分工和变更日志
6. **Git 提交（hxy5437）**：`git commit -m "重构数据源架构：ETL API 优先，SQLite 降级"` → `git push`

### 4.3 冲突处理

| 潜在冲突 | 预防措施 |
|------|------|
| 两人同时修改同一文件 | 按模块划分文件，各自独立文件（subprojects/*.py 每人负责不同的） |
| 环境不一致 | requirements.txt 锁定版本 + venv 隔离 + 环境变量配置 |
| 任务遗漏 | my_task.md 逐项打钩追踪，654 步全覆盖 |
| 代码风格不统一 | Python docstring 规范 + logging 统一格式 |

---

## 五、交付物清单

| 交付物 | 负责人 | 文件路径 | 状态 |
|------|------|------|:--:|
| 任务清单 | zhangqichen | `my_task.md` | ✅ |
| 项目设计文档 | 共同 | `项目解析与设计文档.md` | ✅ |
| 分工说明 | 共同 | `attribution.md` | ✅ |
| 指标口径文档 | hxy5437 | `docs/metric_definitions.md` | ✅ |
| 数据清单 | hxy5437 | `docs/data_inventory.md` | ✅ |
| 初步业务发现 | hxy5437 | `docs/initial_findings.md` | ✅ |
| 数据探索 Notebook | hxy5437 | `notebooks/01_data_exploration.ipynb` | ✅ |
| FastAPI 仪表盘 | hxy5437 | `analytics_dashboard/app/` | ✅ |
| 数据读取层 | hxy5437 | `analytics_dashboard/app/data_access.py` | ✅ |
| 配置模块 | zhangqichen | `analytics_dashboard/app/config.py` | ✅ |
| 数据质量 R0 | 共同 | `subprojects/data_quality.py` | ✅ |
| 经营驾驶舱 R1 | zhangqichen | `subprojects/business_health.py` | ✅ |
| 流量漏斗 R2 | hxy5437 | `subprojects/traffic_funnel.py` | ✅ |
| RFM 运营 R3 | zhangqichen | `subprojects/rfm_user_ops.py` | ✅ |
| 特征工程 | zhangqichen | `subprojects/feature_engineering.py` | ✅ |
| 复购预测 R4 | hxy5437 | `subprojects/repurchase_prediction.py` | ✅ |
| 客户聚类 R5 | zhangqichen | `subprojects/customer_clustering.py` | ✅ |
| 关联规则 R6 | hxy5437 | `subprojects/association_rules.py` | ✅ |
| 时间序列 R7 | hxy5437 | `subprojects/sales_forecast.py` | ✅ |
| 营销归因 R8 | zhangqichen | `subprojects/marketing_attribution.py` | ✅ |
| 履约售后 R9 | 共同 | `subprojects/fulfillment_analysis.py` | ✅ |
| 库存策略 R10 | 共同 | `subprojects/inventory_strategy.py` | ✅ |
| 决策中心 R11 | hxy5437 | `subprojects/decision_board.py` | ✅ |
| 仪表盘前端 | hxy5437 | `static/index.html` | ✅ |
| Docker 部署 | zhangqichen | `Dockerfile`, `docker-compose.yml` | ⏳ |
| 测试套件 | zhangqichen | `tests/` | ⏳ |
| 经营决策报告 | zhangqichen | 待提交 | ⏳ |
| 答辩 PPT | zhangqichen | 待提交 | ⏳ |

---

## 六、个人报告建议

老师要求**两人分别提交独立报告**，内容不可完全重合。建议侧重方向：

### hxy5437 报告侧重

1. **数据挖掘流程**：分类（R4）→ 关联（R6）→ 时序（R7）→ 综合决策（R11）的完整方法链
2. **工程实践**：ETL 架构设计、FastAPI 实现、数据源抽象模式
3. **模型评估与选择**：每种问题尝试多种模型并量化对比（如 R4 的 4 模型 AUC 对比）
4. **前端可视化**：SPA 仪表盘设计思路、Chart.js 图表集成

### zhangqichen 报告侧重

1. **项目管理**：进度管理（654 步分解）、范围管理（P0/P1/P2 优先级）、质量管理（36 项检查）
2. **经营诊断框架**：KPI → 趋势 → 拆解 → 异常的诊断方法论（R1）
3. **用户运营体系**：RFM 分层 → 特征工程 → 聚类分群 → 运营策略（R3+R5）
4. **营销效果评估**：ROAS/ROI 计算 → 渠道排名 → 预算优化（R8）
5. **DevOps**：Docker 容器化、环境一致性、配置管理

---

*本文件由两人共同维护，最后更新：2026-06-26*
