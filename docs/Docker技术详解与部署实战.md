# Docker 技术详解与 Self Grow 部署实战

> 目标读者：会用 Docker 跑起来，但想搞清**它到底做了什么**、**为什么这么写**、**背后牵扯哪些技术**。
> 配套：[安全设计说明.md](./安全设计说明.md)（上线检查清单）、项目根目录 `Dockerfile` / `.dockerignore` / `docker-compose.yml` / `.env.example` / `nginx/self-grow.conf.example`
> 核实时间：2026-09-14，对照 `backend/config.py`、`backend/main.py`、`backend/requirements.txt`（132 包）

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

**本项目必须用命名卷**：`data.db` 和 `uploads/` 都在 `/data` 下，删容器不能丢。

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
> 最终镜像约 400~600 MB（132 个依赖里有 langchain/langgraph/fastmcp 等大包）。

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
> 公网 HTTP 下抓包即可盗用身份。见 [安全设计说明](./安全设计说明.md) §7.4。

### 3.7.1 Nginx 反代落地：两条路线（2026-09-15 完整实测）

| | 路线 A：Nginx 装在宿主机 | 路线 B：Nginx 跑在容器（本项目自带） |
|---|---|---|
| 安装 | `sudo apt install nginx` | 无需安装，用 `--profile with-nginx` |
| upstream 写什么 | `127.0.0.1:3001`（app）/ `127.0.0.1:8000`（mcp） | **`app:3001` / `mcp:8000`**（compose 服务名） |
| 配置文件位置 | `/etc/nginx/sites-available/self-grow.conf` | `nginx/self-grow.conf`（挂进容器） |
| 证书 | certbot 直接装系统，`/etc/letsencrypt` | certbot 写 `./nginx/certs`，容器挂到 `/etc/letsencrypt` |
| 前提 | 把 app/mcp 的 ports 改成只绑 `127.0.0.1` | 同上；`nginx/self-grow.conf` 必须存在，否则容器起不来 |

**⚠️ 头号坑**：容器里的 Nginx **不能**用 `proxy_pass http://127.0.0.1:3001`
——那是它自己。必须用 compose 服务名。表现为 nginx 启动即报
`host not found in upstream`，或起来后 502。

**路线 B 的四步**：

```bash
cp nginx/self-grow.conf.example nginx/self-grow.conf     # 改里面的域名
# 申请证书（写入 ./nginx/certs，与 compose 的挂载点一致）
docker run --rm -it -p 80:80 \
  -v "$PWD/nginx/certs:/etc/letsencrypt" \
  certbot/certbot certonly --standalone -d 你的域名
# 把 app / mcp 的 ports 都改成只绑回环（如 "127.0.0.1:3001:3001"）
docker compose --profile with-nginx up -d
```

> `nginx` 服务带了 `profiles: ["with-nginx"]`，**默认不会启动** ——
> 日常 `docker compose up -d` 只起 app（和 mcp），不受影响。

**实测结果**（本地按上面步骤完整起栈，用自签证书 + `-H "Host: example.com"`）：

| 检查 | 结果 |
|---|---|
| `http://…:80/api/health` | ✅ `301 Moved Permanently`（跳 HTTPS） |
| `https://…/api/health` | ✅ `{"status":"ok","version":"1.2"}`（反代到 `app:3001` 通） |
| `https://…/api/config.js` | ✅ 输出 `https://example.com`（`X-Forwarded-Proto` 透传正确） |
| `https://…/mcp`（不带 Key） | ✅ `401`（反代到 `mcp:8000` 通、鉴权生效） |
| `https://…/frontend/js/utils.js` | ✅ 200 + `Cache-Control: max-age=604800`（静态缓存生效） |

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

## 3.10 SQLite 的备份特殊性（本项目坑点）

数据库是单文件，**但直接 `cp` 正在写入的 `data.db` 可能拿到损坏的快照**（WAL 模式下尤其）。
正确做法是用 SQLite 的在线备份 API：

```bash
# 用 Python 的 backup API（镜像里一定有 python）
docker compose exec app python -c "
import sqlite3
src = sqlite3.connect('/data/data.db')
dst = sqlite3.connect('/data/backup.db')
with dst: src.backup(dst)
print('backup ok')
"
```

