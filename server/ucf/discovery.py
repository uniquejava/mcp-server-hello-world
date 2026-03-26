"""
Metadata discovery and MCP registration for Unity Catalog functions.
"""

import os
from typing import Any

from databricks.sdk.service.catalog import FunctionInfo

from server import utils
from server.ucf.executor import create_tool_function

CATALOG_ENV = "DATABRICKS_UC_FUNCTIONS_CATALOG"
SCHEMA_ENV = "DATABRICKS_UC_FUNCTIONS_SCHEMA"
PREFIX_ENV = "DATABRICKS_UC_TOOL_PREFIX"


def get_discovery_settings() -> tuple[str | None, str | None, str]:
    """Read discovery settings from environment variables."""
    return (
        os.getenv(CATALOG_ENV),
        os.getenv(SCHEMA_ENV),
        os.getenv(PREFIX_ENV, ""),
    )


def discover_functions(catalog_name: str, schema_name: str) -> list[FunctionInfo]:
    """Fetch full function metadata for one UC schema."""
    print(f"Discovering UC functions from `{catalog_name}.{schema_name}`")
    workspace_client = utils.get_workspace_client()
    functions_api = workspace_client.functions

    function_infos: list[FunctionInfo] = []
    for function_stub in functions_api.list(catalog_name=catalog_name, schema_name=schema_name):
        full_name = function_stub.full_name or function_stub.name
        if not full_name:
            print("Skipping function stub with no full_name/name in discovery response")
            continue
        print(f"Loading UC function metadata for `{full_name}`")
        function_infos.append(functions_api.get(name=full_name))

    discovered_names = [function_info.full_name or function_info.name for function_info in function_infos]
    print(
        f"Discovered {len(function_infos)} UC functions from `{catalog_name}.{schema_name}`: "
        f"{', '.join(discovered_names) if discovered_names else '(none)'}"
    )
    return function_infos


def register_discovered_tools(
    mcp_server: Any,
    *,
    catalog_name: str | None = None,
    schema_name: str | None = None,
    name_prefix: str | None = None,
) -> int:
    """Discover UC functions and register them as MCP tools."""
    env_catalog, env_schema, env_prefix = get_discovery_settings()
    catalog = catalog_name or env_catalog
    schema = schema_name or env_schema
    prefix = env_prefix if name_prefix is None else name_prefix

    if not catalog or not schema:
        print(
            "Skipping UC function auto-registration because "
            f"`{CATALOG_ENV}` or `{SCHEMA_ENV}` is not set."
        )
        return 0

    registered_names: set[str] = set()
    registered_count = 0
    print(
        f"Starting UC function auto-registration for `{catalog}.{schema}` "
        f"with tool prefix `{prefix}`"
    )
    function_infos = discover_functions(catalog, schema)

    for function_info in function_infos:
        tool_function = create_tool_function(function_info, name_prefix=prefix)
        if tool_function.__name__ in registered_names:
            raise ValueError(f"Duplicate generated tool name: `{tool_function.__name__}`")
        print(
            f"Registering MCP tool `{tool_function.__name__}` for "
            f"`{function_info.full_name or function_info.name}`"
        )
        mcp_server.tool(tool_function)
        registered_names.add(tool_function.__name__)
        registered_count += 1

    print(
        f"Finished UC function auto-registration for `{catalog}.{schema}`. "
        f"Registered {registered_count} tools."
    )
    return registered_count
