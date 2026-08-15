"""Implementation of a domain event"""

from dataclasses import dataclass, replace
import uuid
from datetime import datetime, timezone
from typing import Self, ClassVar, Any


@dataclass(frozen=True)
class DomainEvent:
    """This class implements a domain event. All attributes are immutable."""

    GENERATE_VERSION_NUM: ClassVar[int] = -1
    """
    Signals the event store, that there is no version check necessary,
    and it can generate a version number automatically
    """

    id: uuid.UUID
    source: str
    event_type: str
    subject: str
    time: datetime
    data: str | None
    metadata: str | None
    version: int

    @classmethod
    def create(cls, source: str, event_type: str, subject: str, data: str | None = None,
               metadata: str | None = None, version: int = GENERATE_VERSION_NUM) -> Self:
        """Factory to create a domain event. The time and id will be generated automatically"""
        return cls(
            id=uuid.uuid7(),
            source=source,
            event_type=event_type,
            subject=subject,
            time=datetime.now(timezone.utc),
            data=data,
            metadata=metadata,
            version=version
        )

    def with_version(self, version: int) -> DomainEvent:
        """Returns a copy of this domain event with the given version number"""
        return replace(self, version=version)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> DomainEvent:
        """
        creates a Domain Event from a dictionary. The following keys are expected:
        - id (UUID)
        - type (str)
        - subject (str)
        - version (int)
        - time (datetime, ISO8601, UTC)
        - data (any kind of str, but only XML or JSON makes sense)
        - metadata (any kind of str, but only XML or JSON makes sense)
        """

        return cls(
            id=uuid.UUID(row['id']),
            source=row['source'],
            event_type=row['type'],
            subject=row['subject'],
            time=datetime.fromisoformat(row['time']),
            data=row['data'],
            metadata=row['metadata'],
            version=row['version']
        )