然后 `docker cp` 出来。或者简单粗暴：备份前先 `docker compose stop`。

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
| **单进程 FastAPI** | 一个容器搞定，不需要多服务编排 |
| **SQLite 单文件**（WAL 模式） | 必须挂卷；**不能水平扩展多副本**（多进程写同一库会锁竞争） |
| **APScheduler 定时任务**（每日 03:00） | **绝对不能跑 2 个副本**，否则任务执行两次 |
| `uploads/` 存奖励图片 | 也在 `DATA_DIR` 下，一起挂卷 |
| **后端同源 serve 前端** | 不需要 Nginx 也能跑，配 `SELF_GROW_FRONTEND_DIR` 即可 |
| **JWT 密钥** | 必须作为环境变量注入，**缺失会拒绝启动** |
| **CORS** | 公网部署必须用 `SELF_GROW_CORS_ORIGINS` 显式指定域名（默认只放行 localhost） |
| **MemorySaver 会话** | 重启容器后 AI 会话丢失（已知限制，前端已兜底提示） |

**结论**：**单容器 + 一个命名卷 + 可选 Nginx**，不需要 Redis、不需要数据库容器、不需要编排平台。
这是**为规模做的正确取舍**，不是"不懂微服务"——面试要主动说这句。

## 4.2 环境变量清单（更新到鉴权之后）

全部来自 `backend/config.py`：

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `PORT` | `3001` | 服务端口 |
| `SELF_GROW_DATA_DIR` | `backend/` 源码目录 | **决定 `data.db` 与 `uploads/` 落点**，Docker 下设为 `/data` |
| `SELF_GROW_FRONTEND_DIR` | `""`（空则不 serve 前端） | Docker 下设为 `/app/frontend` |
| `AI_API_BASE_URL` / `AI_API_KEY` / `AI_MODEL` | — | LLM 配置（也可在用户中心改，存 `model_configs` 表） |
| `DASHSCOPE_API_KEY` | — | ASR 语音识别（表达训练需要） |
| **`SELF_GROW_JWT_SECRET`** | 无 | **必填**，缺失拒绝启动。`openssl rand -hex 32` |
| `SELF_GROW_JWT_OLD_SECRET` | — | 密钥轮换过渡期用 |
| `SELF_GROW_ACCESS_TTL` / `SELF_GROW_REFRESH_TTL` | 7200 / 2592000 | 令牌有效期（秒） |
| `SELF_GROW_TRUSTED_MODE` | `0` | **生产必须为 0**（开了等于免登录） |
| **`SELF_GROW_CORS_ORIGINS`** | 本机来源 | **公网部署必须显式填域名**，如 `https://grow.example.com` |

派生路径（`config.py:119/122`）：

```python
DB_PATH    = os.path.join(DATA_DIR, "data.db")    # → /data/data.db
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")    # → /data/uploads
```

> ⚠️ `SELF_GROW_PACKAGED` 是个**不存在的变量**（旧 Dockerfile 遗留，代码从未读取），不要写。

## 4.3 三个配置文件（可直接复制）

### `Dockerfile`（项目根目录）

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 时区（很关键）：容器默认 UTC，而本项目大量使用本地时间
#   · SQLite 的 datetime('now','localtime')   · Python 的 date.today()
#   · APScheduler 的 CronTrigger(hour=3)
# 不设的后果：UTC 03:00 触发 = 北京 11:00 才跑；凌晨 0~8 点「今天」算成前一天
# 不需要 apt-get install tzdata —— Debian 的 tzdata 是 required 优先级包，slim 基底自带，
# 而 apt-get update 要从 deb.debian.org 拉 9.6MB 索引（国内实测 4 分钟以上）
ENV TZ=Asia/Shanghai

# 先只拷依赖清单 —— 利用层缓存：改代码不会重装依赖
COPY backend/requirements.txt ./backend/requirements.txt

# 国内服务器直连 pypi.org 拉 129 个包要 6 分钟以上且容易中断，换清华源
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir --retries 5 --timeout 60 \
        -i "${PIP_INDEX_URL}" -r backend/requirements.txt

