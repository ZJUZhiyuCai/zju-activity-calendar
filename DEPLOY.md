# Deploy

更新时间：2026-04-09

这份文档只覆盖当前开源 alpha 的真实可用路径，不描述已经退出主链路的旧脚本和旧 UI。当前推荐部署顺序是：

1. 先构建前端静态资源。
2. 再初始化后端配置和管理员账号。
3. 最后选择单机、单容器或 API + worker 拆分模式。

## 1. 部署前准备

前端构建：

```bash
cd frontend
npm install
npm run build
```

说明：

- `frontend` 的构建产物会直接输出到 `we-mp-rss/static/calendar/`。
- 如果没有这一步，访问 `/` 会返回 `503 frontend_not_built`，这是故意的，不再伪装成可用页面。

后端准备：

```bash
cd ../we-mp-rss
cp config.example.yaml config.yaml
cp .env.example .env
```

至少补这几个变量：

```bash
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD='change-me-before-public-exposure'
export SECRET_KEY='replace-this-in-production'
```

说明：

- 全新机器首次启动时会自动建表。
- 如果设置了 `ADMIN_USERNAME` + `ADMIN_PASSWORD`，或 `ADMIN_USERNAME` + `ADMIN_PASSWORD_HASH`，启动时会自动创建管理员。
- 如果管理员已存在，默认不会重置密码；只有显式设置 `ADMIN_FORCE_UPDATE_PASSWORD=True` 才会覆盖密码。
- 建议第一次启动完成后移除明文 `ADMIN_PASSWORD`，改保留 `ADMIN_PASSWORD_HASH` 或完全移除 bootstrap 变量。

## 2. 最小单机部署

目标：只跑官网来源聚合和学生端前端，不接公众号链路。

```bash
cd we-mp-rss
python3 main.py -config config.yaml --mode api
```

访问：

- 前端入口：`http://127.0.0.1:8001/`
- 活动接口：`http://127.0.0.1:8001/api/v1/wx/activities`

适用场景：

- 只需要官网来源聚合
- 本地或小规模单机部署
- 暂时不接公众号登录和同步

## 3. 本机接通公众号链路

目标：本机维护者可以扫码授权、添加公众号并触发同步。

```bash
cd we-mp-rss
export MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED=True
python3 main.py -config config.yaml --mode all
```

说明：

- `--mode all` 会启动 API、授权服务和同步 worker。
- `MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED=True` 只建议本机临时调试使用。
- 对外部署时应关闭本地免登录旁路，改用正式登录态。

维护接口：

- `GET /api/v1/wx/auth/session`
- `GET /api/v1/wx/auth/qr/code`
- `GET /api/v1/wx/auth/qr/status`
- `GET /api/v1/wx/mps`
- `POST /api/v1/wx/mps`
- `POST /api/v1/wx/mps/{mp_id}/sync`

## 4. API 与 worker 分离部署

只在满足以下条件时建议拆分：

- 已启用共享 Redis
- 你明确接受当前队列模型仍在 alpha 阶段

启动方式：

```bash
python3 main.py -config config.yaml --mode api
python3 main.py -config config.yaml --mode worker
```

如果还需要把公众号扫码服务单独拆出：

```bash
python3 main.py -config config.yaml --mode auth
```

重要限制：

- 如果没有共享 Redis，不要把 `api` 和 `worker` 放在两个独立进程里。
- 当前版本已经避免“接口返回成功但任务根本没跑”的假象；worker 未运行时，`/mps/{mp_id}/sync` 会返回 `503`。

## 5. Docker 生产路径

### 单容器模式

用途：单个应用容器内同时运行 API、auth、worker，最适合维护者自部署和功能验收。

```bash
cd we-mp-rss
docker compose -f compose/docker-compose.yaml up -d --build
```

当前 `compose/docker-compose.yaml` 的真实含义：

- `mysql`：业务数据库
- `redis`：共享队列和缓存
- `singbox`：可选代理出口
- `app`：`START_MODE=all`，同时启动 API、auth、worker

要求：

- `.env` 至少要设置 `ADMIN_USERNAME`、`ADMIN_PASSWORD`、`SECRET_KEY`
- `static/calendar/` 必须已经包含前端构建产物

### SQLite 单容器最小示例

用途：本机快速验证，不建议作为正式生产路径。

```bash
cd we-mp-rss
docker compose -f compose/docker-compose-sqlite.yaml up -d --build
```

说明：

- 该文件只跑 `START_MODE=api`
- 不包含 Redis，所以不适合 API + worker 分离，也不适合正式公众号同步链路

### API + worker 分离模式

用途：把公开 API 和后台同步任务拆成独立容器。

```bash
cd we-mp-rss
docker compose -f compose/docker-compose.split.yaml up -d --build
```

当前 `compose/docker-compose.split.yaml` 的真实含义：

- `api`：`START_MODE=api`
- `worker`：`START_MODE=worker`
- `auth`：`START_MODE=auth`，默认不启动，挂在 `wechat` profile 下
- `mysql` / `redis` / `singbox`：共享依赖

如果需要公众号授权服务，再追加：

```bash
docker compose -f compose/docker-compose.split.yaml --profile wechat up -d
```

### 开发态 Docker

