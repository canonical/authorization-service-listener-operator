## Why

The Authorization Service Listener is a key stateful component of the Canonical Identity / Authorization Platform. This component processes authorization events asynchronously from Apache Kafka and updates state in PostgreSQL.

Currently, there is no charmed operator for this service component. To deploy, configure, run, and scale this component securely on Kubernetes using Juju, we need to implement the `authorization-service-listener-operator` charmed operator.

To maintain architectural consistency across the Authorization Service ecosystem, the new charm must utilize the shared library (`authorization-service-operator-shared`) and follow modern Canonical charm design patterns (e.g., Python `ops` 3.x, `uv` package manager plugin in `charmcraft.yaml`, unified secret handling, and deterministic status reporting).

## What Changes

This change introduces the full `authorization-service-listener-operator` charmed operator. Key changes include:
- **Charm Scaffolding**: Creating a Juju charm structure using standard Python `ops` (version 3.x) with PEP 621-compliant `pyproject.toml` and `charmcraft.yaml` utilizing the `uv` toolchain.
- **Shared Library Integration**: Pinning and leveraging the common framework from `authorization-service-operator-shared` (pinned to `fix/kafka` branch) to handle Pebble services, commands, configuration mapping, exceptions, Kafka relation handling via `data_interfaces` v1, and relation event handlers.
- **Authorization Service Info Relation**: Integrating with `authorization-service-operator` (server charm) via the `authorization-service-info` requirer interface to securely obtain database configuration, Juju secret credentials, and migration readiness.
- **Kafka Client Relation & Federation**: Integrating with Apache Kafka via `authorization_service_operator_shared.kafka.KafkaRelationHandler` (`data_interfaces` v1 `ResourceRequirerEventHandler` requesting `producer,consumer` extra user roles and consumer group prefix `authorization-service`) to obtain Kafka endpoints, TLS parameters, while topics and ACLs are defined via `data-integrator` and services are discovered using embedded schemas.
- **Workload Orchestration**: Configuring Pebble layer execution so that the workload binary `/usr/bin/app` is started with the `listen` subcommand (`/usr/bin/app listen`) with metrics health checks (`http://localhost:9100/metrics`), migration gating, and decoupled deterministic priority-based status collection with workload failure detection.
- **Observability (COS) & Compute Resources**: Integrating Prometheus metrics scraping (`metrics-endpoint`), Grafana dashboards (`grafana-dashboard`), Loki log forwarding (`logging`), distributed tracing via Tempo (`tracing`), and Kubernetes compute resources patching (`KubernetesComputeResourcesPatch`).
- **Comprehensive Unit Testing**: Implementing Scenario-based tests in `tests/unit/test_charm.py` with 100% top-level imports and exercising real relation databag parsing without static mocks.

## Capabilities

### New Capabilities
- `charm-scaffolding`: PEP-621 charm metadata, `charmcraft.yaml` with the `uv` builder plugin, and core charm loop initialization with `ops.Framework`.
- `charm-configuration`: Charm-level configurations (e.g. `log_level`) mapped to workload environment variables.
- `authorization-service-info-integration`: Integration with the server charm over `authorization-service-info` to receive database connection parameters, secret-backed credentials, and migration status.
- `kafka-integration`: Kafka client relation setup using `data_interfaces` v1 to obtain endpoints, credentials, and TLS parameters with `producer,consumer` roles, while decoupling topic/ACL management to `data-integrator`.
- `workload-orchestration`: Pebble layer configuration to run `/usr/bin/app listen` with dynamic environments, metrics health check recovery, migration gating, and decoupled status evaluation.
- `observability`: Integrating Prometheus metrics, Loki log forwarding, Grafana dashboards, Tempo OTLP tracing, and Kubernetes compute resource patching.

### Modified Capabilities
<!-- None -->

## Impact

- **Affected Systems**: Authorization Service Deployment model on Kubernetes.
- **New Repositories/Components**: `authorization-service-listener-operator` charm.
- **External Dependencies**: Requires `authorization-service-operator` (server) and `kafka-k8s` charms.
- **Shared Package Integration**: Direct dependency on `authorization-service-operator-shared` pinned to `fix/kafka`.