# 再拷全部代码（.dockerignore 已排除 .git / .pixi / data.db 等）
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
backend/data.db
backend/data.db-wal
backend/data.db-shm
backend/uploads/*
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
  app:                             # ⚠️ 服务名必须是 app：docker compose exec app ...
    build:
      context: .
      # pip 源透传给 Dockerfile 的 ARG（默认清华源，海外机器在 .env 里覆盖）
      args:
        PIP_INDEX_URL: ${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}
    image: self-grow:1.2
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

  # 可选：MCP Server（把 24 个业务工具暴露给 AI 客户端），
  # 与 app 共用镜像 + **共用同一个 data 卷**。详见 docs/MCP插件说明.md §6
  mcp:
    image: self-grow:1.2
    container_name: self-grow-mcp
    restart: unless-stopped
    command: ["python", "mcp_server.py"]      # 覆盖镜像默认的 python main.py
    ports:
      - "127.0.0.1:8000:8000"                 # 只绑回环，公网走反代/隧道
    environment:
      SELF_GROW_DATA_DIR: /data
      MCP_TRANSPORT: streamable-http
      SELF_GROW_TRUSTED_MODE: "0"             # 必须 0，否则 MCP 的 Key 校验被跳过
    volumes:
      - data:/data                            # ⚠️ 必须与 app 共享
    healthcheck:                              # ⚠️ MCP 没有 /health（会 404），只做 TCP 探测
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8000), 3).close()"]
      interval: 60s
      timeout: 5s
      retries: 3
      start_period: 30s

volumes:
  data:                            # 命名卷：docker volume ls 可看到 <项目名>_data
```

> compose 里的 `${VAR:?错误信息}` 语法：变量未设置时**直接报错拒绝启动**，
> 比"启动了但一登录 500"好排查得多（和后端 `ensure_jwt_secret()` 是同一个思路）。
>
> 不需要 MCP 就只起主站：`docker compose up -d app`（只点名 app，mcp 不会启动）。

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

# 从模板生成 .env（模板里已有各键名与说明）
cp .env.example .env

# ⚠️ 用 sed「替换」而不是 echo「追加」——
#    模板里已经有 SELF_GROW_JWT_SECRET= 这一行，追加会产生重复键
#    （重复键虽然多数实现是后者生效，但 compose 与 python-dotenv 行为不完全一致，容易踩坑）
sed -i "s|^SELF_GROW_JWT_SECRET=.*|SELF_GROW_JWT_SECRET=$(openssl rand -hex 32)|" .env

# 公网访问必须填 CORS 来源（默认只放行 localhost）
sed -i "s|^SELF_GROW_CORS_ORIGINS=.*|SELF_GROW_CORS_ORIGINS=https://你的域名|" .env

# 不用启动就能检查解析结果（缺密钥会直接报错）
docker compose config | grep -E "SELF_GROW_JWT_SECRET|CORS"
```

## 5.3 构建并启动

```bash
docker compose build          # 首次约 1~3 分钟（129 个依赖，走清华源）
docker compose up -d
docker compose logs -f        # 看到 "🌐 登录页" 与 "Application startup complete" 即成功
```

## 5.4 初始化账号密码

```bash
# 注意：镜像里没装 pixi（它只是开发环境的包管理器），直接跑脚本
docker compose exec app python tools/init_password.py
```

默认写入 `test / test123456`（普通用户）与 `admin / admin123456`（管理员）。
**上线后第一件事就是改掉这两个密码**。

> 这两个账号不是空号：`db/init.py` 的 `DEFAULT_DEMO_USERS` / `DEFAULT_DEMO_DIMENSIONS`
> 带了**与本地开发库一致的初始进度**（等级、8 维等级与经验、连续天数），
> 所以新部署一份空库，打开就是有数据的样子。
>
> 想换成自己的数据：改这两处常量即可，**但三个字段必须配套** ——
> `0 ≤ xp < xp_to_next` 且 `xp_to_next == exp_for_level(level)`，
> 否则页面会显示"Lv1 却有 5625 经验、进度 100%"这种自相矛盾的数据。

## 5.5 验证清单

- [ ] `curl http://localhost:3001/api/health` 返回版本号
- [ ] 浏览器打开 `http://服务器IP:3001` → 登录页
      （若页面打开了却提示"无法连接后端服务"：先 **Ctrl+Shift+R 硬刷新** ——
      `/api/config.js` 会被浏览器缓存，旧值里的 `127.0.0.1` 指向的是你自己的电脑。
      仍然不行就看服务端日志**有没有请求进来**：一个请求都没有 = 请求根本没发出去，
      属于地址问题而非跨域问题，见云服务器手册 6.1）
- [ ] `admin` 登录成功 → 用户中心「账户安全」显示"已登录 · admin（管理员）"
- [ ] `test` 登录 → 技能页**没有**"编辑技能"按钮
- [ ] 奖励商城上传一张图片 → `docker compose exec app ls /data/uploads` 能看到
- [ ] **持久化测试**（最重要）：`docker compose down && docker compose up -d` → 数据还在
- [ ] 公网部署：`SELF_GROW_CORS_ORIGINS` 是否正确、是否上了 HTTPS
- [ ] （用了 MCP 的话）`docker compose ps` 里 `self-grow-mcp` 是 `Up (healthy)`；
      不带 Key 调 `http://127.0.0.1:8000/mcp` 返回 **401**（返回别的说明鉴权没生效）；
      在 MCP 里记一条行动 → 网站行动历史能看到（证明两个服务共享同一个卷）

## 5.6 备份与恢复

```bash
# 备份（在线安全备份，见 3.10）
docker compose exec app python -c "
import sqlite3
s=sqlite3.connect('/data/data.db'); d=sqlite3.connect('/data/backup.db')
with d: s.backup(d)
"
docker cp self-grow:/data/backup.db ./backup-$(date +%F).db
docker compose exec app rm /data/backup.db

# 整卷打包（简单粗暴版，需先停服务）
docker compose stop
docker run --rm -v self-grow_data:/data -v $PWD:/backup busybox \
  tar czf /backup/data-$(date +%F).tar.gz /data
docker compose start

# 恢复
docker compose stop
docker run --rm -v self-grow_data:/data -v $PWD:/backup busybox \
  tar xzf /backup/data-2026-09-14.tar.gz -C /
docker compose start
```

## 5.7 升级

```bash
git pull
docker compose build          # 依赖变了才会慢，否则命中缓存
docker compose up -d          # 旧容器停掉，新容器起来，卷不受影响
docker image prune -f         # 清理悬空镜像
```

> 升级前先备份（5.6）。数据库迁移是**启动时自动幂等执行**的（`db/init.py` 的 `ALTER TABLE ... try/except`），
> 所以拉新代码直接重启即可，不用手工跑迁移。

## 5.8 依赖导出踩坑（本项目真实发生，构建连续失败两次）

`requirements.txt` 不是手写的，而是 `pixi run export-reqs` 从开发环境导出的。
这一步连着踩了两颗雷，且都在 `RUN pip install` 阶段才暴露。

### 坑一：conda 包混进 pip 清单

- **现象**：`ERROR: Invalid requirement: '_openmp_mutex==4.5'`
- **根因**：早期用 `pixi list --json` 导出 —— 那是 **conda 视角**，混进了 `_openmp_mutex`、
  `bzip2`、`ca-certificates`（PyPI 上根本没有）以及 `brotli-python`（PyPI 上叫 `brotli`）
- **解决**：改读 `importlib.metadata.distributions()`（**Python 发行版视角**），
  自动拿到正确的 PyPI 名称。包数 177 → 132

### 坑二：Windows 专属包混进 Linux 镜像

- **现象**：
  ```
  ERROR: Could not find a version that satisfies the requirement pywin32==312
  ERROR: No matching distribution found for pywin32==312
  failed to solve: process "/bin/sh -c pip install ..." did not complete successfully
  ```
  最难受的地方：pip 会**先把前面 100 多个包全部下载完**，最后才在 `pywin32` 上撞墙 ——
  实测整个构建跑了 **388 秒**才失败，前面的下载全白费。
- **根因**：`pywin32` 在 PyPI 上**只有 `win32` / `win_amd64` 轮子**，Linux 下没有任何可用文件。
  它本身只是 `keyring` 的 `sys_platform == "win32"` 条件依赖，但
  **conda 解析依赖时会忽略 PyPI 的 sys_platform 标记**，按宿主机（Windows）直接装进开发环境，
  再被导出脚本原样写进清单。同批漏出来的还有 `pywin32-ctypes`、`win_inet_pton`。
- **绕过的弯路**：第一反应是「读 WHEEL 文件的 `Tag:`，把带 win 的剔掉」。**行不通** ——
  实测 Windows 环境的 `site-packages` 里，`cryptography`、`pydantic_core`、`pillow` 这些
  **跨平台**包的 WHEEL 同样写着 `Tag: cp312-cp312-win_amd64`，和 `pywin32` 长得一模一样。
  靠 tag 无法区分「跨平台包在 Windows 上装的轮子」和「本身就只发 Windows 版的包」，
  唯一可靠的离线信号是**包名**。
- **解决**：`tools/export_reqs.py` 加 `PLATFORM_ONLY` 黑名单，并做 **PEP 503 名字归一化**
  （`win_inet_pton` 的元数据名是下划线形式，不归一化就会漏网）。导出时剔除并打印 `[SKIP]` 日志。
  最终 129 个包。

### 上线前的本地预检（不用真起 Docker）

想提前知道清单能不能在 Linux 上装，用 pip 的跨平台 dry-run：

```bash
python -m pip install --dry-run --ignore-installed --no-deps \
  --only-binary=:all: \
  --platform manylinux_2_28_x86_64 --platform manylinux_2_27_x86_64 \
  --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 \
  --python-version 3.12 --target /tmp/pipverify \
  -r backend/requirements.txt
```

末尾出现 `Would install ...` 即全部可解析；出现 `No matching distribution` 就是有包在该平台上不存在。

> ⚠️ `--platform` 要给**多个**标签：`pillow 12.3.0` 只发布了 `manylinux_2_28` 轮子，
> 只给 `manylinux2014_x86_64` 会误报 `No matching distribution found for pillow==12.3.0`，
> 让你误以为清单有问题。

### 顺带一提：构建慢也是坑

388 秒里绝大部分是跨境下载耗时。国内服务器务必配镜像源，并加 `--retries` / `--timeout` 抗抖动：

```dockerfile
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir --retries 5 --timeout 60 \
        -i "${PIP_INDEX_URL}" -r backend/requirements.txt
```

写成 `ARG` 而非硬编码：海外机器 `docker compose build --build-arg PIP_INDEX_URL=https://pypi.org/simple` 即可切回官方源。

**经验总结**：

1. 依赖清单**永远不要手工编辑**，一律从锁定环境重新导出
2. 导出脚本必须**打日志说明剔除了什么**，否则换个环境你不知道自己少了什么
3. 构建期的失败要**在本地提前拦截**（dry-run 一条命令的事），别等服务器上跑 6 分钟才失败

## 5.9 复盘：一个"保险起见"的步骤拖慢了整个构建

### 现象

本地构建卡在第 5 步（`RUN apt-get update && apt-get install tzdata`）**四分钟没动静**，日志停在这行：

```
Get:4 http://deb.debian.org/debian trixie/main amd64 Packages [9678 kB]
```

9.6MB 的包索引，从 `deb.debian.org` 拉 —— 这是整个 Dockerfile 里**唯一一个连海外源的步骤**，
成了最慢的一层。

### 验证（10 秒就能做）

怀疑"这条 apt 是不是根本没必要"，不要查资料，直接起一个纯净基础镜像实测：

```bash
docker run --rm python:3.12-slim sh -c \
  'ls -l /usr/share/zoneinfo/Asia/Shanghai; TZ=Asia/Shanghai date'
```

```
-rw-r--r-- 1 root root 561 Apr 28 18:45 /usr/share/zoneinfo/Asia/Shanghai   ← 本来就有
Tue Sep 15 00:11:37 CST 2026                                               ← 直接就是 CST
```

### 结论与修正

Debian 里 `tzdata` 是 **required 优先级**包，`slim` 只裁掉文档、编译器这类东西，裁不掉它。
所以 `ENV TZ=Asia/Shanghai` **一条就够**，apt 那两行是白加的：

```dockerfile
ENV TZ=Asia/Shanghai          # 就这一行
```

删掉后：整个镜像构建 **约 100 秒**（原来光 apt 一步就 4 分钟以上）。
实测确认时区仍然正确：

```bash
docker exec <容器> date       # Tue Sep 15 00:16:17 CST 2026 ✅
```

### 通用教训

1. **"保险起见"加的东西是有维护成本的**：多一个外部源依赖、多一条失败路径、
   多 4 分钟构建时间。加之前先问一句"真的需要吗"
2. **可疑假设花 10 秒实测掉** —— `docker run --rm <基础镜像> <命令>` 比翻资料快得多，
   而且结论是这台机器上的事实，不是别人的博客
3. **但别顺手把真正的"保险"也删掉**：`ENV TZ` 必须留（删了时区就回 UTC），
   删的只是多余的 apt。判断依据是**实测结果**，不是"看着像多余"

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
| `pip install` 报 `No matching distribution found for pywin32==312` | 依赖清单里混进了 Windows 专属包 | 重新 `pixi run export-reqs`；**别手工注释掉了事**（见 5.8） |
| `pip install` 报 `Invalid requirement: '_openmp_mutex==4.5'` | 清单来自 conda 视角 | 重新导出，读 Python 元数据（见 5.8） |
| 构建极慢（几分钟且容易断） | 直连 pypi.org / deb.debian.org；或上下文太大 | 配国内镜像源（见 5.8）；**去掉不必要的 `apt-get`**（见 5.9）；检查 `.dockerignore` 是否排除了 `.pixi/`、`.git/` |
| 定时任务晚 8 小时、日期算成前一天 | 容器时区是 UTC | `ENV TZ=Asia/Shanghai`（slim 基底自带 zoneinfo，见 5.9） |

---

# 第七部分：面试怎么讲（60 秒）

> "部署上我用 Docker 单容器：基础镜像 `python:3.12-slim`，依赖走 `requirements.txt`——
> 它是从 pixi 锁定版本导出的，保证线上和开发环境版本一致。
>
> 有两个点值得说：一是**数据目录用环境变量 `SELF_GROW_DATA_DIR` 指向 `/data` 并挂命名卷**，
> 因为 SQLite 是单文件，写在容器可写层的话删容器数据就没了；
> 二是**密钥一律走 compose 的 environment 注入**，镜像里不放任何敏感信息——
> 镜像是分层的，写进去再删也没用，`docker history` 能看到。
>
> 架构上我刻意**只用一个容器**：SQLite + APScheduler 决定了它不能水平扩展多副本，
> 否则定时任务会执行两次、数据库会有锁竞争。这不是不懂微服务，
> 是这个规模下多副本的收益远小于复杂度。真要上量，我会先把 SQLite 换掉再谈扩展。"

**常见追问**：

| 问题 | 要点 |
|---|---|
| 容器和虚拟机区别？ | 容器共享宿主内核，靠 namespace 隔离 + cgroups 限流；VM 虚拟整硬件 |
| 镜像为什么分层？ | 共享、缓存、增量传输；所以 Dockerfile 要把稳定的写前面 |
| 数据怎么持久化？ | 命名卷；容器可写层随容器消失 |
| 密钥怎么管？ | 环境变量/compose 注入，绝不进镜像（分层删不掉） |
| 为什么不扩展多副本？ | SQLite 单文件 + APScheduler，多副本会重复执行定时任务（**能主动说这个很加分**） |
| 怎么瘦身镜像？ | slim 基础镜像、多阶段构建、`.dockerignore`、`--no-cache-dir` |
| 依赖怎么保证线上线下一致？ | pixi 锁版本 → 导出 pip 清单。注意 **conda 解析会忽略 PyPI 的 `sys_platform` 标记**，Windows 专属包（pywin32）会漏进来，必须按包名显式剔除（见 5.8） |
| 构建失败怎么快速定位？ | 看失败发生在**哪一层**：`pip install` 层失败是清单问题，`COPY` 层失败是上下文问题；跨平台问题本地 dry-run 就能提前拦（见 5.8） |
| 怎么判断一条 Dockerfile 指令该不该留？ | **先实测再决定**：`docker run --rm <基础镜像> <命令>`。我曾为"保险"加了 `apt-get install tzdata`，实测基底自带 zoneinfo，白等 4 分钟（见 5.9） |
| 构建时间怎么优化？ | 分三层看：基础镜像层（slim）、依赖层（国内镜像源 + 层缓存前置）、代码层（`.dockerignore`）。**先量再优化**，本项目的瓶颈是海外 apt/pypi 源 |

---

## 附录：命令速查

```bash
# 构建与运行
docker compose build / up -d / down / restart
docker compose logs -f [service]
docker compose exec app bash
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
docker history self-grow:1.2       # 看镜像每一层（含有没有误写密钥）
docker compose config              # 渲染后的最终配置（含变量替换结果）
```
