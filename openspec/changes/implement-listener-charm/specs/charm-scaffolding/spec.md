## Purpose

This capability governs the project's structural layout, package metadata, container orchestration resource definitions, and Juju interface endpoints required to successfully build and deploy the `authorization-service-listener-operator` charm using Charmcraft 3.x.

---

## ADDED Requirements

### Requirement: PEP 621 Python Packaging
The charm project SHALL utilize a PEP 621-compliant `pyproject.toml` declaration, specifying metadata, build backends, and package dependencies.
- It MUST list `ops >= 3.0.0` and the shared operator library `authorization-service-operator-shared`.
- It MUST specify a development environment group with `pytest`, `pytest-mock`, `jubilant`, `codespell`, and `ruff`.

#### Scenario: Pyproject dependency resolution
- **WHEN** the project dependencies are resolved by `uv`
- **THEN** it successfully installs `ops` (version >= 3.0.0) and the shared operator library in the virtual environment

---

### Requirement: Charmcraft uv Build Plugin and Bases
The `charmcraft.yaml` configuration file SHALL use modern Charmcraft 3.x standards:
- It MUST specify `type: charm`.
- It MUST declare the build-plugin as `uv`.
- It MUST define target Ubuntu platforms (`ubuntu@22.04:amd64` and `ubuntu@26.04:amd64`).

#### Scenario: Charmcraft builds target platforms
- **WHEN** `charmcraft pack` is executed
- **THEN** it compiles the charm utilizing the `uv` build plugin

---

### Requirement: Workload Container and Resource Definitions
The `charmcraft.yaml` file SHALL declare a single workload container named `listener` backed by an OCI image resource.

- Container name: `listener`
- Resource name: `oci-image` (type: `oci-image`)

#### Scenario: Workload container validation
- **WHEN** the charm starts up and parses the metadata
- **THEN** the unit expects an active container named `listener` matching the resource image

---

### Requirement: Juju Relation Endpoints Definition
The `charmcraft.yaml` file SHALL explicitly define all integration relation endpoints:

| Endpoint | Role | Interface | Optional | Description |
|---|---|---|---|---|
| `authorization-service-info` | requires | `authorization_service_info` | `false` | Server relation providing DB credentials & migration status |
| `sts-info` | requires | `sts_info` | `false` | Secure Token Service relation providing JWKS URL for standalone gRPC JWT verification |
| `kafka` | requires | `kafka_client` | `true` | Apache Kafka relation reserved for future `platform` ingestion mode |
| `metrics-endpoint` | provides | `prometheus_scrape` | `true` | Exposes metrics to Prometheus scrape targets |
| `grafana-dashboard` | provides | `grafana_dashboard` | `true` | Delivers Grafana JSON dashboards |
| `logging` | requires | `loki_push_api` | `true` | Forwards workload logs to Loki |
| `tracing` | requires | `tracing` | `true` | Exports distributed traces to Tempo via OTLP |

#### Scenario: Metadata defines relations
- **WHEN** Juju inspects the charm's compiled metadata
- **THEN** it registers `authorization-service-info` and `sts-info` as required relations, and `kafka`, `logging`, `tracing`, `metrics-endpoint`, and `grafana-dashboard` as optional endpoints
