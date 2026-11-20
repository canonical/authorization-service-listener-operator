# Terraform module for authorization-service-listener

This directory contains a Terraform module facilitating the deployment of the `authorization-service-listener` charm using the Juju Terraform provider.

## Usage

```hcl
module "authorization_service_listener" {
  source = "github.com/canonical/authorization-service-listener-operator//terraform"

  model_uuid = var.model_uuid
  app_name   = "authorization-service-listener"
  channel    = "latest/stable"
  units      = 1
}
```

For the complete list of inputs, outputs, and provider requirements, see [MODULE_SPECS.md](./MODULE_SPECS.md).
