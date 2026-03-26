-- Grants for the current Databricks App service principal.
-- App SP client ID: a0aff86f-ded3-4634-987f-aeb4077c3257

-- Base catalog/schema access for the app service principal.
GRANT USE CATALOG ON CATALOG workspace TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;
GRANT USE SCHEMA ON SCHEMA workspace.demo TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;

-- Required for UC function auto-discovery and execution from workspace.demo.
GRANT EXECUTE ON SCHEMA workspace.demo TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;

-- Optional telemetry table access for debugging and validation.
GRANT SELECT ON TABLE workspace.demo.otel_logs TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;
GRANT MODIFY ON TABLE workspace.demo.otel_logs TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;

GRANT SELECT ON TABLE workspace.demo.otel_spans TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;
GRANT MODIFY ON TABLE workspace.demo.otel_spans TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;

GRANT SELECT ON TABLE workspace.demo.otel_metrics TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;
GRANT MODIFY ON TABLE workspace.demo.otel_metrics TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;

GRANT SELECT ON TABLE workspace.demo.otel_annotations TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;
GRANT MODIFY ON TABLE workspace.demo.otel_annotations TO `a0aff86f-ded3-4634-987f-aeb4077c3257`;
