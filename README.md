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
| `admin2` | `123456` | 管理员（交叉改克重验收用） |
| `worker` | `123456` | 操作工 |

登录页已预填 `admin` / `123456`。后端 entrypoint 执行 migrate + seed。

## 业务规则

1. 布卷状态不可设为「已固化」（`cured`），除非该卷**最近一条** `DipRun` 的 `cureHours` 已记录且 **≥ 12**。
2. **克重写入分界**（`backend/core/rules.py::can_change_weight`）：
   - 操作工只能把克重仍为出厂默认 **380** 的卷写下**第一个非 380 的值**；已经不是 380 的克重不得再改；
   - 管理员可改任意**未固化**卷的克重（含交叉修改）；
   - **已固化卷全员不可改克重**（管理员也不行）。
3. 每次成功的克重改写都写入审计表 `WeightAuditLog`（谁、何时、旧值→新值），可在「克重审计」页（`/weight-audits`，API `/api/weight-audits/`）查看；台账与面板两个入口共用同一后端分界。
4. 克重带乐观锁版本号 `version`：改克重必须携带 `expectedVersion`，过期返回 **409**；修改接口在事务内对布卷行加锁，两名管理员交叉改同一卷时只留一版，工人一律按分界规则拒绝（403）。

## 快速启动

```bash
cd d:\work\document\bytecode\claudeCodePro\SailCloth\SailCloth-01
docker compose up --build
```

浏览器打开 http://localhost:3740

## SPA 信息架构

- **登录** → 进入主工作面
- **`/` 帆布间晾晒架（主）**：按帆布间挂布卷芯片（挂签状态 `raw` / `dipping` / `cured`）；点击打开右侧面板登记 `DipRun`、切换固化状态、按分界写入克重；架下为浸渍流水次要信息流
- **`/weight-audits` 克重审计**：克重改写流水（谁/何时/旧值→新值），只读
- **`/rolls` · `/dips`（次要台账）**：保留列表/表单 CRUD，侧栏降级为「台账」入口，非主路径；克重编辑同样受分界约束

API：JWT、`/api/lofts|rolls|dips|dashboard|weight-audits/`。

## 配色

海军蓝（navy）+ 帆布米色（canvas），与温室绿主题区分。
