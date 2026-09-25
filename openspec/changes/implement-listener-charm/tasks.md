## 1. Project Scaffolding & Dependencies

- [x] 1.1 Create PEP 621-compliant `pyproject.toml` declaring dependencies (`ops>=3.0.0`, `authorization-service-operator-shared` pinned to `fix/kafka`) and dev tools (`pytest`, `pytest-mock`, `jubilant`, `codespell`, `ruff`).
- [x] 1.2 Create `charmcraft.yaml` with `uv` builder plugin, `listener` workload container, config options (proxy, resources), and relation definitions (`authorization-service-info`, `kafka`, `metrics-endpoint`, `grafana-dashboard`, `logging`, `tracing`).
- [x] 1.3 Create `src/constants.py` defining container name (`listener`), Pebble service name, default ports, and relation names.

## 2. Core Charm & Relation Integrations

- [x] 2.1 Implement `src/charm.py` with `AuthorizationServiceListenerCharm` using explicit `ops.Framework` constructor signature.
- [x] 2.2 Initialize `AuthorizationServiceInfoRequirer` on endpoint `authorization-service-info` and handle `authorization_service_info_updated` / `authorization_service_info_broken` events.
- [x] 2.3 Initialize `KafkaRelationHandler` from shared library on endpoint `kafka` using `data_interfaces` v1 (`producer,consumer` roles, `authorization-service` consumer group prefix).
- [x] 2.4 Initialize COS Observability handlers (`MetricsRelationHandler`, `GrafanaDashboardHandler`, `LogForwarder`, `TracingEndpointRequirer`) and `KubernetesComputeResourcesPatch`.
- [x] 2.5 Configure `PebbleService` (command `/usr/bin/app listen`, `include_checks=True` with metrics endpoint check), `CommandLine`, and `WorkloadService`.

## 3. Workload Orchestration & Status Evaluation

- [x] 3.1 Implement database migration checking (`_check_migration_state`) using `CommandLine.migrate_status(db.dsn)`.
- [x] 3.2 Implement decoupled status collection in `_on_collect_status` (evaluating config, prerequisites, migration, and workload failure states in priority order).
- [x] 3.3 Add resource patch status via `event.add_status(self.resources_patch.get_status())` and set final active status as `ops.ActiveStatus()`.
- [x] 3.4 Wire `_on_holistic_handler` to restart or replan Pebble workload on relation and config changes (Kafka endpoints/secrets).

## 4. Unit Testing & Quality Verification

- [x] 4.1 Set up `tests/unit/conftest.py` with `ops.testing.Context` and relation fixtures (`authz_info_relation`, `kafka_relation`, `mocked_k8s_resource_patch`, `mock_migrate_status`).
- [x] 4.2 Write Scenario-based unit tests in `tests/unit/test_charm.py` verifying status reporting, missing relations, migration gate, Kafka env vars, Pebble planning, and active status.
- [x] 4.3 Ensure all imports in test files are strictly placed at the top of the file.
- [x] 4.4 Run `ruff check .`, `ruff format --check .`, `codespell`, and `pytest tests/unit` to verify clean execution.
