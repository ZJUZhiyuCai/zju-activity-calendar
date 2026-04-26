# 浙大活动日历 - 技术状态与路线图

更新时间：2026-04-26

---

## 一、当前生产状态

### 1.1 部署拓扑

```
kanzheli.online / www.kanzheli.online
    ↓
Nginx HTTPS 反向代理
    ├─ /calendar/ 与前端静态资源 → Docker nginx: calendar-frontend → 127.0.0.1:8001
    └─ /api/                         → FastAPI 后端          → 127.0.0.1:8002
```

后端以 `we-mp-rss/.env` 中的 `START_MODE=all` 运行，已经同时启用：

- FastAPI 活动 API
- APScheduler 定时活动采集
- 微信公众号扫码授权与 token 刷新
- 公众号文章同步 worker
- 文章内容补全 worker

Redis 当前仍为禁用状态：`REDIS_ENABLED=False`。队列状态只在进程内维护，适合当前单机部署。

### 1.2 端口与进程

| 服务 | 端口 | 当前用途 |
|------|------|----------|
| 前端 Docker nginx | `127.0.0.1:8001` | 托管前端构建产物 |
| 后端 FastAPI / uvicorn | `0.0.0.0:8002` | API、采集调度、微信授权、worker |
| 宿主机 Nginx | `80` / `443` | 域名入口与 HTTPS |

后端当前启动方式：

```bash
cd /root/Calendar/we-mp-rss
set -a && source .env && set +a
nohup ./venv/bin/python main.py -config config.yaml --mode "$START_MODE" > backend.log 2>&1 &
```

当前后端 PID 写入 `we-mp-rss/backend.pid`。

### 1.3 数据目录

当前项目使用 `we-mp-rss/data` 作为唯一运行数据目录，不再使用 `/root/Calendar/data`。

关键文件：

| 文件 | 说明 |
|------|------|
| `we-mp-rss/data/db.db` | SQLite 主库 |
| `we-mp-rss/data/wx.lic` | 微信公众号登录态与 token |
| `we-mp-rss/backend.log` | 后端运行日志 |

`.env` 中数据库配置为：

```bash
DB=sqlite:///data/db.db
```

### 1.4 HTTPS

`kanzheli.online` 与 `www.kanzheli.online` 已配置 HTTPS。证书由 Certbot 管理，自动续期 dry-run 已验证通过。

常用检查：

```bash
curl -sk https://kanzheli.online/api/v1/wx/sys/health/live
curl -sk https://kanzheli.online/api/v1/wx/sys/health/ready
curl -sk https://kanzheli.online/api/v1/wx/sys/source_status
```

---

## 二、数据与来源

### 2.1 当前数据库统计

截至 2026-04-26 17:30 CST 首轮重启采集后：

| 表/指标 | 数量 |
|---------|------|
| `feeds` | 24 |
| `articles` | 886 |
| `activities` | 284 |
| `activities.website` | 70 |
| `activities.wechat` | 214 |
| `record_bucket=activity` | 237 |
| `record_bucket=non_activity` | 47 |

首轮采集日志结果：

```text
采集完成: 写入/更新 230 条活动
scraper completed | upserted=230 total_collected=230 total_valid=230
```

### 2.2 当前来源状态

当前共有 21 个逻辑来源、29 个来源通道：

| 状态 | 数量 |
|------|------|
| 已尝试通道 | 29 |
| 正常通道 | 28 |
| 异常通道 | 1 |

异常项：

| 来源 | 渠道 | 原因 |
|------|------|------|
| 光电科学与工程学院 `opt` | website | 上游 `office.opt.zju.edu.cn` 当前网络不可达 |

### 2.3 官网来源

已接入官网来源包括：

- 图书馆讲座
- 研究生院
- 本科生院
- 研究生活动
- 国际教育学院
- 计算机科学与技术学院
- 文学院
- 经济学院
- 管理学院
- 医学院
- 光电科学与工程学院
- 软件学院

其中 `opt` 当前上游断连；若上游恢复或改 URL，需要更新来源配置。

### 2.4 微信公众号来源

当前已接入公众号来源包括：

- 图书馆讲座
- 研究生院
- 本科生院
- 管理学院
- 经济学院
- 文学院
- 计算机科学与技术学院
- 医学院
- 机械工程学院
- 电气工程学院
- 生命科学学院
- 公共管理学院
- 外国语学院
- 信息与电子工程学院
- 能源工程学院
- 传媒与国际文化学院
- 竺可桢学院

