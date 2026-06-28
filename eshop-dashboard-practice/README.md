# 商城经营仪表盘与数据挖掘综合实践

> **课程**：IT 项目管理 × 数据挖掘  
> **团队**：胡熙媛 × 张琪琛  
> **提交日期**：2026 年 6 月

---

## 一、项目简介

本项目基于模拟电商 24 个月经营数据（20,000 用户、117,111 订单、1,036,457 行为事件），完成从数据理解、特征工程到数据挖掘建模、经营决策辅助的全流程实践，最终构建一个 B/S 架构的交互式经营仪表盘系统。

### 关键数字

| 维度 | 数据 |
|------|------|
| GMV | ¥1.56 亿 |
| 订单量 | 108,043 单 |
| 买家数 | 18,118 人 |
| 数据库 | 34 张表，251 MB（SQLite） |
| 数据挖掘模块 | 12 个（R0~R11） |
| Git 提交 | 30+ commits |
| 代码规模 | ~8,500 行（Python 6,000 + JS/HTML 2,500） |

---

## 二、项目文件结构

```
eshop-dashboard-practice/
├── README.md                          ← 本文件（使用说明）
├── docker-compose.yml                 ← Docker 编排（一键部署）
├── .dockerignore                      ← Docker 构建排除规则
├── package.json                       ← 统管脚本
│
├── server/                            ← 商城后端（Node.js + Express）
│   ├── Dockerfile                     ← 商城 API 容器化
│   ├── src/server.js                  ← 733 行，含 /api/etl/* 只读接口
│   ├── src/db.js                      ← 数据库初始化
│   ├── src/seed.js                    ← 数据填充脚本
│   └── data/eshop.sqlite              ← 商城业务数据库（251 MB）
│
├── analytics_dashboard/               ← 仪表盘后端（Python + FastAPI）
│   ├── Dockerfile                     ← 仪表盘容器化
│   ├── requirements.txt               ← Python 依赖
│   ├── app/
│   │   ├── main.py                    ← 993 行，50+ 个 API 端点
│   │   ├── config.py                  ← 配置（数据源模式切换）
│   │   ├── data_access.py             ← 555 行，ETL API / SQLite / CSV 三层数据源
│   │   ├── utils.py                   ← 工具函数
│   │   └── subprojects/               ← 12 个数据挖掘子项目
│   │       ├── data_quality.py            ← R0：6 维度 36 项数据质量检查
│   │       ├── business_health.py         ← R1：经营驾驶舱（KPI+趋势+异常）
│   │       ├── traffic_funnel.py          ← R2：5 层流量漏斗诊断
│   │       ├── rfm_user_ops.py            ← R3：RFM 用户分群运营
│   │       ├── feature_engineering.py     ← 用户/商品宽表构建（20,000×63）
│   │       ├── repurchase_prediction.py    ← R4：复购预测（AUC=0.998）
│   │       ├── customer_clustering.py     ← R5：K-Means 客户聚类
│   │       ├── association_rules.py       ← R6：Apriori 关联规则
│   │       ├── sales_forecast.py          ← R7：时间序列预测
│   │       ├── marketing_attribution.py    ← R8：营销 ROAS 归因
│   │       ├── fulfillment_analysis.py    ← R9：履约与售后分析
│   │       ├── inventory_strategy.py      ← R10：ABC 库存策略
│   │       └── decision_board.py          ← R11：综合决策中心
│   ├── static/index.html              ← 仪表盘前端 SPA（1,200+ 行）
│   └── tests/                         ← 测试文件
│
├── client/                            ← 商城 React 前端（Vite）
├── docs/                              ← 教学文档
├── exports/                           ← CSV 数据导出
└── notebooks/                         ← Jupyter 数据探索
```

---

## 三、老师验收方式

### 方式 A：Docker 一键部署（推荐，最快）

**前提**：电脑已安装 Docker（Ubuntu 参考下方安装命令，Windows/Mac 安装 Docker Desktop）

