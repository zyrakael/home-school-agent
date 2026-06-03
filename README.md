# Home-school Agent

家校沟通 Agent MVP，后端使用 FastAPI + MySQL。应用启动时不会自动建表，也不会写入演示数据；接口只从 `DATABASE_URL` 指向的数据库读取数据。

## Run

1. 准备环境变量：

```bash
cp .env.example .env
```

按你的 MySQL 账号修改 `.env` 里的 `DATABASE_URL`。

2. 如果需要本地 MySQL：

```bash
docker compose up -d
```

3. 初始化数据库结构：

```bash
mysql -h 127.0.0.1 -P 3306 -u root -pagent agent < schema.sql
```

4. 启动后端：

```bash
uv run uvicorn app.main:app --reload
```

5. 启动前端：

```bash
cd web
npm install
npm run dev
```

## Data Source

所有学生、作业、课堂表现、错题数据都来自 MySQL。请直接向数据库表写入真实数据：

- `classes`
- `students`
- `homeworks`
- `homework_details`
- `homework_questions`
- `lesson_performances`
- `wrong_questions`

API 不会在启动时创建、重置或填充这些表。
