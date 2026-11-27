# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for Authorization Service Listener Operator."""

import json

from authorization_service_operator_shared.constants import (
    GRPC_PORT,
    HTTP_PORT,
    PEBBLE_SERVICE_NAME,
)
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
    sts_relation: testing.Relation,
) -> None:
    """Test unit status when authorization-service-info relation is missing."""
    state = create_state(
        relations=[sts_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == BlockedStatus(
        "Missing required relation: authorization-service-info"
    )


def test_waiting_database_credentials_status(
    ctx: testing.Context,
    sts_relation: testing.Relation,
) -> None:
    """Test unit status when database credentials are missing from info relation."""
    empty_info_relation = testing.Relation(
        endpoint="authorization-service-info",
        interface="authorization_service_info",
        remote_app_name="authorization-service",
        remote_app_data={},
    )
    state = create_state(relations=[empty_info_relation, sts_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for database credentials")


def test_missing_sts_relation_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
) -> None:
    """Test unit status when sts-info relation is missing in standalone mode."""
    state = create_state(relations=[authz_info_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == BlockedStatus("Missing required relation: sts-info")


def test_waiting_sts_ready_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
) -> None:
    """Test unit status when sts-info relation is joined but not yet ready."""
    empty_sts_relation = testing.Relation(
        endpoint="sts-info",
        interface="sts_info",
        remote_app_name="secure-token-service",
        remote_app_data={},
    )
    state = create_state(relations=[authz_info_relation, empty_sts_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("STS relation is not ready yet")


def test_waiting_kafka_ready_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test unit status when kafka relation is joined but not yet ready."""
    empty_kafka_relation = testing.Relation(
        endpoint="kafka",
        interface="kafka_client",
        remote_app_name="kafka-k8s",
        remote_app_data={},
    )
    state = create_state(relations=[authz_info_relation, sts_relation, empty_kafka_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Kafka relation is not ready yet")


def test_waiting_server_migration_status(
    ctx: testing.Context,
    mocker,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test unit status when server database migration is pending."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        return_value=True,
    )
    state = create_state(relations=[authz_info_relation, sts_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for the server to run migration")


def test_waiting_server_migration_on_workload_error(
    ctx: testing.Context,
    mocker,
    caplog,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test unit status is BlockedStatus and DB password is redacted when migrate_status fails."""
    mocker.patch(
        "authorization_service_operator_shared.cli.CommandLine.migrate_status",
        side_effect=WorkloadError(
            "Command ['/usr/bin/app', 'migrate', 'status', '--dsn', 'postgres://authz_user:authz_pass@pg.internal:5432/authorization_service'] failed"
        ),
    )
    state = create_state(relations=[authz_info_relation, sts_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == BlockedStatus("Failed to check database migration status, see logs")
    assert "authz_pass" not in out.unit_status.message
    assert "Failed to check migration status:" in caplog.text
    assert "<redacted>" in caplog.text
    assert "authz_pass" not in caplog.text


def test_invalid_log_level_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test unit status is BlockedStatus when log_level is invalid."""
    state = create_state(
        config={"log_level": "trace"},
        relations=[authz_info_relation, sts_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert isinstance(out.unit_status, BlockedStatus)
    assert "Invalid configuration" in out.unit_status.message


def test_invalid_ingestion_mode_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test unit status is BlockedStatus when ingestion_mode is not standalone."""
    state = create_state(
        config={"ingestion_mode": "platform"},
        relations=[authz_info_relation, sts_relation],
    )
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert isinstance(out.unit_status, BlockedStatus)
    assert "Invalid configuration" in out.unit_status.message
    assert "ingestion_mode" in out.unit_status.message


def test_failing_workload_health_check_status(
    ctx: testing.Context,
    mocker,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test unit status is BlockedStatus when workload health check is failing."""
    mocker.patch(
        "authorization_service_operator_shared.services.WorkloadService.is_failing",
        return_value=True,
    )
    state = create_state(relations=[authz_info_relation, sts_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == BlockedStatus(
        "Failed to start the service, please check the container logs"
    )


def test_waiting_for_workload_to_start_status(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test unit status is WaitingStatus when prerequisites are met but service is not running."""
    state = create_state(relations=[authz_info_relation, sts_relation])
    out = ctx.run(ctx.on.collect_unit_status(), state)

    assert out.unit_status == WaitingStatus("Waiting for workload to start")


def test_active_status_without_kafka(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test unit status is ActiveStatus() in standalone mode when kafka relation is absent."""
    state = create_state(
        relations=[authz_info_relation, sts_relation],
    )
    out_plan = ctx.run(ctx.on.config_changed(), state)
    out_status = ctx.run(ctx.on.collect_unit_status(), out_plan)

    assert out_status.unit_status == ActiveStatus()


def test_pebble_ready_plans_layer_opens_ports_and_updates_version(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test pebble_ready event opens ports, plans layer, and sets workload version."""
    state = create_state(
        relations=[authz_info_relation, sts_relation],
    )
    container = state.get_container(CONTAINER_NAME)
    out = ctx.run(ctx.on.pebble_ready(container), state)

    planned_container = out.get_container(CONTAINER_NAME)
    assert PEBBLE_SERVICE_NAME in planned_container.plan.services
    assert planned_container.plan.services[PEBBLE_SERVICE_NAME].command == "/usr/bin/app listen"
    assert out.workload_version == "0.2.1"
    assert testing.TCPPort(HTTP_PORT) in out.opened_ports
    assert testing.TCPPort(GRPC_PORT) in out.opened_ports


def test_pebble_layer_environment(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test Pebble layer environment variables and health check are correctly injected."""
    state = create_state(
        config={"log_level": "debug"},
        relations=[authz_info_relation, sts_relation],
    )
    out = ctx.run(ctx.on.config_changed(), state)

    container = out.get_container(CONTAINER_NAME)
    service = container.plan.services[PEBBLE_SERVICE_NAME]
    env = service.environment

    assert env["LISTENER_MODE"] == "standalone"
    assert env["LISTENER_FEDERATED_SERVICES_STRATEGY"] == "fs"
    assert "FEDERATED_SERVICES" not in env
    assert "KAFKA_FEDERATED_SERVICES" not in env
    assert "KAFKA_ENABLED" not in env
    assert env["EXTAUTHZ_JWK_SET_URL"] == "https://sts.internal/.well-known/jwks.json"
    assert env["STS_ADDRESS"] == "sts.internal:9090"
    assert env["STS_USE_TLS"] == "true"
    assert env["POSTGRES_HOST"] == "pg.internal"
    assert env["POSTGRES_PORT"] == "5432"
    assert env["POSTGRES_DB"] == "authorization_service"
    assert env["POSTGRES_USER"] == "authz_user"
    assert env["POSTGRES_PASSWORD"] == "authz_pass"
    assert env["LOG_LEVEL"] == "debug"
    assert env["METRICS_ENABLED"] == "true"
    assert env["METRICS_PORT"] == "9100"
    assert env["METRICS_PATH"] == "/metrics"
    assert env["TELEMETRY_ENABLED"] == "false"
    assert env["OTEL_SERVICE_NAME"] == "authorization-service-listener"

    check = container.plan.checks["ready"]
    assert check.http["url"] == f"http://localhost:{HTTP_PORT}/healthz"


def test_tracing_relation_enables_telemetry(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
    tracing_relation: testing.Relation,
) -> None:
    """Test joining the tracing relation enables telemetry and sets OTLP endpoint."""
    state = create_state(
        relations=[authz_info_relation, sts_relation, tracing_relation],
    )
    out = ctx.run(ctx.on.relation_changed(tracing_relation), state)

    container = out.get_container(CONTAINER_NAME)
    env = container.plan.services[PEBBLE_SERVICE_NAME].environment
    assert env["TELEMETRY_ENABLED"] == "true"
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "tempo:4317"
    assert env["OTEL_SERVICE_NAME"] == "authorization-service-listener"

    broken_out = ctx.run(ctx.on.relation_broken(out.get_relation(tracing_relation.id)), out)
    broken_env = (
        broken_out.get_container(CONTAINER_NAME).plan.services[PEBBLE_SERVICE_NAME].environment
    )
    assert broken_env["TELEMETRY_ENABLED"] == "false"
    assert broken_env["OTEL_SERVICE_NAME"] == "authorization-service-listener"
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in broken_env


def test_tracing_relation_missing_protocol_on_non_leader(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test non-leader unit handles tracing relation without requested protocol gracefully."""
    empty_tracing_relation = testing.Relation(
        endpoint="tracing",
        interface="tracing",
        remote_app_name="tempo-coordinator-k8s",
        remote_app_data={"receivers": "[]"},
    )
    state = create_state(
        leader=False,
        relations=[authz_info_relation, sts_relation, empty_tracing_relation],
    )
    out = ctx.run(ctx.on.relation_changed(empty_tracing_relation), state)

    container = out.get_container(CONTAINER_NAME)
    env = container.plan.services[PEBBLE_SERVICE_NAME].environment
    assert env["TELEMETRY_ENABLED"] == "false"
    assert env["OTEL_SERVICE_NAME"] == "authorization-service-listener"
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in env


def test_metrics_endpoint_relation_publishes_scrape_jobs_and_alerts(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test that metrics-endpoint relation publishes scrape jobs and alert rules."""
    metrics_relation = testing.Relation(
        endpoint="metrics-endpoint",
        interface="prometheus_scrape",
        remote_app_name="prometheus-k8s",
    )
    state = create_state(
        leader=True,
        relations=[authz_info_relation, sts_relation, metrics_relation],
    )
    out = ctx.run(ctx.on.relation_joined(metrics_relation), state)

    rel_out = out.get_relation(metrics_relation.id)
    scrape_jobs = json.loads(rel_out.local_app_data["scrape_jobs"])
    assert scrape_jobs == [
        {"metrics_path": "/metrics", "static_configs": [{"targets": ["*:9100"]}]}
    ]
    alert_rules = json.loads(rel_out.local_app_data["alert_rules"])
    alert_names = {
        rule["alert"] for group in alert_rules.get("groups", []) for rule in group.get("rules", [])
    }
    assert "AuthorizationServiceListenerUnavailable-multiple" in alert_names
    assert "AuthorizationServiceListenerUnavailable-all" in alert_names


def test_logging_relation_configures_log_forwarding(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test that logging relation configures Pebble log forwarding and alert rules."""
    logging_relation = testing.Relation(
        endpoint="logging",
        interface="loki_push_api",
        remote_app_name="loki-k8s",
        remote_units_data={
            0: {"endpoint": '{"url": "http://loki:3100/loki/api/v1/push"}'},
        },
    )
    state = create_state(
        leader=True,
        relations=[authz_info_relation, sts_relation, logging_relation],
    )
    out = ctx.run(ctx.on.relation_changed(logging_relation), state)

    container = out.get_container(CONTAINER_NAME)
    assert "listener-log-forwarding" in container.layers
    rel_out = out.get_relation(logging_relation.id)
    alert_rules = json.loads(rel_out.local_app_data["alert_rules"])
    alert_names = {
        rule["alert"] for group in alert_rules.get("groups", []) for rule in group.get("rules", [])
    }
    assert "HighFrequencyHighSeverityLog" in alert_names


def test_resource_reqs_from_config(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test _resource_reqs_from_config returns adjusted resource requirements."""
    state = create_state(
        config={"cpu": "500m", "memory": "512Mi"},
        relations=[authz_info_relation, sts_relation],
    )
    with ctx(ctx.on.config_changed(), state) as manager:
        reqs = manager.charm._resource_reqs_from_config()
        assert reqs.limits == {"cpu": "0.5", "memory": "536870912"}
        assert reqs.requests == {"cpu": "100m", "memory": "200Mi"}


def test_sts_relation_broken_stops_service(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test that breaking the sts-info relation stops the Pebble service."""
    state = create_state(
        relations=[authz_info_relation, sts_relation],
    )
    planned_state = ctx.run(ctx.on.config_changed(), state)
    assert (
        planned_state.get_container(CONTAINER_NAME).service_statuses[PEBBLE_SERVICE_NAME]
        == pebble.ServiceStatus.ACTIVE
    )

    broken_state = ctx.run(ctx.on.relation_broken(sts_relation), planned_state)
    assert (
        broken_state.get_container(CONTAINER_NAME).service_statuses[PEBBLE_SERVICE_NAME]
        == pebble.ServiceStatus.INACTIVE
    )


def test_info_relation_broken_stops_service(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test that breaking the authorization-service-info relation stops the Pebble service."""
    state = create_state(
        relations=[authz_info_relation, sts_relation],
    )
    planned_state = ctx.run(ctx.on.config_changed(), state)
    assert (
        planned_state.get_container(CONTAINER_NAME).service_statuses[PEBBLE_SERVICE_NAME]
        == pebble.ServiceStatus.ACTIVE
    )

    broken_state = ctx.run(ctx.on.relation_broken(authz_info_relation), planned_state)
    assert (
        broken_state.get_container(CONTAINER_NAME).service_statuses[PEBBLE_SERVICE_NAME]
        == pebble.ServiceStatus.INACTIVE
    )


def test_pebble_layer_with_kafka_relation(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test Pebble layer environment variables when optional kafka relation is present."""
    state = create_state(
        relations=[authz_info_relation, sts_relation, kafka_relation],
    )
    out = ctx.run(ctx.on.config_changed(), state)

    container = out.get_container(CONTAINER_NAME)
    env = container.plan.services[PEBBLE_SERVICE_NAME].environment

    assert env["KAFKA_ENABLED"] == "true"
    assert env["KAFKA_BROKERS"] == "kafka.internal:9092"
    assert env["KAFKA_CONSUMER_GROUP"] == "authorization-service"
    assert env["KAFKA_TLS_ENABLED"] == "false"

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
    sts_relation: testing.Relation,
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
        relations=[authz_info_relation, sts_relation, kafka_relation],
        secrets=secrets,
    )
    out = ctx.run(ctx.on.config_changed(), state)
    container = out.get_container(CONTAINER_NAME)
    env = container.plan.services[PEBBLE_SERVICE_NAME].environment

    assert env["KAFKA_TLS_ENABLED"] == "true"
    assert env["KAFKA_TLS_CA"] == "cert-data"


def test_kafka_relation_created_requests_roles_and_consumer_group(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
) -> None:
    """Test that new Kafka relation requests producer,consumer roles and consumer group prefix."""
    rel = testing.Relation(
        endpoint=KAFKA_INTEGRATION_NAME,
        interface="kafka_client",
        remote_app_name="kafka-k8s",
    )
    state = create_state(
        relations=[authz_info_relation, sts_relation, rel],
    )
    out = ctx.run(ctx.on.relation_created(rel), state)
    out_rel = out.get_relation(rel.id)
    assert out_rel.local_app_data["version"] == "v1"
    requests = json.loads(out_rel.local_app_data["requests"])
    assert len(requests) == 1
    assert requests[0]["resource"] == "permissions.authorization_service"
    assert requests[0]["extra-user-roles"] == "producer,consumer"
    assert requests[0]["consumer-group-prefix"] == "authorization-service"


def test_kafka_relation_broken_removes_kafka_env_vars_and_stays_active(
    ctx: testing.Context,
    authz_info_relation: testing.Relation,
    sts_relation: testing.Relation,
    kafka_relation: testing.Relation,
) -> None:
    """Test that breaking the optional kafka relation removes Kafka env vars and stays active."""
    state = create_state(
        relations=[authz_info_relation, sts_relation, kafka_relation],
    )
    planned_state = ctx.run(ctx.on.config_changed(), state)
    assert (
        planned_state.get_container(CONTAINER_NAME).service_statuses[PEBBLE_SERVICE_NAME]
        == pebble.ServiceStatus.ACTIVE
    )

    broken_state = ctx.run(ctx.on.relation_broken(kafka_relation), planned_state)
    container = broken_state.get_container(CONTAINER_NAME)
    assert container.service_statuses[PEBBLE_SERVICE_NAME] == pebble.ServiceStatus.ACTIVE
    env = container.plan.services[PEBBLE_SERVICE_NAME].environment
    assert "KAFKA_BROKERS" not in env
    assert "KAFKA_ENABLED" not in env

    status_state = ctx.run(ctx.on.collect_unit_status(), broken_state)
    assert status_state.unit_status == ActiveStatus()
