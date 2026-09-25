# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared fixtures for listener charm unit tests."""

import json
from typing import Any

import ops
import pytest
from authorization_service_operator_shared.database import DatabaseConfig
from ops import ActiveStatus, testing
from pytest_mock import MockerFixture

from charm import AuthorizationServiceListenerCharm
from constants import (
    AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME,
    CONTAINER_NAME,
    KAFKA_INTEGRATION_NAME,
)

APP_NAME = "authorization-service-listener"
MODEL_NAME = "testing"

DB_CONFIG = DatabaseConfig(
    host="pg.internal",
    port="5432",
    dbname="authorization_service",
    username="authz_user",
    password="authz_pass",
)


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture) -> None:
    """Prevent KubernetesComputeResourcesPatch from making real K8s API calls."""
    mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="testing",
        _patch=lambda *a, **kw: None,
        is_ready=lambda *a, **kw: True,
        get_status=lambda *a, **kw: ActiveStatus(),
    )


@pytest.fixture(autouse=True)
def mock_migrate_status(mocker: MockerFixture) -> None:
    """Mock CommandLine.migrate_status to return False (migrations up to date) by default."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        return_value=False,
    )


def create_state(
    *,
    leader: bool = True,
    can_connect: bool = True,
    config: dict[str, Any] | None = None,
    relations: list[testing.Relation] | None = None,
    secrets: list[testing.Secret] | None = None,
    extra_execs: list[testing.Exec] | None = None,
    service_status: dict[str, ops.pebble.ServiceStatus] | None = None,
) -> testing.State:
    """Build a testing.State with sensible defaults."""
    default_execs: list[testing.Exec] = []
    if can_connect:
        default_execs.append(
            testing.Exec(["/usr/bin/app", "version"], return_code=0, stdout="0.2.1\n")
        )

    if extra_execs:
        default_execs.extend(extra_execs)

    container = testing.Container(
        name=CONTAINER_NAME,
        can_connect=can_connect,
        execs=set(default_execs),
        service_statuses=service_status or {},
    )

    default_secrets = [
        testing.Secret(
            id="secret:123",
            tracked_content={"db-password": "authz_pass"},
            latest_content={"db-password": "authz_pass"},
        ),
        testing.Secret(
            id="secret:kafka-user",
            tracked_content={"username": "relation-user", "password": "relation-password"},
            latest_content={"username": "relation-user", "password": "relation-password"},
            owner="remote",
        ),
        testing.Secret(
            id="secret:kafka-tls",
            tracked_content={"tls": "false"},
            latest_content={"tls": "false"},
            owner="remote",
        ),
    ]

    return testing.State(
        containers=[container],
        config=config or {},
        leader=leader,
        model=testing.Model(name=MODEL_NAME),
        relations=relations or [],
        secrets=secrets or default_secrets,
    )


@pytest.fixture
def authz_info_relation() -> testing.Relation:
    """Provide a matching authorization-service-info relation."""
    return testing.Relation(
        endpoint=AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME,
        interface="authorization_service_info",
        remote_app_name="authorization-service",
        remote_app_data={
            "workload_version": "0.2.1",
            "migration_version": "0.2.1",
            "db_host": "pg.internal",
            "db_port": "5432",
            "db_name": "authorization_service",
            "db_user": "authz_user",
            "db_secret_id": "secret:123",
        },
    )


@pytest.fixture
def kafka_relation() -> testing.Relation:
    """Provide a matching kafka relation."""
    return testing.Relation(
        endpoint=KAFKA_INTEGRATION_NAME,
        interface="kafka_client",
        remote_app_name="kafka-k8s",
        local_app_data={
            "version": "v1",
            "requests": json.dumps(
                [
                    {
                        "resource": "permissions.authorization_service",
                        "request-id": "req-1",
                        "salt": "salt-1",
                        "extra-user-roles": "producer,consumer",
                        "consumer-group-prefix": "authorization-service",
                    }
                ]
            ),
        },
        remote_app_data={
            "version": "v1",
            "requests": json.dumps(
                [
                    {
                        "request-id": "req-1",
                        "endpoints": "kafka.internal:9092",
                        "secret-user": "secret:kafka-user",
                        "secret-tls": "secret:kafka-tls",
                    }
                ]
            ),
        },
    )


@pytest.fixture
def ctx() -> testing.Context:
    """Context fixture for listener charm testing."""
    return testing.Context(AuthorizationServiceListenerCharm)
