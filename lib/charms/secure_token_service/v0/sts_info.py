"""Interface library for sharing Secure Token Service (STS) info.

This library provides a Python API for both providing and requesting STS
deployment info such as endpoints and TLS state.

## Getting Started

To get started using the library, you need to fetch the library using `charmcraft`:

```shell
cd some-charm
charmcraft fetch-lib charms.secure_token_service.v0.sts_info
```

### Provider side

In the `metadata.yaml` (or `charmcraft.yaml`) of the charm, add the following:

```yaml
provides:
  sts-info:
    interface: sts_ready
```

Then, to initialise the library:

```python
from charms.secure_token_service.v0.sts_info import StsInfoProvider

class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.sts_info = StsInfoProvider(self)
        self.framework.observe(self.sts_info.on.sts_info_ready, self._on_sts_info_ready)

    def _on_sts_info_ready(self, event):
        self.sts_info.update_relations_app_data(
            http_address="https://sts.example.com",
            grpc_address="sts.example.svc.cluster.local:9090",
            tls_enabled=True,
        )
```

### Requirer side

In the `metadata.yaml` (or `charmcraft.yaml`) of the charm, add the following:

```yaml
requires:
  sts-info:
    interface: sts_ready
    limit: 1
```

Then, to initialise the library:

```python
from charms.secure_token_service.v0.sts_info import (
    StsInfoRelationError,
    StsInfoRequirer,
)

class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.sts_info = StsInfoRequirer(self)
        self.framework.observe(
            self.sts_info.on.sts_info_relation_updated,
            self._on_sts_info_relation_updated,
        )
        self.framework.observe(
            self.sts_info.on.sts_info_relation_broken,
            self._on_sts_info_relation_broken,
        )

    def _on_sts_info_relation_updated(self, event):
        try:
            sts_data = self.sts_info.get_sts_info()
        except StsInfoRelationError as e:
            ...

    def _on_sts_info_relation_broken(self, event):
        ...
```
"""

import logging

from ops.charm import CharmBase, RelationBrokenEvent, RelationChangedEvent, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents
from pydantic import BaseModel, StrictBool, ValidationError, field_serializer, field_validator

# The unique Charmhub library identifier, never change it
LIBID = "cb702f64e24d4f5f8448c49ed2eda26f"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

PYDEPS = ["pydantic"]

RELATION_NAME = "sts-info"
INTERFACE_NAME = "sts_info"
logger = logging.getLogger(__name__)


class StsInfoData(BaseModel):
    """Validated data model for the sts-info relation databag."""

    http_address: str
    grpc_address: str
    jwks_url: str
    tls_enabled: StrictBool

    @field_validator("tls_enabled", mode="before")
    @classmethod
    def deserialize_bool(cls, v: str | bool) -> bool:
        """Accept stringified booleans stored in the relation databag."""
        if isinstance(v, str):
            return v.casefold() == "true"
        return v

    @field_serializer("tls_enabled")
    def serialize_bool(self, v: bool) -> str:
        """Store tls_enabled as a lowercase string in the relation databag."""
        return str(v).lower()


class StsInfoRelationReadyEvent(EventBase):
    """Event to notify the charm that the sts-info relation is ready."""


class StsInfoProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `StsInfoProvider`."""

    sts_info_ready = EventSource(StsInfoRelationReadyEvent)


class StsInfoRelationUpdatedEvent(EventBase):
    """Event emitted when the sts-info relation data changes."""


class StsInfoRelationBrokenEvent(EventBase):
    """Event emitted when the sts-info relation is removed."""


class StsInfoRequirerEvents(ObjectEvents):
    """Event descriptor for events raised by `StsInfoRequirer`."""

    sts_info_relation_updated = EventSource(StsInfoRelationUpdatedEvent)
    sts_info_relation_broken = EventSource(StsInfoRelationBrokenEvent)


class StsInfoProvider(Object):
    """Provider side of the sts-info relation."""

    on = StsInfoProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME) -> None:
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_created)

    def _on_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.sts_info_ready.emit()

    def update_relations_app_data(
        self,
        http_address: str,
        grpc_address: str,
        tls_enabled: bool,
    ) -> None:
        """Update all active sts-info relations with current endpoint info.

        Only the leader unit writes to the relation databag.
        """
        if not self._charm.unit.is_leader():
            return

        data = StsInfoData(
            http_address=http_address,
            grpc_address=grpc_address,
            jwks_url=f"{http_address.rstrip('/')}/.well-known/jwks.json",
            tls_enabled=tls_enabled,
        )
        serialized = data.model_dump()

        for relation in self.model.relations[self._relation_name]:
            relation.data[self._charm.app].update(serialized)


class StsInfoRelationError(Exception):
    """Base class for sts-info relation exceptions."""


class StsInfoRelationMissingError(StsInfoRelationError):
    """Raised when the sts-info relation is missing."""

    def __init__(self) -> None:
        self.message = "Missing sts-info relation"
        super().__init__(self.message)


class StsInfoRelationDataMissingError(StsInfoRelationError):
    """Raised when information is missing from the sts-info relation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class StsInfoRequirer(Object):
    """Requirer side of the sts-info relation."""

    on = StsInfoRequirerEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME) -> None:
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name

        events = self.charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_broken, self._on_relation_broken)

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        self.on.sts_info_relation_updated.emit()

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        self.on.sts_info_relation_broken.emit()

    def is_ready(self) -> bool:
        """Return True if the relation exists and all required fields are valid."""
        try:
            self.get_sts_info()
            return True
        except StsInfoRelationError:
            return False

    def get_sts_info(self) -> StsInfoData:
        """Return the validated STS endpoint info from the relation databag.

        Raises:
            StsInfoRelationMissingError: when no relation exists.
            StsInfoRelationDataMissingError: when the relation databag is empty or invalid.
        """
        relations = self.model.relations[self.relation_name]
        if not relations:
            raise StsInfoRelationMissingError()

        if not (app := relations[0].app):
            raise StsInfoRelationMissingError()

        data = dict(relations[0].data[app])
        if not data:
            logger.info("No sts-info relation data available.")
            raise StsInfoRelationDataMissingError("Missing relation data")

        try:
            return StsInfoData.model_validate(data)
        except ValidationError as e:
            raise StsInfoRelationDataMissingError(f"Invalid or incomplete relation data: {e}") from e
