# SailCloth-01 · 帆布浸渍防水台

帆布间布卷与浸渍固化台账基线项目（Django 5 + DRF + Vue 3 SPA）。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Django 5 · DRF · SimpleJWT · django-cors-headers · Gunicorn |
| 前端 | Vue 3 · Vite · Pinia · Vue Router |
| 数据库 | PostgreSQL 15 |
| 部署 | Docker Compose · Nginx（前端反代 `/api`） |

## 路径与端口

- **项目路径**：`d:\work\document\bytecode\claudeCodePro\SailCloth\SailCloth-01`
- **前端**：http://localhost:3740
- **API**：http://localhost:8740
- **PostgreSQL**：localhost:6140

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 管理员 |
| `worker` | `123456` | 操作工 |

登录页已预填 `admin` / `123456`。后端 entrypoint 执行 migrate + seed。

## 业务规则

布卷状态不可设为「已固化」（`cured`），除非该卷**最近一条** `DipRun` 的 `cureHours` 已记录且 **≥ 12**。

**克重写入分界**（`fabric_weight_gsm`，出厂默认 380）：

- **操作工**：克重仍为出厂默认 380 时，只能写下第一个非 380 的实测值；已经不是 380 的克重不能再改。
- **管理员**：可改任意**未固化**卷的克重。
- **已固化卷**：全员不得改克重。
- 每次克重落库写一条 `WeightAuditLog`（谁、何时、旧值→新值、写入入口 panel/ledger），并将布卷 `version` +1；改克重必须携带 `expectedVersion`，两名管理员交叉改同一卷时后到者收 **409**，只留一版。
- 上述为后端强制规则（`backend/core/rules.py`、`core/serializers.py`），前端输入框的禁用只是界面镜像。

规则实现：`backend/core/rules.py`

## 快速启动

```bash
cd d:\work\document\bytecode\claudeCodePro\SailCloth\SailCloth-01
docker compose up --build
```

浏览器打开 http://localhost:3740

## SPA 信息架构

- **登录** → 进入主工作面
- **`/` 帆布间晾晒架（主）**：按帆布间挂布卷芯片（挂签状态 `raw` / `dipping` / `cured`）；点击打开右侧面板登记 `DipRun`、切换固化状态、在权限范围内改写克重；架下为浸渍流水次要信息流
- **`/weight-audit` 克重审计（顶栏）**：只读专页，按时间倒序展示每次克重改写（时间、帆布间、卷号、旧值→新值、操作人、写入入口），可按布卷筛选
- **`/rolls` · `/dips`（次要台账）**：保留列表/表单 CRUD，侧栏降级为「台账」入口，非主路径；台账页克重输入同样遵守写入分界

完整顶栏含「晾晒架」与「克重审计」。

API：JWT，`/api/lofts|rolls|dips|weight-logs|dashboard/`；`weight-logs` 只读。改克重的 PATCH `/api/rolls/{id}/` 须带 `expectedVersion` 与 `source`（`panel` / `ledger`）。

## 配色

海军蓝（navy）+ 帆布米色（canvas），与温室绿主题区分。
