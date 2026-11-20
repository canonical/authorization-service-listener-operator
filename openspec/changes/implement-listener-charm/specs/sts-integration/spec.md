## Purpose

This capability governs the integration with the Secure Token Service (STS) via the `sts-info` relation when the listener operates in `standalone` ingestion mode. It ensures the listener workload receives `EXTAUTHZ_JWK_SET_URL` (along with `STS_ADDRESS` and `STS_USE_TLS`) to verify Bearer JWTs on incoming `PermissionIngestionService/IngestPermissionUpdate` gRPC calls, gates startup when the relation is missing or not ready, and stops the workload when the relation is removed.

---

## ADDED Requirements

### Requirement: STS Info Integration via Shared Library
The listener charm SHALL integrate with `secure-token-service-operator` via `STSRelationHandler` from `authorization_service_operator_shared.sts` (`charms.secure_token_service.v0.sts_info.StsInfoRequirer`, interface: `sts_info`) on endpoint `sts-info`.

#### Scenario: STS relation handler is initialized
- **WHEN** the charm initializes
- **THEN** it instantiates `STSRelationHandler` on endpoint `sts-info` and observes `sts_info_relation_updated` and `sts_info_relation_broken` events

---

### Requirement: Charm blocks when sts-info relation is missing in standalone mode
When `ingestion_mode` is set to `"standalone"`, the `sts-info` relation SHALL be required (`optional: false` in `charmcraft.yaml`), and `_on_collect_status` SHALL report `BlockedStatus("Missing required relation: sts-info")` when the relation is absent.

#### Scenario: No sts-info relation present in standalone mode
- **WHEN** `ingestion_mode` is `"standalone"` and no `sts-info` relation is joined
- **THEN** `_on_collect_status` reports `BlockedStatus("Missing required relation: sts-info")`
- **AND** the Pebble service is NOT started

---

### Requirement: STS Environment Mapping and Readiness Gate
When `ingestion_mode` is `"standalone"`, the listener charm SHALL gate workload planning until `STSRelationHandler.is_ready()` returns `True`, and SHALL translate the `sts-info` relation databag into workload environment variables:

| Env var | Source field (`StsInfoData`) | Description |
|---|---|---|
| `EXTAUTHZ_JWK_SET_URL` | `jwks_url` | JWKS URL used by the standalone gRPC ingestion server to verify Bearer JWTs |
| `STS_ADDRESS` | `grpc_address` | STS gRPC address |
| `STS_USE_TLS` | `tls_enabled` | Boolean string (`"true"` / `"false"`) indicating TLS usage |

#### Scenario: STS relation provides complete data
- **WHEN** the `sts-info` relation is joined and provides valid `http_address`, `grpc_address`, `jwks_url`, and `tls_enabled`
- **THEN** `STSRelationHandler.to_env_vars()` injects `EXTAUTHZ_JWK_SET_URL`, `STS_ADDRESS`, and `STS_USE_TLS` into the Pebble layer environment
- **AND** `_on_holistic_handler()` re-applies the Pebble layer with these variables

#### Scenario: STS relation data is incomplete
- **WHEN** `ingestion_mode` is `"standalone"` and the `sts-info` relation is joined but `jwks_url` is not yet published
- **THEN** `_on_collect_status` reports `WaitingStatus("STS relation is not ready yet")`
- **AND** the Pebble service is NOT started

---

### Requirement: STS relation teardown stops the workload in standalone mode
When `ingestion_mode` is `"standalone"`, the charm SHALL stop the Pebble service and report `BlockedStatus("Missing required relation: sts-info")` when the `sts-info` relation is broken.

#### Scenario: STS relation is broken
- **WHEN** `sts_info_relation_broken` fires while `ingestion_mode` is `"standalone"`
- **THEN** `PebbleService.stop()` is called to halt the listener service
- **AND** `_on_collect_status` reports `BlockedStatus("Missing required relation: sts-info")`
