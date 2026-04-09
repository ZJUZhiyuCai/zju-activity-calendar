# 浙大活动日历数据服务

当前目录是“浙大活动日历”项目的后端采集与聚合层。

- 学生端产品：`../frontend`
- 数据服务：`we-mp-rss/`
- 当前职责：采集官网和公众号活动信息，并为日历前端提供统一接口

## 快速启动

```bash
cd ../frontend
npm install
npm run build

cd ../we-mp-rss
cp config.example.yaml config.yaml
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD='change-me-before-sharing'
python3 main.py -config config.yaml --mode api
```

启动后访问 `http://127.0.0.1:8001/`，根路径应直接打开学生端活动日历。

默认启动只会拉起活动 API，不会强制执行公众号登录或内置 Redis。
首次启动会自动建表；如果设置了 `ADMIN_USERNAME` + `ADMIN_PASSWORD` 或 `ADMIN_PASSWORD_HASH`，也会同时准备管理员账号。
如果需要启用公众号授权/同步能力，再在 `config.yaml` 或环境变量里显式打开：

```yaml
startup:
  enable_auth_service: true
  enable_embedded_redis: true

redis:
  enabled: true
```

运行模式：

- `python3 main.py -config config.yaml --mode api`
  只启动活动 API，适合最小部署和官网来源聚合。
- `python3 main.py -config config.yaml --mode worker`
  只启动同步 worker，适合与 API 分离部署。
- `python3 main.py -config config.yaml --mode auth`
  只启动公众号授权服务。
- `python3 main.py -config config.yaml --mode all`
  同时启动 API、授权和 worker，适合本机接通公众号维护链路。

重要限制：

- `POST /api/v1/wx/mps/{mp_id}/sync` 只有在 `worker` 或 `all` 模式下才会真正入队。
- 如果未开启共享 Redis，不要把 `api` 和 `worker` 分到两个独立进程，否则队列不会共享。
- 本项目当前仍处于开源 alpha 阶段，公众号链路属于实验性增强能力，不承诺长期稳定。
- Docker 入口也已经使用同一套运行参数，可通过 `START_MODE=api|worker|auth|all` 控制。
- `../frontend` 的 `npm run build` 会直接输出到 `static/calendar/`；没有构建前端时，根路径会明确返回 `503 frontend_not_built`。
- 来源级维护接口已支持按来源手动刷新：`POST /api/v1/wx/sys/sources/{source_id}/refresh?source_channel=website|wechat`

## Docker 运行

单容器：

```bash
cd ../we-mp-rss
cp .env.example .env
docker compose -f compose/docker-compose.yaml up -d --build
```

API + worker 分离：

```bash
cd ../we-mp-rss
cp .env.example .env
docker compose -f compose/docker-compose.split.yaml up -d --build
```

如果分离模式还要启动公众号授权服务：

```bash
docker compose -f compose/docker-compose.split.yaml --profile wechat up -d
```

注意：

- `.env` 至少要设置 `ADMIN_USERNAME`、`ADMIN_PASSWORD`、`SECRET_KEY`
- `compose/docker-compose-sqlite.yaml` 只适合本机最小验证，不适合正式 worker 拆分
- 更完整的 Docker 和管理员初始化说明见仓库根目录 `../DEPLOY.md`

如果只是本机调试维护链路，可以临时打开：

```bash
export MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED=True
```

随后再访问以下接口：

```text
GET  /api/v1/wx/auth/session
GET  /api/v1/wx/auth/qr/code
GET  /api/v1/wx/auth/qr/status
GET  /api/v1/wx/mps/search/{kw}
POST /api/v1/wx/mps
POST /api/v1/wx/mps/{mp_id}/sync
```

`POST /api/v1/wx/mps` 支持两种方式：
- 直接传 `mp_name + mp_id`
- 传 `article_url`，后端会先从文章页解析公众号信息再补齐入库

## 主要接口

- `GET /api/v1/wx/activities`
- `GET /api/v1/wx/activities/{id}`
- `GET /api/v1/wx/activities/search`
- `GET /api/v1/wx/colleges`
- `GET /api/v1/wx/sys/health/live`
- `GET /api/v1/wx/sys/health/ready`
- `GET /api/v1/wx/sys/source_status`
- `GET /api/v1/wx/sys/source_metrics`
- `POST /api/v1/wx/sys/sources/{source_id}/refresh`
- `GET /api/v1/wx/sys/queue_status`
- `GET /api/v1/wx/sys/queue_history`
- `GET /api/v1/wx/sys/config_summary`

## 说明

- 公众号授权、扫码、纳入采集名单属于后台维护动作，不是学生端产品主流程。
- 旧的 WebUI 和 HTML 模板视图已经退出主运行链路。
- RSS 输出、资源反代、初始化同步脚本也已经从当前产品链路移除。
- Access Key、消息任务、webhook、级联分发等旧能力已经从当前产品链路移除。
- `static/calendar/` 是由 `../frontend` 构建得到的前端产物。
- 核心接口错误响应已增加 `category` 字段，便于区分鉴权错误、参数错误、服务状态错误、外部依赖错误和内部错误。
