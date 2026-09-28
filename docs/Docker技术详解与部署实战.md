# Docker 技术详解与 Self Grow 部署实战

> 目标读者：会用 Docker 跑起来，但想搞清**它到底做了什么**、**为什么这么写**、**背后牵扯哪些技术**。
> 配套：仓库根目录的 `Dockerfile` / `docker-compose.yml` / `.env.example`（可运行的配置实体）
> 核实时间：2026-09-14，对照 `backend/config.py`、`backend/main.py`、`backend/requirements.txt`（177 包）

---

# 第一部分：Docker 是什么

## 1.1 它解决的三个问题

| 问题 | 没有 Docker 时 | 有 Docker 后 |
|---|---|---|
| **"我这能跑，线上跑不了"** | 依赖 Python 版本、系统库、路径、环境变量逐个对齐 | 镜像把这些**全部打包**，运行单元一致 |
| **装个东西把系统搞脏** | 依赖散落在 `/usr/lib`、注册表、各种配置目录 | 依赖只存在于**镜像层**，删容器即干净 |
| **部署要写一堆文档** | "先装 Python 3.12，再 pip install，再改配置文件第 3 行…" | `docker compose up -d` 一条命令 |

一句话概括：**Docker 把"应用 + 它依赖的一切"打包成一个标准单元（镜像），在任何装了 Docker 的机器上以相同方式运行（容器）。**

## 1.2 Docker ≠ 虚拟机（面试必问）

```
传统虚拟机                          Docker 容器
┌─────────────────────┐            ┌─────────────────────┐
│ App A    │ App B    │            │ App A    │ App B    │
├──────────┼──────────┤            ├──────────┼──────────┤
│ Bins/Lib │ Bins/Lib │            │ Bins/Lib │ Bins/Lib │
├──────────┼──────────┤            └──────────┴──────────┘
│ Guest OS │ Guest OS │  ← 每个 VM        │ Docker Engine  │
├──────────┼──────────┤    都要一整套 OS  ├────────────────┤
│ Hypervisor          │            │ Host OS (Linux)     │
├─────────────────────┤            ├─────────────────────┤
│ Host OS             │            │ 硬件                │
└─────────────────────┘            └─────────────────────┘
  启动：分钟级，GB 级                 启动：秒级，MB 级
```

| 维度 | 虚拟机 | 容器 |
|---|---|---|
| 隔离层级 | 硬件级（Hypervisor 虚拟整套硬件） | **操作系统级**（共享宿主内核） |
| 隔离强度 | 强，可跑不同内核（Linux 上跑 Windows） | 较弱，**共享内核**（所以 Linux 容器不能直接在 Windows 内核上跑，Docker Desktop 是靠内置 Linux VM） |
| 启动 | 分钟级 | 秒级 |
| 体积 | GB | MB~百 MB |
| 性能损耗 | 5~20% | 几乎无损（就是普通进程） |

**关键认知**：容器本质就是**被 Linux 内核限制和隔离的普通进程**，不是"轻量虚拟机"。
`docker ps` 看到的容器，在宿主机 `ps aux` 里能看到对应进程。

## 1.3 什么时候不该用 Docker

诚实一点，这些场景容器是负担：

- 需要**图形界面**或深度硬件访问（GPU 除外，有专门方案）
- 单文件二进制、无依赖的小工具（直接拷过去更简单）
- **需要持久化的数据库且没有可靠的卷方案**时——但个人项目挂个卷就够了（本项目就是）
- Windows GUI 应用

---

# 第二部分：核心概念逐个拆开

## 2.1 镜像（Image）—— 只读模板

**镜像 = 一个只读的文件系统快照 + 运行配置**。它不是一个大文件，而是**一堆只读层（Layer）叠起来**。

```dockerfile
FROM python:3.12-slim        # 第 1 层：基础镜像（含 Debian + Python）
COPY requirements.txt .      # 第 2 层
RUN pip install -r ...       # 第 3 层（最大的一层，几百 MB）
COPY . .                     # 第 4 层
```

**为什么要分层？** 三个巨大好处：

