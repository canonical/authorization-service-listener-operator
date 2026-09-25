## Purpose

This capability governs how the listener charm validates and applies operator-supplied configuration. It ensures that all charm config options are properly validated before reaching the workload, provides meaningful `BlockedStatus` feedback when values are invalid, and maps config values to the workload's environment variables via the `CharmConfig` wrapper from the shared library. It also covers resource requirements (`cpu`, `memory`) applied to the Kubernetes container via `KubernetesComputeResourcesPatch`.

---

## ADDED Requirements

### Requirement: log_level config is validated against accepted values
The charm SHALL validate `log_level` against `debug`, `info`, `warn`, `error`. Invalid values SHALL raise `ConfigError` and result in `BlockedStatus`.

#### Scenario: Valid log_level is accepted
- **WHEN** the operator sets `log_level` to `"debug"`
- **THEN** the charm accepts the value and includes `LOG_LEVEL=debug` in the Pebble layer environment

#### Scenario: Invalid log_level is rejected
- **WHEN** the operator sets `log_level` to an unlisted value (e.g., `"verbose"`)
- **THEN** `CharmConfig.from_charm()` raises `ConfigError`
- **AND** `_on_collect_status` reports `BlockedStatus` with a descriptive message

---

### Requirement: Default config values are applied when not overridden
The charm SHALL use defaults defined in `charmcraft.yaml` when the operator has not set a config option.

#### Scenario: No operator override
- **WHEN** `log_level` has not been set by the operator
- **THEN** the Pebble layer is built with `LOG_LEVEL=info` (from `charmcraft.yaml` default)

---

### Requirement: All charm config options are mapped to workload environment variables via CharmConfig
`CharmConfig` from the shared library SHALL produce the full set of environment variables derived from charm config. Static values are handled by `DEFAULT_CONTAINER_ENV` and SHALL NOT appear in `CharmConfig.to_env_vars()`.

The following config options SHALL be mapped:

| Config key           | Env var                                    | Notes                                            |
|----------------------|--------------------------------------------|--------------------------------------------------|
| `log_level`          | `LOG_LEVEL`                                | Required; `debug|info|warn|error`               |
| `dev`                | `DEV`                                      | Bool; default `false`                            |
| `http_proxy`         | `HTTP_PROXY`                               | Optional string                                  |
| `https_proxy`        | `HTTPS_PROXY`                              | Optional string                                  |
| `no_proxy`           | `NO_PROXY`                                 | Optional string                                  |

#### Scenario: to_env_vars() includes all set config options
- **WHEN** `CharmConfig(log_level="debug", dev=True).to_env_vars()` is called
- **THEN** it returns a dict containing at least `{"LOG_LEVEL": "debug", "DEV": "true"}`

---

### Requirement: CPU and memory resource requirements are applied to the container
The charm SHALL accept `cpu` and `memory` config options and apply them to the Kubernetes container resources via `KubernetesComputeResourcesPatch` (from `charms.observability_libs.v0.kubernetes_compute_resources_patch`). These values SHALL NOT be injected as environment variables.

- `cpu` (type: string, optional) — Kubernetes CPU resource value, e.g. `"500m"` or `"2"`. Applied as both `limits.cpu` and `requests.cpu`.
- `memory` (type: string, optional) — Kubernetes memory resource value, e.g. `"256Mi"` or `"1Gi"`. Applied as both `limits.memory` and `requests.memory`.

When either `cpu` or `memory` is unset (empty string), that dimension is omitted from the resource spec.

`KubernetesComputeResourcesPatch` is instantiated in `charm.py` `__init__` with a `resource_reqs_func` lambda that reads `CharmConfig.cpu` and `CharmConfig.memory`. The `patch_failed` event SHALL set `BlockedStatus`.

#### Scenario: Resource requirements are applied when both cpu and memory are set
- **WHEN** the operator sets `cpu="500m"` and `memory="256Mi"`
- **THEN** `KubernetesComputeResourcesPatch` patches the StatefulSet with `limits={"cpu": "500m", "memory": "256Mi"}` and `requests={"cpu": "500m", "memory": "256Mi"}`

#### Scenario: Resource requirements are omitted when not set
- **WHEN** `cpu` and `memory` are unset
- **THEN** `KubernetesComputeResourcesPatch` is initialised with empty resource specs (no patching of cpu/memory)

#### Scenario: Resource patch failure sets BlockedStatus
- **WHEN** `KubernetesComputeResourcesPatch` emits `patch_failed`
- **THEN** `_on_collect_status` reports `BlockedStatus` with the event message
