"""
Helpers for converting Unity Catalog function metadata into MCP tools.
"""

import os
import re
from collections.abc import Callable
from typing import Any

from databricks.sdk.service.catalog import (
    ColumnTypeName,
    FunctionInfo,
    FunctionParameterInfo,
)
from databricks.sdk.service.sql import (
    Disposition,
    Format,
    StatementParameterListItem,
    StatementState,
)

from server import utils

SUPPORTED_SCALAR_TYPES: dict[ColumnTypeName, type] = {
    ColumnTypeName.BOOLEAN: bool,
    ColumnTypeName.DOUBLE: float,
    ColumnTypeName.FLOAT: float,
    ColumnTypeName.INT: int,
    ColumnTypeName.LONG: int,
    ColumnTypeName.SHORT: int,
    ColumnTypeName.STRING: str,
}


def sanitize_tool_name(name: str) -> str:
    """Convert a UC function name into a valid MCP tool identifier."""
    sanitized = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    if not sanitized:
        raise ValueError("Function name cannot be converted into a valid MCP tool name.")
    if sanitized[0].isdigit():
        sanitized = f"ucf_{sanitized}"
    return sanitized


def get_python_type(param: FunctionParameterInfo) -> type:
    """Map common Databricks SQL types to Python types for MCP schema generation."""
    type_name = param.type_name
    if type_name in SUPPORTED_SCALAR_TYPES:
        return SUPPORTED_SCALAR_TYPES[type_name]

    # TODO: support more SQL types like DECIMAL, DATE/TIMESTAMP, ARRAY, MAP, STRUCT, VARIANT.
    return str


def coerce_default_value(param: FunctionParameterInfo) -> Any:
    """Convert UC metadata defaults into Python defaults when possible."""
    if param.parameter_default is None:
        return None

    raw_value = param.parameter_default
    python_type = get_python_type(param)
    if python_type is bool:
        return raw_value.lower() in {"1", "true", "yes", "y"}
    if python_type is int:
        return int(raw_value)
    if python_type is float:
        return float(raw_value)
    if python_type is str:
        return raw_value

    return raw_value


def get_input_params(function_info: FunctionInfo) -> list[FunctionParameterInfo]:
    """Return input params sorted by position."""
    params = function_info.input_params.parameters if function_info.input_params else None
    return sorted(params or [], key=lambda param: param.position)


def get_return_param_names(function_info: FunctionInfo) -> list[str] | None:
    """Return declared output column names when present."""
    params = function_info.return_params.parameters if function_info.return_params else None
    if not params:
        return None

    names = [param.name for param in params if param.name]
    return names or None


def is_table_function(function_info: FunctionInfo) -> bool:
    """Detect table-valued functions from catalog metadata."""
    return function_info.data_type == ColumnTypeName.TABLE_TYPE


def get_column_names(response, function_info: FunctionInfo) -> list[str] | None:
    """Prefer execution manifest column names, then fall back to declared return params."""
    manifest = response.manifest
    schema = manifest.schema if manifest else None
    columns = schema.columns if schema else None
    if columns:
        names = [column.name for column in columns if column.name]
        if names:
            return names
    return get_return_param_names(function_info)


def parse_result(rows: list[list[Any]] | None, column_names: list[str] | None = None) -> Any:
    """Convert SQL rows into a natural Python result."""
    if not rows:
        return None

    if len(rows) == 1 and len(rows[0]) == 1:
        return rows[0][0]

    if column_names and all(len(row) == len(column_names) for row in rows):
        records = [dict(zip(column_names, row, strict=True)) for row in rows]
        return records[0] if len(records) == 1 else records

    return rows[0] if len(rows) == 1 else rows


def build_statement(function_info: FunctionInfo, params: list[FunctionParameterInfo]) -> str:
    """Build the SQL statement used to execute the UC function."""
    placeholders = ", ".join(f":{param.name}" for param in params)
    function_name = function_info.full_name or function_info.name
    if not function_name:
        raise ValueError("Function metadata is missing full_name/name.")

    if is_table_function(function_info):
        return f"SELECT * FROM {function_name}({placeholders})"
    return f"SELECT {function_name}({placeholders}) AS result"