1. **共享**：10 个镜像都用 `python:3.12-slim`，磁盘上只存一份基础层
2. **缓存**：改了代码第 4 层，重建时前 3 层直接命中缓存 → 秒级构建
3. **增量传输**：`docker pull` 只下载本地没有的层

> **因此 Dockerfile 有一条铁律**：**变化频率低的放前面，高的放后面**。
> 先 `COPY requirements.txt` 再 `RUN pip install`，最后 `COPY . .` ——
> 如果反过来（先 `COPY . .` 再装依赖），你改一行代码就会让 pip 重装一遍。

### 写时复制（Copy-on-Write）

镜像层只读，容器运行时在上面加一层**可写层**：

```
┌───────────────────────────┐
│ 容器可写层（Container Layer）│ ← 你改的文件都存在这
├───────────────────────────┤
│ 镜像层 4  COPY . .          │ ┐
│ 镜像层 3  pip install       │ │ 只读
│ 镜像层 2  COPY requirements │ │
│ 镜像层 1  python:3.12-slim  │ ┘
└───────────────────────────┘
```

- 读文件：从上往下找，命中即用
- 改文件：把该文件**复制**到可写层再改（CoW）
- 删文件：在可写层标记"白障"（whiteout），上层看不见了，下层还在

**推论**：容器里删文件不会让镜像变小；容器删掉后，可写层也一起没了——**这就是为什么数据库必须挂卷**。

## 2.2 容器（Container）—— 镜像的运行实例

```bash
docker run -d --name web -p 3001:3001 nginx
#        │   │              │          └─ 镜像名
#        │   │              └─ 端口映射 宿主:容器
#        │   └─ 给容器起名字
#        └─ detach，后台运行
```

**镜像 : 容器 = 类 : 对象**。一个镜像可以跑出 N 个容器，互不干扰。

容器生命周期：

```
created → running → paused → stopped → deleted
              ↓
          exited（非 0 = 异常退出）
```

## 2.3 数据持久化：三种挂载方式

| 方式 | 写法 | 存在哪 | 适用场景 |
|---|---|---|---|
| **命名卷**（推荐） | `volume: dbdata:/data` | Docker 管理的目录（`/var/lib/docker/volumes/`） | **数据库、上传文件** |
| 绑定挂载 | `-v /host/path:/data` | 宿主机指定路径 | 需要直接编辑的文件（配置、代码热重载） |
| tmpfs | `--tmpfs /tmp` | **内存** | 敏感临时数据 |

**本项目必须用命名卷**：数据库落在 `mysql_data` 卷，`uploads/`（奖励图片）与 `logs/` 落在 `data` 卷，
删容器不能丢。

```bash
docker volume inspect self-grow_data    # 看卷实际在宿主机哪个目录
```

## 2.4 网络

| 模式 | 说明 |
|---|---|
| `bridge`（默认） | 容器在虚拟网桥里，有独立 IP；**通过 `-p` 端口映射才对外可见** |
| `host` | 直接用宿主网络栈，无隔离，性能略好 |
| `none` | 无网络 |

**端口映射 `-p 3001:3001`** = 宿主 3001 → 容器 3001（靠 iptables NAT 实现，见 3.4）。

**Compose 里的容器互通**：同一 `docker-compose.yml` 的服务默认在同一网桥，**用服务名当主机名**互相访问：

```yaml
services:
  app:   ...   # 其他容器里访问 http://app:3001
  nginx: ...   # 访问 http://app:3001 而不是 localhost
```

## 2.5 Dockerfile 指令速查

| 指令 | 作用 | 是否产生新层 |
|---|---|---|
| `FROM` | 指定基础镜像 | 是（起点） |
| `RUN` | **构建时**执行命令（装依赖、编译） | ✅ 是 |
| `COPY` / `ADD` | 拷贝文件进镜像 | ✅ 是 |
| `ENV` | 设置环境变量 | ❌ 只改配置 |
| `WORKDIR` | 设置工作目录 | ❌ |
| `EXPOSE` | **声明**端口（只是文档作用，不实际映射） | ❌ |
| `CMD` | 容器启动默认命令（**可被 `docker run` 后面覆盖**） | ❌ |
| `ENTRYPOINT` | 容器启动主命令（不易被覆盖，CMD 变它的参数） | ❌ |
| `HEALTHCHECK` | 健康检查 | ❌ |
| `USER` | 指定运行用户（安全：别用 root） | ❌ |

