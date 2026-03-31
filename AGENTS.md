# AGENTS.md

This repository is a Databricks Apps MCP server based on the official
`mcp-server-hello-world` template.

## Project layout

- `server/app.py` - creates the FastMCP app and combines FastAPI + MCP routes
- `server/tools.py` - registers MCP tools
- `server/utils.py` - Databricks auth helpers and request header context
- `server/main.py` - local entrypoint
- `app.yaml` - Databricks Apps deployment config
- `grants.sql` - example Unity Catalog / telemetry grants for the app service principal
- `README_Changes.md` - custom changes on top of the official template
- `README_cn.md` - personal Chinese notes for local reference

## Branches

- `main` - keep close to the official template and deployment/issue repro setup
- `ucf` - contains the Unity Catalog function auto-discovery changes

If the user asks about UCF auto-discovery work, check whether they want work on
the `ucf` branch rather than `main`.

## Current UCF design

On branch `ucf`, the main custom logic lives under:

- `server/ucf/discovery.py`
- `server/ucf/executor.py`

The intent is to keep the official template structure mostly unchanged while
grouping UCF-specific logic in `server/ucf/`.

## Databricks app setup notes

For the UCF-enabled version, the Databricks App needs:

- an App resource named `sql-warehouse`
- `DATABRICKS_WAREHOUSE_ID` from `valueFrom: sql-warehouse`
- `DATABRICKS_UC_FUNCTIONS_CATALOG`
- `DATABRICKS_UC_FUNCTIONS_SCHEMA`

If `sql-warehouse` is not configured, app startup can fail with:

```text
Error resolving resource sql-warehouse specified in app.yaml
```

If UC permissions are missing, startup may log:

```text
Discovered 0 UC functions from `workspace.demo`: (none)
```

## Auth behavior

- Local runs: `WorkspaceClient()` uses the developer's Databricks auth
- Databricks App runs: detect via `DATABRICKS_APP_NAME`
- End-user auth comes from `x-forwarded-access-token`
- `get_user_authenticated_workspace_client()` requires that header in app mode

## Working style for this repo

- Preserve the official template structure unless the user explicitly asks for a refactor
- Keep custom enhancements isolated and easy to diff against the template
- Prefer adding new feature logic under a focused subpackage instead of crowding `server/`
- Do not add telemetry or request-logging features unless explicitly requested
- Do not add absolute local filesystem paths to committed repo files

## Validation

For meaningful code changes, prefer:

1. `uv run pytest tests/ -v`
2. `uv run python -m compileall server`
3. Local startup verification when relevant
