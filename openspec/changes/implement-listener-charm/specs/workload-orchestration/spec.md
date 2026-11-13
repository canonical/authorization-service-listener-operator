## Purpose

This capability governs the full lifecycle of the `authorization-service-listener` Pebble workload — from initial startup through configuration changes, upgrades, and status collection. It covers the Pebble layer definition (entrypoint, standalone mode environment, HTTP `/healthz` readiness check), container port exposure, workload version reporting, database schema status verification, and decoupled deterministic status evaluation.

---

## ADDED Requirements

### Requirement: Pebble service runs the listen entrypoint in standalone mode with HTTP /healthz readiness check
The Pebble layer for the listener component MUST define the service command as `/usr/bin/app listen` with `LISTENER_MODE=standalone` and `LISTENER_FEDERATED_SERVICES_STRATEGY=fs` in the environment. Because the listener exposes an HTTP health server on port 8070 (`GET /healthz`), the Pebble layer SHALL be rendered with `include_checks=True` and `check_url="http://localhost:8070/healthz"` (the default in `PebbleService.render_pebble_layer`), configuring an HTTP check named `ready` and setting `on-check-failure: {"ready": "restart"}`.

#### Scenario: Pebble layer contains the listen command, standalone mode env vars, and healthz check
- **WHEN** `PebbleService.render_pebble_layer` is called with `_charm_config`, `{"LISTENER_MODE": "standalone", "LISTENER_FEDERATED_SERVICES_STRATEGY": "fs"}`, `_database_config`, and `_sts`
- **THEN** the returned `Layer` contains the service command `/usr/bin/app listen`
- **AND** the environment includes `LISTENER_MODE="standalone"` and `LISTENER_FEDERATED_SERVICES_STRATEGY="fs"`
- **AND** the layer contains an HTTP check named `ready` targeting `http://localhost:8070/healthz`
- **AND** the service definition includes `on-check-failure: {"ready": "restart"}`

#### Scenario: Service opens ports, starts, and reports version on pebble_ready
- **WHEN** the charm receives the `pebble_ready` event and all required relations (`authorization-service-info` and `sts-info`) are satisfied
- **THEN** the charm calls `WorkloadService.open_port()` to open HTTP (`8070`) and gRPC (`9091`) ports on the unit
- **AND** pushes the Pebble layer, starts the listener service, and calls `WorkloadService.update_workload_version()`
- **AND** `_on_collect_status` reports `ActiveStatus()`

---

### Requirement: Workload version is reported on pebble_ready
The charm SHALL call `WorkloadService.update_workload_version()` on `pebble_ready`. Internally, this delegates to `CommandLine.get_service_version()`, which runs `/usr/bin/app version` via Pebble exec and sets the workload version on the unit.

#### Scenario: Version is set after successful start
- **WHEN** `pebble_ready` fires and the service starts successfully
- **THEN** the charm calls `WorkloadService.update_workload_version()` and sets the workload version on the unit
- **AND** `_on_collect_status` reports `ActiveStatus()`

---

### Requirement: Server Migration Gate and Status Reporting
The listener charm SHALL call `CommandLine.migrate_status(db.dsn)` to check whether server migrations are up-to-date before running the workload. Migration checks SHALL be encapsulated in `_get_migration_status()`.

#### Scenario: Migration check error
- **WHEN** `CommandLine.migrate_status(db.dsn)` raises an operational error
- **THEN** `_get_migration_status()` returns `BlockedStatus("Failed to check database migration status, see logs")`
- **AND** the Pebble service is NOT started

#### Scenario: Migration pending on server
- **WHEN** `CommandLine.migrate_status(db.dsn)` returns `True` (pending migrations)
- **THEN** `_get_migration_status()` returns `WaitingStatus("Waiting for the server to run migration")`
- **AND** the Pebble service is NOT started

#### Scenario: Migration completed on server
- **WHEN** `CommandLine.migrate_status(db.dsn)` returns `False`
- **THEN** `_get_migration_status()` returns `None` and execution proceeds to workload status checks

---

### Requirement: Workload Status and Failure Detection
The listener charm SHALL check workload execution state in `_get_workload_status()`, reporting `BlockedStatus` when the service or health check fails.

#### Scenario: Workload service is failing
- **WHEN** `WorkloadService.is_failing()` returns `True` (Pebble service in ERROR status or ready check has failures/is DOWN)
- **THEN** `_get_workload_status()` returns `BlockedStatus("Failed to start the service, please check the container logs")`

#### Scenario: Workload service is starting
- **WHEN** `WorkloadService.is_failing()` is `False` but `WorkloadService.is_running()` is `False`
- **THEN** `_get_workload_status()` returns `WaitingStatus("Waiting for workload to start")`

#### Scenario: Workload service running normally
- **WHEN** `WorkloadService.is_running()` is `True` and `WorkloadService.is_failing()` is `False`
- **THEN** `_get_workload_status()` returns `None`

---

### Requirement: Deterministic Priority Status Evaluation in `_on_collect_status`
The charm SHALL evaluate unit status in a strict, deterministic priority order during `_on_collect_status`:

1. **Configuration Status (`_get_config_status`)**:
   - If charm configuration has errors (invalid `log_level` or unsupported `ingestion_mode`): `BlockedStatus`
2. **Prerequisite Status (`_get_prerequisite_status`)**:
   - Container connectivity: `WaitingStatus("Waiting for container")`
   - Missing info relation: `BlockedStatus("Missing required relation: authorization-service-info")`
   - Database credentials not ready: `WaitingStatus("Waiting for database credentials")`
   - When `ingestion_mode == "standalone"`:
     - Missing `sts-info` relation: `BlockedStatus("Missing required relation: sts-info")`
     - `sts-info` relation not ready: `WaitingStatus("STS relation is not ready yet")`
3. **Migration Status (`_get_migration_status`)**:
   - Migration check error: `BlockedStatus("Failed to check database migration status, see logs")`
   - Migration pending: `WaitingStatus("Waiting for the server to run migration")`
4. **Workload Status (`_get_workload_status`)**:
   - Service failing: `BlockedStatus("Failed to start the service, please check the container logs")`
   - Service not running: `WaitingStatus("Waiting for workload to start")`
5. **Resource Patch Status**: `event.add_status(self.resources_patch.get_status())`
6. **Active Status**: `ActiveStatus()`

#### Scenario: All prerequisites satisfied in standalone mode without Kafka
- **WHEN** `ingestion_mode` is `"standalone"`, `authorization-service-info` and `sts-info` relations are ready, migrations are completed, and the workload is running and healthy (with no `kafka` relation present)
- **THEN** `_on_collect_status` reports `ActiveStatus()`
