## Context

The `authorization-service-listener-operator` is a Juju charmed operator that automates the deployment, lifecycle management, and integration of the Authorization Service's listener component on Kubernetes.

Upstream `authorization-service` (PR #117) introduced configurable operating modes (`platform`, `standalone`, and `hybrid`) under a dedicated `listener` configuration section (`LISTENER_MODE`, `LISTENER_FEDERATED_SERVICES_STRATEGY`, `LISTENER_FEDERATED_SERVICES`), removing `KAFKA_ENABLED` and decoupling the federated service registry from `KafkaConfig`:
- **`standalone` mode**: Starts a gRPC server (`GRPC_PORT`, default `9091`) exposing `PermissionIngestionService/IngestPermissionUpdate` authenticated via Ory Hydra Bearer JWTs (`EXTAUTHZ_JWK_SET_URL`), alongside the HTTP health check server (`HTTP_PORT`, default `8070`, `GET /healthz`) and optional Prometheus metrics server (`METRICS_PORT`), without requiring or initializing a Kafka broker.
- **`platform` mode**: Preserves the Kafka consumer pipeline (`KAFKA_BROKERS`, `KAFKA_CONSUMER_GROUP`).
- **`hybrid` mode**: Runs both the Kafka consumer pipeline and the gRPC ingestion server concurrently.

For now, the charmed operator is scoped to support only `standalone` mode (`ingestion_mode=standalone`), with the possibility to introduce other ingestion modes in the future (where `platform` mode will require the `kafka` integration). The charm does not require OpenFGA and does not block if the `kafka` integration is missing.

This operator follows Canonical's modern charm design patterns established in `authorization-service-operator` and `authorization-service-worker-operator`:
- Using Astral's `uv` builder plugin for deterministic and high-speed packaging.
- Reusing common libraries from `authorization-service-operator-shared`.
- Clean separation of concerns with unified secret handling for database credentials via the `authorization-service-info` relation and JWKS discovery via `sts-info`.
- Deterministic priority-based status collection in `_on_collect_status`.

## Goals / Non-Goals

**Goals:**
- Implement a robust charmed operator for the Authorization Service Listener using Python `ops` 3.x.
- Support `standalone` ingestion mode via the `ingestion_mode` charm configuration option (default `"standalone"`), rejecting unsupported modes with `BlockedStatus` until future modes (`platform`, `hybrid`) are implemented.
- Maximize code reuse by consuming `authorization-service-operator-shared` (`AuthorizationServiceInfoRequirer`, `STSRelationHandler`, `MetricsRelationHandler`, `GrafanaDashboardHandler`, `PebbleService`, `WorkloadService`, `CommandLine`, `CharmConfig`).
- Securely receive database credentials and migration readiness from `authorization-service-operator` via `authorization-service-info`.
- Require `sts-info` integration via `STSRelationHandler` when `ingestion_mode=standalone` to supply `EXTAUTHZ_JWK_SET_URL` for Bearer JWT verification on the gRPC ingestion endpoint, blocking when the relation is missing and waiting when not ready.
- Ensure the charm integrates with `kafka` via `KafkaRelationHandler` (`optional: true` in `charmcraft.yaml`) without blocking when the `kafka` relation is missing.
- Configure the Pebble execution layer to start `/usr/bin/app listen` with `LISTENER_MODE=standalone` and `LISTENER_FEDERATED_SERVICES_STRATEGY=fs`, open HTTP (`8070`) and gRPC (`9091`) ports on `pebble_ready`, and use `http://localhost:8070/healthz` for the Pebble readiness check.
- Implement COS observability (Prometheus scraping, Grafana dashboards, Loki logging, Tempo tracing) and Kubernetes compute resources patching.
- Provide comprehensive unit tests with Scenario (`ops.testing`), top-level imports, and no artificial mock fixtures.

**Non-Goals:**
- Supporting `platform` or `hybrid` ingestion modes in this iteration (kept as a planned future extension of `ingestion_mode`).
- Connecting directly to PostgreSQL (`postgresql-k8s`) or running migrations locally (the server charm manages PostgreSQL and executes schema migrations).
- Integrating with OpenFGA (the listener does not interface with OpenFGA).

## Architecture & Decisions

### Decision 1: Shared Library Dependency (`authorization-service-operator-shared`)
- **Choice**: Consume common relation handlers and service abstractions directly from `authorization-service-operator-shared`.
- **Rationale**: The shared library centralizes configuration parsing, CLI interactions, secret decoding, and relation handlers across the Authorization Service charm ecosystem.
- **Components Used**:
  - `AuthorizationServiceInfoRequirer`: Handles `authorization-service-info` relation events, decodes Juju secrets for DB password, and constructs `DatabaseConfig`.
  - `STSRelationHandler`: Wraps `StsInfoRequirer` (`charms.secure_token_service.v0.sts_info`) on the `sts-info` endpoint, extracting `jwks_url`, `grpc_address`, and `tls_enabled` and producing `EXTAUTHZ_JWK_SET_URL`, `STS_ADDRESS`, and `STS_USE_TLS`.
  - `KafkaRelationHandler`: Wraps `ResourceRequirerEventHandler` (`charms.data_platform_libs.v1.data_interfaces`) on the optional `kafka` endpoint, requesting `resource="permissions.authorization_service"`, `extra-user-roles="producer,consumer"`, and `consumer-group-prefix="authorization-service"`, and producing `KAFKA_*` environment variables when the relation is present and ready.
  - `MetricsRelationHandler`, `GrafanaDashboardHandler`, & `TracingConfig`: Coordinates COS Prometheus metrics (`METRICS_ENABLED=true`, `METRICS_PORT=9100`, `METRICS_PATH=/metrics`), Grafana dashboard endpoints, and OpenTelemetry tracing (`TELEMETRY_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`) via `TracingEndpointRequirer`, alongside Loki log forwarding via `LogForwarder`.
  - `PebbleService` & `WorkloadService`: Encapsulates Pebble layer rendering with readiness checks (`http://localhost:8070/healthz`), port opening (`open_port()`), planning, service restart on failure, failure state detection (`is_failing()`), and workload version reporting.
  - `CommandLine`: Handles workload CLI execution (`/usr/bin/app version`, `/usr/bin/app migrate status`).

### Decision 2: Ingestion Mode Configuration (`ingestion_mode`) and Future Mode Extensibility
- **Choice**: Define `ingestion_mode` in `charmcraft.yaml` (type `string`, default `standalone`), validate it against `VALID_INGESTION_MODES = frozenset({"standalone"})`, and inject `LISTENER_MODE=<ingestion_mode>` and `LISTENER_FEDERATED_SERVICES_STRATEGY=fs` into the Pebble environment.
- **Rationale**: Upstream PR #117 introduced `LISTENER_MODE` (`platform`, `standalone`, `hybrid`) and `LISTENER_FEDERATED_SERVICES_STRATEGY` under `ListenerConfig`. Currently only `standalone` mode is supported in the charm.
- **Note on Future Ingestion Modes**: When `platform` (and `hybrid`) ingestion modes are introduced in future iterations, `VALID_INGESTION_MODES` will be expanded to include `"platform"` (and `"hybrid"`), and the `kafka` relation (`KafkaRelationHandler`) will be required when `ingestion_mode` requires Kafka. Until then, `kafka` is marked `optional: true` in `charmcraft.yaml` so missing `kafka` integration never blocks the charm, while still handling the relation via `KafkaRelationHandler` when integrated.

### Decision 3: STS Integration (`sts-info`) Required in Standalone Mode
- **Choice**: When `ingestion_mode == "standalone"`, require the `sts-info` relation (`optional: false` in `charmcraft.yaml`), gate Pebble planning on `_is_sts_relation_present` and `_is_sts_ready`, and stop the workload when `sts-info` is broken.
- **Rationale**: In `standalone` mode, `cmd/listen.go` validates `ComponentExtAuthz` (`EXTAUTHZ_JWK_SET_URL`) and verifies Bearer JWTs on every incoming `PermissionIngestionService/IngestPermissionUpdate` gRPC request against the JWKS endpoint provided by `sts-info`.

### Decision 4: Database Credentials via `authorization-service-info`
- **Choice**: Consume database credentials via `AuthorizationServiceInfoRequirer` rather than a direct `pg-database` relation.
- **Rationale**: The server charm provisions database users, manages migration state, and shares credentials via Juju secrets. Listener checks `CommandLine.migrate_status(db.dsn)` to verify that migrations are up-to-date before starting.

### Decision 5: Pebble Layer Command, Ports, & Health Check
- **Choice**: Start the application with `/usr/bin/app listen`, open HTTP (`8070`) and gRPC (`9091`) ports via `WorkloadService.open_port()` on `pebble_ready`, and configure the Pebble HTTP readiness check at `http://localhost:8070/healthz` (`include_checks=True`).
- **Rationale**: In `standalone` mode, the listener serves gRPC ingestion requests on port `9091` and exposes an unconditional HTTP liveness probe at `http://localhost:8070/healthz` (independent of whether Prometheus metrics are enabled).

### Decision 6: Deterministic Priority Status Collection
- **Choice**: In `_on_collect_status`, evaluate conditions deterministically in strict priority order via decoupled status getters:
  1. Configuration status (`_get_config_status`): config validation (`log_level` and `ingestion_mode` must be valid) -> `BlockedStatus("Invalid configuration: ...")`
  2. Prerequisite status (`_get_prerequisite_status`):
     - `container_connectivity` -> `WaitingStatus("Waiting for container")`
     - `authorization-service-info` relation presence -> `BlockedStatus("Missing required relation: authorization-service-info")`
     - Database credentials readiness -> `WaitingStatus("Waiting for database credentials")`
     - When `ingestion_mode == "standalone"`:
       - `sts-info` relation presence -> `BlockedStatus("Missing required relation: sts-info")`
       - `sts-info` readiness (`jwks_url` available) -> `WaitingStatus("STS relation is not ready yet")`
  3. Migration status (`_get_migration_status`):
     - Migration check execution error -> `BlockedStatus("Failed to check database migration status, see logs")`
     - Server migration pending -> `WaitingStatus("Waiting for the server to run migration")`
  4. Workload status (`_get_workload_status`):
     - Workload failing (`is_failing()`) -> `BlockedStatus("Failed to start the service, please check the container logs")`
     - Workload not running -> `WaitingStatus("Waiting for workload to start")`
  5. Resource patch status -> `event.add_status(self.resources_patch.get_status())`
  6. Active status -> `ActiveStatus()`

### Decision 7: Unit Testing Strategy
- **Choice**: Use `ops.testing` (Scenario) with 100% top-level imports and direct relation databag assertions.
- **Rationale**: Avoids brittle static mocks, ensures production databag parsing is exercised, and maintains clean linting standards.

## Risks / Trade-offs

- **[Risk]**: Unavailability of STS JWKS endpoint during listener startup in `standalone` mode.
  - *Mitigation*: The charm gates startup on `STSRelationHandler.is_ready()` and replans/stops the Pebble service upon relation updates or removal.
- **[Risk]**: Database migrations pending on server charm.
  - *Mitigation*: `CommandLine.migrate_status(db.dsn)` gates the listener in `WaitingStatus("Waiting for the server to run migration")` until the server completes schema migrations.
