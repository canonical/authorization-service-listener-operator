# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants for the Authorization Service Listener Operator."""

CONTAINER_NAME = "listener"

AUTHORIZATION_SERVICE_INFO_INTEGRATION_NAME = "authorization-service-info"
KAFKA_INTEGRATION_NAME = "kafka"
STS_INFO_INTEGRATION_NAME = "sts-info"
METRICS_INTEGRATION_NAME = "metrics-endpoint"
GRAFANA_INTEGRATION_NAME = "grafana-dashboard"
LOGGING_INTEGRATION_NAME = "logging"
TRACING_INTEGRATION_NAME = "tracing"

STANDALONE_INGESTION_MODE = "standalone"
VALID_INGESTION_MODES = frozenset({STANDALONE_INGESTION_MODE})
