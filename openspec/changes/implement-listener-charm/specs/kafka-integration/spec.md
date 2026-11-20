## Purpose

This capability governs the integration with Apache Kafka via the `kafka` relation. The `kafka` relation is optional (`optional: true` in `charmcraft.yaml`) so that a missing `kafka` relation does NOT block the charm when operating in `standalone` mode. When the `kafka` relation is joined, `KafkaRelationHandler` requests `producer,consumer` extra user roles and consumer group prefix `authorization-service` on `permissions.authorization_service`, waits for broker endpoints, and propagates connection endpoints and TLS settings into the Pebble environment.

> **Note on Future Platform Ingestion Mode**: Upstream `authorization-service` PR #117 supports `platform` (Kafka), `standalone` (gRPC), and `hybrid` (Kafka + gRPC) operating modes via `LISTENER_MODE`. When `platform` ingestion mode is introduced in a future charm iteration via the `ingestion_mode` configuration option, the `kafka` relation will be mandatory when `ingestion_mode=platform`.

---

## ADDED Requirements

### Requirement: Optional Kafka Integration via data_interfaces v1
The listener charm SHALL declare the `kafka` relation endpoint (`interface: kafka_client`) with `optional: true` in `charmcraft.yaml` and integrate with Apache Kafka cluster relation endpoints utilizing `KafkaRelationHandler` from `authorization_service_operator_shared.kafka` (`data_platform_libs.v1.data_interfaces.ResourceRequirerEventHandler` with `KafkaRequestModel` and `KafkaResponseModel`), requesting default topic `permissions.authorization_service`, producer and consumer roles (`extra_user_roles="producer,consumer"`), and consumer group prefix `authorization-service`.

#### Scenario: Kafka request model is published
- **WHEN** the `kafka` relation is created
- **THEN** the requirer publishes `version="v1"` and a request in `requests` requesting `resource="permissions.authorization_service"`, `extra-user-roles="producer,consumer"`, and `consumer-group-prefix="authorization-service"`

#### Scenario: Kafka configuration is parsed
- **WHEN** the `kafka` relation response provides bootstrap server endpoints and credentials (via V1 secrets or databags)
- **THEN** `KafkaRelationHandler` parses the brokers, credentials, and TLS settings and exposes them to the charm

---

### Requirement: External Topic Provisioning via Data-Integrator and Embedded Discovery
The listener charm SHALL decouple Kafka topic creation and ACL management from its local databag. Topics and topic-level ACLs are provisioned externally via the `data-integrator` charm. The workload automatically discovers onboarded services using its embedded discovery strategy (`LISTENER_FEDERATED_SERVICES_STRATEGY=fs`).

#### Scenario: Topics provisioned externally and services discovered via embedded strategy
- **WHEN** the listener charm joins the `kafka` relation
- **THEN** the listener charm does NOT publish dynamic per-service topic creation requests in the relation databag
- **AND** the listener relies on topics created and managed via `data-integrator`
- **AND** the listener workload binary automatically discovers onboarded federated services from embedded schemas

---

### Requirement: Charm does not block when kafka relation is missing
Because the `kafka` relation is optional (`optional: true`), the charm SHALL NOT report `BlockedStatus` when no `kafka` relation is present.

#### Scenario: No Kafka relation present in standalone mode
- **WHEN** the charm is deployed with `ingestion_mode=standalone`, valid `authorization-service-info` and `sts-info` relations, and no `kafka` relation
- **THEN** the charm plans and starts the `/usr/bin/app listen` Pebble service with `LISTENER_MODE=standalone`
- **AND** `_on_collect_status` reports `ActiveStatus()`

---

### Requirement: Kafka Environment Mapping
When the `kafka` relation is joined and ready, the listener charm SHALL translate Kafka relation data into environment variables via `KafkaRelationHandler`:

| Env var | Source field | Description |
|---|---|---|
| `KAFKA_ENABLED` | `"true"` | Boolean flag enabling Kafka listener consumer |
| `KAFKA_BROKERS` | `bootstrap_server` | Comma-separated list of broker host:port addresses |
| `KAFKA_CONSUMER_GROUP` | `consumer_group` | String identifying the unique listener consumer group (`authorization-service`) |
| `FEDERATED_SERVICES_STRATEGY` | `"fs"` | Strategy for discovering federated permission event topics from embedded files |
| `KAFKA_TLS_ENABLED` | `tls` | TLS enablement string (if provided by Kafka relation) |
| `KAFKA_TLS_CA` | `tls-ca` | TLS CA certificate (if provided by Kafka relation) |

#### Scenario: Environment variables injected when Kafka relation is active
- **WHEN** the `kafka` relation is joined and active
- **THEN** the Pebble layer is rendered with `KAFKA_ENABLED`, `KAFKA_BROKERS`, `KAFKA_CONSUMER_GROUP`, `FEDERATED_SERVICES_STRATEGY`, and any available TLS variables
- **AND** `_on_holistic_handler()` re-applies the Pebble layer with these variables

#### Scenario: Kafka relation data is incomplete
- **WHEN** the `kafka` relation is joined but bootstrap servers are not yet published
- **THEN** `_on_collect_status` reports `WaitingStatus("Kafka relation is not ready yet")`
- **AND** the Pebble service is NOT re-planned until Kafka endpoints are available

---

### Requirement: Kafka relation teardown re-plans the workload without blocking
When the optional `kafka` relation is removed, the charm SHALL re-plan the Pebble layer without Kafka environment variables and remain operational in `standalone` mode.

#### Scenario: Kafka relation is broken
- **WHEN** the `relation_broken` event fires for the `kafka` relation
- **THEN** `_on_holistic_handler()` re-plans the Pebble layer without `KAFKA_*` environment variables
- **AND** `_on_collect_status` continues to report `ActiveStatus()` when standalone prerequisites are satisfied
