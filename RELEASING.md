# Releasing

更新时间：2026-04-09

这份文档描述当前仓库对外发布到 GitHub Release 的最小严肃流程。目标不是“发一个 tag 就算结束”，而是保证每个 release 都能回答三件事：

1. 这次改了什么。
2. 部署方需要改什么。
3. 现在还已知有什么问题。

## 1. 发版前检查

- 确认 `OPEN_SOURCE_CHECKLIST.md` 中当前版本承诺的项目已经完成。
- 确认 `README.md`、`DEPLOY.md`、`CONTRIBUTING.md` 没有和代码行为脱节。
- 确认前端已经重新构建并本地验证过。
- 确认没有把本机数据、`.env`、数据库文件、抓取缓存带进待发布内容。

建议至少执行：

```bash
cd we-mp-rss
python3 -m unittest discover -s tests

cd ../frontend
npm install
npm run test:smoke
npm run lint
npm run build
```

## 2. 版本整理

- 更新需要对外说明的文档日期。
- 如果接口、环境变量、部署步骤有变化，必须同步 `README.md` 与 `DEPLOY.md`。
- 如果存在新增风险、降级路径或已知限制，必须写进本次 release notes。

## 3. Release Notes 模板

每个 release 至少包含以下结构：

### Highlights

- 用户或维护者真正会感知到的变化。

### Breaking / Config Changes

- 新增或废弃的环境变量。
- 启动命令、Docker、数据库路径变化。
- 任何需要维护者手动处理的事项。

### Validation

- 本次 release 运行了哪些自动化检查。

### Known Issues

- 当前明确存在但未解决的问题。
- 哪些能力仍属于实验性质。

## 4. GitHub Release 操作顺序

1. 在主分支确认代码、文档、测试都已收口。
2. 创建 tag，例如 `v0.1.0`。
3. 在 GitHub Draft Release 中填写 release notes。
4. 把 `Breaking / Config Changes` 和 `Known Issues` 写完整后再发布。

## 5. 当前已知要求

- 公众号链路仍然是可选增强能力，release notes 必须继续明确这一点。
- 如果本次 release 影响了 `START_MODE`、管理员初始化、前端构建路径或健康检查接口，必须在 release notes 里单列。
- 如果本次 release 没有跑前端测试或构建，不能标记为可部署 release。
