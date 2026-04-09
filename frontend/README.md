# 浙大活动日历前端

这个目录是学生端产品本体，不是后台管理页。

当前前端目标：
- 让浙大本科生快速预览今天、明天、本周有什么活动
- 优先展示时间、地点、校区、主办方这些决策信息
- 在真实数据不足时也保持可验证的交互体验

## 主要结构

- `src/App.jsx`：页面状态、数据加载、降级逻辑
- `src/components/Calendar.jsx`：月历视图
- `src/components/PreviewRail.jsx`：快速预览侧栏
- `src/components/ActivityDetail.jsx`：活动详情
- `src/api/index.js`：活动接口与演示数据

## 开发命令

```bash
npm install
npm run dev
npm run lint
npm run build
```

构建产物会输出到 `we-mp-rss/static/calendar/`，由后端同源提供。

## 设计原则

- 首页默认就是活动预览，不绕去后台
- 本科生决策效率优先于“信息全量展示”
- 允许演示数据兜底，但真实接口优先
- 未来活动优先于历史归档
