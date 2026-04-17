# 浙大活动日历 — 技术状态与路线图

更新时间：2026-04-15

---

## 一、当前项目状态

### 1.1 整体架构

```
frontend/          React 学生端日历（Vite 构建，产物输出到 we-mp-rss/static/calendar/）
we-mp-rss/         Python 后端（FastAPI + SQLAlchemy + APScheduler）
config.json        校级/学院信息源配置（来源 ID、URL、CSS 选择器）
```

后端运行模式由 `START_MODE` 控制：

| 模式 | 说明 |
|------|------|
| `api` | 仅启动 HTTP API 和定时采集，不含公众号授权和 worker |
| `worker` | 仅启动后台同步 worker（需要共享 Redis） |
| `auth` | 仅启动公众号扫码授权服务 |
| `all` | 同时启动 API、授权、worker |

### 1.2 端口分配

| 服务 | 端口 | 说明 |
|------|------|------|
| 前端 dev server（`npm run dev`） | **8001** | Vite 开发服务器，代理 `/api` 到后端 |
| 后端 API（uvicorn） | **8002** | FastAPI，配置在 `we-mp-rss/.env` 的 `PORT` |
| 内置 Redis（可选） | 6379 | 默认禁用（`REDIS_ENABLED=False`） |

生产模式下前端 build 产物由后端静态服务（`/calendar/`），不存在端口冲突。

### 1.3 本地启动方式

**后端（终端 1）：**
```bash
cd we-mp-rss
source venv/bin/activate
set -a && source .env && set +a
python3 main.py -config config.yaml --mode api
```

**前端开发服务器（终端 2）：**
```bash
cd frontend
npm run dev
# 监听 http://localhost:8001/calendar/
# /api/* 自动代理到 http://localhost:8002
```

**仅构建前端（生产）：**
```bash
cd frontend
npm run build
# 产物输出到 we-mp-rss/static/calendar/，由后端静态服务
```

### 1.4 数据库（SQLite，路径 `data/db.db`）

| 表 | 用途 |
|----|------|
| `activities` | 官网/公众号活动持久化 |
| `articles` | 公众号文章原始数据 |
| `feeds` | 已添加的公众号元数据 |
| `users` | 管理员账号 |
| `config_management` | 运行时配置 |

### 1.5 活动数据流（当前已实现）

```
定时采集（APScheduler，每小时）
    ↓
core/activity_scraper.py::scrape_and_persist()
    ├─ 官网来源：HTTP 抓取 + BeautifulSoup 解析
    └─ 公众号来源：从 articles 表读取并转换
    ↓
写入 activities 表（upsert by id）
    ↓
GET /api/v1/wx/activities
    └─ 从 activities 表读取 → 装饰计算字段 → 返回前端
```

首次启动时，后台线程立即执行一次采集，之后按 `SCRAPE_INTERVAL_MINUTES`（默认 60）定时执行。数据库为空时自动回退到实时抓取。

### 1.6 当前来源状态（2026-04-13）

| 来源 | 渠道 | 状态 | 活动数 |
|------|------|------|--------|
| 图书馆讲座 | website | ✅ | 14 |
| 国际教育学院 | website | ✅ | 14 |
| 文学院 | website | ✅ | 14 |
| 计算机学院 | website | ✅ | 12 |
| 管理学院 | website | ✅ | 5 |
| 光电学院 | website | ❌ 上游断连 | 0 |
| 其余学院 | website/wechat | ✅（0 条，来源无近期活动） | 0 |

### 1.7 已启用的功能

- 官网来源聚合（15 个来源，22/23 正常）
- 活动数据库持久化 + 每小时定时采集
- 前端日历展示（React，格子宽度已修复）
- 管理员登录（`admin` / `admin123`，**上线前必须修改**）
- 健康检查：`/api/v1/wx/sys/health/live`、`/api/v1/wx/sys/health/ready`
- 来源状态：`/api/v1/wx/sys/source_status`、`/api/v1/wx/sys/source_metrics`

### 1.8 已禁用的功能

- 微信公众号扫码授权（需要 `--mode all` 和 Playwright）
- 公众号文章同步（需要 worker 模式）
- Redis 队列（`REDIS_ENABLED=False`）

---

## 二、启用微信公众号检索功能

### 2.1 前置条件

| 条件 | 说明 |
|------|------|
| 微信账号 | 需要一个可以登录微信公众平台的个人微信账号 |
| Playwright 浏览器 | 用于自动化扫码授权，需要安装 Firefox |
| 服务器可访问 `mp.weixin.qq.com` | 微信平台 API 地址，需要网络可达 |

### 2.2 安装 Playwright 浏览器

```bash
cd we-mp-rss
source venv/bin/activate
playwright install firefox
```

如果服务器无法直接访问微信，需要配置代理（见 2.5 节）。

### 2.3 修改配置

在 `we-mp-rss/.env` 中修改以下变量：

