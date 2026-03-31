from fastapi.testclient import TestClient

from server.app import combined_app


def test_managed_list_tools(monkeypatch):
    def fake_list_tools(catalog: str, schema: str):
        assert catalog == "demo_catalog"
        assert schema == "demo_schema"
        return [
            {
                "name": "demo_catalog__demo_schema__get_customer_count",
                "description": "Count customers",
                "inputSchema": {
                    "type": "object",
                    "properties": {"market": {"type": "string"}},
                    "required": ["market"],
                    "additionalProperties": False,
                },
            }
        ]

    monkeypatch.setattr("server.managed_mcp.routes.list_tools", fake_list_tools)
    client = TestClient(combined_app)

    response = client.post(
        "/api/2.0/mcp/functions/demo_catalog/demo_schema",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["tools"][0]["name"] == "demo_catalog__demo_schema__get_customer_count"


def test_managed_call_tool(monkeypatch):
    def fake_call_tool(
        catalog: str,
        schema: str,
        tool_name: str,
        arguments: dict,
        request_name: str | None = None,
    ):
        assert catalog == "demo_catalog"
        assert schema == "demo_schema"
        assert tool_name == "get_customer_count"
        assert request_name == "demo_catalog__demo_schema__get_customer_count"
        assert arguments == {"market": "AU"}
        return {
            "success": True,
            "result": [{"market": "AU", "customer_count": 3}],
            "columns": ["market", "customer_count"],
        }

    monkeypatch.setattr("server.managed_mcp.routes.call_tool", fake_call_tool)
    client = TestClient(combined_app)

    response = client.post(
        "/api/2.0/mcp/functions/demo_catalog/demo_schema/get_customer_count",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "demo_catalog__demo_schema__get_customer_count",
                "arguments": {"market": "AU"},
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["structuredContent"]["columns"] == ["market", "customer_count"]
    assert body["result"]["structuredContent"]["rows"] == [["AU", 3]]


def test_token_proxy_validation():
    client = TestClient(combined_app)

    response = client.post(
        "/oidc/v1/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "id",
            "client_secret": "secret",
        },
    )

    assert response.status_code == 400
    assert "client_credentials" in response.json()["error"]
