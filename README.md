# Charmed Authorization Service Listener Operator

A Juju Charmed Operator for the Canonical Authorization Service Listener on Kubernetes.

## Description

The Authorization Service Listener manages permission-update event ingestion and state synchronization in PostgreSQL for the Charmed Authorization Service.

The charm currently operates in **`standalone` mode** (`ingestion_mode=standalone`), running the listener workload (`/usr/bin/app listen`) with:
- A gRPC ingestion server (`GRPC_PORT=9091`) exposing `PermissionIngestionService/IngestPermissionUpdate`, authenticated via Bearer JWTs verified against the Secure Token Service (STS) JWKS endpoint (`EXTAUTHZ_JWK_SET_URL`).
- An HTTP health check server (`HTTP_PORT=8070`, `GET /healthz`) and Prometheus metrics endpoint (`METRICS_PORT=9100`, `GET /metrics`).
- Direct state persistence to the shared PostgreSQL database (without requiring OpenFGA or a Kafka broker).

> **Note**: Support for additional ingestion modes (such as `platform` mode backed by Kafka) is planned for future iterations via the `ingestion_mode` configuration option.

This charm does not connect to PostgreSQL directly; instead, it receives database connection credentials and schema migration status from the `authorization-service-operator` (server charm) via the `authorization-service-info` relation.

## Usage

### Prerequisites

- A Kubernetes cluster with Juju bootstrapped.
- Deployed instances of:
  - `postgresql-k8s`
  - `openfga-k8s`
  - `secure-token-service` (providing `sts_info`)
  - `authorization-service` (the server charm)

### Deployment

Deploy the listener charm and integrate it with the Authorization Service server and Secure Token Service:

```bash
# Deploy the listener charm
juju deploy authorization-service-listener --trust

# Integrate with the Authorization Service server (provides DB credentials & migration state)
juju integrate authorization-service-listener:authorization-service-info authorization-service:authorization-service-info

# Integrate with Secure Token Service (provides JWKS endpoint for standalone gRPC ingestion)
juju integrate authorization-service-listener:sts-info secure-token-service:sts-info
```

### Configuration

| Option | Type | Default | Description |
|---|---|---|---|
| `ingestion_mode` | `string` | `standalone` | Permission-update ingestion mode for the listener workload (`standalone`). |
| `log_level` | `string` | `info` | Log verbosity (`debug`, `info`, `warn`, `error`). |
| `dev` | `boolean` | `false` | Enable development mode. |
| `http_proxy` | `string` | — | HTTP proxy URL (`HTTP_PROXY`). |
| `https_proxy` | `string` | — | HTTPS proxy URL (`HTTPS_PROXY`). |
| `no_proxy` | `string` | — | Comma-separated list of domains excluded from proxying (`NO_PROXY`). |
| `cpu` | `string` | — | Kubernetes CPU limit (e.g. `"500m"`). |
| `memory` | `string` | — | Kubernetes memory limit (e.g. `"512Mi"`). |

## Integrations (Relations)

### Required Relations

- **`authorization-service-info`** (`authorization_service_info`): Receives PostgreSQL connection details (including Juju secret credentials) and verifies that database migrations have been executed by the server charm.
- **`sts-info`** (`sts_info`): Receives the Secure Token Service JWKS URL (`EXTAUTHZ_JWK_SET_URL`), gRPC address, and TLS configuration required in `standalone` ingestion mode.

### Optional Relations

- **`kafka`** (`kafka_client`): Reserved for future `platform` ingestion mode support. Not required in `standalone` mode.
- **`metrics-endpoint`** (`prometheus_scrape`): Exposes Prometheus metrics on port `9100` (`/metrics`).
- **`grafana-dashboard`** (`grafana_dashboard`): Provides pre-configured Grafana dashboards to COS.
- **`logging`** (`loki_push_api`): Forwards container logs to Loki.
- **`tracing`** (`tracing`): Sends OpenTelemetry traces to Tempo (`otlp_http`, `otlp_grpc`).

## Development

Run linters and unit tests using `tox`:

```bash
tox -e lint
tox -e unit
```

## License

This software is licensed under the [Apache License 2.0](LICENSE).
