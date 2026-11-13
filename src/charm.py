#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Operator for Authorization Service Listener."""

import logging

import ops
from authorization_service_operator_shared.cli import CommandLine
from authorization_service_operator_shared.configs import CharmConfig
from authorization_service_operator_shared.constants import PEBBLE_SERVICE_NAME
from authorization_service_operator_shared.database import DatabaseConfig
from authorization_service_operator_shared.exceptions import WorkloadError
from authorization_service_operator_shared.info import AuthorizationServiceInfoRequirer
from authorization_service_operator_shared.kafka import KafkaRelationHandler
from authorization_service_operator_shared.observability import (
    GrafanaDashboardHandler,
    MetricsRelationHandler,
    TracingConfig,
)
from authorization_service_operator_shared.services import PebbleService, WorkloadService
from authorization_service_operator_shared.sts import STSRelationHandler
from authorization_service_operator_shared.utils import container_connectivity
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from ops.pebble import Layer

from constants import (
    AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME,
    CONTAINER_NAME,
    GRAFANA_INTEGRATION_NAME,
    KAFKA_INTEGRATION_NAME,
    LOGGING_INTEGRATION_NAME,
    METRICS_INTEGRATION_NAME,
    STANDALONE_INGESTION_MODE,
    STS_INFO_INTEGRATION_NAME,
    TRACING_INTEGRATION_NAME,
    VALID_INGESTION_MODES,
)

logger = logging.getLogger(__name__)


