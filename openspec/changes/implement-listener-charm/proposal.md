## Why

The Authorization Service Listener is a key stateful component of the Canonical Identity / Authorization Platform. It validates incoming permission-update envelopes against the federated service registry and durably persists them into the PostgreSQL `permission_update_work` queue for asynchronous tuple application by the worker component.

With upstream `authorization-service` PR #117, the `listen` command supports configurable operating modes (`standalone`, `platform`, and `hybrid`) under a dedicated `listener` configuration section (`LISTENER_MODE`, `LISTENER_FEDERATED_SERVICES_STRATEGY`, `LISTENER_FEDERATED_SERVICES`). In `standalone` mode, the listener exposes a `PermissionIngestionService/IngestPermissionUpdate` gRPC endpoint authenticated via Ory Hydra Bearer JWTs (`EXTAUTHZ_JWK_SET_URL`) and operates without requiring or initializing a Kafka broker.

To deploy, configure, run, and scale this component securely on Kubernetes using Juju, we need to implement the `authorization-service-listener-operator` charmed operator. For now, the charm only supports `standalone` mode (`ingestion_mode=standalone`), with the possibility to introduce other ingestion modes (such as `platform` mode requiring Kafka) in the future.

## What Changes

This change introduces the `authorization-service-listener-operator` charmed operator. Key changes include:
- **Charm Scaffolding**: Creating a Juju charm structure using standard Python `ops` (version 3.x) with PEP 621-compliant `pyproject.toml` and `charmcraft.yaml` utilizing the `uv` toolchain.
- **Ingestion Mode Configuration (`ingestion_mode`)**: Adding the `ingestion_mode` charm configuration option (default `"standalone"`). Currently only `"standalone"` is supported and validated, setting `LISTENER_MODE=standalone` and `LISTENER_FEDERATED_SERVICES_STRATEGY=fs` in the Pebble environment. Other ingestion modes (such as `"platform"`, which requires Kafka, and `"hybrid"`) will be supported in future iterations.
- **Shared Library Integration**: Pinning and leveraging the common framework from `authorization-service-operator-shared` to handle Pebble services, commands, configuration mapping, exceptions, STS relation handling, and relation event handlers.
- **Authorization Service Info Relation**: Integrating with `authorization-service-operator` (server charm) via the `authorization-service-info` requirer interface to securely obtain database configuration, Juju secret credentials, and migration readiness.
- **STS Info Relation (`sts-info`)**: Integrating with `secure-token-service-operator` via `STSRelationHandler` (`charms.secure_token_service.v0.sts_info`) as a required relation when `ingestion_mode=standalone` to configure `EXTAUTHZ_JWK_SET_URL` for Bearer JWT verification on the gRPC ingestion server, blocking the charm when the relation is missing and waiting when not ready.
- **Kafka Relation (Deferred for Future Platform Mode)**: Declaring `kafka` (`kafka_client`) as `optional: true` in `charmcraft.yaml` so the charm does not block when the Kafka integration is missing, and deferring `KafkaRelationHandler` in `src/charm.py` until `platform` ingestion mode is introduced.
- **Workload Orchestration**: Configuring Pebble layer execution so that the workload binary `/usr/bin/app` is started with `/usr/bin/app listen`, opening container ports (`8070` HTTP and `9091` gRPC) via `WorkloadService.open_port()`, configuring the HTTP readiness check on `http://localhost:8070/healthz`, gating on database migrations, and evaluating unit status deterministically.
- **Observability (COS) & Compute Resources**: Integrating Prometheus metrics scraping (`metrics-endpoint`), Grafana dashboards (`grafana-dashboard`), Loki log forwarding (`logging`), distributed tracing via Tempo (`tracing`), and Kubernetes compute resources patching (`KubernetesComputeResourcesPatch`).
- **Comprehensive Unit Testing**: Implementing Scenario-based tests in `tests/unit/test_charm.py` with 100% top-level imports and exercising real relation databag parsing without static mocks.

## Capabilities

### New Capabilities
- `charm-scaffolding`: PEP-621 charm metadata, `charmcraft.yaml` with the `uv` builder plugin, and core charm loop initialization with `ops.Framework`.
- `charm-configuration`: Charm-level configurations (`ingestion_mode`, `log_level`, proxy, compute resources) validated and mapped to workload environment variables.
- `authorization-service-info-integration`: Integration with the server charm over `authorization-service-info` to receive database connection parameters, secret-backed credentials, and migration status.
- `sts-integration`: Integration with the Secure Token Service charm over `sts-info` (required in `standalone` mode) to obtain `EXTAUTHZ_JWK_SET_URL` for gRPC JWT authentication.
- `kafka-integration`: Optional `kafka` relation definition in metadata reserved for future `platform` ingestion mode without blocking `standalone` deployments.
- `workload-orchestration`: Pebble layer configuration to run `/usr/bin/app listen` in `standalone` mode with port opening, `/healthz` readiness checks, migration gating, and decoupled status evaluation.
- `observability`: Integrating Prometheus metrics, Loki log forwarding, Grafana dashboards, Tempo OTLP tracing, and Kubernetes compute resource patching.

### Modified Capabilities
<!-- None -->

## Impact

- **Affected Systems**: Authorization Service Deployment model on Kubernetes.
- **New Repositories/Components**: `authorization-service-listener-operator` charm.
- **External Dependencies**: Requires `authorization-service-operator` (server) and `secure-token-service-operator` (`sts-info` in `standalone` mode). `kafka-k8s` is optional and not required in `standalone` mode.
- **Shared Package Integration**: Direct dependency on `authorization-service-operator-shared`.
