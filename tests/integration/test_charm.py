# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the Authorization Service Listener charm."""

import logging
import os
from pathlib import Path

import jubilant
import pytest

from tests.integration.util import (
    APP,
    APP_IMAGE,
    is_blocked,
)

logger = logging.getLogger(__name__)

DEPLOY_TIMEOUT = 10 * 60


@pytest.mark.juju_setup
def test_build_and_deploy(juju: jubilant.Juju, local_charm: Path, tmp_path: Path) -> None:
    """Deploy authorization-service-listener; assert the charm reaches BlockedStatus."""
    logger.info("Fetching Authorization Service image")
    gh_username = os.getenv("GH_USERNAME")
    gh_pat = os.getenv("GH_PAT")

    # Handle the image resource based on environment (GitHub CI/local)
    if gh_username and gh_pat:
        image_resource_path = tmp_path / "image.yaml"
        content = f"registrypath: {APP_IMAGE}\nusername: {gh_username}\npassword: {gh_pat}\n"
        image_resource_path.write_text(content)
        resource = {"oci-image": str(image_resource_path)}
    else:
        resource = {"oci-image": APP_IMAGE}

    juju.deploy(
        local_charm,
        app=APP,
        resources=resource,
        trust=True,
    )

    juju.wait(
        ready=is_blocked(APP),
        timeout=DEPLOY_TIMEOUT,
    )
