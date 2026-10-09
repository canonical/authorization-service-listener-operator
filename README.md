# Charmed Authorization Service Listener Operator

A Charmed Operator managing asynchronous event ingestion from Apache Kafka and state synchronization for the Canonical Authorization Service.

## Description

The Authorization Service Listener Operator runs as a Kubernetes workload executing `/usr/bin/app listen`. It consumes permission and relation change events asynchronously from Apache Kafka topics (`<slug>.permissions`) for configured federated services and updates state in PostgreSQL.

It integrates with:
- **`authorization-service`** (Server charm): Obtains PostgreSQL database connection details, credentials (via Juju secrets), and tracks database migration readiness.
- **`kafka`** (Charmed Kafka): Ingests change events from Kafka brokers.
- **`cos-lite`** (COS Observability Stack): Exposes Prometheus metrics, Grafana dashboards, Loki log forwarding, and Tempo OpenTelemetry tracing.

---

## Build

To pack the charm into a `.charm` file:

```bash
charmcraft pack
```

---

## Deployment & Integrations

### 1. Deploy Prerequisites (Kafka, ZooKeeper, PostgreSQL, and Server Charm)

Deploy Apache Kafka and ZooKeeper using the Charmed Kafka operators:

```bash
# Deploy ZooKeeper and Kafka
juju deploy zookeeper-k8s --channel 3/stable --trust
juju deploy kafka-k8s --channel 3/stable --trust
juju integrate kafka-k8s:zookeeper zookeeper-k8s:zookeeper

# Deploy PostgreSQL
juju deploy postgresql-k8s --channel 14/stable --trust

# Deploy the Authorization Service server charm
juju deploy authorization-service --channel latest/edge --trust
juju integrate authorization-service:pg-database postgresql-k8s:database
```

### 2. Deploy the Listener Charm

Deploy the listener operator using the packed `.charm` artifact and its OCI workload image:

```bash
juju deploy ./authorization-service-listener_*.charm authorization-service-listener \
  --resource oci-image=$(yq eval '.resources.oci-image.upstream-source' charmcraft.yaml) \
  --trust
```

### 3. Integrate the Listener Charm

The listener charm requires relations with the Authorization Service server charm and Kafka:

```bash
# Relate to the Server charm (provides database credentials & tracks migration readiness)
juju integrate authorization-service-listener:authorization-service-info authorization-service:authorization-service-info

# Relate to Apache Kafka
juju integrate authorization-service-listener:kafka kafka-k8s:kafka-client
```

> [!NOTE]
> **Known Limitation — Upstream Kafka SASL/SCRAM Support:**
> Charmed Kafka enforces SASL (SCRAM-SHA-512) authentication. The current upstream `authorization-service listen` workload binary does not yet support Kafka SASL authentication or TLS configuration (`KafkaConfig` upstream lacks SASL/TLS fields). Consequently, integrating with a secured Charmed Kafka cluster causes the listener binary to fail on startup (`kafka fetch error: EOF`). Full end-to-end integration with Charmed Kafka is pending upstream SASL/SCRAM support in the workload binary.

### 4. (Optional) Integrate Observability (COS Lite)

```bash
juju integrate authorization-service-listener:metrics-endpoint prometheus-k8s:metrics-endpoint
juju integrate authorization-service-listener:grafana-dashboard grafana-k8s:grafana-dashboard
juju integrate authorization-service-listener:logging loki-k8s:logging
juju integrate authorization-service-listener:tracing tempo-k8s:tracing
```

---

## Configuration

| Option | Type | Default | Description |
|---|---|---|---|
| `federated_services` | string | `authorization-service` | Comma-separated list of federated service names/slugs to consume permission change events for. The listener subscribes to `<slug>.permissions` on Kafka. |
| `log_level` | string | `info` | Logging verbosity level (`panic`, `fatal`, `error`, `warn`, `info`, `debug`, `trace`). |
| `cpu` | string | `""` | K8s CPU resource limits (e.g., `500m`, `1`). |
| `memory` | string | `""` | K8s memory resource limits (e.g., `500Mi`, `1Gi`). |
| `http_proxy` | string | `""` | HTTP proxy URL for outbound requests. |
| `https_proxy` | string | `""` | HTTPS proxy URL for outbound requests. |
| `no_proxy` | string | `""` | Comma-separated list of destinations to bypass proxy. |

Example:

```bash
juju config authorization-service-listener federated_services="authorization-service,permissions" log_level="debug"
```

---

## Migration Synchronization

The listener charm monitors database migration readiness via the `authorization-service-info` relation. When the server charm has pending migrations, the listener defers workload execution and sets unit status to `WaitingStatus("Waiting for the server to run migration")` until the server completes migration.

---

## Developer Instructions

### Prerequisites

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) package manager
- [`tox`](https://tox.wiki/) and `tox-uv`

### Running Checks & Tests

```bash
# Format code
tox -e fmt

# Run static analysis and linting
tox -e lint

# Run unit tests with coverage
tox -e unit

# Run integration tests (requires a running Juju model)
tox -e integration
```

---

## License

The Charmed Authorization Service Listener Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](LICENSE) for more details.
