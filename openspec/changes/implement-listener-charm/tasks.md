## 1. Project Scaffolding & Dependencies

- [x] 1.1 Create PEP 621-compliant `pyproject.toml` declaring dependencies (`ops>=3.0.0`, `authorization-service-operator-shared`) and dev tools (`pytest`, `pytest-mock`, `jubilant`, `codespell`, `ruff`).
- [x] 1.2 Create `charmcraft.yaml` with `uv` builder plugin, `listener` workload container, config options (`ingestion_mode` defaulting to `standalone`, `log_level`, proxy, resources), and relation definitions (`authorization-service-info`, `sts-info`, optional `kafka`, `metrics-endpoint`, `grafana-dashboard`, `logging`, `tracing`).
- [x] 1.3 Create `src/constants.py` defining container name (`listener`), Pebble service name, relation names (`authorization-service-info`, `sts-info`, `kafka`, etc.), and supported ingestion modes (`VALID_INGESTION_MODES = frozenset({"standalone"})`).

## 2. Core Charm & Relation Integrations

- [x] 2.1 Implement `src/charm.py` with `AuthorizationServiceListenerCharm` using explicit `ops.Framework` constructor signature.
- [x] 2.2 Initialize `AuthorizationServiceInfoRequirer` on endpoint `authorization-service-info` and handle `authorization_service_info_updated` / `authorization_service_info_broken` events.
- [x] 2.3 Initialize `STSRelationHandler` from shared library on endpoint `sts-info` (vendoring `lib/charms/secure_token_service/v0/sts_info.py`) to supply `EXTAUTHZ_JWK_SET_URL` in `standalone` mode, and initialize `KafkaRelationHandler` on the optional `kafka` endpoint.
- [x] 2.4 Initialize COS Observability handlers (`MetricsRelationHandler`, `GrafanaDashboardHandler`, `TracingEndpointRequirer` with `TracingConfig`, `LogForwarder`) and `KubernetesComputeResourcesPatch`.
- [x] 2.5 Configure `PebbleService` (command `/usr/bin/app listen`, `LISTENER_MODE=standalone`, `LISTENER_FEDERATED_SERVICES_STRATEGY=fs`, `include_checks=True` with `/healthz` check on port `8070`), `CommandLine`, and `WorkloadService` (calling `open_port()` on `pebble_ready`).

## 3. Workload Orchestration & Status Evaluation

- [x] 3.1 Implement database migration checking (`_check_migration_state`) using `CommandLine.migrate_status(db.dsn)`.
- [x] 3.2 Implement decoupled status collection in `_on_collect_status` evaluating config (`log_level`, `ingestion_mode`), prerequisites (`authorization-service-info`, `sts-info` when `ingestion_mode=standalone`, without blocking on missing `kafka`), migration, and workload failure states in priority order.
- [x] 3.3 Add resource patch status via `event.add_status(self.resources_patch.get_status())` and set final active status as `ops.ActiveStatus()`.
- [x] 3.4 Wire `_on_holistic_handler` and relation-broken handlers to replan or stop the Pebble workload on relation and config changes.

## 4. Unit Testing & Quality Verification

- [x] 4.1 Set up `tests/unit/conftest.py` with `ops.testing.Context` and relation fixtures (`authz_info_relation`, `sts_relation`, `mocked_k8s_resource_patch`, `mock_migrate_status`).
- [x] 4.2 Write Scenario-based unit tests in `tests/unit/test_charm.py` verifying status reporting, missing relations (`authorization-service-info`, `sts-info`), non-blocking when `kafka` is absent, `ingestion_mode` validation, migration gate, `LISTENER_MODE=standalone` / `EXTAUTHZ_JWK_SET_URL` env vars, port opening, Pebble planning, and active status.
- [x] 4.3 Ensure all imports in test files are strictly placed at the top of the file.
- [x] 4.4 Run `ruff check .`, `ruff format --check .`, `codespell`, `pytest tests/unit`, and `openspec validate --all --no-interactive` to verify clean execution.
