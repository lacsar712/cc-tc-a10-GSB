# 隧道收敛测缝台

测量员登记里程桩号与收敛毫米值。接口进程内后台线程认领待判行（不另起 worker 容器），按绝对值是否不超过 3.0 mm 给出合格或超限。页面是 Svelte。

## 技术栈

- 后端：Flask、Gunicorn、SQLAlchemy、进程内认领线程
- 前端：Svelte、Vite、nginx 反代 `/api`
- 数据库：PostgreSQL 16

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3201 |
| 接口 | http://localhost:8201 |
| PostgreSQL | localhost:54401（库名 `tunnelconv`） |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| surveyor | surv123456 | 可提交、可拍快照 |
| inspector | insp123456 | 只读（可查阅快照，不能拍） |

## 通车快照

通车窗打开时，监理要回看当时还在路上的测缝单。页眉进入「通车快照」专页，页面分三栏：新开快照（填窗口名称）、历史快照、快照明细（编号 / 断面 / 毫米）。

- 有写权限的人点「拍快照」，把当时待办和在办测缝单的编号、断面、毫米抄进快照库（`POST /api/snapshots`）。
- 巡检身份只能查阅历史快照与明细（`GET /api/snapshots`、`GET /api/snapshots/{id}`），点快照返回 403。
- 快照头与全部明细在同一事务一次提交，任一步失败整体回滚，不留半截。
- 快照落成后即为定格档案：在线单据再办结或改状态都不会回头改快照，快照库与实时台账新旧两套互不相干（快照无任何更新/删除接口）。

## 启动

```bash
cd projects/21-tunnel-convergence-desk
docker compose up --build
```

健康检查：`GET http://localhost:8201/api/health`

## 种子

| 桩号 | 收敛 | 结论 |
|------|------|------|
| K12+180 | 1.2 mm | 合格 |
| K18+040 | 5.6 mm | 超限 |