```bash
# 1. 解压提交的 zip 文件，进入目录
cd eshop-dashboard-practice

# 2. 一键构建并启动（首次约 3-5 分钟，之后秒启）
docker compose up -d --build

# 3. 等待 "healthy" 状态
docker compose ps
# 看到 eshop-mall-api (healthy) + eshop-dashboard (healthy) 即成功

# 4. 浏览器打开仪表盘
# http://localhost:8000/static/index.html
```

**Docker 安装（Ubuntu）**：
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER  # 重新登录生效
```

### 方式 B：本地开发运行

**前提**：已安装 Node.js 20+ 和 Python 3.12+

```bash
cd eshop-dashboard-practice

# 1. 安装依赖
npm run install:all

# 2. 启动 ETL API（终端1，保持运行）
npm run start:mall-api
# → 监听 http://localhost:38173

# 3. 启动仪表盘（终端2，保持运行）
npm run start:dashboard
# → 监听 http://localhost:8000

# 4. 浏览器打开
# http://localhost:8000/static/index.html
```

### 验收清单

| 验收项 | 操作 | 预期结果 |
|------|------|------|
| ETL API 可用 | `curl http://localhost:38173/api/health` | `{"ok":true}` |
| 仪表盘 API 可用 | `curl http://localhost:8000/health` | `{"ok":true,"data_source":"etl"}` |
| 核心指标正确 | `curl http://localhost:8000/api/summary` | GMV=156027298.84，订单=108043 |
| 仪表盘前端 | 浏览器打开 8000 端口 | 14 个页面可切换，数据正常 |
| Swagger 文档 | 浏览器打开 `/docs` | 50+ 个 API 可交互测试 |
| 子项目列表 | `curl http://localhost:8000/api/subprojects` | 12 个子项目全部 completed |

---

## 四、仪表盘功能导航

打开前端后，左侧有 **14 个入口**，分 3 组：

### 核心仪表盘
| 页面 | 说明 |
|------|------|
| 🏠 经营总览 | 6 个核心 KPI + GMV 趋势 + 品类贡献 + 决策信号 |
| 🔻 漏斗诊断 R2 | 5 层 CSS 梯形漏斗 + 设备热力图 + 渠道切片 + 再营销名单 |
| 👥 客户分析 R3/R5 | RFM 8 层分群 + Cohort 留存 + K-Means 聚类 + 用户搜索 |
| 🛒 商品与购物篮 R6 | Apriori 关联规则 + 捆绑推荐 + 单品推荐引擎 |
| 📈 预测与库存 R7/R10 | GMV 时间序列预测 + 安全库存 + ABC 分类 + 补货建议 |
| 📢 营销归因 R8 | 渠道 ROAS 排名 + 优惠券分析 + 预算优化建议 |

### 数据挖掘模块
| 页面 | 说明 |
|------|------|
| ✅ 数据质量 R0 | 6 维度质量检查清单 + 通过/警告/失败分布 |
| 📊 经营驾驶舱 R1 | 完整 KPI 面板 + 月度趋势 + 品类排名 + 异常告警 |
| 🤖 复购预测 R4 | 4 模型对比（AUC 0.898~0.998）+ 特征重要性 |
| 🚚 履约售后 R9 | 承运商延迟率 + 退款分析 + 评论舆情 + 风险清单 |

### 综合工具
| 页面 | 说明 |
|------|------|
| 🎯 综合决策 R11 | 健康度雷达图 + 机会/风险/动作清单 + PDF 周报导出 |
| 🤖 AI 分析助手 | 接入 DeepSeek/GPT，输入 API Key 后智能分析 |
| ⚙️ 系统配置 | 数据源模式、API 文档、缓存管理 |

---

## 五、技术架构

```
用户浏览器
    │
    ▼
┌─────────────────────────────┐
│  FastAPI 仪表盘 (8000)       │
│  • 前端 SPA (Chart.js)       │
│  • 12 个分析子项目 API        │
│  • 数据源: ETL API 优先       │
└──────────┬──────────────────┘
           │ HTTP
           ▼
┌─────────────────────────────┐
│  Node.js ETL API (38173)     │
│  • 34 张表只读查询            │
│  • 数据质量检查               │
│  • 核心指标口径               │
└──────────┬──────────────────┘
           │ SQLite
           ▼
┌─────────────────────────────┐
│  eshop.sqlite (251 MB)       │
│  20,000 用户 × 117,111 订单   │
│  1,036,457 行为事件           │
└─────────────────────────────┘
```

