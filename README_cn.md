这次迁移的改动主要是：

- 新增 `ROOT/server/ucf/discovery.py`
  - 读取 `DATABRICKS_UC_FUNCTIONS_CATALOG`
  - 读取 `DATABRICKS_UC_FUNCTIONS_SCHEMA`
  - 调 `functions.list()` + `functions.get()`
  - 动态注册 UC functions 为 MCP tools

- 新增 `ROOT/server/ucf/executor.py`
  - 根据 UC metadata 生成 FastMCP-compatible tool signatures
  - 支持常见 scalar 参数、默认值、table function/scalar function

- 更新 `ROOT/server/tools.py`
  - 保留原来的 `health`
  - 保留原来的 `get_current_user`
  - 在 `load_tools()` 末尾接上自动 discovery/register

我还做了基本验证：

- `compileall server` 通过
- 导入 `server.app` 成功
- 在未设置 discovery 环境变量时，能正常启动并打印：
  - `Skipping UC function auto-registration ...`
  - `Successfully registered 0 Unity Catalog Functions as MCP tools`

`app.yaml` 里有：

- `DATABRICKS_WAREHOUSE_ID`
- `DATABRICKS_UC_FUNCTIONS_CATALOG`
- `DATABRICKS_UC_FUNCTIONS_SCHEMA`

其中：

- `DATABRICKS_WAREHOUSE_ID`：执行 UC function 必需
- `DATABRICKS_UC_FUNCTIONS_CATALOG`：discovery 必需
- `DATABRICKS_UC_FUNCTIONS_SCHEMA`：discovery 必需

`DATABRICKS_UC_TOOL_PREFIX` 是可选的，所以我没有默认放进去。

## 原理说明

### `ucf_discovery.py` 是做什么的

`ucf_discovery.py` 负责“发现有哪些 UC functions 可以暴露为 MCP tools”。

它的主要流程是：

- 读取环境变量里的目标 `catalog.schema`
- 调 Databricks Functions API：
  - `functions.list()`
  - `functions.get()`
- 拿到每个 UC function 的完整 metadata
- 调 `create_tool_function(...)` 为每个 function 生成一个可注册的 Python tool function
- 再调用 `mcp_server.tool(...)` 动态注册进去

可以把它理解成“发现和注册层”。

### `ucf_executor.py` 是做什么的

`ucf_executor.py` 负责“把 UC function metadata 变成真正可执行的 MCP tool”。

它里面有两层关键逻辑：

- `create_tool_function(...)`
- `execute_function(...)`

### `create_tool_function(...)` 的原理

它的核心原理是：

- 先从 UC function metadata 里拿到参数信息
- 再动态拼一段 Python 函数源码
- 用 `exec()` 把这段源码变成一个真正的 Python function
- 然后把这个 function 注册成 FastMCP tool

之所以这样做，是因为 FastMCP 更适合接收“有显式参数签名”的真实函数，而不是只有 `**kwargs` 的函数。

例如，如果 UC function 是：

- `workspace.demo.get_customer_detail(customer_id INT)`

生成出来的 Python function 大致会像这样：

```python
def get_customer_detail(*, customer_id: int, warehouse_id: str | None = None) -> dict:
    return _executor(**{
        "customer_id": customer_id,
        "warehouse_id": warehouse_id,
    })
```

如果 UC function 有默认值，例如：

- `workspace.demo.get_top_customers(limit_count INT DEFAULT 2)`

生成出来会像这样：

```python
def get_top_customers(*, limit_count: int = 2, warehouse_id: str | None = None) -> dict:
    return _executor(**{
        "limit_count": limit_count,
        "warehouse_id": warehouse_id,
    })
```

如果 UC function 没有参数，例如：

- `workspace.demo.get_customer_count()`

生成出来会像这样：

```python
def get_customer_count(*, warehouse_id: str | None = None) -> dict:
    return _executor(**{
        "warehouse_id": warehouse_id,
    })
```

所以可以把 `create_tool_function(...)` 理解成：

- 它根据 metadata 动态生成“函数壳子”
- 这个壳子有 FastMCP 需要的显式签名
- 真正执行逻辑并不写在这个壳子里

### `_executor(...)` 是什么

`_executor(...)` 不是 Databricks SDK 的内置对象，也不是 FastMCP 的内置对象。

它是我们在动态生成函数时，提前塞进 `namespace` 里的一个桥接入口。

代码里大致是这样：

```python
namespace = {
    "_executor": lambda **kwargs: execute_function(function_info, kwargs),
    ...
}
```

意思是：

- 动态生成的函数只负责收参数
- 然后把参数交给 `_executor(...)`
- `_executor(...)` 再去调用真正的 `execute_function(...)`

所以 `_executor(...)` 可以理解成：

- 一个薄薄的适配层
- 用来把动态生成的函数和共享执行逻辑接起来

### `execute_function(...)` 是什么

`execute_function(...)` 是真正执行 UC function 的核心执行器。

所有动态生成出来的 MCP tools，最终都会调用它。

它主要做这些事情：

- 读取 `warehouse_id`
- 检查参数是否齐全
- 处理默认参数值
- 生成 SQL 参数绑定
- 根据 function 类型拼 SQL
  - scalar function: `SELECT function(...) AS result`
  - table function: `SELECT * FROM function(...)`
- 调 `statement_execution.execute_statement(...)`
- 检查执行状态
- 解析 SQL 返回结果
- 统一返回一个结构化 dict

所以它的定位可以理解成：

- 所有动态 MCP tools 共用的一套底层执行引擎

### 调用链怎么理解

整个调用链可以这样理解：

1. `register_discovered_tools(...)`
   - 发现 UC functions
   - 为每个 function 调 `create_tool_function(...)`
   - 注册成 MCP tool

2. 某个 MCP tool 被调用
   - 例如 `get_customer_detail(...)`

3. 动态生成的函数壳子执行
   - 它只是把参数交给 `_executor(...)`

4. `_executor(...)` 调用 `execute_function(...)`

5. `execute_function(...)`
   - 拼 SQL
   - 调 Databricks SQL
   - 返回结果

可以用一句话概括：

- `ucf_discovery.py` 负责“找到并注册”
- `create_tool_function(...)` 负责“生成函数壳子”
- `execute_function(...)` 负责“真正执行”
