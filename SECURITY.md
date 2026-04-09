# Security

更新时间：2026-04-09

## 当前安全边界

- 默认情况下，维护接口需要登录态。
- `maintenance.allow_local_unauthenticated` 已默认关闭。
- 只有显式设置 `MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED=True` 时，本机请求才允许绕过维护登录。
- 前端生产路径默认不再回退到 mock 数据，避免把系统故障伪装成真实活动。

## 敏感配置

以下内容不应提交到公共仓库：

- `config.yaml`
- 真实数据库连接串
- Redis 密码
- JWT secret
- 微信登录 token、cookie、二维码状态文件
- 任意生产 webhook 地址

建议做法：

- 仅提交 `config.example.yaml`
- 通过环境变量覆盖生产敏感值
- 定期轮换 `SECRET_KEY`、Redis 密码和微信相关会话

## 默认暴露面

公开接口：

- `/`
- `/api/v1/wx/activities`
- `/api/v1/wx/activities/{id}`
- `/api/v1/wx/activities/search`
- `/api/v1/wx/colleges`
- `/api/v1/wx/sys/health/live`
- `/api/v1/wx/sys/health/ready`
- `/api/v1/wx/sys/source_status`

维护接口：

- `/api/v1/wx/auth/*`
- `/api/v1/wx/mps*`
- `/api/v1/wx/sys/info`
- `/api/v1/wx/sys/resources`

不建议直接把维护接口在未加额外网关保护的情况下暴露到公网。

## 已知风险

- 公众号采集链路依赖扫码授权和平台侧策略，稳定性和可持续性都有限。
- SQLite 适合单机和演示，不适合高并发生产场景。
- API/worker 分离部署当前依赖共享 Redis；没有共享队列后端时不要拆进程。

## 漏洞提交

在问题公开前，请优先私下联系项目维护者；不要把 token、cookie、会话截图或可复现攻击细节直接发到公开 issue。

建议附带：

- 影响范围
- 复现步骤
- 预期行为与实际行为
- 是否需要轮换密钥或下线实例
