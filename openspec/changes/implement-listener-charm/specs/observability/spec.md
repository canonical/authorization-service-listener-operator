## Purpose

This capability governs how the Authorization Service Listener integrates with the Canonical Observability Stack (COS) and Kubernetes compute resource management. It covers Prometheus metrics scraping, log forwarding to Loki, Grafana dashboard publishing, distributed tracing via Tempo, and Kubernetes resource patching.

---

## ADDED Requirements

### Requirement: Charm exposes Prometheus scraping metrics via metrics-endpoint relation
The charm SHALL provide a `metrics-endpoint` relation (interface: `prometheus_scrape`, provider: `prometheus-k8s`) utilizing `MetricsRelationHandler` from `authorization-service-operator-shared`.

#### Scenario: Metrics handler configures Pebble environment and scrape target
- **WHEN** `MetricsRelationHandler` is initialized and passed to `render_pebble_layer`
- **THEN** `MetricsRelationHandler` registers the unit's scrape target on port `9100` and path `/metrics` along with Prometheus alert rules from `src/prometheus_alert_rules/`
- **AND** `METRICS_ENABLED=true`, `METRICS_PORT=9100`, and `METRICS_PATH=/metrics` are added to the Pebble environment

---

### Requirement: Charm forwards logs to Loki via logging relation
The charm SHALL consume the `logging` relation endpoint (interface: `loki_push_api`, provider: `loki-k8s`) utilizing `LogForwarder` / Loki charm library.

#### Scenario: Loki relation is established
- **WHEN** the `logging` relation is joined and the Loki endpoint is available
- **THEN** the charm configures the workload to forward logs to the provided Loki push URL and publishes Loki alert rules from `src/loki_alert_rules/`

#### Scenario: Loki relation is absent
- **WHEN** no `logging` relation is present
- **THEN** the charm continues to operate and logs are emitted locally only

---

### Requirement: Charm provides a Grafana dashboard via relation
The charm SHALL provide a `grafana-dashboard` relation endpoint (interface: `grafana_dashboard`, provider: `grafana-k8s`) utilizing `GrafanaDashboardHandler` from the shared library.

#### Scenario: Grafana relation is established
- **WHEN** the `grafana-dashboard` relation is joined
- **THEN** `GrafanaDashboardHandler` automatically publishes the pre-configured JSON dashboards inside `src/grafana_dashboards` to the relation databag

---

### Requirement: Charm enables distributed tracing when the tracing relation is joined
The charm SHALL consume the `tracing` relation (interface: `tracing`, provider: `tempo-coordinator-k8s`) requesting the `otlp_grpc` protocol. When joined and ready, `TELEMETRY_ENABLED` SHALL be set to `true`, `OTEL_EXPORTER_OTLP_ENDPOINT` SHALL be set from the `otlp_grpc` relation data, and `OTEL_SERVICE_NAME` SHALL be set to `"authorization-service-listener"`.

#### Scenario: Tracing relation is established
- **WHEN** the `tracing` relation is joined and the provider publishes an `otlp_grpc` endpoint
- **THEN** the charm sets `TELEMETRY_ENABLED=true`, `OTEL_EXPORTER_OTLP_ENDPOINT=<endpoint>`, and `OTEL_SERVICE_NAME="authorization-service-listener"` in the Pebble environment
- **AND** `_on_holistic_handler()` re-applies the Pebble layer with the updated env vars

#### Scenario: Tracing relation is absent
- **WHEN** no `tracing` relation is present or ready
- **THEN** `TELEMETRY_ENABLED=false` (from `DEFAULT_CONTAINER_ENV`) and `OTEL_SERVICE_NAME="authorization-service-listener"`
- **AND** the unit does NOT enter `BlockedStatus`

---

### Requirement: Kubernetes Compute Resources Patching
The charm SHALL instantiate `KubernetesComputeResourcesPatch` to manage container CPU and memory requests/limits based on charm configuration.
- The charm SHALL observe `resources_patch.on.patch_failed` and include `self.resources_patch.get_status()` in `_on_collect_status`.

#### Scenario: Compute resource patch fails
- **WHEN** resource limits cannot be applied by K8s
- **THEN** `_on_collect_status` reflects the non-active patch status
