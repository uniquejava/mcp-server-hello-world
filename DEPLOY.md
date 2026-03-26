
## Deploy

```sh
# Login
databricks auth login --host https://dbc-61e256ef-e253.cloud.databricks.com

# Create a Databricks app to host the MCP server:
$ databricks apps create mcp-server-hello-world

# Upload the source code to Databricks and deploy the app by running the following commands from the directory containing your `app.yaml` file:
$ DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName) && echo $DATABRICKS_USERNAME
$ databricks sync . "/Users/$DATABRICKS_USERNAME/mcp-server-hello-world"

# If not started
$ databricks apps start mcp-server-hello-world

# Deploy
$ databricks apps deploy mcp-server-hello-world --source-code-path "/Workspace/Users/$DATABRICKS_USERNAME/mcp-server-hello-world"

$ databricks apps list
$ databricks apps stop mcp-server-hello-world
$ databricks apps delete mcp-server-hello-world
```

## How to deploy (from dbx app overview page)

https://dbc-61e256ef-e253.cloud.databricks.com/apps/mcp-server-hello-world?o=7474659924928926