微信登录态当前有效，token 到期时间见 `backend.log`；授权服务会注册每小时 token 刷新任务。

---

## 三、活动解析链路

### 3.1 数据流

```
APScheduler 每小时触发
    ↓
core/activity_scraper.py::scrape_and_persist()
    ├─ website: HTTP 抓取列表页与详情页
    └─ wechat: 从 articles 表读取公众号文章
    ↓
候选活动过滤
    ↓
LLM JSON 解析 + 旧规则兜底
    ↓
写入 activities 表
    ↓
GET /api/v1/wx/activities
```

首次启动时后台线程会立即执行一次采集，之后按 `SCRAPE_INTERVAL_MINUTES=60` 定时执行。公众号自动同步按 `*/30 * * * *` 调度。

### 3.2 LLM 解析

当前已经正式接入 LLM 解析，公众号和网页来源都会进入同一套 JSON 提取链路。

配置项：

```bash
ACTIVITY_LLM_ENABLED=True
ACTIVITY_LLM_API_URL=https://api.deepseek.com
ACTIVITY_LLM_MODEL=deepseek-v4-flash
ACTIVITY_LLM_TIMEOUT_SECONDS=45
ACTIVITY_LLM_MAX_ARTICLES_PER_SOURCE=2
ACTIVITY_LLM_MAX_WEBSITE_ITEMS_PER_SOURCE=2
```

说明：

- API key 从 `.env` 中读取，不写入文档。
- LLM 返回格式要求是 JSON。
- 返回格式错误或解析失败时最多重试 2 次。
- 仍失败则写入 `llm_pending=True` / `llm_error`，保留旧规则可解析出的字段。
- 解析字段包括：时间、校区、地点、二课/美育加分、主讲人、主办方、活动类型、摘要、置信度等。

当前 `activities` 表 284 条记录均已带有 LLM 标记字段。

### 3.3 代码入口

| 文件 | 说明 |
|------|------|
| `we-mp-rss/core/activity_llm.py` | LLM 请求、JSON 解析、重试与 pending 标记 |
| `we-mp-rss/core/activity_sources/website.py` | 官网来源抓取与网页详情 LLM 解析 |
| `we-mp-rss/core/activity_sources/wechat.py` | 公众号文章转活动与 LLM 解析 |
| `we-mp-rss/core/non_activity_classifier.py` | 活动/非活动记录分桶 |
| `we-mp-rss/core/models/activity.py` | `activities` 表字段模型 |
| `we-mp-rss/tools/test_activity_llm.py` | LLM 单篇解析测试工具 |

---

## 四、运行与维护

### 4.1 重启后端

```bash
cd /root/Calendar/we-mp-rss
kill "$(cat backend.pid)"
set -a && source .env && set +a
nohup ./venv/bin/python main.py -config config.yaml --mode "$START_MODE" > backend.log 2>&1 &
echo $! > backend.pid
```

重启后观察：

```bash
tail -f backend.log
curl -sk https://kanzheli.online/api/v1/wx/sys/health/live
curl -sk https://kanzheli.online/api/v1/wx/sys/source_status
```

### 4.2 前端 Docker

前端生产容器名为 `calendar-frontend`，由 Nginx 托管构建后的静态文件并监听 `127.0.0.1:8001`。

更新前端后通常需要：

```bash
cd /root/Calendar/frontend
npm run build
docker restart calendar-frontend
```

### 4.3 扫码授权

如微信登录态失效，可通过以下接口重新扫码：

```text
GET /api/v1/wx/auth/qr/code
GET /api/v1/wx/auth/qr/image
GET /api/v1/wx/auth/qr/status
GET /api/v1/wx/auth/qr/over
GET /api/v1/wx/auth/session
```

---

## 五、待办事项

- [x] 使用 `we-mp-rss/data` 作为唯一数据目录
- [x] 配置 `kanzheli.online` HTTPS
- [x] 启用微信公众号授权、同步 worker 与活动采集
- [x] 接入 DeepSeek LLM 解析公众号文章
- [x] 接入 DeepSeek LLM 解析网页来源
- [x] 新增多个学院公众号来源
- [ ] 将 `SECRET_KEY` 替换为随机强密钥
- [ ] 修复或替换光电学院 `opt` 官网来源
- [ ] 评估 LLM 误判样本，优化提示词和候选过滤
- [ ] 需要多进程/多节点时迁移到 PostgreSQL 与 Redis
