## Purpose

This capability governs the integration with the `authorization-service-operator` (server charm) via the `authorization-service-info` relation. It ensures the listener workload receives database connection parameters and Juju secret credentials, verifies that schema migrations have been performed on the server side, and stops the service when the relation is removed.

---

## ADDED Requirements

### Requirement: Authorization Service Info Integration via Shared Library
The listener charm SHALL integrate with the server charm via `AuthorizationServiceInfoRequirer` from `authorization-service-operator-shared`.

#### Scenario: Info requirer is initialized
- **WHEN** the charm initializes
- **THEN** it instantiates `AuthorizationServiceInfoRequirer` on endpoint `authorization-service-info` and observes its update and broken events

---

### Requirement: Charm blocks when authorization-service-info relation is not established
The charm SHALL report `BlockedStatus("Missing required relation: authorization-service-info")` via `_on_collect_status` when the `authorization-service-info` relation is missing.

#### Scenario: No info relation present
- **WHEN** the unit starts and no `authorization-service-info` relation is joined
- **THEN** `_on_collect_status` reports `BlockedStatus("Missing required relation: authorization-service-info")`
- **AND** the Pebble service is NOT started

---

### Requirement: Database credentials and configuration from info relation
The charm SHALL consume database parameters via `DatabaseConfig.from_info(info)` using the Juju secret ID provided in the relation databag (`db_secret_id`). The connection details SHALL be converted to standard environment variables:

| Env var | Source field |
|---|---|
| `POSTGRES_HOST` | `db_host` |
| `POSTGRES_PORT` | `db_port` |
| `POSTGRES_USER` | `db_user` |
| `POSTGRES_PASSWORD` | Retrieved from Juju secret `db_secret_id` |
| `POSTGRES_DB` | `db_name` |
| `POSTGRES_SSL_MODE` | `"disable"` |

#### Scenario: Info relation provides complete database credentials
- **WHEN** the `authorization-service-info` relation databag contains complete database connection data and a valid secret ID
- **THEN** `DatabaseConfig.from_info(info).to_env_vars()` produces discrete `POSTGRES_*` environment variables
- **AND** `_on_holistic_handler()` re-plans the Pebble layer

#### Scenario: Database credentials not yet published
- **WHEN** the `authorization-service-info` relation is joined but database credentials or secrets are not yet available
- **THEN** `_on_collect_status` reports `WaitingStatus("Waiting for database credentials")`
- **AND** the Pebble service is NOT started

---

### Requirement: Server Migration Gate
The charm SHALL check `CommandLine.migrate_status(db.dsn)` to verify that database schema migrations have been applied by the server component.

#### Scenario: Database migration error
- **WHEN** `CommandLine.migrate_status(db.dsn)` raises a `WorkloadError`
- **THEN** `_on_collect_status` reports `BlockedStatus("Failed to check database migration status, see logs")`
- **AND** the listener service is NOT started

#### Scenario: Database migration pending
- **WHEN** `CommandLine.migrate_status(db.dsn)` indicates that database migrations are pending
- **THEN** `_on_collect_status` reports `WaitingStatus("Waiting for the server to run migration")`
- **AND** the listener service is NOT started

#### Scenario: Database migration completed
- **WHEN** `CommandLine.migrate_status(db.dsn)` returns `False` (no pending migrations)
- **THEN** migration check passes and status check proceeds to workload execution

---

### Requirement: Info relation teardown stops the workload
The charm SHALL stop the service and report `BlockedStatus` when the `authorization-service-info` relation is removed.

#### Scenario: Info relation broken
- **WHEN** `authorization_service_info_broken` fires
- **THEN** `PebbleService.stop()` is called
- **AND** `_on_collect_status` reports `BlockedStatus("Missing required relation: authorization-service-info")`
