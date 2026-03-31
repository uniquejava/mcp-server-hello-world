import contextvars
import os
from collections.abc import Mapping

from databricks.sdk import WorkspaceClient

header_store = contextvars.ContextVar("header_store")


def get_request_token(headers: Mapping[str, str] | None = None) -> str | None:
    """Extract a bearer token from supported request headers."""
    headers = headers or header_store.get({})

    authorization = headers.get("authorization") or headers.get("Authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token

    forwarded_token = headers.get("x-forwarded-access-token")
    if forwarded_token:
        return forwarded_token

    return None


def get_workspace_client():
    token = get_request_token()
    if token:
        return WorkspaceClient(token=token, auth_type="pat")
    return WorkspaceClient()


def get_workspace_host() -> str:
    """Return the configured Databricks workspace host."""
    return WorkspaceClient().config.host


def get_user_authenticated_workspace_client():
    # Check if running in a Databricks App environment
    is_databricks_app = "DATABRICKS_APP_NAME" in os.environ

    if not is_databricks_app:
        # Running locally, use default authentication
        return WorkspaceClient()

    # Running in Databricks App, require user authentication token
    token = get_request_token()

    if not token:
        raise ValueError(
            "Authentication token not found in request headers "
            "(`Authorization` bearer token or `x-forwarded-access-token`). "
        )

    return WorkspaceClient(token=token, auth_type="pat")
