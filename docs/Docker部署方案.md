# Docker 部署方案

> 将 Self Grow 个人成长系统一键部署到云服务器

## 架构

```
用户浏览器
     │
     ▼
 云服务器 :3001
     │
 ┌───┴───────────────────────────┐
 │   Docker 容器                  │
 │   ┌──────────────────────────┐ │
 │   │  FastAPI main.py         │ │
 │   │  serve API + 前端静态文件 │ │
 │   ├──────────────────────────┤ │
 │   │  Volumes (持久化)         │ │
 │   │  - /data/data.db         │ │
 │   │  - /data/uploads/        │ │
 │   └──────────────────────────┘ │
 └───────────────────────────────┘
```

## 文件清单

把以下 3 个文件放到项目**根目录**（与 `.gitignore` 同级）：

| 文件 | 说明 |
|------|------|
| `Dockerfile` | 镜像构建说明 |
| `.dockerignore` | 排除无需进镜像的文件 |
| `docker-compose.yml` | 服务编排 |

## 一、Dockerfile

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# backend/pixi.lock 仅作环境声明参考；实际安装走 requirements.txt
# （requirements.txt 由 `pixi run export-reqs` 从 pixi 锁定版本生成，与开发环境完全一致）
COPY backend/requirements.txt ./backend/requirements.txt

# 安装 Python 依赖（版本与 pixi 开发环境一致）
RUN pip install --no-cache-dir -r backend/requirements.txt

# 复制全部项目代码（.dockerignore 会排除不需要的）
COPY . .

# 后端代码目录
WORKDIR /app/backend

# 环境变量
ENV PORT=3001
ENV SELF_GROW_FRONTEND_DIR=/app/frontend
ENV SELF_GROW_PACKAGED=0

# 暴露端口
EXPOSE 3001

# 启动
CMD ["python", "main.py"]
```

## 二、.dockerignore

```gitignore
# .dockerignore
.git/
.gitignore
__pycache__/
*.pyc
.pixi/
backend/.pixi/
backend/__pycache__/
backend/data.db
backend/uploads/*
backend/.env
backend/tests/
backend/pixi.lock
node_modules/
*.log
*.bak
```

## 三、docker-compose.yml

```yaml
# docker-compose.yml
services:
  self-grow:
    build: .
    ports:
      - "3001:3001"
    environment:
      - AI_API_BASE_URL=${AI_API_BASE_URL:-https://api.sfkey.cn/v1}
      - AI_API_KEY=${AI_API_KEY}
      - AI_MODEL=${AI_MODEL:-glm-5.2}
      - PORT=3001
      - SELF_GROW_FRONTEND_DIR=/app/frontend
    volumes:
      - self-grow-data:/data
      - self-grow-uploads:/app/backend/uploads
    restart: unless-stopped

volumes:
  self-grow-data:
  self-grow-uploads:
```

## 四、云服务器部署步骤

### 4.1 安装 Docker

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 退出终端重新登录，或执行: newgrp docker

# 验证
docker --version
docker compose version
```

### 4.2 克隆代码

```bash
git clone <你的仓库地址> self-grow
cd self-grow
```

### 4.3 配置 AI API Key

```bash
# 创建 .env 文件（不会提交到 git）
echo "AI_API_KEY=你的真实API密钥" > .env

# 可选：修改 API 地址和模型
echo "AI_API_BASE_URL=https://api.sfkey.cn/v1" >> .env
echo "AI_MODEL=glm-5.2" >> .env
```

### 4.4 构建并启动

```bash
# 首次构建
docker compose build

# 启动
docker compose up -d

# 查看日志
docker compose logs -f

# 按 Ctrl+C 退出日志查看
```

### 4.5 验证运行

```bash
# 健康检查
curl http://localhost:3001/api/health

# 预期返回：{"status": "ok", ...}
```

浏览器访问 `http://服务器IP:3001` 即可进入应用。

## 五、使用方式

### 启动 / 停止

```bash
docker compose up -d          # 启动（后台）
docker compose down           # 停止
docker compose restart        # 重启
```

### 查看状态

```bash
docker compose ps             # 容器状态
docker compose logs -f        # 实时日志
docker compose logs --tail=50 # 最近 50 行日志
```

### 更新代码后重新部署

```bash
git pull
docker compose build --no-cache
docker compose up -d --force-recreate
```

### 备份数据库

```bash
# 备份到当前目录
docker run --rm \
  -v self-grow_data-data:/data \
  -v $(pwd):/backup \
  alpine cp /data/data.db /backup/data-$(date +%F).db.backup

# 恢复（假设有备份文件 data.db.backup）
docker run --rm \
  -v self-grow_data-data:/data \
  -v $(pwd):/backup \
  alpine cp /backup/data.db.backup /data/data.db
docker compose restart
```

### 导入已有数据库

如果本地已有 `data.db` 想迁移到服务器：

```bash
# 先启动一次让 Docker 创建卷
docker compose up -d
docker compose down

# 找到卷的挂载点
docker volume inspect self-grow_data-data | grep Mountpoint

# 复制数据文件进去
sudo cp /本地路径/data.db <上面查到的Mountpoint>/data.db
sudo chmod 644 <Mountpoint>/data.db

# 重启
docker compose up -d
```

## 六、配置你自己的域名（可选）

```nginx
# /etc/nginx/sites-available/self-grow
server {
    listen 80;
    server_name 你的域名.com;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/self-grow /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

之后配 HTTPS（Let's Encrypt + Certbot）：

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名.com
```

## 七、注意事项

| 注意事项 | 说明 |
|---------|------|
| API Key 安全 | 不要写在 docker-compose.yml 里，使用 `.env` 文件传入 |
| 数据持久化 | `data.db` 存储在 Docker 卷中，**容器删除数据不丢** |
| 防火墙 | 云服务器安全组/防火墙放行 `3001` 端口（或 nginx 的 `80`/`443`） |
| 性能 | SQLite 适合单用户/小团队，多用户并发建议后续考虑切换 PostgreSQL |
| 前端目录 | `SELF_GROW_FRONTEND_DIR` 指向容器内的 `/app/frontend`，由 FastAPI 自动 serve |
| 日志 | `docker compose logs` 即可查看，无需进容器 |