```bash
cd we-mp-rss
docker compose -f compose/docker-compose.dev.yaml up -d --build
```

说明：

- `backend` 挂载本地源码目录
- 默认 `START_MODE=all`
- 主要用于受控开发环境，不是推荐的生产 compose

## 6. 关键环境变量

- `CONFIG_PATH`：容器入口读取的运行配置文件路径，默认 `/app/config.yaml`
- `START_MODE`：容器或脚本入口运行模式，允许 `api / worker / auth / all`
- `PORT`：后端端口，默认 `8001`
- `DB`：数据库连接串，默认 `sqlite:///data/db.db`
- `SECRET_KEY`：JWT 和维护权限相关密钥，生产必须替换
- `ADMIN_USERNAME`：启动时准备的管理员用户名，默认建议 `admin`
- `ADMIN_PASSWORD`：启动时使用的明文管理员密码，只建议首次初始化
- `ADMIN_PASSWORD_HASH`：启动时使用的管理员密码哈希，适合替代明文密码
- `ADMIN_FORCE_UPDATE_PASSWORD`：是否在管理员已存在时强制覆盖密码，默认 `False`
- `MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED`：本机维护旁路，默认 `False`
- `STARTUP_ENABLE_AUTH_SERVICE`：是否启用授权服务预热，默认 `False`
- `STARTUP_ENABLE_EMBEDDED_REDIS`：是否启动内置 Redis，默认 `False`
- `REDIS_ENABLED`：是否启用 Redis，默认 `False`
- `REDIS_URL`：共享 Redis 地址
- `VITE_ENABLE_DEMO_FALLBACK`：前端是否允许演示数据兜底，默认仅开发环境允许

## 7. 数据库与管理员初始化

- 默认数据库是 SQLite，足够本地演示和小规模单机部署。
- Docker 生产 compose 默认走 MySQL + Redis。
- 全新机器首次启动时，FastAPI 启动事件会自动执行建表。
- 管理员初始化不再依赖旧的 `USERNAME/PASSWORD` 假参数；当前正式入口只有 `ADMIN_USERNAME`、`ADMIN_PASSWORD`、`ADMIN_PASSWORD_HASH`。
- 如果你要把服务直接暴露到公网，必须先确认管理员账号已经可登录，再关闭 `MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED`。

## 8. 健康检查与排障

健康检查：

- `GET /api/v1/wx/sys/health/live`
- `GET /api/v1/wx/sys/health/ready`
- `GET /api/v1/wx/sys/source_status`
- `GET /api/v1/wx/sys/source_metrics`

维护排障接口：

- `GET /api/v1/wx/sys/queue_status`
- `GET /api/v1/wx/sys/queue_history`
- `GET /api/v1/wx/sys/config_summary`
- `POST /api/v1/wx/sys/sources/{source_id}/refresh?source_channel=website|wechat`

来源手动刷新说明：

- `source_channel=website`：会直接重新抓取该官网来源。
- `source_channel=wechat`：会重新加载当前聚合库中的该公众号来源缓存，不等价于重新抓取微信上游。
- 如果要真正抓取公众号上游最新文章，继续使用 `POST /api/v1/wx/mps/{mp_id}/sync`。

## 9. PostgreSQL 官方部署路径

如果你准备把项目长期跑在公网，推荐优先使用 PostgreSQL，而不是 SQLite。

连接串示例：

```bash
export DB='postgresql://zju_calendar:change-me@127.0.0.1:5432/zju_activity_calendar'
```

推荐方式：

- API 单机模式：`python3 main.py -config config.yaml --mode api`
- API + worker 分离：配合共享 Redis，分别启动 `--mode api` 和 `--mode worker`
- Docker：当前仓库暂未提供官方 PostgreSQL compose 文件，建议将 PostgreSQL 作为独立托管依赖接入，再沿用现有应用容器

当前边界：

- 本项目现在仍以 `create_all` 自动建表为主，不包含正式迁移体系。
- 因此 PostgreSQL 路径已经可用，但仍更适合维护者自部署和受控环境，而不是高频多环境升级场景。

快速排障：

- 打开页面但没有活动：
  先看 `/api/v1/wx/sys/health/ready`、`/api/v1/wx/sys/source_status`、`/api/v1/wx/sys/source_metrics`
- 能打开维护接口但同步失败：
  检查是否使用了 `--mode worker` 或 `--mode all`，再看 `/api/v1/wx/sys/queue_status`
- 不确定配置到底从哪里来：
  看 `/api/v1/wx/sys/config_summary`，确认 `config.json`、`config.yaml` 和环境变量覆盖边界
- 前端显示真实故障状态：
  说明生产默认 mock 已关闭，需要先修后端或来源状态
- 本机维护接口 401：
  确认是否已显式设置 `MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED=True`
- Docker 容器启动了但 `/` 返回 `503 frontend_not_built`：
  说明你还没有执行 `frontend/npm run build`，或者没有把 `we-mp-rss/static/calendar/` 带进镜像
- 登录接口始终失败：
  先确认是否真的提供了 `ADMIN_PASSWORD` 或 `ADMIN_PASSWORD_HASH`，再确认是否误开了 `ADMIN_FORCE_UPDATE_PASSWORD=False` 导致旧密码仍然有效
