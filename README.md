# 经营归因分析系统（Insight-Agent）

当前已完成详细设计第 16 章的阶段一至阶段五。

## 目录

```text
frontend/          Vue 3 + TypeScript + Vite
backend/           FastAPI + SQLAlchemy + Alembic
compose.dev.yml    本地 MySQL/Redis 开发依赖
```

## 1. 准备环境变量

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
```

样例密码只用于本地开发，不能直接用于正式环境。

## 2. 启动 MySQL 和 Redis

```powershell
docker compose -f compose.dev.yml up -d
```

这是本地开发依赖，不是生产部署方案。

如果需要启用远程服务器上的 Keycloak，在服务器 `192.168.200.10` 上执行：

```powershell
docker compose --profile oidc up -d keycloak
```

Keycloak 默认访问地址为 `http://192.168.200.10:8080`，数据保存在
`insight_keycloak_data` 卷中。首次启动后，在 Keycloak 管理控制台创建
`insight` Realm、`insight-agent` Client 和演示用户；Client 的回调地址应登记为
`http://127.0.0.1:8000/auth/callback`。然后将生成的 Client Secret 写入
`backend/.env` 的 `OIDC_CLIENT_SECRET`。

## 3. 启动后端

```powershell
Set-Location backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

数据库结构以 `backend/migrations` 中的 Alembic 迁移为唯一权威来源。正常开发和升级
统一执行 `alembic upgrade head`。`sql/init_insight_agent.sql` 是对应当前 Alembic head
的全新数据库初始化快照，不应绕过迁移单独修改；快照会写入 `alembic_version`，后续仍可
继续通过 Alembic 升级。

后端使用 `uv` 管理 Python 解释器和依赖，不需要手动激活虚拟环境。`uv sync` 会根据 `backend/pyproject.toml` 和 `backend/uv.lock` 创建或同步 `backend/.venv`。

如果希望从项目根目录执行，也可以使用：

```powershell
uv sync --project backend --extra dev
uv run --project backend alembic upgrade head
uv run --project backend uvicorn app.main:app --reload
```

可用检查接口：

- `GET http://127.0.0.1:8000/api/health/live`：进程存活；
- `GET http://127.0.0.1:8000/api/health/ready`：MySQL 和 Redis 就绪状态；
- `GET http://127.0.0.1:8000/docs`：OpenAPI 文档。

API 启动后，还需要在另一个终端启动 Agent Worker：

```powershell
Set-Location backend
uv run python -m app.workers.main
```

Worker 使用 LangGraph 执行“问题定义—查数—校验—分析—证据—归因—报告”节点链，
通过数据库事件和 Redis Pub/Sub 把节点、工具及结果状态推送到前端。API 与 Worker 必须
使用同一组 MySQL、Redis 和 `AGENT_DATA_ROOT`。
Worker 使用独立 Redis 客户端；`TASK_WORKER_REDIS_SOCKET_TIMEOUT_SECONDS` 必须长于
阻塞取队列的 `TASK_WORKER_BLOCK_TIMEOUT_SECONDS`，代码会自动保留至少 5 秒余量。
后端配置固定从项目根目录 `.env`（可选）和 `backend/.env` 读取，不受命令执行目录影响；
若同名配置同时存在，以 `backend/.env` 的非空值为准，预留空值不会覆盖有效配置。

## 4. 启动前端

```powershell
Set-Location frontend
pnpm install
pnpm dev
```

访问 `http://127.0.0.1:5173`。

## 5. 验证

```powershell
Set-Location backend
uv run ruff check --no-cache app tests migrations
uv run pytest -q -p no:cacheprovider

Set-Location ../frontend
pnpm type-check
pnpm build
```

## 阶段一完成项

- Vue 3、TypeScript、Vite、Pinia 和 Vue Router 基础壳；
- FastAPI 应用工厂、配置管理和健康检查；
- SQLAlchemy 异步 MySQL 连接和 Redis 异步连接；
- 14 张基础表 ORM 模型和 Alembic 初始迁移；
- 统一 `{code, message, data, trace_id}` 响应；
- 统一业务异常、参数异常、HTTP 异常和未知异常处理；
- HTTP/WebSocket `trace_id` 中间件；
- 本地 MySQL、Redis 开发依赖配置。

## 阶段二完成项

- OIDC Authorization Code + PKCE 登录、回调和退出登录；
- ID Token 的签名、issuer、audience、过期时间和 nonce 校验；
- OIDC 用户到本地用户的映射，本地角色不会被外部声明覆盖；
- Redis 服务端会话和 HttpOnly Cookie，提供 `GET /api/me`；
- 带用户所有权校验的会话新建、列表、重命名、归档和软删除；
- 历史消息游标分页和附件摘要查询；
- Vue 登录页、路由守卫和会话/对话/报告三栏工作台。

启动登录功能前，请在 `backend/.env` 配置 `OIDC_ISSUER`、`OIDC_CLIENT_ID`；
机密客户端还需配置 `OIDC_CLIENT_SECRET`，并在身份提供方登记
`http://127.0.0.1:8000/auth/callback` 回调地址。

