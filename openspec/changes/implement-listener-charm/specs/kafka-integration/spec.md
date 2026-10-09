## Purpose

This capability governs the integration with Apache Kafka via the `kafka` relation. It ensures the listener workload has access to a running Kafka broker cluster before it is started, propagates connection endpoints and credentials as environment variables (`KAFKA_ENABLED`, `KAFKA_BROKERS`, `KAFKA_CONSUMER_GROUP`, TLS settings), requests `producer,consumer` extra user roles and consumer group prefix, and halts execution when the relation is missing or broken. Topics and ACLs are defined externally via the `data-integrator` charm, while service onboarding uses the workload binary's embedded discovery strategy.

---

## ADDED Requirements

### Requirement: Kafka Integration via data_interfaces v1
The listener charm SHALL integrate with Apache Kafka cluster relation endpoints utilizing `KafkaRelationHandler` from `authorization_service_operator_shared.kafka` (`data_platform_libs.v1.data_interfaces.ResourceRequirerEventHandler` with `KafkaRequestModel` and `KafkaResponseModel`, interface: `kafka_client`), requesting default topic `permissions.authorization_service`, producer and consumer roles (`extra_user_roles="producer,consumer"`), and consumer group prefix `authorization-service`.

#### Scenario: Kafka request model is published
- **WHEN** the `kafka` relation is created
- **THEN** the requirer publishes `version="v1"` and a request in `requests` requesting `resource="permissions.authorization_service"`, `extra-user-roles="producer,consumer"`, and `consumer-group-prefix="authorization-service"`

#### Scenario: Kafka configuration is parsed
- **WHEN** the `kafka` relation response provides bootstrap server endpoints and credentials (via V1 secrets or databags)
- **THEN** `KafkaRelationHandler` parses the brokers, credentials, and TLS settings and exposes them to the charm

---

### Requirement: External Topic Provisioning via Data-Integrator and Embedded Discovery
The listener charm SHALL decouple Kafka topic creation and ACL management from its local databag. Topics and topic-level ACLs are provisioned externally via the `data-integrator` charm. The workload automatically discovers onboarded services using its embedded discovery strategy (`FEDERATED_SERVICES_STRATEGY=fs`).

#### Scenario: Topics provisioned externally and services discovered via embedded strategy
- **WHEN** the listener charm joins the `kafka` relation
- **THEN** the listener charm does NOT publish dynamic topic creation requests in the relation databag
- **AND** the listener relies on topics created and managed via `data-integrator`
- **AND** the listener workload binary automatically discovers onboarded federated services from embedded schemas

---

### Requirement: Charm blocks when kafka relation is not established
The charm SHALL report `BlockedStatus("Missing required relation: kafka")` via `_on_collect_status` when the `kafka` relation is missing.

#### Scenario: No Kafka relation present on startup
- **WHEN** the unit starts and no `kafka` relation is joined
- **THEN** `_on_collect_status` reports `BlockedStatus("Missing required relation: kafka")`
- **AND** the Pebble service is NOT started

---

### Requirement: Kafka Environment Mapping
The listener charm SHALL translate Kafka relations into environment variables required by the workload's `KafkaConfig` mapping:

| Env var | Source field | Description |
|---|---|---|
| `KAFKA_ENABLED` | `"true"` | Boolean flag enabling Kafka listener consumer |
| `KAFKA_BROKERS` | `bootstrap_server` | Comma-separated list of broker host:port addresses |
| `KAFKA_CONSUMER_GROUP` | `consumer_group` | String identifying the unique listener consumer group (`authorization-service`) |
| `FEDERATED_SERVICES_STRATEGY` | `"fs"` | Strategy for discovering federated permission event topics from embedded files |
| `KAFKA_TLS_ENABLED` | `tls` | TLS enablement string (if provided by Kafka relation) |
| `KAFKA_TLS_CA` | `tls-ca` | TLS CA certificate (if provided by Kafka relation) |

#### Scenario: Environment variables injected
- **WHEN** the `kafka` relation is joined and active
- **THEN** the Pebble layer is rendered with `KAFKA_ENABLED`, `KAFKA_BROKERS`, `KAFKA_CONSUMER_GROUP`, `FEDERATED_SERVICES_STRATEGY`, and any available TLS variables
- **AND** `_on_holistic_handler()` re-applies the Pebble layer with these variables

#### Scenario: Kafka relation data is incomplete
- **WHEN** the `kafka` relation is joined but bootstrap servers are not yet published
- **THEN** `_on_collect_status` reports `WaitingStatus("Kafka relation is not ready yet")`
- **AND** the Pebble service is NOT started

---

### Requirement: Kafka relation teardown blocks the workload
The charm SHALL stop the service and report `BlockedStatus` when the `kafka` relation is removed.

#### Scenario: Kafka relation is broken
- **WHEN** the `relation_broken` event fires for the `kafka` relation
- **THEN** `PebbleService.stop()` is called to halt event consumption
- **AND** `_on_collect_status` reports `BlockedStatus("Missing required relation: kafka")`
