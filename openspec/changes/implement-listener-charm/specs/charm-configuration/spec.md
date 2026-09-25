## Purpose

This capability governs how the listener charm validates and applies operator-supplied configuration. It ensures that all charm config options (`ingestion_mode`, `log_level`, proxy settings) are properly validated before reaching the workload, provides meaningful `BlockedStatus` feedback when values are invalid, and maps config values to the workload's environment variables. It also covers resource requirements (`cpu`, `memory`) applied to the Kubernetes container via `KubernetesComputeResourcesPatch`.

---

## ADDED Requirements

### Requirement: ingestion_mode config is validated and mapped to LISTENER_MODE
The charm SHALL define an `ingestion_mode` configuration option in `charmcraft.yaml` with default value `"standalone"`. Currently, the charm SHALL validate `ingestion_mode` against `VALID_INGESTION_MODES = frozenset({"standalone"})` and inject `LISTENER_MODE=<ingestion_mode>` and `LISTENER_FEDERATED_SERVICES_STRATEGY=fs` into the Pebble layer environment. Invalid or unsupported values SHALL result in `BlockedStatus`.

> **Note**: In future iterations, `ingestion_mode` will be extended to support additional operating modes introduced in upstream `authorization-service` PR #117 (such as `"platform"` mode, which requires the `kafka` integration, and `"hybrid"` mode).

#### Scenario: Valid standalone ingestion_mode is accepted by default
- **WHEN** `ingestion_mode` is set to `"standalone"` (or left at its default)
- **THEN** the charm accepts the value and includes `LISTENER_MODE=standalone` and `LISTENER_FEDERATED_SERVICES_STRATEGY=fs` in the Pebble layer environment

#### Scenario: Unsupported ingestion_mode is rejected
- **WHEN** the operator sets `ingestion_mode` to an unsupported value (e.g., `"platform"` or `"invalid"`)
- **THEN** `_on_collect_status` reports `BlockedStatus` with a descriptive `"Invalid configuration: ..."` message
- **AND** the Pebble service is NOT re-planned

---

### Requirement: log_level config is validated against accepted values
The charm SHALL validate `log_level` against `debug`, `info`, `warn`, `error`. Invalid values SHALL result in `BlockedStatus`.

#### Scenario: Valid log_level is accepted
- **WHEN** the operator sets `log_level` to `"debug"`
- **THEN** the charm accepts the value and includes `LOG_LEVEL=debug` in the Pebble layer environment

#### Scenario: Invalid log_level is rejected
- **WHEN** the operator sets `log_level` to an unlisted value (e.g., `"trace"`)
- **THEN** `_on_collect_status` reports `BlockedStatus` with a descriptive `"Invalid configuration: ..."` message

---

### Requirement: Default config values are applied when not overridden
The charm SHALL use defaults defined in `charmcraft.yaml` when the operator has not set a config option.

#### Scenario: No operator override
- **WHEN** `log_level` and `ingestion_mode` have not been set by the operator
- **THEN** the Pebble layer is built with `LOG_LEVEL=info` and `LISTENER_MODE=standalone` (from `charmcraft.yaml` defaults)

---

### Requirement: All charm config options are mapped to workload environment variables
`CharmConfig` from the shared library and the charm's listener configuration SHALL produce the environment variables derived from charm config. Static values are handled by `DEFAULT_CONTAINER_ENV` and SHALL NOT appear in `CharmConfig.to_env_vars()`.

The following config options SHALL be mapped:

| Config key           | Env var                                    | Notes                                            |
|----------------------|--------------------------------------------|--------------------------------------------------|
| `ingestion_mode`     | `LISTENER_MODE`                            | Default `"standalone"`; currently only `"standalone"` is valid |
| `log_level`          | `LOG_LEVEL`                                | Required; `debug\|info\|warn\|error`             |
| `dev`                | `DEV`                                      | Bool; default `false`                            |
| `http_proxy`         | `HTTP_PROXY`                               | Optional string                                  |
| `https_proxy`        | `HTTPS_PROXY`                              | Optional string                                  |
| `no_proxy`           | `NO_PROXY`                                 | Optional string                                  |

Additionally, the charm SHALL inject `LISTENER_FEDERATED_SERVICES_STRATEGY=fs` into the Pebble environment so the workload discovers onboarded federated services from embedded schemas.

#### Scenario: to_env_vars() includes all set config options
- **WHEN** `CharmConfig` is rendered with `log_level="debug"`
- **THEN** the Pebble environment contains `"LOG_LEVEL": "debug"`, `"LISTENER_MODE": "standalone"`, and `"LISTENER_FEDERATED_SERVICES_STRATEGY": "fs"`

---

### Requirement: CPU and memory resource requirements are applied to the container
The charm SHALL accept `cpu` and `memory` config options and apply them to the Kubernetes container resources via `KubernetesComputeResourcesPatch` (from `charms.observability_libs.v0.kubernetes_compute_resources_patch`). These values SHALL NOT be injected as environment variables.

- `cpu` (type: string, optional) — Kubernetes CPU resource value, e.g. `"500m"` or `"2"`.
- `memory` (type: string, optional) — Kubernetes memory resource value, e.g. `"256Mi"` or `"1Gi"`.

When either `cpu` or `memory` is unset (empty string), default requests (`cpu="100m"`, `memory="200Mi"`) are applied via `adjust_resource_requirements`.

`KubernetesComputeResourcesPatch` is instantiated in `charm.py` `__init__` with a `resource_reqs_func` callback. The `patch_failed` event SHALL be observed and reflected in `_on_collect_status`.

#### Scenario: Resource requirements are applied when both cpu and memory are set
- **WHEN** the operator sets `cpu="500m"` and `memory="256Mi"`
- **THEN** `KubernetesComputeResourcesPatch` patches the StatefulSet with the adjusted limits and requests

#### Scenario: Resource requirements use default requests when limits are not set
- **WHEN** `cpu` and `memory` are unset
- **THEN** `KubernetesComputeResourcesPatch` applies the default requests (`cpu="100m"`, `memory="200Mi"`) without limits

#### Scenario: Resource patch failure sets BlockedStatus
- **WHEN** `KubernetesComputeResourcesPatch` reports a failed patch status
- **THEN** `_on_collect_status` reports the non-active patch status
