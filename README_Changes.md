# README Changes

This document summarizes what was added on top of the official Databricks
`mcp-server-hello-world` template.

## What Changed from the Official Template

Compared with the original Databricks template, this version adds automatic
Unity Catalog function discovery and registration.

Instead of manually adding one MCP tool at a time in `server/tools.py`, the
server can:

- discover UC functions from a configured `catalog.schema`
- fetch function metadata from the Databricks Functions API
- generate FastMCP-compatible tool signatures dynamically
- execute UC functions through Databricks SQL statement execution

The main added files are:

- `server/ucf/discovery.py`
- `server/ucf/executor.py`

This keeps the overall template structure intact while making it easier to
compare the original template with the auto-discovery implementation.

## Databricks Setup Steps

Before deploying this UCF-enabled version, complete these steps in Databricks:

1. Create or confirm that the target Unity Catalog functions already exist in the target schema, for example `workspace.demo`.
2. Open the Databricks App Overview page for this app.
3. Under **App resources**, add a SQL warehouse resource with the key `sql-warehouse`.
4. Make sure the app service principal has the required grants by running the SQL in `grants.sql`.

## App Configuration

The UC auto-discovery flow uses these environment variables:

- `DATABRICKS_WAREHOUSE_ID`: required for executing discovered UC functions
- `DATABRICKS_UC_FUNCTIONS_CATALOG`: required
- `DATABRICKS_UC_FUNCTIONS_SCHEMA`: required
- `DATABRICKS_UC_TOOL_PREFIX`: optional

Example Databricks App config:

```yaml
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: DATABRICKS_UC_FUNCTIONS_CATALOG
    value: "workspace"
  - name: DATABRICKS_UC_FUNCTIONS_SCHEMA
    value: "demo"
```

In the Databricks App Overview page, add an App resource under **App resources**
with the key `sql-warehouse`, so `DATABRICKS_WAREHOUSE_ID` can be resolved from
`valueFrom: sql-warehouse`.

## Grant SQL

Run the SQL statements in `grants.sql` for the current Databricks App service principal.

At minimum, the app service principal needs:

- `USE CATALOG` on the target catalog
- `USE SCHEMA` on the target schema
- `EXECUTE ON SCHEMA` on the target schema

If this resource is not configured, app startup can fail with an error like:

```text
[ERROR] Error resolving resource sql-warehouse specified in app.yaml.
Please make sure to configure a resource with name sql-warehouse
```

## Common Failure Symptoms

- If the `sql-warehouse` App resource is missing, app startup can fail with:
  - `Error resolving resource sql-warehouse specified in app.yaml`
- If UC permissions are missing, discovery may log:
  - `Discovered 0 UC functions from workspace.demo: (none)`
