# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pytest fixtures for integration tests."""

import logging
import os
import subprocess
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def local_charm() -> Path:
    """Return path to the packed charm, building it if necessary."""
    if charm_path := os.getenv("CHARM_PATH"):
        path = Path(charm_path)
        if not path.exists():
            raise FileNotFoundError(
                f"CHARM_PATH is set to '{charm_path}' but the file does not exist"
            )
        return path.resolve()

    if local := next(Path(".").glob("authorization-service-listener*.charm"), None):
        return local.resolve()

    logger.info("No charm file found — running 'charmcraft pack'")
    try:
        subprocess.run(["charmcraft", "pack"], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Charm build failed: {e}") from e

    if packed := next(Path(".").glob("authorization-service-listener*.charm"), None):
        return packed.resolve()

    raise RuntimeError("charmcraft pack succeeded but no .charm file was produced")
