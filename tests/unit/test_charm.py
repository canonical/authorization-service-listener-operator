# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for Authorization Service Listener Operator."""

import json

from authorization_service_operator_shared.constants import PEBBLE_SERVICE_NAME
from authorization_service_operator_shared.exceptions import WorkloadError
from conftest import CONTAINER_NAME, create_state
from ops import ActiveStatus, BlockedStatus, WaitingStatus, pebble, testing

from constants import KAFKA_INTEGRATION_NAME


def test_cannot_connect_status(ctx: testing.Context) -> None:
    """Test unit status when container cannot connect."""
    state = create_state(can_connect=False)
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for container")


def test_missing_info_relation_status(
    ctx: testing.Context,
    kafka_relation: testing.Relation,
) -> None:
    """Test unit status when authorization-service-info relation is missing."""
    state = create_state(
        relations=[kafka_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == BlockedStatus(
        "Missing required relation: authorization-service-info"
    )


def test_waiting_database_credentials_status(
    ctx: testing.Context,
    kafka_relation: testing.Relation,
) -> None:
    """Test unit status when database credentials are missing from info relation."""
    empty_info_relation = testing.Relation(
        endpoint="authorization-service-info",
        interface="authorization_service_info",
        remote_app_name="authorization-service",
        remote_app_data={},
    )
    state = create_state(relations=[empty_info_relation, kafka_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for database credentials")


def test_missing_kafka_relation_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
) -> None:
    """Test unit status when kafka relation is missing."""
    state = create_state(relations=[authz_info_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == BlockedStatus("Missing required relation: kafka")


def test_waiting_kafka_ready_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
) -> None:
    """Test unit status when kafka relation is joined but not yet ready."""
    empty_kafka_relation = testing.Relation(
        endpoint="kafka",
        interface="kafka_client",
        remote_app_name="kafka-k8s",
        remote_app_data={},
    )
    state = create_state(relations=[authz_info_relation, empty_kafka_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Kafka relation is not ready yet")


def test_waiting_server_migration_status(
    ctx: testing.Context,
    mocker,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test unit status when server database migration is pending."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        return_value=True,
    )
    state = create_state(relations=[authz_info_relation, kafka_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for the server to run migration")


def test_waiting_server_migration_on_workload_error(
    ctx: testing.Context,
    mocker,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test unit status is BlockedStatus when migrate_status raises WorkloadError."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        side_effect=WorkloadError("migration check error"),
    )
    state = create_state(relations=[authz_info_relation, kafka_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == BlockedStatus("Failed to check database migration status, see logs")


def test_invalid_log_level_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test unit status is BlockedStatus when log_level is invalid."""
    state = create_state(
        config={"log_level": "trace"},
        relations=[authz_info_relation, kafka_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert isinstance(out.unit_status, BlockedStatus)
    assert "Invalid configuration" in out.unit_status.message


def test_failing_workload_health_check_status(
    ctx: testing.Context,
    mocker,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test unit status is BlockedStatus when workload health check is failing."""
    mocker.patch(
        "authorization_service_operator_shared.services.WorkloadService.is_failing",
        return_value=True,
    )
    state = create_state(relations=[authz_info_relation, kafka_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == BlockedStatus(
        "Failed to start the service, please check the container logs"
    )


def test_active_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test unit status is ActiveStatus() when all requirements are satisfied."""
    state = create_state(
        relations=[authz_info_relation, kafka_relation],
    )
    out_plan = ctx.run(ctx.on.config_changed(), state)
    out_status = ctx.run(ctx.on.collect_unit_status(), out_plan)

    assert out_status.unit_status == ActiveStatus()


def test_pebble_ready_plans_layer_and_updates_version(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test pebble_ready event plans layer and sets workload version."""
    state = create_state(
        relations=[authz_info_relation, kafka_relation],
    )
    container = state.get_container(CONTAINER_NAME)
    out = ctx.run(ctx.on.pebble_ready(container), state)

    planned_container = out.get_container(CONTAINER_NAME)
    assert PEBBLE_SERVICE_NAME in planned_container.plan.services
    assert planned_container.plan.services[PEBBLE_SERVICE_NAME].command == "/usr/bin/app listen"
    assert out.workload_version == "0.2.1"


def test_pebble_layer_environment(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test Pebble layer environment variables and health check are correctly injected."""
    state = create_state(
        config={"log_level": "debug"},
        relations=[authz_info_relation, kafka_relation],
    )
    out = ctx.run(ctx.on.config_changed(), state)

    container = out.get_container(CONTAINER_NAME)
    service = container.plan.services[PEBBLE_SERVICE_NAME]
    env = service.environment

    assert env["FEDERATED_SERVICES_STRATEGY"] == "fs"
    assert "FEDERATED_SERVICES" not in env
    assert "KAFKA_FEDERATED_SERVICES" not in env
    assert env["KAFKA_ENABLED"] == "true"
    assert env["KAFKA_BROKERS"] == "kafka.internal:9092"
    assert env["KAFKA_CONSUMER_GROUP"] == "authorization-service"
    assert env["KAFKA_TLS_ENABLED"] == "false"
    assert env["POSTGRES_HOST"] == "pg.internal"
    assert env["POSTGRES_PORT"] == "5432"
    assert env["POSTGRES_DB"] == "authorization_service"
    assert env["POSTGRES_USER"] == "authz_user"
    assert env["POSTGRES_PASSWORD"] == "authz_pass"
    assert env["LOG_LEVEL"] == "debug"

    check = container.plan.checks["ready"]
    assert check.http["url"] == "http://localhost:9100/metrics"

    rel = out.get_relation(kafka_relation.id)
    assert rel.local_app_data["version"] == "v1"
    requests = json.loads(rel.local_app_data["requests"])
    assert len(requests) == 1
    assert requests[0]["resource"] == "permissions.authorization_service"
    assert requests[0]["extra-user-roles"] == "producer,consumer"
    assert requests[0]["consumer-group-prefix"] == "authorization-service"


def test_pebble_layer_with_kafka_tls_enabled(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test Pebble layer environment when Kafka TLS is enabled."""
    secrets = [
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
            tracked_content={"tls": "true", "tls-ca": "cert-data"},
            latest_content={"tls": "true", "tls-ca": "cert-data"},
            owner="remote",
        ),
    ]
    state = create_state(
        relations=[authz_info_relation, kafka_relation],
        secrets=secrets,
    )
    out = ctx.run(ctx.on.config_changed(), state)
    container = out.get_container(CONTAINER_NAME)
    env = container.plan.services[PEBBLE_SERVICE_NAME].environment

    assert env["KAFKA_TLS_ENABLED"] == "true"
    assert env["KAFKA_TLS_CA"] == "cert-data"


def test_pebble_layer_command(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test Pebble layer command is /usr/bin/app listen."""
    state = create_state(
        relations=[authz_info_relation, kafka_relation],
    )
    out = ctx.run(ctx.on.config_changed(), state)

    container = out.get_container(CONTAINER_NAME)
    service = container.plan.services[PEBBLE_SERVICE_NAME]
    assert service.command == "/usr/bin/app listen"


def test_database_config_provided_by_authz_info_relation(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test unit status is active when database credentials are provided by authz_info_relation."""
    state = create_state(
        relations=[authz_info_relation, kafka_relation],
    )
    out_plan = ctx.run(ctx.on.config_changed(), state)
    out_status = ctx.run(ctx.on.collect_unit_status(), out_plan)

    assert out_status.unit_status == ActiveStatus()


def test_kafka_relation_created_requests_roles_and_consumer_group(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
) -> None:
    """Test that new Kafka relation requests producer,consumer roles and consumer group prefix."""
    rel = testing.Relation(
        endpoint=KAFKA_INTEGRATION_NAME,
        interface="kafka_client",
        remote_app_name="kafka-k8s",
    )
    state = create_state(
        relations=[authz_info_relation, rel],
    )
    out = ctx.run(ctx.on.relation_created(rel), state)
    out_rel = out.get_relation(rel.id)
    assert out_rel.local_app_data["version"] == "v1"
    requests = json.loads(out_rel.local_app_data["requests"])
    assert len(requests) == 1
    assert requests[0]["resource"] == "permissions.authorization_service"
    assert requests[0]["extra-user-roles"] == "producer,consumer"
    assert requests[0]["consumer-group-prefix"] == "authorization-service"


def test_kafka_relation_broken_stops_service(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test that breaking the kafka relation stops the Pebble service."""
    state = create_state(
        relations=[authz_info_relation, kafka_relation],
    )
    planned_state = ctx.run(ctx.on.config_changed(), state)
    assert (
        planned_state.get_container(CONTAINER_NAME).service_statuses[PEBBLE_SERVICE_NAME]
        == pebble.ServiceStatus.ACTIVE
    )

    broken_state = ctx.run(ctx.on.relation_broken(kafka_relation), planned_state)
    assert (
        broken_state.get_container(CONTAINER_NAME).service_statuses[PEBBLE_SERVICE_NAME]
        == pebble.ServiceStatus.INACTIVE
    )
