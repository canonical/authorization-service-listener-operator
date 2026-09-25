## Context

The `authorization-service-listener-operator` is a Juju charmed operator that automates the deployment, lifecycle management, and integration of the Authorization Service's listener component on Kubernetes. 

The listener is a stateful service that consumes authorization events asynchronously from Apache Kafka and updates state in PostgreSQL. It does not provide an external HTTP/gRPC serving endpoint (unlike the server component) and does not require OpenFGA.

This operator follows Canonical's modern charm design patterns established in `authorization-service-operator` and `authorization-service-worker-operator`:
- Using Astral's `uv` builder plugin for deterministic and high-speed packaging.
- Reusing common libraries from `authorization-service-operator-shared` pinned to `fix/kafka`.
- Clean separation of concerns with unified secret handling for database credentials via the `authorization-service-info` relation.
- Deterministic priority-based status collection in `_on_collect_status`.

## Goals / Non-Goals

**Goals:**
- Implement a robust charmed operator for the Authorization Service Listener using Python `ops` 3.x.
- Maximize code reuse by consuming `authorization-service-operator-shared` (`AuthorizationServiceInfoRequirer`, `KafkaRelationHandler`, `MetricsRelationHandler`, `GrafanaDashboardHandler`, `PebbleService`, `WorkloadService`, `CommandLine`, `CharmConfig`).
- Securely receive database credentials and migration readiness from `authorization-service-operator` via `authorization-service-info`.
- Integrate with Apache Kafka clusters via `authorization_service_operator_shared.kafka.KafkaRelationHandler` (`data_platform_libs.v1.data_interfaces.ResourceRequirerEventHandler` requesting `producer,consumer` extra user roles and `authorization-service` consumer group prefix).
- Configure Pebble execution layer to start the service with `/usr/bin/app listen` with metrics readiness checks (`include_checks=True`, `check_url="http://localhost:9100/metrics"`).
- Implement full COS observability (Prometheus scraping, Grafana dashboards, Loki logging, Tempo tracing) and Kubernetes compute resources patching.
- Provide comprehensive unit tests with Scenario (`ops.testing`), top-level imports, and no artificial mock fixtures.

**Non-Goals:**
- Connecting directly to PostgreSQL (`postgresql-k8s`) or running migrations locally (the server charm manages PostgreSQL and executes schema migrations).
- Integrating with OpenFGA (the listener does not interface with OpenFGA).
- Exposing an HTTP ingress / serving endpoint.

## Architecture & Decisions

### Decision 1: Shared Library Dependency (`authorization-service-operator-shared`)
- **Choice**: Pin `authorization-service-operator-shared` to `@fix/kafka` branch in `pyproject.toml`, and consume `KafkaRelationHandler` directly from the shared library.
- **Rationale**: The shared library centralizes common configuration parsing, CLI interactions, secret decoding, and relation handlers across the Authorization Service charm ecosystem. For Kafka, the shared library's `KafkaRelationHandler` uses `data_interfaces` v1 to negotiate with modern Kafka operators (`kafka-k8s` / `kafka-operator` 4/stable) requesting `producer,consumer` roles.
- **Components Used**:
  - `AuthorizationServiceInfoRequirer`: Handles `authorization-service-info` relation events, decodes Juju secrets for DB password, and constructs `DatabaseConfig`.
  - `KafkaRelationHandler`: Coordinates Kafka relation endpoints using `data_interfaces` v1, requests `producer,consumer` extra roles and `authorization-service` consumer group prefix, extracts TLS credentials, and produces `KAFKA_BROKERS`, `KAFKA_CONSUMER_GROUP`, and TLS environment variables, with topics/ACLs managed externally via `data-integrator`.
  - `MetricsRelationHandler` & `GrafanaDashboardHandler`: Coordinates COS Prometheus metrics and Grafana dashboard endpoints.
  - `PebbleService` & `WorkloadService`: Encapsulates Pebble layer rendering with readiness checks, planning, service restart on failure, failure state detection (`is_failing()`), and workload version reporting.
  - `CommandLine`: Handles workload CLI execution (`/usr/bin/app version`, `/usr/bin/app migrate status`).

### Decision 2: Database Credentials via `authorization-service-info`
- **Choice**: Consume database credentials via `AuthorizationServiceInfoRequirer` rather than a direct `pg-database` relation.
- **Rationale**: The server charm provisions database users, manages migration state, and shares credentials via Juju secrets. Listener checks `CommandLine.migrate_status(db.dsn)` to verify that migrations are up-to-date before starting.

### Decision 3: Pebble Layer Command & Configuration
- **Choice**: Start the application with `/usr/bin/app listen`, `include_checks=True` (pointing to `http://localhost:9100/metrics`), and injected Kafka environment variables with embedded service discovery.
- **Rationale**: The listener exposes Prometheus metrics on port 9100, which serves as a reliable HTTP readiness probe to restart the container if the listener daemon enters a dead or hung state. Topics and ACLs are defined externally in Kafka via `data-integrator`, and the workload discovers onboarded services using its embedded schema discovery strategy (`FEDERATED_SERVICES_STRATEGY=fs`), removing the need for a charm-level `federated_services` config option.

### Decision 4: Deterministic Priority Status Collection
- **Choice**: In `_on_collect_status`, evaluate conditions deterministically in strict priority order via decoupled status getters:
  1. Configuration status (`_get_config_status`): config validation, valid log levels -> `BlockedStatus`
  2. Prerequisite status (`_get_prerequisite_status`):
     - `container_connectivity` -> `WaitingStatus("Waiting for container")`
     - `authorization-service-info` relation presence -> `BlockedStatus("Missing required relation: authorization-service-info")`
     - Database credentials readiness -> `WaitingStatus("Waiting for database credentials")`
     - `kafka` relation presence -> `BlockedStatus("Missing required relation: kafka")`
     - Kafka brokers / ready state -> `WaitingStatus("Kafka relation is not ready yet")`
  3. Migration status (`_get_migration_status`):
     - Migration check execution error -> `BlockedStatus("Failed to check database migration status, see logs")`
     - Server migration pending -> `WaitingStatus("Waiting for the server to run migration")`
  4. Workload status (`_get_workload_status`):
     - Workload failing (`is_failing()`) -> `BlockedStatus("Failed to start the service, please check the container logs")`
     - Workload not running -> `WaitingStatus("Waiting for workload to start")`
  5. Resource patch status -> `event.add_status(self.resources_patch.get_status())`
  6. Active status -> `ActiveStatus()`

### Decision 5: Unit Testing Strategy
- **Choice**: Use `ops.testing` (Scenario) with 100% top-level imports and direct relation databag assertions.
- **Rationale**: Avoids brittle static mocks, ensures production databag parsing is exercised, and maintains clean linting standards.

## Risks / Trade-offs

- **[Risk]**: Temporary unavailability of Kafka cluster during listener startup.
  - *Mitigation*: The charm gates startup on `KafkaRelationHandler.is_ready()` and restarts the Pebble service upon relation updates.
- **[Risk]**: Database migrations pending on server charm.
  - *Mitigation*: `CommandLine.migrate_status(db.dsn)` gates the listener in `WaitingStatus("Waiting for the server to run migration")` until the server completes schema migrations.
