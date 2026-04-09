# GitHub Push Prep

更新时间：2026-04-09

这份文档只描述第一次把“浙大活动日历”公开推到 GitHub 时的建议边界，目的是避免首个公开 commit 把不相关目录、临时状态和维护者本机垃圾一起推上去。

## 1. 首次公开仓库建议纳入范围

建议纳入：

- 根目录文档：`README.md`、`DEPLOY.md`、`SECURITY.md`、`CONTRIBUTING.md`、`RELEASING.md`
- 根目录治理文件：`.gitignore`、`.editorconfig`、`.gitattributes`、`.github/`
- 根目录配置：`config.json`
- 产品前端：`frontend/`
- 数据聚合后端：`we-mp-rss/`
- 设计/规划文档：`浙大活动日历技术方案.md`、`浙大信息源配置表.md`

## 2. 首次公开仓库建议排除范围

建议暂时排除：

- `wexin-read-mcp/`

理由：

- 该目录本身已经是一个独立 Git 仓库。
- 它不是当前开源主产品 `frontend + we-mp-rss` 的必要运行依赖。
- 把它和主仓库一起公开，会在首版边界上制造歧义：别人会分不清这是主链路、实验工具，还是未来子项目。

当前处理方式：

- 根级 `.gitignore` 已显式忽略 `wexin-read-mcp/`
- 如果未来要开源，建议作为独立仓库或后续子模块单独处理

## 3. 首次公开前最后检查

```bash
git status --short
cd we-mp-rss && python3 -m unittest discover -s tests
cd ../frontend && npm run test:smoke && npm run lint && npm run build
```

确认以下项成立：

- 没有 `.env`
- 没有数据库文件
- 没有 `.DS_Store`
- 没有硬编码弱口令示例
- Docker、README、DEPLOY 之间没有互相打架的启动说明

## 4. 推荐首个公开版本

建议首个 GitHub tag 使用：

```text
v0.1.0-alpha
```

理由：

- 当前仓库已经达到“别人可部署、可排障、可协作”的 alpha 水位
- 但公众号链路仍然是可选增强能力，管理员面板和 fixture 回放测试等 P2 仍未完成

## 5. 推荐的首次提交说明

推荐首个公开 commit message：

```text
chore: prepare zju-activity-calendar for open source alpha
```

如果要拆成两次提交，更合理的切法是：

1. `chore: prepare repository docs and release process`
2. `feat: harden runtime, deploy flow, and activity observability`

## 6. Release Notes 草稿

首版 GitHub Release 草稿见：

- `docs/releases/v0.1.0-alpha.md`
