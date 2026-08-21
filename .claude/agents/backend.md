---
name: "backend"
description: "编写src目录下的后端代码时"
model: inherit
color: blue
memory: project
disallowedTools: mcp__yunxiao, mcp__playwright, mcp__excel, mcp__ssh
---

# Backend Subagent 配置

## 项目概述

后端模块，基于 Python>=3.11+ + FastAPI（端口 8082），MySQL 持久化，使用 uv 管理依赖。

## 建议目录结构

```
src/
├── server.py               # FastAPI 入口
├── group_chat_sentiment/   # xxx主题
├── test_drive/             # xxx主题
├── task_manager/           # 任务调度（共享）
│   ├── controller/ → service/ → mapper/
├── yo_mysql/               # 连接池 + @Transaction
├── controller/             # 顶层 API 控制器
└── utils/                  # llm/env/mysql 等
```
### Python 代码规范

- **所有方法必须同步**（`def`，禁止 `async def`）。同一功能下禁止混用同步/异步。
- **模块方式导入**：项目目录为根，使用 `import src.utils.xxx`，不要 `from . import`。
- **文件组织**：每个功能模块要合理组织文件关系，不要都写在一个文件下。



## 强制规范

### 1. 同步方法（禁止 async）

```python
# ✅ 正确
def query_task(task_id: str, conn=None):

# ❌ 错误
async def query_task(task_id: str):
```

### 2. 模块导入（项目根目录为根）

```python
# ✅ 正确
import src.utils.llm
from src.task_manager.service import task_service

# ❌ 错误
from . import xxx
```

### 3. 事务管理与 conn 注入（核心规则）

#### 3.1 @Transaction() 的 conn 自动注入机制

```python
from src.yo_mysql.transaction import Transaction

@Transaction()
def create_task(params, conn=None):
    # conn 自动从线程池注入，不需要调用方传递
    conn.execute(...)
```

#### 3.2 conn 自动复用（线程绑定）

当父方法 A（有 `@Transaction()`）调用子方法 B（也有 `@Transaction()`）时，B **不会创建新 conn**，而是自动复用 A 的 conn（conn 绑定在线程上）。因此**不需要传 conn**，注解会自动处理。

```python
@Transaction()
def parent_method(params, conn=None):
    # conn 自动注入
    child_method(params, conn=conn)  # ✅ 子方法自动复用父方法的 conn

@Transaction()
def child_method(params, conn=None):
    # conn 自动复用，不会新建
    conn.execute(...)
```

#### 3.3 事务一致性的范围

| 场景 | 是否需要事务一致性 | 做法 |
|------|-------------------|------|
| **查询操作** | ❌ 不需要 | 每个查询独立事务，调完即释放 |
| **写入操作（单一表）** | 可选 | 单个 @Transaction 即可 |
| **写入操作（多表原子性）** | ✅ 需要 | 封装在一个 mapper 方法中，标 @Transaction() |

**关键原则**：只有"同时插入/更新多个数据，需要原子性（全成功或全失败）"时才需要事务一致性。查询永远不需要。

#### 3.4 外层文件（非 mapper）的改造原则

外层文件（data/、summary/、analysis/ 等）**不应当察觉 conn 的存在**：

- ❌ 函数签名里没有 conn
- ❌ 不调用 `db_utils.query(conn, sql)` — `db_utils` 是 mapper 内部工具
- ❌ 不出现任何 SQL 字符串
- ✅ 只调用 mapper 的业务方法（如 `query_msg_analysis_sentiment_stats()`）
- ✅ mapper 方法通过 `@Transaction()` 自动注入 conn

```python
# ❌ 错：外层传 conn，有 SQL
def extract_overview(conn, date_day, car_series_type=DEFAULT_CAR_SERIES):
    total_msgs = query(conn, "SELECT COUNT(*) ...", (...))

# ✅ 对：外层不传 conn，不调 SQL
def extract_overview(date_day, car_series_type=DEFAULT_CAR_SERIES):
    total_msgs = query_msg_analysis_count_by_date_and_car_series(date_day, car_series_type)
```

#### 3.5 写入场景的事务管理

```python
# ❌ 错：手动管理事务，外层传 conn
def import_data():
    conn = get_conn()
    try:
        insert_batch1(..., conn=conn)
        insert_batch2(..., conn=conn)
        conn.commit()
    finally:
        release_conn(conn)

# ✅ 对：@Transaction 自动复用 conn，外层无感知
@Transaction()
def import_data(conn=None):
    insert_batch1(...)  # 自动复用上面的 conn
    insert_batch2(...)  # 自动复用上面的 conn
```

### 4. conn 参数的放置规则

- `conn` 必须是函数**最后一个参数**，默认值为 `conn=None`
- 禁止 `get_conn()`/`release_conn()` 出现在功能代码中（mapper 层禁止，外层更禁止）
- `@Transaction()` 标注的方法，conn 由框架自动注入, 禁止传递conn， @Transaction的方法嵌套，框架会自动保证conn一致
- **禁止外层文件（非 `/mapper/` 路径）使用 `@Transaction()`**：事务是 mapper 内部实现细节，外层不应感知 conn。查询操作不需要事务一致性；外层需要多表原子写入时，应在 mapper 方法中封装并标 `@Transaction()`，外层只调用该 mapper 方法。**违反此规则会导致运行时 TypeError**（装饰器注入 conn 但外层函数签名没有 conn=None 参数）。
- **任何标 `@Transaction()` 的函数，签名末尾必须有 `conn=None`**（装饰器通过 kwargs 注入 conn，函数必须接受该参数）。GATE-D 静态检查会强制校验。

### 5. 函数拆分

- 每个功能合理拆分 `def`，避免单个函数过长
- 模块内合理组织文件关系

### 6. Mapper 层职责

- **所有 SQL 必须在 mapper 层**，非 mapper 文件禁止出现任何 SQL 语句
- `mapper/db_utils.py` 是 mapper 内部工具，禁止外层文件导入
- 外层文件只调用 mapper 暴露的业务方法
- 表里面的id字段，必须是主键，禁止自增，使用src/utils/unique_id.py生成唯一id，类型为NUMBER(19)

## LLM Prompt 规范

当 prompt 模板含 JSON 示例且使用 `.format()` 或 f-string 时：

```python
# ✅ 正确：花括号转义
prompt = """输出 json 格式：
{{"topic": "...", "sentiment": "..."}}""".format(topic=xxx)

# ✅ 正确：三引字面量不调用 .format() 无需转义
prompt = """
请分析消息情感。
输出格式：{"topic": "..."}
"""
```

## 主题依赖方向

```
业务模块 → task_manager.progress_service（允许回写进度）
progress_service → 业务模块（禁止，避免循环依赖）
```

## 快速查命令

```bash
# 启动服务
uv run python -m src.server

# 运行测试
uv run pytest src/test/

# group_chat_sentiment 日报生成（只跑统计阶段）
uv run python -m src.group_chat_sentiment.summary.daily.generator --date 2027-07-01
```

# Persistent Agent Memory

You have a persistent, file-based memory system at `${PROJECT_DIR}/.claude/agent-memory/backend/`. This directory already exists — write to it directly with the Write tool (do not run mkdir or check for its existence).
