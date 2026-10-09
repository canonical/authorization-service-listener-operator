# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared helpers and constants for integration tests."""

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import jubilant
import yaml
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP = METADATA["name"]
APP_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]

StatusPredicate = Callable[[jubilant.Status], bool]


def all_active(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_active(status, *apps)


def is_active(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_active


def is_blocked(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_blocked


def is_waiting(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_waiting


def any_error(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.any_error(status, *apps)


def unit_number(app: str, expected_num: int) -> StatusPredicate:
    return lambda status: len(status.apps[app].units) == expected_num


def and_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: all(predicate(status) for predicate in predicates)


def or_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: any(predicate(status) for predicate in predicates)


def get_unit_data(juju: jubilant.Juju, unit_name: str) -> dict:
    stdout = juju.cli("show-unit", unit_name)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


def get_integration_data(
    juju: jubilant.Juju,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> dict | None:
    data = get_unit_data(juju, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


def get_app_integration_data(
    juju: jubilant.Juju,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> dict | None:
    data = get_integration_data(juju, app_name, integration_name, unit_num)
    return data.get("application-data") if data else None


@contextmanager
def remove_integration(
    juju: jubilant.Juju, remote_app_name: str, integration_name: str
) -> Generator[None, None, None]:
    """Temporarily remove an integration, restoring it after the context exits."""
    juju.remove_relation(f"{APP}:{integration_name}", remote_app_name)
    try:
        yield
    finally:
        try:
            for attempt in Retrying(
                retry=retry_if_exception_type(jubilant.CLIError),
                wait=wait_exponential(multiplier=2, min=1, max=30),
                stop=stop_after_attempt(10),
                reraise=True,
            ):
                with attempt:
                    juju.integrate(f"{APP}:{integration_name}", remote_app_name)
        except RetryError:
            logger.error(
                "Failed to restore the integration: %s:%s - %s",
                APP,
                integration_name,
                remote_app_name,
            )
            raise RuntimeError("Failed to restore integration")

        juju.wait(
            ready=lambda status: jubilant.all_active(status, APP, remote_app_name),
            timeout=5 * 60,
        )