## 阶段三完成项

- 用户消息、任务和初始事件同事务创建，使用 `client_msg_id` 保证幂等；
- `queued/running/waiting_input/success/failed/cancelled` 状态转换约束；
- `POST /api/chat/ws-token` 一次性短期 Token，Redis 原子消费并保留数据库审计记录；
- `WS /api/chat/ws/chat` 消息、取消、澄清、心跳和事件补拉协议；
- 任务事件落库、Redis Pub/Sub 实时发布和 `GET /api/tasks/{task_id}/events` 补拉；
- 任务查询、取消标记、Worker 队列消费和队列投递补偿；
- 前端消息发送、事件去重、心跳、指数退避重连、任务状态和取消操作。

## 阶段四完成项

- 可序列化 `AgentState`，以及 `load_context`、`define_problem`、
  `ask_clarification`、`build_analysis_plan`、`query_data`、`validate_data`、
  `analyze_with_pandas` 七节点 LangGraph；
- `define_problem`、`ask_clarification` 和 `build_analysis_plan` 使用 LangChain 模型的
  Pydantic 结构化输出；缺失指标、时间范围或对比基线会进入 `waiting_input`；
- `file_read` 只接受当前用户、当前会话的 `attachment_id`，不接受模型提供的物理路径；
- `db_query` 只通过 Data Agent 调用业务数据，包含只读 SQL、多语句、系统表、危险函数、
  可选表白名单、超时、返回行数和扫描行数限制，应用不直连业务库；
- `pandas_analyze` 计算时间范围内的指标、月度趋势、基线对比、结构贡献和统计异常，
  同时保存公式、口径和数据缺口；
- CSV、JSON/JSONL、Parquet、XLSX/XLS 和文本附件的受控上传、读取、下载与未提交删除；
- 节点和工具开始/结束事件落库，前端实时展示执行时间线；
- 阶段四输出作为阶段五证据、归因和正式报告节点的受控输入，不直接冒充归因结论。

### 阶段四配置

阶段四要求配置 LLM。基础配置供当前及后续 Agent 继承：

```dotenv
MODEL_PROVIDER=openai_compatible
MODEL_NAME=<model-name>
API_KEY=<secret>
BASE_URL=<openai-compatible-api-base>
```

如分析 Agent 需要独立模型或 API，可设置 `ANALYSIS_AGENT_MODEL_PROVIDER`、
`ANALYSIS_AGENT_MODEL_NAME`、`ANALYSIS_AGENT_API_KEY`、`ANALYSIS_AGENT_BASE_URL` 和
`ANALYSIS_AGENT_TIMEOUT_SECONDS`，非空值会覆盖基础配置。Embedding 和 reranker 尚未进入
当前流程，因此暂不声明对应配置。

无附件时，Agent 会调用受控 Data Agent；其服务地址由 `DATA_AGENT_BASE_URL` 指定，
接口为 `POST {DATA_AGENT_BASE_URL}/query`。未配置 Data Agent 且任务没有附件时，任务会以
`DATA_AGENT_NOT_CONFIGURED` 明确失败，不会自动连接业务数据库或生成虚假数据。

## 阶段五完成项

- 回收阶段四延后项：`build_evidence` 生成可引用证据，`determine_attribution` 将结论区分为
  `confirmed/probable/to_verify`，已证实结论必须关联证据；
- `build_report_ir`、`validate_report` 和 `render_report` 形成完整六部分 Report IR，使用
  Pydantic 校验有限数值、证据引用、图表白名单和数据量，校验失败最多回退重建一次；
- 生成 HTML、Markdown 和 Report IR JSON 三类文件，HTML 使用 ECharts 渲染；提供
  `GET /api/results/{task_id}` 和 `/api/results/{task_id}/export?format=html|md|json`；
- 市场表现分析补充订单量、客单价、转化率、ROAS 及渠道/地区等维度变化；库存分析补充
  库存总量、覆盖天数及缺货、积压、滞销商品识别；
- 长会话按消息数或字符数触发事实型上下文摘要，加载时组合最新摘要和未覆盖消息；
- 支持失败任务 `POST /api/tasks/{task_id}/retry`，Data Agent 临时错误自动重试，模型沿用
  LangChain 重试，Report IR 执行一次受控重建；
- 管理员可通过 `GET /api/admin/logs` 和前端 `/admin/logs` 按任务、Trace 和级别查询脱敏日志；
- Vue 报告栏展示问题定义、关键指标、证据、归因结论、待补数据、下一步建议、ECharts
  图表和文件下载；切换历史会话时恢复最近任务及正式结果。

### 阶段五配置

上下文压缩可通过以下变量调整：

```dotenv
CONTEXT_SUMMARY_MESSAGE_THRESHOLD=30
CONTEXT_SUMMARY_CHAR_THRESHOLD=12000
CONTEXT_SUMMARY_RETAIN_MESSAGES=10
```

自动建议和库存风险规则是第一版确定性口径，真实业务上线前仍需按企业字段字典、库存周期、
补货点和经营指标口径校准。HTML 报告当前从固定 CDN 加载 ECharts；前端工作台使用本地依赖。
