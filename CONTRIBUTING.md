# Contributing

更新时间：2026-04-09

## 开发目标

这个仓库当前优先做两件事：

- 把官网来源主链路变成别人能跑、能排障、能接手的开源项目
- 把公众号链路收敛成可选增强能力，而不是默认依赖

不接受为了“先跑起来”继续堆不可维护分支、隐式副作用和生产默认假数据回退。

## 本地开发

```bash
cd frontend
npm install
npm run build

cd ../we-mp-rss
cp config.example.yaml config.yaml
python3 main.py -config config.yaml --mode api
```

如果你要调试公众号链路：

```bash
cd we-mp-rss
export MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED=True
python3 main.py -config config.yaml --mode all
```

## 提交前自检

后端：

```bash
cd we-mp-rss
python3 -m unittest discover -s tests
```

前端：

```bash
cd frontend
npm run lint
npm run build
npm run test:smoke
```

## 代码要求

- 不要在 import 时偷偷启动线程、队列、授权流程或外部连接。
- 生产环境不要静默回退到演示数据。
- 新接口要区分公开接口和维护接口。
- 新接口报错时，优先补 `category`，不要继续把所有问题都归到单一 `50001` 语义里。
- 新来源接入时，优先补测试和状态可见性，不接受“只有本地能跑”的适配。
- 改动要尽量做成小而完整的切片，避免把解析逻辑继续堆进同一个巨型函数。

## 来源适配提交流程

新增或修复来源时，请一并提交：

- 来源说明和可访问性前提
- 解析逻辑改动
- 至少一个回归测试或 fixture 思路
- 失败时的错误信息和可观测字段

当前来源分层约定：

- 来源注册放在 `we-mp-rss/core/activity_sources/registry.py`
- 各来源通道适配器放在 `we-mp-rss/core/activity_sources/`
- `we-mp-rss/core/zju_activity.py` 只保留聚合、过滤、排序和状态汇总，不再继续堆来源特例

如果来源依赖登录、扫码或平台侧反爬策略，请在 PR 描述里明确标成实验性。

## PR 说明

PR 至少要写清楚：

- 解决了什么问题
- 改动是否影响公开 API 或维护接口
- 手动验证方式
- 还没解决的风险或后续工作
