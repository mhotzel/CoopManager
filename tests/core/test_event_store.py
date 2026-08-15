"""Test cases for the event store implementation for sqlite3"""
from datetime import datetime
from pathlib import Path
from sqlite3 import (Connection, Row, connect, register_adapter,
                     register_converter)
from uuid import uuid7

import pytest

from coop_manager.core import DomainEvent
from coop_manager.core.event_store import SqliteEventStore


def adapt_datetime_iso(val: datetime) -> str:
    """Convert datetime.datetime to ISO 8601 string for SQLite storage."""
    return val.isoformat()


def convert_datetime_iso(val: bytes) -> datetime:
    """Parse ISO 8601 string from SQLite back into datetime.datetime."""
    return datetime.fromisoformat(val.decode("utf-8"))


@pytest.fixture
def db_connection():
    """Provides a database connection for each test case"""
    db_path = Path(__name__).parent / 'tests' / 'data'
    db_path.mkdir(parents=True, exist_ok=True)
    db_file = db_path / 'testdb.sqlite'

    db_file.unlink()

    db: Connection = connect(db_file)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA synchronous = NORMAL;")
    db.execute("PRAGMA busy_timeout = 5000;")

    # Register the custom adapter and converter globally
    register_adapter(datetime, adapt_datetime_iso)
    register_converter("timestamp", convert_datetime_iso)

    db.row_factory = Row

    yield db

    db.close()


def test_create_sqlite_event_store(db_connection: Connection):
    """Tests the creation af the sqlite event store"""
    SqliteEventStore(db_connection)


def test_add_single_event(db_connection: Connection):
    """Adds a single event to the store"""

    event = DomainEvent.create(
        source='test.source',
        event_type='test.type',
        subject='test.subject',
        data='test.data',
        metadata='test.metadata'
    )

    store = SqliteEventStore(db_connection)
    store.add_events([event])


def test_add_single_event_nodata(db_connection: Connection):
    """Adds a single event to the store without payload"""

    event = DomainEvent.create(
        source='test.source',
        event_type='test.type',
        subject='test.subject'
    )

    store = SqliteEventStore(db_connection)
    store.add_events([event])


def test_add_events_autoversion(db_connection: Connection):
    """Adds a sequence of events to the store with automatically assigned versions"""

    events = []
    for _ in range(3):
        events.append(DomainEvent.create(
            source='test.source',
            event_type='test.type',
            subject='test.subject',
            data='test.data',
            metadata='test.metadata'
        ))

    store = SqliteEventStore(db_connection)
    store.add_events(events)


def test_get_event_by_id_found(db_connection: Connection):
    """Tests if a domain event can be found by it's id (UUID)"""
    store = SqliteEventStore(db_connection)

    event = DomainEvent.create(
        source='test.source',
        event_type='test.type',
        subject='test.subject',
        version=0
    )

    store.add_events([event])
    event_retrieved = store.read_event_by_id(event.id)
    assert event_retrieved is not None
    assert str(event.id) == str(event_retrieved.id)
    assert event == event_retrieved


def test_get_event_by_id_notfound(db_connection: Connection):
    """Tests if a domain event can not be found by it's id (UUID)"""
    store = SqliteEventStore(db_connection)

    event = DomainEvent.create(
        source='test.source',
        event_type='test.type',
        subject='test.subject',
        version=0
    )

    store.add_events([event])
    event_retrieved = store.read_event_by_id(uuid7())
    assert event_retrieved is None


def test_get_events_by_subject_empty(db_connection: Connection):
    """Tests reading a couple of events by theire subject"""

    events = []
    for version in range(4):
        events.append(DomainEvent.create(
            source='test.source',
            event_type='test.type',
            subject='test.subject',
            data='test.data',
            metadata='test.metadata',
            version=version
        ))

    store = SqliteEventStore(db_connection)
    store.add_events(events)

    events_retrieved = store.read_events_by_subject('test.subject')
    assert len(events_retrieved) == len(events)
    for orig, retr in zip(events, events_retrieved):
        assert orig == retr
