# 商城仪表盘与经营辅助决策实践项目

本项目用于 IT 项目管理实践课。学生从商城源码开始，完成本地开发环境、Git 项目管理、仪表盘开发、经营辅助决策板块和 Docker Compose 部署。

## 技术栈

- 商城源码：Node.js + Express + SQLite，React + Vite
- 仪表盘：Python + FastAPI
- 数据挖掘子项目：经营健康诊断、RFM、复购预测、客户分群、关联规则、销售预测、营销归因
- 数据：商城业务库、ETL 只读接口、课程导出 CSV
- 部署：Docker Compose，目标环境为 Ubuntu Linux

## 本地开发

```bash
npm run install:all
npm run dev
```

访问：

```text
FastAPI 仪表盘：http://127.0.0.1:8000
商城 API：http://127.0.0.1:38173/api/health
商城原前端：http://127.0.0.1:39174
```

## 验证

```bash
npm run verify
npm run start:dashboard
npm run test:dashboard
```

## Docker Compose 部署

```bash
docker compose up --build -d
docker compose ps
```

访问：

```text
http://localhost:8080
```

详细 Ubuntu 部署步骤见 [docs/ubuntu-docker-compose-guide.md](docs/ubuntu-docker-compose-guide.md)。

## 课堂交付要求

- `git log --oneline --decorate --graph --all` 能体现功能演进。
- 至少包含环境搭建、后端 API、前端仪表盘、Docker 部署四类提交。
- `npm run verify` 通过。
- `docker compose up --build` 能在 Ubuntu Linux 环境部署。
- 能解释仪表盘中每个经营指标对应的数据挖掘或商业决策知识点。