---

## 六、Git 提交历史（完整演进过程）

```
aa0e027  Docker部署完成：2容器健康运行+ETL链路验证
39a6865  Docker构建修复：添加npm/pip国内镜像加速
cdc3871  Docker部署：docker-compose.yml+FastAPI Dockerfile
042caa0  加载动画升级：纯SVG循环动画(仪表盘窗口+柱状图+漏斗+粒子轨道)
df4e492  全面修复：SVG加载动画+PDF导出+8处空白修复+AI间距+捆绑丰富
6fb8ca4  关键修复：加载动画+空数据保护+null安全+商品页重写
e3f8e57  性能革命：启动预加载28个API+AI设置UI重做+零等待翻页
d905432  紧急修复：导航点击bug+14区域扩展+渐进渲染+4个新页面
8cb539c  前端改造完成：14次迭代，旧395行→新1011行+72KB
953370a  动画抛光：fadeIn+scaleIn入场动画+交错延迟
eb31b27  响应式完善：768/640断点+侧栏阴影+移动端适配
2d7f9a4  性能优化：50ms防抖导航+渐进式渲染+GPU加速
57c6dd4  系统配置增强：3列布局+快捷键参考+API文档
4d06740  AI助手增强+用户搜索：快捷提问+模型配置
c48af06  综合诊断重做：雷达图+健康度大盘
93d340f  营销归因增强：ROAS气泡图+活动KPI
dd109ba  预测库存增强：补货建议+模型MAPE
4001bbe  商品购物篮增强：Lift分布+强关联筛选
3e1f02b  客户分析增强：散点图+RFM渐变卡片
34de341  漏斗诊断深度重做：梯形CSS漏斗+热力图
541f9f7  首页经营总览增强：渐变KPI+品类贡献
05d4922  前端全面重构 v1：性能框架+亮色设计+9页面
4484843  重构数据源架构：ETL API优先，SQLite降级
```

---

## 七、交付物打包清单

发给老师的 zip 包应包含以下内容（**不要包含** `node_modules/`、`venv/`、`.git/`）：

```
eshop-dashboard-practice.zip
├── README.md                    ← 本使用说明
├── docker-compose.yml           ← Docker 部署配置
├── .dockerignore
├── package.json
├── server/
│   ├── Dockerfile
│   ├── src/
│   ├── data/eshop.sqlite        ← 数据库（必需！251 MB）
│   └── package.json
├── analytics_dashboard/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── data_access.py
│   │   ├── utils.py
│   │   └── subprojects/         ← 12 个分析模块
│   ├── static/index.html        ← 仪表盘前端
│   └── tests/
├── docs/                        ← 教学文档
├── exports/                     ← CSV 导出数据
└── notebooks/                   ← Jupyter 探索
```

**打包命令**（在项目根目录执行）：
```bash
zip -r eshop-dashboard-practice.zip . \
  -x "node_modules/*" "venv/*" ".git/*" "dist/*" \
  "__pycache__/*" "*.pyc" "*.sqlite-shm" "*.sqlite-wal" \
  ".cache/*" "client/node_modules/*"
```

---

## 八、常见问题

**Q: 仪表盘打开很慢？**  
A: 首次需要预加载 28 个 API（约 30 秒），之后页面切换瞬间完成。加载动画会显示进度。

**Q: ETL API 连不上？**  
A: 确保先启动 mall-api（38173 端口），再启动 dashboard。

**Q: AI 助手怎么用？**  
A: 前往 AI 分析助手页面 → 填入模型名称（如 `deepseek-chat`）+ API Key + Base URL → 保存 → 点击快捷提问或输入问题。

**Q: 数据能导出吗？**  
A: 综合诊断页面 → 点击「下载经营周报 PDF」→ 浏览器打印对话框 → 保存为 PDF。

---

> **项目仓库**：https://github.com/ZhangQichen-zqc/eshop-dashboard-practice  