**RUN 的两种写法区别**：

```dockerfile
RUN pip install flask          # shell 形式，走 /bin/sh -c
RUN ["pip", "install", "flask"]# exec 形式，直接执行，不经过 shell
```

exec 形式的好处：**PID 1 就是你的程序**，能正确接收 SIGTERM（优雅退出）；shell 形式里 PID 1 是 sh，信号不转发给子进程（经典坑）。

**CMD vs ENTRYPOINT**：

```dockerfile
CMD ["python", "main.py"]                    # docker run img  →  python main.py
                                             # docker run img bash → bash（CMD 被整个替换）
ENTRYPOINT ["python", "main.py"]             # docker run img --help → python main.py --help
```

## 2.6 Docker Compose —— 多容器的编排

只有 `docker run` 时，你得记住一长串参数。Compose 把**运行时的所有配置写进 YAML**：

```yaml
services:            # 每个服务 = 一个容器
  app:
    build: .         # 从当前目录 Dockerfile 构建
    ports: [...]
    environment: [...]
    volumes: [...]
    restart: unless-stopped
    # depends_on: [db]   # 声明启动顺序（注意：不等待"就绪"）
```

> `depends_on` 只保证**启动顺序**，不保证依赖服务已经能接受连接。
> 真正的"等待就绪"需要在应用里重试，或用 `healthcheck` + `condition: service_healthy`。
> 本项目只有一个容器、无外部依赖，所以不需要关心这点。

## 2.7 `.dockerignore` —— 构建上下文

执行 `docker build .` 时，Docker 会把**当前目录所有文件**打包发给守护进程（这就是"构建上下文"）。
一个带 `.pixi/`（几百 MB）的项目不配 `.dockerignore`，每次构建都要传几百 MB。

它的语法和 `.gitignore` 一样，但作用不同：`.gitignore` 管 git 追踪，`.dockerignore` 管构建上下文。

---

# 第三部分：Docker 背后牵扯的技术栈

这一部分是"会用"和"懂"的分水岭。

## 3.1 Linux Namespace —— 隔离从哪来

容器"看起来像独立机器"，靠的是内核的 namespace 机制：**让一组进程只能看到部分系统资源**。

| Namespace | 隔离什么 | 效果 |
|---|---|---|
| `pid` | 进程号 | 容器内 `ps` 只看到自己的进程，PID 从 1 开始 |
| `net` | 网络 | 独立的网卡、IP、端口表、路由表 |
| `mnt` | 挂载点 | 容器有自己的 `/`，看不到宿主文件系统 |
| `uts` | 主机名 | 容器可以有自己的 hostname |
| `ipc` | 进程间通信 | 独立的消息队列/共享内存 |
| `user` | 用户和组 | 容器内 root 可以映射到宿主普通用户（安全加固） |

```bash
# 亲手验证：在容器和宿主各看一眼
docker run --rm python:3.12-slim ps aux      # 只有 2 个进程
ps aux | wc -l                               # 宿主上百个
```

## 3.2 cgroups —— 资源限制从哪来

namespace 管"看得见什么"，**cgroups（control groups）管"能用多少"**：

```bash
docker run -m 512m --cpus=0.5 myimage   # 内存上限 512MB，CPU 最多半核
```

不加限制时容器能用光宿主资源——**所以生产环境一定要设限制**，否则一个死循环能拖垮整台机器。

## 3.3 UnionFS / overlay2 —— 分层怎么实现的

镜像"叠层"靠的是**联合文件系统**（Docker 现在默认用 `overlay2`）：

```
lowerdir = 镜像各只读层（从下往上）
upperdir = 容器可写层
merged   = 容器里看到的统一视图 /
```

读文件时从 upperdir 往下找，写文件时写入 upperdir，删除时在 upperdir 建 whiteout 标记。
**这就是为什么容器读写性能和宿主磁盘几乎一样**（没有虚拟化层）。

