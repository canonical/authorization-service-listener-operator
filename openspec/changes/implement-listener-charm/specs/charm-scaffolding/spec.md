## Purpose

This capability governs the project's structural layout, package metadata, container orchestration resource definitions, and Juju interface endpoints required to successfully build and deploy the `authorization-service-listener-operator` charm using Charmcraft 3.x.

---

## ADDED Requirements

### Requirement: PEP 621 Python Packaging
The charm project SHALL utilize a PEP 621-compliant `pyproject.toml` declaration, specifying metadata, build backends, and package dependencies.
- It MUST list `ops >= 3.0.0` and the shared operator library `authorization-service-operator-shared` (pinned to `main` branch).
- It MUST specify a development environment group with `pytest`, `pytest-mock`, `jubilant`, `codespell`, and `ruff`.

#### Scenario: Pyproject dependency resolution
- **WHEN** the project dependencies are resolved by `uv`
- **THEN** it successfully installs `ops` (version >= 3.0.0) and the shared operator library in the virtual environment

---

### Requirement: Charmcraft uv Build Plugin and Bases
The `charmcraft.yaml` configuration file SHALL use modern Charmcraft 3.x standards:
- It MUST specify `type: charm`.
- It MUST declare the build-plugin as `uv`.
- It MUST define Ubuntu 24.04 (`noble`) as the build and run target environment.

#### Scenario: Charmcraft builds Noble target
- **WHEN** `charmcraft pack` is executed
- **THEN** it compiles the charm targeting Ubuntu 24.04 utilizing the `uv` build plugin

---

### Requirement: Workload Container and Resource Definitions
The `charmcraft.yaml` file SHALL declare a single workload container named `listener` backed by an OCI image resource.

- Container name: `listener`
- Resource name: `authorization-service-image` (type: `oci-image`)

#### Scenario: Workload container validation
- **WHEN** the charm starts up and parses the metadata
- **THEN** the unit expects an active container named `listener` matching the resource image

---

### Requirement: Juju Relation Endpoints Definition
The `charmcraft.yaml` file SHALL explicitly define all integration relation endpoints:

| Endpoint | Role | Interface | Description |
|---|---|---|---|
| `authorization-service-info` | requires | `authorization_service_info` | Server relation providing DB credentials & migration status |
| `kafka` | requires | `kafka_client` | Apache Kafka relation to ingest events |
| `metrics-endpoint` | provides | `prometheus_scrape` | Exposes metrics to Prometheus scrape targets |
| `grafana-dashboard` | provides | `grafana_dashboard` | Delivers Grafana JSON dashboards |
| `logging` | requires | `loki_push_api` | Forwards workload logs to Loki |
| `tracing` | requires | `tracing` | Exports distributed traces to Tempo via OTLP |

#### Scenario: Metadata defines relations
- **WHEN** Juju inspects the charm's compiled metadata
- **THEN** it registers all required and optional endpoints
