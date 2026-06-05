# Home-school Agent

家校沟通 Agent API 与前端 Agent 工作台。这个项目只负责接收老师的自然语言需求、通过 MCP Gateway 调用远程 MCP 数据工具，并生成可编辑的家校沟通草稿。

本项目不再内置学生、班级、作业、错题等本地数据接口；这些数据能力由同级独立项目 `../mcp-data-service` 提供。

## Internal Flow

```text
AgentPlanner
  -> SkillSelector
  -> ToolRouter / ToolPolicy
  -> MCPAgentChain
  -> AgentChatResponse
```

- `AgentPlanner` 调用 LLM 识别 intent、拆解任务，并输出内部 `data_needs`。
- `SkillSelector` 按 intent 选择 1 个主 Skill 和 1 个通用家校沟通 Skill。
- `ToolRouter` 将抽象 `data_needs` 映射成允许调用的 MCP tool 白名单。
- `MCPAgentChain` 只向 LLM 暴露白名单内工具，并在调用前做工具名和 required 参数校验。
- 执行计划只在后端内部使用，不返回前端。

`mcp-data-service` 只提供 MCP 数据工具，不负责 Planner、Skill 或 ToolPolicy。

## Run

1. 准备环境变量：

```bash
cp .env.example .env
```

2. 启动同级 MCP 数据服务：

```bash
cd ../mcp-data-service
cp .env.example .env
uv run python -m mcp_data_service.main
```

3. 在本项目 `.env` 中配置 MCP 连接：

```env
MCP_SERVERS='[{"name":"data","transport":"streamable_http","url":"http://127.0.0.1:8100/mcp","headers":{"Authorization":"Bearer <token>"},"tool_prefixes":["user","learning","wrong_question","lesson"],"timeout_seconds":10}]'
```

4. 启动后端 Agent API：

```bash
uv run uvicorn app.main:app --reload
```

5. 启动前端 Agent 工作台：

```bash
cd web
npm install
npm run dev
```

## API

- `POST /agent/mvp/chat`

请求体使用 `app.schemas.agent.AgentChatRequest`，返回 `app.schemas.response.AgentChatResponse`。

## Boundary

- 不直接连接业务数据库。
- 不提供学生、班级、作业等 CRUD/查询接口。
- 不内置 MCP Server。
- 不发送消息给家长，只生成老师可编辑草稿。