## 3.4 iptables / NAT —— 端口映射原理

`-p 3001:3001` 并不是"Docker 进程在转发流量"。实际是 Docker 在宿主机的 iptables 里加了 NAT 规则：

```bash
sudo iptables -t nat -L DOCKER -n    # 能看到 DNAT 规则
```

访问宿主 3001 的包被内核直接 DNAT 到容器 IP 的 3001。
**推论**：这意味着即使你用防火墙只放行 3001，容器的其他端口仍可能通过 `docker-proxy` 暴露——
生产上应该用 `127.0.0.1:3001:3001` 只绑本地回环，再由 Nginx 对外。

## 3.5 镜像瘦身

| 手段 | 效果 |
|---|---|
| 用 `-slim` 基础镜像 | `python:3.12` ≈ 1 GB → `python:3.12-slim` ≈ 150 MB |
| **多阶段构建** | 编译期装 gcc/cmake，运行期只拷产物（Go/C++/前端构建必备） |
| `.dockerignore` | 别把 `.git`、`.pixi`、`node_modules` 传进去 |
| 合并 RUN + 清理缓存 | `RUN apt-get update && apt-get install -y x && rm -rf /var/lib/apt/lists/*` |
| `--no-cache-dir` | pip 不缓存 wheel（本项目 Dockerfile 已用） |

> 本项目是纯 Python，不需要编译器，所以 `python:3.12-slim` + `pip install --no-cache-dir` 就够了，
> 最终镜像约 400~600 MB（177 个依赖里有 langchain/langgraph/fastmcp/numpy 等大包）。

## 3.6 反向代理 Nginx —— 为什么容器前要有它

容器直接暴露 3001 能用，但生产上几乎都会前置 Nginx，因为：

| 能力 | 说明 |
|---|---|
| **HTTPS 终结** | SSL 证书配在 Nginx，后端仍是 HTTP（本项目代码不用改一行） |
| 多服务共用 80/443 | 一台机器跑多个项目时按域名路由 |
| 静态资源缓存 | 前端 JS/CSS 由 Nginx 直接返回，比 Python 快 |
| 限流、压缩、日志 | 通用能力 |
| 隐藏后端端口 | 只暴露 443 |

## 3.7 HTTPS / Let's Encrypt

```bash
# certbot 自动申请并续期（Nginx 插件版）
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your.domain.com
# 证书 90 天过期，certbot 会装个 systemd timer 自动续期
```

> **本项目必须上 HTTPS 的理由**（不是"最佳实践"这种空话）：
> JWT 的 Access Token 和 API Key 都在 HTTP 头里明文传输，
> 公网 HTTP 下抓包即可盗用 Access Token。**上公网必须 HTTPS**（Nginx 终止 TLS 即可）。

## 3.8 PID 1 与优雅退出、日志

- 容器的 **PID 1 进程退出 = 容器退出**
- `docker stop` 先发 **SIGTERM**，10 秒后还不退出才 SIGKILL
- 所以应用要**处理 SIGTERM** 做清理（本项目 APScheduler 在 lifespan 里 shutdown）

日志的最佳实践是**输出到 stdout/stderr**，由 Docker 收集：

```bash
docker compose logs -f            # 实时看
docker compose logs --tail 100 app
```

> 不要在容器里写日志文件到文件系统（会随容器消失，还得配 logrotate）。

## 3.9 配置管理：环境变量 vs `.env` vs Secret

**12-Factor App 原则**：配置存环境变量，不进镜像。

| 方式 | 适用 | 本项目 |
|---|---|---|
| `ENV` in Dockerfile | 非敏感默认值 | `PORT`、`SELF_GROW_DATA_DIR`、`SELF_GROW_FRONTEND_DIR` |
| compose `environment` | 部署相关配置 | 上面的 + AI 相关 |
| `.env` 文件 | 本地开发；compose 的 `${VAR}` 从这里取值 | **`.env` 必须 gitignore** |
| Docker Secret / K8s Secret | 生产密钥 | 个人项目用 `.env` + 文件权限即可 |