class AuthorizationServiceListenerCharm(ops.CharmBase):
    """Listener charm for Canonical Authorization Service."""

    def __init__(self, framework: ops.Framework) -> None:
        """Initialize the listener charm."""
        super().__init__(framework)

        container = self.unit.get_container(CONTAINER_NAME)
        self._cli = CommandLine(container)
        self._pebble_service = PebbleService(
            container,
            service_name=PEBBLE_SERVICE_NAME,
            command="/usr/bin/app listen",
        )
        self._workload_service = WorkloadService(
            self.unit,
            self._cli,
            container,
            service_name=PEBBLE_SERVICE_NAME,
        )

        self._charm_config = CharmConfig(self.model.config)

        # Kubernetes resource patch
        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            CONTAINER_NAME,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        # Relation handlers
        self.authz_info = AuthorizationServiceInfoRequirer(
            self,
            relation_name=AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME,
        )
        self._sts = STSRelationHandler(
            self,
            relation_name=STS_INFO_INTEGRATION_NAME,
        )
        self._kafka_handler = KafkaRelationHandler(
            self,
            relation_name=KAFKA_INTEGRATION_NAME,
            consumer_group="authorization-service",
        )
        self._kafka_relation_breaking = False
        self.metrics_handler = MetricsRelationHandler(
            self,
            relation_name=METRICS_INTEGRATION_NAME,
        )
        self.grafana_handler = GrafanaDashboardHandler(
            self,
            relation_name=GRAFANA_INTEGRATION_NAME,
        )
        self._tracing = TracingEndpointRequirer(
            self, relation_name=TRACING_INTEGRATION_NAME, protocols=["otlp_http", "otlp_grpc"]
        )
        self._logging = LogForwarder(self, relation_name=LOGGING_INTEGRATION_NAME)

        # Register event observers
        self.framework.observe(self.on.collect_unit_status, self._on_collect_status)
        self.framework.observe(self.on.config_changed, self._on_holistic_handler)
        self.framework.observe(self.on.update_status, self._on_holistic_handler)
        self.framework.observe(self.on.listener_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.resources_patch.on.patch_failed, self._on_holistic_handler)

        self.framework.observe(
            self.authz_info.on.authorization_service_info_updated,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self.authz_info.on.authorization_service_info_broken,
            self._on_info_relation_broken,
        )

        self.framework.observe(
            self._sts.requirer.on.sts_info_relation_updated,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self._sts.requirer.on.sts_info_relation_broken,
            self._on_sts_relation_broken,
        )

        self.framework.observe(
            self._kafka_handler.kafka.on.resource_created,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self._kafka_handler.kafka.on.endpoints_changed,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self._kafka_handler.kafka.on.authentication_updated,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self.on[KAFKA_INTEGRATION_NAME].relation_changed,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self.on[KAFKA_INTEGRATION_NAME].relation_broken,
            self._on_kafka_relation_broken,
        )

        self.framework.observe(
            self._tracing.on.endpoint_changed,
            self._on_holistic_handler,
        )
        self.framework.observe(
            self._tracing.on.endpoint_removed,
            self._on_holistic_handler,
        )

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        """Build resource requirements from charm config."""
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        requests = {"cpu": "100m", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)

    @property
    def _ingestion_mode(self) -> str:
        """Return configured ingestion mode."""
        return str(self.model.config.get("ingestion_mode", STANDALONE_INGESTION_MODE))

    @property
    def _database_config(self) -> DatabaseConfig:
        """Return database config from server info relation."""
        info = self.authz_info.get_info()
        if info and info.is_db_ready:
            return DatabaseConfig.from_info(info)
        return DatabaseConfig()

    @property
    def _is_database_ready(self) -> bool:
        """True if database connection details are provided by server info relation."""
        return self._database_config.is_ready

    @property
    def _is_sts_ready(self) -> bool:
        """True if STS relation details (including JWKS URL) are available."""
        return self._sts.is_ready()

    @property
    def _is_kafka_ready(self) -> bool:
        """True if Kafka bootstrap server details are available."""
        return self._kafka_handler.is_ready()

    @property
    def _pebble_layer(self) -> Layer:
        """Render Pebble layer with updated command and env vars."""
        return self._pebble_service.render_pebble_layer(
            self._charm_config,
            {
                "LISTENER_MODE": self._ingestion_mode,
                "LISTENER_FEDERATED_SERVICES_STRATEGY": "fs",
            },
            self._database_config,
            self._sts,
            self._kafka_handler if self._is_kafka_relation_present else {},
            self.metrics_handler,
            TracingConfig.load(self._tracing),
        )

    @property
    def _is_info_relation_present(self) -> bool:
        """True if authorization-service-info relation exists."""
        return bool(self.model.relations.get(AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME))

    @property
    def _is_sts_relation_present(self) -> bool:
        """True if sts-info relation exists."""
        return bool(self.model.relations.get(STS_INFO_INTEGRATION_NAME))

    @property
    def _is_kafka_relation_present(self) -> bool:
        """True if an active kafka relation exists."""
        return (
            bool(self.model.relations.get(KAFKA_INTEGRATION_NAME))
            and not self._kafka_relation_breaking
        )

    def _get_config_issues(self) -> list[str]:
        """Return a list of configuration validation errors."""
        issues = self._charm_config.get_missing_config_keys()
        if self._ingestion_mode not in VALID_INGESTION_MODES:
            issues.append(
                f"ingestion_mode={self._ingestion_mode!r} (must be one of {sorted(VALID_INGESTION_MODES)})"
            )
        return issues

    def _check_migration_state(self) -> tuple[bool, str | None]:
        """Check whether database migration is pending.

        Returns:
            Tuple of (is_pending: bool, error_msg: str | None).
        """
        if not container_connectivity(self, CONTAINER_NAME) or not self._is_database_ready:
            return False, None
        try:
            return self._cli.migrate_status(self._database_config.dsn), None
        except WorkloadError as exc:
            logger.error("Failed to check migration status: %s", exc)
            return False, str(exc)

    def _on_holistic_handler(self, _event: ops.EventBase) -> None:
        """Apply workload layer when all prerequisite relations are satisfied."""
        if self._get_config_issues():
            return

        is_pending, migration_err = self._check_migration_state()
        if (
            not container_connectivity(self, CONTAINER_NAME)
            or not self._is_info_relation_present
            or not self._is_database_ready
            or (
                self._ingestion_mode == STANDALONE_INGESTION_MODE
                and (not self._is_sts_relation_present or not self._is_sts_ready)
            )
            or (self._is_kafka_relation_present and not self._is_kafka_ready)
            or is_pending
            or migration_err
        ):
            return

        self._pebble_service.plan(self._pebble_layer)

    def _on_info_relation_broken(self, event: ops.EventBase) -> None:
        """Handle authorization-service-info relation broken — stop listener workload."""
        self._pebble_service.stop()
        self._on_holistic_handler(event)

    def _on_sts_relation_broken(self, event: ops.EventBase) -> None:
        """Handle STS relation broken — stop listener workload."""
        if self._ingestion_mode == STANDALONE_INGESTION_MODE:
            self._pebble_service.stop()
        self._on_holistic_handler(event)

    def _on_kafka_relation_broken(self, event: ops.RelationBrokenEvent) -> None:
        """Handle Kafka relation broken — re-plan workload without Kafka environment."""
        self._kafka_relation_breaking = True
        self._on_holistic_handler(event)

    def _on_pebble_ready(self, event: ops.PebbleReadyEvent) -> None:
        """Handle Pebble ready event."""
        self._workload_service.open_port()
        self._on_holistic_handler(event)
        self._workload_service.update_workload_version()

    def _get_config_status(self) -> ops.StatusBase | None:
        """Return status for configuration validation errors."""
        if missing := self._get_config_issues():
            return ops.BlockedStatus(f"Invalid configuration: {missing}")
        return None

    def _get_prerequisite_status(self) -> ops.StatusBase | None:
        """Return status for container connectivity and prerequisite relations."""
        if not container_connectivity(self, CONTAINER_NAME):
            return ops.WaitingStatus("Waiting for container")
        if not self._is_info_relation_present:
            return ops.BlockedStatus(
                f"Missing required relation: {AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME}"
            )
        if not self._is_database_ready:
            return ops.WaitingStatus("Waiting for database credentials")
        if self._ingestion_mode == STANDALONE_INGESTION_MODE:
            if not self._is_sts_relation_present:
                return ops.BlockedStatus(f"Missing required relation: {STS_INFO_INTEGRATION_NAME}")
            if not self._is_sts_ready:
                return ops.WaitingStatus("STS relation is not ready yet")
        if self._is_kafka_relation_present and not self._is_kafka_ready:
            return ops.WaitingStatus("Kafka relation is not ready yet")
        return None

    def _get_migration_status(self) -> ops.StatusBase | None:
        """Return status for database migration state."""
        is_pending, migration_err = self._check_migration_state()
        if migration_err:
            return ops.BlockedStatus("Failed to check database migration status, see logs")
        if is_pending:
            return ops.WaitingStatus("Waiting for the server to run migration")
        return None

    def _get_workload_status(self) -> ops.StatusBase | None:
        """Return status for workload execution."""
        if self._workload_service.is_failing():
            return ops.BlockedStatus(
                "Failed to start the service, please check the container logs"
            )
        if not self._workload_service.is_running():
            return ops.WaitingStatus("Waiting for workload to start")
        return None

    def _on_collect_status(self, event: ops.CollectStatusEvent) -> None:
        """Collect unit status deterministically in priority order."""
        for status_getter in (
            self._get_config_status,
            self._get_prerequisite_status,
            self._get_migration_status,
            self._get_workload_status,
        ):
            if status := status_getter():
                event.add_status(status)
                return

        event.add_status(self.resources_patch.get_status())
        event.add_status(ops.ActiveStatus())


if __name__ == "__main__":
    ops.main(AuthorizationServiceListenerCharm)
