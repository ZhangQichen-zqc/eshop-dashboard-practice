# Ubuntu Linux Docker Compose 部署指导

## 1. 环境准备

在 Ubuntu 服务器上安装 Docker 与 Compose 插件：

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

将当前用户加入 docker 组后重新登录：

```bash
sudo usermod -aG docker $USER
```

## 2. 上传项目

把 `eshop-dashboard-practice` 上传到服务器，例如：

```bash
scp -r eshop-dashboard-practice user@server:/opt/eshop-dashboard-practice
```

进入目录：

```bash
cd /opt/eshop-dashboard-practice
```

## 3. 构建与启动

```bash
docker compose up --build -d
```

查看状态：

```bash
docker compose ps
docker compose logs -f dashboard
```

## 4. 验收

浏览器访问：

```text
http://服务器IP:8080
```

命令行验证：

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/summary
curl http://127.0.0.1:38173/api/health
```

## 5. 停止与重启

```bash
docker compose down
docker compose up -d
```

## 6. 常见问题

- 端口冲突：修改 `docker-compose.yml` 左侧端口，例如 `"18080:8000"`。
- 首次加载慢：FastAPI 会计算用户宽表、关联规则和决策板，首次请求需要等待，后续请求使用进程缓存。
- 数据库不可读：确认 `server/data/eshop.sqlite` 存在，并且 `dashboard` 服务挂载了 `./server/data:/data:ro`。