**绝对不能做**：把 `AI_API_KEY`、`SELF_GROW_JWT_SECRET` 写进 Dockerfile 或提交到 git。
镜像是分层的——即使后面一层删掉了，前面那层里密钥仍在（`docker history` 能看到）。

## 3.10 MySQL 容器的备份（本项目做法）

数据库跑在 **compose 里的 `mysql` 服务**（数据在 `mysql_data` 命名卷，且**不对外发布端口**）。
备份不能直接 `cp` 卷目录（InnoDB 有 redo/undo，热拷会拿到不一致的快照），要用 `mysqldump`：

```bash
# ① 一致性逻辑备份（--single-transaction 保证不锁表）
docker compose exec mysql sh -c \
  'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --databases "$MYSQL_DATABASE"' \
  > backup-$(date +%F).sql

# ② 恢复
docker compose exec -T mysql sh -c \
  'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < backup-2026-09-24.sql
```

> ⚠️ `--single-transaction` 只对 **InnoDB** 有效（本项目全是 InnoDB），
> 它靠一致性快照读，不会阻塞写入。
>
> 另一个卷 `data` 存的是**非数据库**数据（`uploads/` 奖励图片、`logs/`），
> 那部分可以直接 `docker run --rm -v ...:/data alpine tar` 打包，没有一致性要求。

## 3.11 CI/CD 一句话

```yaml
# .github/workflows/docker.yml（示意）
- uses: docker/build-push-action@v5
  with:
    push: true
    tags: ghcr.io/you/self-grow:latest
```

构建镜像 → 推到仓库（Docker Hub / GHCR / 阿里云 ACR）→ 服务器 `docker compose pull && up -d`。
个人项目可以省掉 CI，直接在服务器上 `git pull && docker compose build`。

---

# 第四部分：结合 Self Grow 的部署设计

## 4.1 先分析本项目形态

| 特征 | 对 Docker 部署的影响 |
|---|---|
| **FastAPI 应用容器** | 一个 `app` 容器；另有 `mcp`（MCP 插件）与 `mysql` |
| **MySQL 8.0**（独立容器） | 数据在 `mysql_data` 卷；**不发布端口**，只在 compose 网络内可连 |
| **APScheduler 定时任务**（每日 03:00 等） | **绝对不能跑 2 个副本**，否则任务重复执行（含 AI 资讯抓取） |
| `uploads/` 存奖励图片、`logs/` 存日志 | 一起挂在 `data` 卷 |
| **后端同源 serve 前端** | 不需要 Nginx 也能跑，配 `SELF_GROW_FRONTEND_DIR` 即可 |
| **JWT 密钥** | 必须作为环境变量注入，**缺失会拒绝启动** |
| **CORS** | 公网部署必须用 `SELF_GROW_CORS_ORIGINS` 显式指定域名（默认只放行 localhost） |
| **MemorySaver 会话** | 重启容器后 AI 会话丢失（已知限制；技能树对话记录已由前端按树持久化） |

**结论**：**三个容器（app + mcp + mysql）+ 两个命名卷 + 可选 Nginx**，不需要 Redis、不需要编排平台。
这是**为规模做的正确取舍**，不是"不懂微服务"——面试要主动说这句：
真正需要多副本时，要先解决的是「会话状态外置 + 定时任务加分布式锁」，而不是先加机器。

## 4.2 环境变量清单（更新到鉴权之后）

