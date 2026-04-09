# 浙大活动日历

面向浙大本科生的活动预览产品。

当前仓库处于开源 alpha 整理阶段，不是“开箱即用的稳定 SaaS”。官网来源主链路已经可以独立运行；公众号链路仍然是可选增强能力，依赖扫码授权、平台策略和维护状态，不保证长期稳定。

当前阶段的目标不是做一个臃肿的“全校活动大全”，而是让用户在很短时间内看懂：

- 这周有什么值得去
- 时间地点是否明确
- 离自己常驻校区远不远
- 是否值得点开详情

## 仓库结构

- `frontend/`：学生端产品，本体是日历首页和快速预览交互
- `we-mp-rss/`：内部采集与聚合层，负责官网与公众号活动数据整理
- `config.json`：校级/学院信息源配置
- `浙大活动日历技术方案.md`：产品目标、当前状态、执行顺序
- `浙大信息源配置表.md`：来源优先级、公众号接入策略、修复顺序
- `OPEN_SOURCE_CHECKLIST.md`：开源发布前的 P0 / P1 / P2 长任务清单
- `DEPLOY.md`：单机部署、API/worker 拆分运行、常见故障排查
- `SECURITY.md`：默认暴露面、敏感配置和漏洞提交流程
- `CONTRIBUTING.md`：本地开发、测试和 PR 约定
- `RELEASING.md`：GitHub Release 与版本说明流程
- `docs/OPEN_SOURCE_ACCEPTANCE_REPORT.md`：当前开源 alpha 的验收结论、未签收项和发布建议
- `docs/releases/`：GitHub Release 草稿与版本说明草案
- `docs/archive/`：一次性历史记录与已完成事项归档
- `LICENSE`：仓库根许可证；当前仓库默认沿用现有 MIT 文本，若未来某个子目录采用不同许可证，必须在子目录内单独声明

## 当前产品判断

- 首页应该直接展示活动，而不是后台入口
- 官网来源负责稳定结构化信息
- 公众号来源负责补未来讲座预告
- `frontend/` 才是产品，`we-mp-rss/` 只是数据服务
- 后端只保留最小维护能力：登录、扫码授权、公众号搜索/添加/同步
- 已移除旧 RSS 输出、资源反代、初始化同步脚本等非主链路能力

## 本地启动

前端：

```bash
cd frontend
npm install
npm run dev
```

生产构建到后端静态目录：

```bash
cd frontend
npm run build
```

后端：

```bash
cd we-mp-rss
cp config.example.yaml config.yaml
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD='change-me-before-sharing'
python3 main.py -config config.yaml --mode api
```

启动后访问 `http://127.0.0.1:8001/`，根路径应直接进入学生端活动日历。
后端首次启动会自动建表；如果设置了 `ADMIN_USERNAME` + `ADMIN_PASSWORD` 或 `ADMIN_PASSWORD_HASH`，也会在启动时自动准备管理员账号。

如果需要公众号链路：

```bash
cd we-mp-rss
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD='change-me-before-sharing'
python3 main.py -config config.yaml --mode all
```

最小可用建议：

- 只看官网聚合和前端：`--mode api`
- 本机调试公众号授权和同步：`--mode all`
- 独立跑 worker：`--mode worker`
- 只预热公众号授权：`--mode auth`

注意：

- `POST /api/v1/wx/mps/{mp_id}/sync` 需要 `worker` 或 `all` 模式。
- 如果没有共享 Redis，不建议把 `api` 和 `worker` 分到两个独立进程部署，否则任务队列不会共享。
- 本地未登录调试维护接口时，必须显式设置 `MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED=True`。
- Docker 镜像入口也已经收敛到同一套运行模型：通过 `START_MODE=api|worker|auth|all` 控制，不再依赖旧的 `-job/-init` 启动参数。
- `frontend/` 的 `npm run build` 会直接把产物写到 `we-mp-rss/static/calendar/`，部署前必须先完成这一步，否则根路径会返回 `503 frontend_not_built`。
- 来源级维护接口已支持按来源手动刷新：`POST /api/v1/wx/sys/sources/{source_id}/refresh?source_channel=website|wechat`

## Docker 路径

先构建前端：

```bash
cd frontend
npm install
npm run build
```

再准备后端环境：

```bash
cd ../we-mp-rss
cp config.example.yaml config.yaml
cp .env.example .env
```

至少设置这些变量：

```bash
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD='change-me-before-public-exposure'
```

单容器模式：

```bash
docker compose -f compose/docker-compose.yaml up -d --build
```

API + worker 分离模式：

```bash
docker compose -f compose/docker-compose.split.yaml up -d --build
```

如果分离模式还需要公众号扫码授权，再显式带上：

```bash
docker compose -f compose/docker-compose.split.yaml --profile wechat up -d
```

更完整的生产说明见 `DEPLOY.md`。

## 当前主链路

```text
/ 
 -> React 日历首页
 -> /api/v1/wx/activities
 -> 后端聚合官网 + 公众号文章
 -> 输出统一活动结构
 -> 前端按本科生预览逻辑展示
```

## 支持矩阵

- 官网来源聚合：默认支持，开源 alpha 主链路。
- 公众号搜索/添加：可选增强能力，需要维护权限和扫码授权。
- 公众号同步入库：需要维护权限以及 `worker` 或 `all` 模式。
- 前端演示数据：仅开发环境或显式设置 `VITE_ENABLE_DEMO_FALLBACK=true` 时允许回退。
- 健康检查：`/api/v1/wx/sys/health/live`、`/api/v1/wx/sys/health/ready`、`/api/v1/wx/sys/source_status`
- 来源级统计：`/api/v1/wx/sys/source_metrics`
- 来源手动刷新：`/api/v1/wx/sys/sources/{source_id}/refresh`
- 队列维护状态：`/api/v1/wx/sys/queue_status`、`/api/v1/wx/sys/queue_history`
- 配置边界摘要：`/api/v1/wx/sys/config_summary`
- 错误响应：维护接口和核心活动接口现在会返回 `category` 字段，用于区分 `auth / validation / not_found / service_state / external_dependency / config / internal`

## 现在不做的事

- 不把采集维护后台当成学生端产品
- 不优先做复杂报名流程
- 不为了保留上游形态而保留旧 UI、旧文档和旧脚本
- 不继续维护 Access Key、消息任务、webhook 编排这类旧助手能力
