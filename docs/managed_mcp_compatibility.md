# Managed MCP Compatibility Design

This document describes how the custom MCP server should expose a Databricks
managed-MCP-compatible surface so existing agent code can migrate with minimal
changes.

## Goal

Keep the current FastMCP `/mcp` endpoint unchanged, and add a compatibility
layer that lets existing clients continue to:

- fetch an OAuth token from the same host
- list tools from `/api/2.0/mcp/functions/{catalog}/{schema}`
- call tools from `/api/2.0/mcp/functions/{catalog}/{schema}/{tool_name}`

The compatibility layer should be isolated from the core FastMCP app so it is
easy to maintain and compare against the template.

## Migration Strategy

### Server-side changes

Add a new package under `server/managed_mcp/` with clear separation of concerns:

- `server/managed_mcp/models.py`
  - request/response models for the compatibility endpoints
- `server/managed_mcp/service.py`
  - tool listing and invocation logic
  - token proxy logic
- `server/managed_mcp/routes.py`
  - FastAPI router definitions only

Keep UC discovery and execution in `server/ucf/` as the source of truth. The
compatibility layer should call into `server.ucf.discovery` and
`server.ucf.executor`, not duplicate UC-specific logic.

### AI agent changes

The existing agent code can keep its current JSON-RPC payloads and URL shapes.
The only intended client-side change is configuration:

- point `DATABRICKS_HOST` to the custom app host instead of the workspace host
- keep using the same `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`,
  `DATABRICKS_CATALOG`, and `DATABRICKS_SCHEMA`

No second host is required because the custom MCP server will proxy
`POST /oidc/v1/token` to the real Databricks workspace token endpoint.

## Endpoint Design

### 1. Token proxy

`POST /oidc/v1/token`

Behavior:

- accept `application/x-www-form-urlencoded`
- only allow `grant_type=client_credentials`
- forward the form body to the real workspace
- return the upstream token response

Security constraints:

- do not implement a generic proxy
- resolve the upstream workspace host from server-side Databricks config
- do not log client secrets or raw access tokens

### 2. Managed MCP compatible list route

`POST /api/2.0/mcp/functions/{catalog}/{schema}`

Behavior:

- require `method == "tools/list"`
- discover UC functions from the requested `catalog.schema`
- return a JSON-RPC response with a `result.tools` array

Each returned tool should include:

- managed-MCP-style fully qualified tool name:
  `{catalog}__{schema}__{function_name}`
- description from UC metadata
- JSON schema generated from the function parameters

### 3. Managed MCP compatible call route

`POST /api/2.0/mcp/functions/{catalog}/{schema}/{tool_name}`

Behavior:

- require `method == "tools/call"`
- accept either:
  - `params.name == "{catalog}__{schema}__{tool_name}"`, or
  - `params.name == "{tool_name}"`
- execute the UC function using the existing executor
- return a JSON-RPC response containing `result.structuredContent`

`structuredContent` should include:

- `columns`: ordered column names
- `rows`: list-of-lists row data

This matches the existing agent expectation when it converts MCP output to a
`pandas.DataFrame`.

## Authentication Design

The compatibility endpoints should support both:

- `Authorization: Bearer <token>` from external agents
- `x-forwarded-access-token` from Databricks Apps front-door auth

`server/utils.py` should expose a shared helper for extracting a request token.
When a request token is available, the server should prefer it when creating a
Databricks `WorkspaceClient`.

## Implementation Notes

- Keep the existing FastMCP `/mcp` endpoint unchanged.
- Add the compatibility router to the auxiliary FastAPI app in `server/app.py`.
- Additive changes only: do not remove or rename current tools.
- Extend the UC executor response with column metadata so the compatibility
  layer can build `structuredContent` without re-executing SQL.

## Validation

Recommended validation for this change:

1. `uv run pytest tests/ -v`
2. `uv run python -m compileall server`

## Expected agent behavior after migration

The minimal demo should still work with the same sequence:

1. `POST /oidc/v1/token`
2. `POST /api/2.0/mcp/functions/{catalog}/{schema}` with `tools/list`
3. `POST /api/2.0/mcp/functions/{catalog}/{schema}/{tool_name}` with `tools/call`

The only intended operational change is that `DATABRICKS_HOST` now points to
the custom Databricks App instead of the workspace host.