全部来自 `backend/config.py`：

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `PORT` | `3001` | 服务端口 |
| `SELF_GROW_DATA_DIR` | `backend/` 源码目录 | **决定 `uploads/` 与 `logs/` 落点**，Docker 下设为 `/data` |
| **`SELF_GROW_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`** | — | **唯一的数据源配置**。Docker 下 `HOST` 必须是 **服务名 `mysql`**，写 `127.0.0.1` 会指向 app 容器自己 |
| `SELF_GROW_FRONTEND_DIR` | `""`（空则不 serve 前端） | Docker 下设为 `/app/frontend` |
| `AI_API_BASE_URL` / `AI_API_KEY` / `AI_MODEL` | — | LLM 配置（也可在用户中心改，存 `model_configs` 表） |
| `DASHSCOPE_API_KEY` | — | ASR 语音识别（表达训练需要） |
| **`SELF_GROW_JWT_SECRET`** | 无 | **必填**，缺失拒绝启动。`openssl rand -hex 32` |
| `SELF_GROW_JWT_OLD_SECRET` | — | 密钥轮换过渡期用 |
| `SELF_GROW_ACCESS_TTL` / `SELF_GROW_REFRESH_TTL` | 7200 / 2592000 | 令牌有效期（秒） |
| `SELF_GROW_TRUSTED_MODE` | `0` | **生产必须为 0**（开了等于免登录） |
| **`SELF_GROW_CORS_ORIGINS`** | 本机来源 | **公网部署必须显式填域名**，如 `https://grow.example.com` |

派生路径（`config.py`）：

```python
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")    # → /data/uploads
LOG_DIR    = os.path.join(DATA_DIR, "logs")       # → /data/logs（app.log / mcp.log）
```

> ⚠️ `SELF_GROW_PACKAGED` 是个**不存在的变量**（旧 Dockerfile 遗留，代码从未读取），不要写。
> ⚠️ `SELF_GROW_DB_BACKEND` / `DB_PATH` / `data.db` 也都**不存在了**（2026-09-23 移除 SQLite），
> 老部署里留着只会看到一条"已废弃"的 WARNING。

## 4.3 三个配置文件（可直接复制）

### `Dockerfile`（项目根目录）

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 先只拷依赖清单 —— 利用层缓存：改代码不会重装依赖
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 再拷全部代码（.dockerignore 已排除 .git / .pixi / .env 等）
COPY . .

WORKDIR /app/backend

# 非敏感默认值；密钥类一律走 compose environment 注入
ENV PORT=3001
ENV SELF_GROW_DATA_DIR=/data
ENV SELF_GROW_FRONTEND_DIR=/app/frontend
ENV PYTHONUNBUFFERED=1            # 日志直接输出，不被 Python 缓冲

EXPOSE 3001

