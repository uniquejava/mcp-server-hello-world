"""Service helpers for Databricks managed-MCP compatibility routes."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from databricks.sdk.service.catalog import FunctionInfo, FunctionParameterInfo

from server import utils
from server.managed_mcp.models import ToolDescriptor
from server.ucf.discovery import discover_functions
from server.ucf.executor import execute_function, get_input_params, get_python_type

TOKEN_TIMEOUT_SECONDS = 30


def get_function_short_name(function_info: FunctionInfo) -> str:
    """Return the short function name used in compatibility URLs."""
    if function_info.name:
        return function_info.name

    full_name = function_info.full_name or ""
    if "." in full_name:
        return full_name.rsplit(".", maxsplit=1)[-1]
    return full_name


def build_managed_tool_name(catalog: str, schema: str, function_info: FunctionInfo) -> str:
    """Return a managed-MCP-style tool name."""
    return f"{catalog}__{schema}__{get_function_short_name(function_info)}"


def get_json_schema_type(param: FunctionParameterInfo) -> str:
    """Map Python parameter types to JSON Schema types."""
    python_type = get_python_type(param)
    if python_type is bool:
        return "boolean"
    if python_type is int:
        return "integer"
    if python_type is float:
        return "number"
    return "string"


def build_input_schema(function_info: FunctionInfo) -> dict[str, Any]:
    """Build a JSON schema for one UC function."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in get_input_params(function_info):
        properties[param.name] = {
            "type": get_json_schema_type(param),
            "title": param.name,
            "description": param.comment or "Function argument.",
        }
        if param.parameter_default is None:
            required.append(param.name)
        else:
            properties[param.name]["default"] = param.parameter_default

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def build_tool_descriptor(catalog: str, schema: str, function_info: FunctionInfo) -> ToolDescriptor:
    """Convert UC metadata into a managed-MCP-style tool descriptor."""
    return ToolDescriptor(
        name=build_managed_tool_name(catalog, schema, function_info),
        description=function_info.comment or f"Call Unity Catalog function `{function_info.full_name}`.",
        inputSchema=build_input_schema(function_info),
    )


def list_tools(catalog: str, schema: str) -> list[ToolDescriptor]:
    """List compatible tools for one catalog/schema."""
    return [
        build_tool_descriptor(catalog, schema, function_info)
        for function_info in discover_functions(catalog, schema)
    ]


def _candidate_function_names(catalog: str, schema: str, tool_name: str, request_name: str | None) -> set[str]:
    candidates = {
        tool_name,
        f"{catalog}.{schema}.{tool_name}",
        f"{catalog}__{schema}__{tool_name}",
    }
    if request_name:
        candidates.add(request_name)
        if "__" in request_name:
            candidates.add(request_name.rsplit("__", maxsplit=1)[-1])
        if "." in request_name:
            candidates.add(request_name.rsplit(".", maxsplit=1)[-1])
    return candidates


def resolve_function_info(
    catalog: str, schema: str, tool_name: str, request_name: str | None = None
) -> FunctionInfo:
    """Resolve one requested tool name to UC metadata."""
    candidates = _candidate_function_names(catalog, schema, tool_name, request_name)

    for function_info in discover_functions(catalog, schema):
        full_name = function_info.full_name or ""
        short_name = get_function_short_name(function_info)
        managed_name = build_managed_tool_name(catalog, schema, function_info)
        if full_name in candidates or short_name in candidates or managed_name in candidates:
            return function_info

    raise LookupError(
        f"Unable to find Unity Catalog function `{tool_name}` in `{catalog}.{schema}`."
    )


def _coerce_rows(result: Any, columns: list[str]) -> list[list[Any]]:
    """Convert executor output into structuredContent rows."""
    if result is None:
        return []
    if isinstance(result, dict):
        return [[result.get(column) for column in columns]]
    if isinstance(result, list):
        if not result:
            return []
        first_item = result[0]
        if isinstance(first_item, dict):
            return [[row.get(column) for column in columns] for row in result]
        if isinstance(first_item, list):
            return result
        return [[item] for item in result]
    return [[result]]


def build_structured_content(execution_result: dict[str, Any]) -> dict[str, Any]:
    """Build managed-MCP-style structured content from executor output."""
    result = execution_result.get("result")
    columns = execution_result.get("columns")

    if not columns:
        if isinstance(result, dict):
            columns = list(result.keys())
        elif isinstance(result, list) and result and isinstance(result[0], dict):
            columns = list(result[0].keys())
        else:
            columns = ["result"]

    return {
        "columns": columns,
        "rows": _coerce_rows(result, columns),
    }


def call_tool(
    catalog: str,
    schema: str,
    tool_name: str,
    arguments: dict[str, Any],
    request_name: str | None = None,
) -> dict[str, Any]:
    """Execute a compatible tool request."""
    function_info = resolve_function_info(catalog, schema, tool_name, request_name=request_name)

    call_arguments = dict(arguments)
    meta = call_arguments.pop("_meta", None)
    if isinstance(meta, dict) and meta.get("warehouse_id") and "warehouse_id" not in call_arguments:
        call_arguments["warehouse_id"] = meta["warehouse_id"]

    return execute_function(function_info, call_arguments)


def proxy_token_request(form_data: dict[str, str]) -> tuple[int, dict[str, Any]]:
    """Forward a client-credentials token request to the workspace host."""
    if form_data.get("grant_type") != "client_credentials":
        raise ValueError("Only `grant_type=client_credentials` is supported.")

    for required_key in ("client_id", "client_secret"):
        if not form_data.get(required_key):
            raise ValueError(f"Missing required form field: `{required_key}`")

    workspace_host = utils.get_workspace_host().rstrip("/")
    request = Request(
        f"{workspace_host}/oidc/v1/token",
        data=urlencode(form_data).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=TOKEN_TIMEOUT_SECONDS) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"error": body}