```bash
# 启用授权服务
STARTUP_ENABLE_AUTH_SERVICE=True

# 允许本机免登录访问维护接口（仅调试用，上线后关闭）
MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED=True
```

在 `we-mp-rss/config.yaml` 中确认：

```yaml
server:
  auth_web: true        # 使用 Playwright web 模式授权

gather:
  model: web            # 采集模式：web（获取永久链接）
  content: false        # 是否采集文章正文（开启会显著增加请求量）
```

### 2.4 以 all 模式启动

```bash
cd we-mp-rss
set -a && source .env && set +a
source venv/bin/activate
python3 main.py -config config.yaml --mode all
```

### 2.5 代理配置（如需）

如果服务器无法直接访问微信，在 `.env` 中配置：

```bash
PROXY_ENABLED=True
PROXY_HTTP_URL=http://127.0.0.1:7890   # HTTP/SOCKS5 代理地址
```

### 2.6 扫码授权流程

启动后，通过以下接口完成授权（需要 `MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED=True` 或先登录获取 token）：

```
1. 获取二维码
   GET /api/v1/wx/auth/qr/code
   → 返回 { code, uuid }

2. 查看二维码图片
   GET /api/v1/wx/auth/qr/image
   → 返回图片，用浏览器打开或保存后扫码

3. 轮询扫码状态（每 2 秒一次）
   GET /api/v1/wx/auth/qr/status
   → 返回 { login_status: true/false }

4. 确认完成
   GET /api/v1/wx/auth/qr/over

5. 验证登录态
   GET /api/v1/wx/auth/session
   → 返回 { is_logged_in: true, token: "...", ... }
```

### 2.7 搜索并添加公众号

授权成功后：

```
1. 搜索公众号
   GET /api/v1/wx/mps/search/{关键词}
   → 返回匹配的公众号列表，包含 mp_name、mp_id（base64 编码的 fakeid）

2. 添加公众号
   POST /api/v1/wx/mps
   Body: { "mp_name": "浙大计算机学院", "mp_id": "<base64_fakeid>" }
   → 写入 feeds 表，返回 { id, mp_name, sync_queued }

3. 触发文章同步
   POST /api/v1/wx/mps/{mp_id}/sync?start_page=0&end_page=5
   → 将同步任务加入队列，worker 异步执行

4. 查看同步状态
   GET /api/v1/wx/sys/queue_status
```

### 2.8 同步后的数据流

公众号文章同步完成后，文章存入 `articles` 表。下一次定时采集（或手动 `?refresh=true`）时，`WechatActivityAdapter` 会从 `articles` 表读取文章、过滤活动关键词、转换为活动记录，写入 `activities` 表，前端即可展示。

### 2.9 Token 自动刷新

授权成功后，APScheduler 会注册一个每小时执行的 token 刷新任务（debug 模式下每 10 分钟），自动维持登录态，无需手动重新扫码。Token 存储在 `data/wx.lic`。

---

## 三、关键文件索引

| 文件 | 说明 |
|------|------|
| `we-mp-rss/core/activity_scraper.py` | 定时采集入口 |
| `we-mp-rss/core/zju_activity.py` | 活动服务（list_activities 读 DB） |
| `we-mp-rss/core/models/activity.py` | activities 表模型 |
| `we-mp-rss/core/activity_sources/website.py` | 官网抓取适配器 |
| `we-mp-rss/core/activity_sources/wechat.py` | 公众号文章转活动适配器 |
| `we-mp-rss/driver/auth.py` | 微信授权 + token 刷新调度 |
| `we-mp-rss/driver/wx.py` | Playwright web 模式驱动 |
| `we-mp-rss/apis/auth.py` | 扫码授权 API |
| `we-mp-rss/apis/mps.py` | 公众号管理 API |
| `we-mp-rss/web.py` | FastAPI 应用入口，startup 事件 |
| `we-mp-rss/.env` | 运行时环境变量（含端口、数据库、密钥） |
| `we-mp-rss/config.yaml` | 运行时配置（从 config.example.yaml 复制） |
| `config.json` | 信息源配置（来源 ID、URL、选择器） |
| `frontend/vite.config.js` | Vite 配置（端口 8001、API 代理到 8002） |
| `frontend/src/components/Calendar.jsx` | 日历组件 |
| `frontend/src/styles/global.css` | 全局样式 |

---

## 四、待办事项

- [x] 修改管理员密码（已修改）
- [ ] 将 `SECRET_KEY` 替换为随机强密钥
- [ ] 安装 Playwright Firefox 并测试公众号扫码授权
- [ ] 配置代理（如服务器无法直接访问微信）
- [ ] 添加更多官网来源（参考 `浙大信息源配置表.md`）
- [ ] 修复光电学院来源（上游网站连接问题）
- [ ] 考虑迁移到 PostgreSQL（当前 SQLite 适合单机，不适合多节点）