def execute_function(function_info: FunctionInfo, kwargs: dict[str, Any]) -> dict:
    """Execute one UC function using metadata-derived SQL and parameter binding."""
    warehouse_id = kwargs.pop("warehouse_id", None) or os.getenv("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        return {
            "success": False,
            "message": (
                "SQL warehouse ID is required. Pass `warehouse_id` or set "
                "`DATABRICKS_WAREHOUSE_ID`."
            ),
        }

    params = get_input_params(function_info)
    statement_params: list[StatementParameterListItem] = []
    input_values: dict[str, Any] = {}
    for param in params:
        if param.name in kwargs:
            value = kwargs[param.name]
        elif param.parameter_default is not None:
            value = coerce_default_value(param)
        else:
            return {
                "success": False,
                "message": f"Required parameter `{param.name}` is missing and has no default.",
            }

        input_values[param.name] = value
        statement_params.append(
            StatementParameterListItem(name=param.name, type=param.type_text, value=str(value))
        )

    statement = build_statement(function_info, params)

    try:
        workspace_client = utils.get_workspace_client()
        response = workspace_client.statement_execution.execute_statement(
            statement=statement,
            warehouse_id=warehouse_id,
            parameters=statement_params or None,
            disposition=Disposition.INLINE,
            format=Format.JSON_ARRAY,
            wait_timeout="30s",
        )
    except Exception as exc:
        return {
            "success": False,
            "message": f"Failed to execute Unity Catalog function `{function_info.full_name}`.",
            "error": str(exc),
        }

    status = response.status
    state = str(status.state) if status and status.state else "UNKNOWN"
    if not status or status.state != StatementState.SUCCEEDED:
        error_message = status.error.message if status and status.error else None
        return {
            "success": False,
            "message": f"Unity Catalog function `{function_info.full_name}` execution did not succeed.",
            "state": state,
            "error": error_message,
            "statement_id": response.statement_id,
        }

    rows = response.result.data_array if response.result else None
    column_names = get_column_names(response, function_info)
    result = parse_result(rows, column_names)
    return {
        "success": True,
        "function": function_info.full_name,
        "input": input_values,
        "result": result,
        "columns": column_names,
        "statement_id": response.statement_id,
        "warehouse_id": warehouse_id,
    }


def build_tool_doc(function_info: FunctionInfo) -> str:
    """Build an MCP-friendly docstring from UC metadata."""
    lines = [function_info.comment or f"Call Unity Catalog function `{function_info.full_name}`."]
    params = get_input_params(function_info)
    if params:
        lines.append("")
        lines.append("Args:")
        for param in params:
            default_suffix = ""
            if param.parameter_default is not None:
                default_suffix = f" (default: {param.parameter_default})"
            lines.append(
                f"    {param.name} ({param.type_text}): {param.comment or 'Function argument.'}{default_suffix}"
            )

    lines.append(
        "    warehouse_id (STRING, optional): SQL Warehouse ID. Falls back to "
        "DATABRICKS_WAREHOUSE_ID."
    )
    lines.append("")
    lines.append("Returns:")
    lines.append("    dict: Execution result with success, result, and statement metadata.")
    return "\n".join(lines)


def create_tool_function(function_info: FunctionInfo, *, name_prefix: str = "") -> Callable[..., dict]:
    """Create a FastMCP-compatible tool function from one Unity Catalog function."""
    function_name = sanitize_tool_name(f"{name_prefix}{function_info.name or function_info.full_name}")
    params = get_input_params(function_info)

    namespace: dict[str, Any] = {
        "_executor": lambda **kwargs: execute_function(function_info, kwargs),
        "dict": dict,
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
    }

    signature_parts = ["*"]
    call_parts: list[str] = []
    for param in params:
        python_type = get_python_type(param).__name__
        if param.parameter_default is None:
            signature_parts.append(f"{param.name}: {python_type}")
        else:
            signature_parts.append(
                f"{param.name}: {python_type} = {coerce_default_value(param)!r}"
            )
        call_parts.append(f'"{param.name}": {param.name}')

    signature_parts.append("warehouse_id: str | None = None")
    call_parts.append('"warehouse_id": warehouse_id')

    source = (
        f"def {function_name}({', '.join(signature_parts)}) -> dict:\n"
        f"    return _executor(**{{{', '.join(call_parts)}}})\n"
    )
    exec(source, namespace)
    tool_function = namespace[function_name]
    tool_function.__doc__ = build_tool_doc(function_info)
    return tool_function
