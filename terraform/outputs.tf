# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

output "application" {
  description = "The deployed juju_application resource"
  value       = juju_application.authorization_service_listener
}

output "provides" {
  description = "Map of provides endpoint names"
  value = {
    grafana-dashboard = "grafana-dashboard"
    metrics-endpoint  = "metrics-endpoint"
  }
}

output "requires" {
  description = "Map of requires endpoint names"
  value = {
    authorization-service-info = "authorization-service-info"
    kafka                      = "kafka"
    logging                    = "logging"
    sts-info                   = "sts-info"
    tracing                    = "tracing"
  }
}
