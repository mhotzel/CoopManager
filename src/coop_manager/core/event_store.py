"""Implements a event store interface and a default implementation for sqlite3"""
from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime
from sqlite3 import Connection
from uuid import UUID
from typing import List

from . import DomainEvent


class EventStore(ABC):
    """Interface for event store implementations"""

    @abstractmethod
    def add_events(self, events: Sequence[DomainEvent]) -> None:
        """Adds a sequence of domain events to the event store"""

    @abstractmethod
    def read_event_by_id(self, uuid: UUID) -> DomainEvent | None:
        """Reads a specific domain event by it's ID"""

    @abstractmethod
    def read_events_by_subject(self, subject: str) -> Sequence[DomainEvent]:
        """Reads all domain events to the given subject"""


class SqliteEventStore(EventStore):
    """Implementation of an event store with a sqlite database as backend"""

    def __init__(self, db: Connection) -> None:
        super().__init__()
        self._conn = db
        self._create_db()

    def add_events(self, events: Sequence[DomainEvent]) -> None:

        sql = """
            INSERT INTO domain_events
                    (id,   source, type,  subject,  version,
                     time,  data,  metadata,  recorded_at)
            VALUES  (:id, :source, :type, :subject, :version, :time, :data, :metadata, :recorded_at)
        """
        with self._conn:
            with closing(self._conn.cursor()) as cur:
                for event in events:
                    if event.version == DomainEvent.GENERATE_VERSION_NUM:
                        event = event.with_version(
                            self._get_last_version(self._conn, event.subject))
                    cur.execute(sql, {
                        'id': str(event.id),
                        'source': event.source,
                        'type': event.event_type,
                        'subject': event.subject,
                        'version': event.version,
                        'time': event.time.isoformat(),
                        'data': event.data,
                        'metadata': event.metadata,
                        'recorded_at': datetime.now(UTC).isoformat()
                    })

    def _get_last_version(self, conn: Connection, subject: str) -> int:
        """Returns the last version of a event stream"""

        sql = """
            SELECT
                MAX(e.version) as max_ver
            FROM domain_events e
            WHERE e.subject = :subject
        """
        with closing(conn.cursor()) as cur:
            cur.execute(sql, {'subject': subject})
            row = cur.fetchone()
            max_version = 0 if row['max_ver'] is None else row['max_ver'] + 1

        return max_version

    def _create_db(self) -> None:
        sql = """
            -- Store for all domain events
            CREATE TABLE IF NOT EXISTS `domain_events` (
                `position` INTEGER PRIMARY KEY AUTOINCREMENT,
                `id` TEXT NOT NULL,
                `source` TEXT NOT NULL,
                `type` TEXT NOT NULL,
                `subject` TEXT NOT NULL,
                `version` INTEGER NOT NULL,
                `time` TEXT NOT NULL,
                `data` TEXT,
                'metadata' TEXT,
                `recorded_at` TEXT NOT NULL,
                UNIQUE(`subject`, `version`),
                UNIQUE(`id`)
            ) STRICT;

            -- Indexes for faster lookups
            CREATE INDEX IF NOT EXISTS `idx_event_type` ON `domain_events` (`type`);
            CREATE INDEX IF NOT EXISTS `idx_subject_stream` ON `domain_events` (`subject`, `version`);
        """

        with closing(self._conn.cursor()) as cur:
            cur.executescript(sql)

    def read_event_by_id(self, uuid: UUID) -> DomainEvent | None:
        """Reads a specific domain event by it's ID"""

        sql = """
        SELECT 
            e.position,
            e.id,
            e.source,
            e.type,
            e.subject,
            e.version,
            e.time,
            e.data,
            e.metadata,
            e.recorded_at
        FROM domain_events e
        WHERE e.id = :id
        """

        with closing(self._conn.cursor()) as cur:
            cur.execute(sql, {'id': str(uuid)})
            row = cur.fetchone()
            if row is not None:
                return DomainEvent.from_dict(row)

    def read_events_by_subject(self, subject: str) -> Sequence[DomainEvent]:
        """Reads all domain events to the given subject"""

        sql = """
        SELECT 
            e.position,
            e.id,
            e.source,
            e.type,
            e.subject,
            e.version,
            e.time,
            e.data,
            e.metadata,
            e.recorded_at
        FROM domain_events e
        WHERE e.subject = :subject
        ORDER BY e.position
        """

        result: List[DomainEvent] = []
        with closing(self._conn.cursor()) as cur:
            cur.execute(sql, {'subject': subject})
            rows = cur.fetchall()
            for row in rows:
                result.append(DomainEvent.from_dict(row))

        return result
