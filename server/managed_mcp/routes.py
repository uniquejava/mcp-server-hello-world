"""FastAPI routes for Databricks managed-MCP compatibility."""

from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server.managed_mcp.models import JsonRpcCallParams, JsonRpcRequest
from server.managed_mcp.service import (
    build_structured_content,
    call_tool,
    list_tools,
    proxy_token_request,
)

router = APIRouter()


def _jsonrpc_error(request_id: int | str | None, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        },
    )


@router.post("/oidc/v1/token")
async def token_proxy(request: Request) -> JSONResponse:
    """Proxy limited OAuth token requests to the workspace host."""
    raw_body = (await request.body()).decode("utf-8")
    parsed_form = {
        key: values[-1]
        for key, values in parse_qs(raw_body, keep_blank_values=True).items()
        if values
    }
    try:
        status_code, payload = proxy_token_request(parsed_form)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return JSONResponse(status_code=status_code, content=payload)


@router.post("/api/2.0/mcp/functions/{catalog}/{schema}")
async def managed_list_tools(catalog: str, schema: str, rpc_request: JsonRpcRequest) -> JSONResponse:
    """Handle Databricks managed-MCP-compatible `tools/list` requests."""
    if rpc_request.method != "tools/list":
        return _jsonrpc_error(rpc_request.id, -32601, "Only `tools/list` is supported on this route.")

    tools = [tool.model_dump() if hasattr(tool, "model_dump") else tool for tool in list_tools(catalog, schema)]
    return JSONResponse(
        status_code=200,
        content={
            "jsonrpc": "2.0",
            "id": rpc_request.id,
            "result": {"tools": tools},
        },
    )


@router.post("/api/2.0/mcp/functions/{catalog}/{schema}/{tool_name}")
async def managed_call_tool(
    catalog: str,
    schema: str,
    tool_name: str,
    rpc_request: JsonRpcRequest,
) -> JSONResponse:
    """Handle Databricks managed-MCP-compatible `tools/call` requests."""
    if rpc_request.method != "tools/call":
        return _jsonrpc_error(rpc_request.id, -32601, "Only `tools/call` is supported on this route.")

    params = rpc_request.params
    if isinstance(params, JsonRpcCallParams):
        request_name = params.name
        arguments = params.arguments
    elif isinstance(params, dict):
        request_name = params.get("name")
        arguments = params.get("arguments", {})
    else:
        request_name = None
        arguments = {}

    try:
        execution_result = call_tool(
            catalog,
            schema,
            tool_name,
            arguments=arguments,
            request_name=request_name,
        )
    except LookupError as exc:
        return _jsonrpc_error(rpc_request.id, -32004, str(exc))

    if not execution_result.get("success"):
        return _jsonrpc_error(
            rpc_request.id,
            -32000,
            execution_result.get("message", "Tool execution failed."),
        )

    structured_content = build_structured_content(execution_result)
    return JSONResponse(
        status_code=200,
        content={
            "jsonrpc": "2.0",
            "id": rpc_request.id,
            "result": {
                "content": [{"type": "text", "text": str(execution_result.get("result"))}],
                "structuredContent": structured_content,
            },
        },
    )