CMD ["python", "main.py"]         # exec 形式：PID 1 就是应用，能收到 SIGTERM
```

### `.dockerignore`（项目根目录）

```gitignore
.git/
.gitignore
__pycache__/
*.pyc
.pixi/
backend/.pixi/
backend/__pycache__/
backend/uploads/*
backend/logs/*
backend/.env
backend/tests/
backend/pixi.lock
node_modules/
*.log
*.bak
docs/screenshots/*.png
```

### `docker-compose.yml`（项目根目录）

```yaml
services:
  self-grow:
    build: .
    image: self-grow:latest
    container_name: self-grow
    restart: unless-stopped        # 崩溃/重启后自动拉起
    ports:
      - "3001:3001"
      # 公网部署建议改成只绑本地回环，由 Nginx 对外：
      # - "127.0.0.1:3001:3001"
    environment:
      PORT: 3001
      SELF_GROW_DATA_DIR: /data
      SELF_GROW_FRONTEND_DIR: /app/frontend
      # ── 必填 ──
      SELF_GROW_JWT_SECRET: ${SELF_GROW_JWT_SECRET:?请在 .env 中设置 JWT 密钥}
      # ── 公网部署必填：CORS 默认只放行 localhost ──
      SELF_GROW_CORS_ORIGINS: ${SELF_GROW_CORS_ORIGINS:-http://localhost:3001}
      # ── 可选：AI ──
      AI_API_BASE_URL: ${AI_API_BASE_URL:-}
      AI_API_KEY: ${AI_API_KEY:-}
      AI_MODEL: ${AI_MODEL:-}
      DASHSCOPE_API_KEY: ${DASHSCOPE_API_KEY:-}
      # 生产务必留空
      SELF_GROW_TRUSTED_MODE: 0
    volumes:
      - data:/data                 # ⚠️ 没有这一行，删容器即丢数据
    # 可选资源限制
    mem_limit: 1g
    cpus: 1.0
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:3001/api/health')"]
      interval: 60s
      timeout: 5s
      retries: 3
      start_period: 20s

volumes:
  data:                            # 命名卷：docker volume ls 可看到 self-grow_data
```

> compose 里的 `${VAR:?错误信息}` 语法：变量未设置时**直接报错拒绝启动**，
> 比"启动了但一登录 500"好排查得多（和后端 `ensure_jwt_secret()` 是同一个思路）。

### `.env`（与 docker-compose.yml 同级，**务必 gitignore**）

```bash
SELF_GROW_JWT_SECRET=用 openssl rand -hex 32 生成的 64 位十六进制
SELF_GROW_CORS_ORIGINS=https://grow.example.com
AI_API_KEY=sk-xxx
```

---

# 第五部分：从零到上线（完整步骤）

## 5.1 服务器准备

```bash
# 安装 Docker（官方脚本）
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# 装 Compose 插件（新版 Docker 自带）
docker compose version
```

## 5.2 拉代码、建密钥

```bash
git clone <你的仓库> self_grow_system && cd self_grow_system

# 生成密钥并写入 .env
echo "SELF_GROW_JWT_SECRET=$(openssl rand -hex 32)" >> .env
# 公网访问时补 CORS 来源
echo "SELF_GROW_CORS_ORIGINS=https://你的域名" >> .env
```

## 5.3 构建并启动

```bash
docker compose build          # 首次约 3~8 分钟（177 个依赖）
docker compose up -d
docker compose logs -f        # 看到 "🌐 登录页" 与 "Application startup complete" 即成功
```

## 5.4 初始化账号密码

```bash
# 注意：镜像里没装 pixi（它只是开发环境的包管理器），直接跑脚本
docker compose exec self-grow python tools/init_password.py
```

默认写入 `test / test123456`（普通用户）与 `admin / admin123456`（管理员）。
**上线后第一件事就是改掉这两个密码**。

## 5.5 验证清单

- [ ] `curl http://localhost:3001/api/health` 返回版本号
- [ ] 浏览器打开 `http://服务器IP:3001` → 登录页
- [ ] `admin` 登录成功 → 用户中心「账户安全」显示"已登录 · admin（管理员）"
- [ ] `test` 登录 → 技能页**没有**"编辑技能"按钮
- [ ] 奖励商城上传一张图片 → `docker compose exec self-grow ls /data/uploads` 能看到
- [ ] **持久化测试**（最重要）：`docker compose down && docker compose up -d` → 数据还在
- [ ] 公网部署：`SELF_GROW_CORS_ORIGINS` 是否正确、是否上了 HTTPS

## 5.6 备份与恢复

```bash
# ① 数据库（一致性逻辑备份，见 3.10）—— 不用停服务
docker compose exec mysql sh -c \
  'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --databases "$MYSQL_DATABASE"' \
  > backup-db-$(date +%F).sql

# ② 附件与日志（data 卷，没有一致性要求）
docker run --rm -v self-grow_data:/data -v $PWD:/backup busybox \
  tar czf /backup/data-$(date +%F).tar.gz /data

# ③ 恢复数据库
docker compose exec -T mysql sh -c \
  'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < backup-db-2026-09-24.sql
```

> ⚠️ 别去 `cp` `mysql_data` 卷目录 —— InnoDB 有 redo/undo 日志，热拷拿到的快照**不保证一致**，
> 恢复时报错或静默损坏都遇到过。`mysqldump --single-transaction` 才是正路。

## 5.7 升级

```bash
git pull
docker compose build          # 依赖变了才会慢，否则命中缓存
docker compose up -d          # 旧容器停掉，新容器起来，卷不受影响
docker image prune -f         # 清理悬空镜像
```

> 升级前先备份（5.6）。数据库迁移是**启动时自动幂等执行**的（`db/init.py` 的 `ALTER TABLE ... try/except`），
> 所以拉新代码直接重启即可，不用手工跑迁移。

---

# 第六部分：排障速查

| 现象 | 原因 | 解决 |
|---|---|---|
| 启动报 `SELF_GROW_JWT_SECRET` 相关错误 | 未设密钥 | compose 的 `${VAR:?}` 会直接拦下；生成后写入 `.env` |
| 能打开页面但登录 500 | 同上（若绕过检查） | 看 `docker compose logs` 里的 `RuntimeError` |
| 删容器后数据没了 | **没挂卷**或挂错路径 | 确认 `volumes: - data:/data` 且 `SELF_GROW_DATA_DIR=/data` |
| 前端 404 / 白屏 | `SELF_GROW_FRONTEND_DIR` 未设或路径错 | 容器内应能 `ls /app/frontend/index.html` |
| 公网访问提示 CORS 错误 | 默认只放行 localhost | 设 `SELF_GROW_CORS_ORIGINS=https://你的域名` |
| 上传的图片 404 | `/uploads` 挂载点用的是 `UPLOAD_DIR`（在 `/data` 下） | 卷挂了就不会丢；检查容器内目录权限 |
| 容器反复重启 | 依赖装不全或端口被占 | `docker compose logs`；`ss -lntp \| grep 3001` |
| 定时任务执行两次 | **跑了 2 个副本** | 本项目只能单副本，不要 `scale` |
| 改了代码没生效 | 镜像未重建 | `docker compose build` 后再 `up -d` |
| 构建极慢 | 构建上下文太大 | 检查 `.dockerignore` 是否排除了 `.pixi/`、`.git/` |

---

# 第七部分：面试怎么讲（60 秒）

> "部署上是 `docker compose` 三个容器：`app`（FastAPI 同时 serve 前端）、`mcp`（MCP 插件）、
> `mysql`。基础镜像 `python:3.12-slim`，依赖走 `requirements.txt`——它是从 pixi 锁定版本导出的，
> 保证线上和开发环境版本一致。`app` 和 `mcp` 都 `depends_on: mysql: service_healthy`，
> 探测用 `mysqladmin ping` 而不是 TCP——因为 MySQL 初始化期间会有一个临时 server 监听 3306，
> 端口通但 SQL 还不能跑。
>
> 两个点值得说：一是**两个命名卷分开**——`mysql_data` 放数据库、`data` 放 `uploads/` 和 `logs/`，
> 都不在容器可写层，删容器不丢；二是**密钥一律走 compose 的 environment 注入**，
> 镜像里不放任何敏感信息——镜像是分层的，写进去再删也没用，`docker history` 能看到。
>
> 架构上我刻意**不扩多副本**：APScheduler 是进程内调度器，两个副本就会重复执行定时任务
> （归档、结算、AI 资讯抓取），LangGraph 的会话也在内存里。这不是不懂微服务，
> 是这个规模下多副本的收益远小于复杂度；真要上量，我会先补分布式锁 + 会话外置，再谈扩容。"

**常见追问**：

| 问题 | 要点 |
|---|---|
| 容器和虚拟机区别？ | 容器共享宿主内核，靠 namespace 隔离 + cgroups 限流；VM 虚拟整硬件 |
| 镜像为什么分层？ | 共享、缓存、增量传输；所以 Dockerfile 要把稳定的写前面 |
| 数据怎么持久化？ | 命名卷；容器可写层随容器消失 |
| 密钥怎么管？ | 环境变量/compose 注入，绝不进镜像（分层删不掉） |
| 为什么不扩展多副本？ | APScheduler 是进程内调度 + 会话在内存，多副本会重复执行定时任务（**能主动说这个很加分**） |
| 怎么瘦身镜像？ | slim 基础镜像、多阶段构建、`.dockerignore`、`--no-cache-dir` |

---

## 附录：命令速查

```bash
# 构建与运行
docker compose build / up -d / down / restart
docker compose logs -f [service]
docker compose exec self-grow bash
docker compose ps

# 镜像与容器
docker images / rmi <id> / image prune -a
docker ps -a / rm -f <id> / logs <id> / inspect <id>
docker stats                       # 实时资源占用

# 卷
docker volume ls / inspect self-grow_data / prune

# 排障
docker compose logs --tail 200 self-grow
docker exec -it self-grow sh       # 进容器看文件
docker history self-grow:latest    # 看镜像每一层（含有没有误写密钥）
```
