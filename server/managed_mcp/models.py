"""Models for Databricks managed-MCP compatibility routes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JsonRpcCallParams(BaseModel):
    """JSON-RPC params for tool invocation."""

    name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)


class JsonRpcRequest(BaseModel):
    """Minimal JSON-RPC request model used by compatibility routes."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: JsonRpcCallParams | dict[str, Any] | None = None


class ToolDescriptor(BaseModel):
    """Managed-MCP compatible tool descriptor."""

    name: str
    description: str
    inputSchema: dict[str, Any]
