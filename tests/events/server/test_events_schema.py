import json
from uuid import uuid4

import pendulum
import pytest
from pendulum.datetime import DateTime

from prefect._internal.pydantic import HAS_PYDANTIC_V2

if HAS_PYDANTIC_V2:
    from pydantic.v1 import ValidationError
else:
    from pydantic import ValidationError


from prefect.server.events.schemas.events import (
    Event,
    ReceivedEvent,
    RelatedResource,
    Resource,
)


def test_client_events_do_not_have_defaults_for_the_fields_it_seems_they_should():
    """While it seems tempting to include a default for `occurred` or `id`, these
    _must_ be provided by the client for truthiness.  They can have defaults in
    client implementations, but should _not_ have them here."""
    with pytest.raises(ValidationError) as error:
        Event(
            event="hello",
            resource={"prefect.resource.id": "hello"},
            id=uuid4(),
        )

    assert error.value.errors() == [
        {
            "loc": ("occurred",),
            "msg": "field required",
            "type": "value_error.missing",
        },
    ]

    with pytest.raises(ValidationError) as error:
        Event(
            occurred=pendulum.now("UTC"),
            event="hello",
            resource={"prefect.resource.id": "hello"},
        )

    assert error.value.errors() == [
        {"loc": ("id",), "msg": "field required", "type": "value_error.missing"},
    ]


def test_client_events_may_have_empty_related_resources():
    event = Event(
        occurred=pendulum.now("UTC"),
        event="hello",
        resource={"prefect.resource.id": "hello"},
        id=uuid4(),
    )
    assert event.related == []


def test_client_event_resources_have_correct_types():
    event = Event(
        occurred=pendulum.now("UTC"),
        event="hello",
        resource={"prefect.resource.id": "hello"},
        related=[
            {"prefect.resource.id": "related-1", "prefect.resource.role": "role-1"},
        ],
        id=uuid4(),
    )
    assert isinstance(event.resource, Resource)
    assert isinstance(event.related[0], Resource)
    assert isinstance(event.related[0], RelatedResource)


def test_client_events_may_have_multiple_related_resources():
    event = Event(
        occurred=pendulum.now("UTC"),
        event="hello",
        resource={"prefect.resource.id": "hello"},
        related=[
            {"prefect.resource.id": "related-1", "prefect.resource.role": "role-1"},
            {"prefect.resource.id": "related-2", "prefect.resource.role": "role-1"},
            {"prefect.resource.id": "related-3", "prefect.resource.role": "role-2"},
        ],
        id=uuid4(),
    )
    assert event.related[0].id == "related-1"
    assert event.related[0].role == "role-1"
    assert event.related[1].id == "related-2"
    assert event.related[1].role == "role-1"
    assert event.related[2].id == "related-3"
    assert event.related[2].role == "role-2"


def test_client_events_may_have_a_name_label():
    event = Event(
        occurred=pendulum.now("UTC"),
        event="hello",
        resource={"prefect.resource.id": "hello", "prefect.resource.name": "Hello!"},
        related=[
            {
                "prefect.resource.id": "related-1",
                "prefect.resource.role": "role-1",
                "prefect.resource.name": "Related 1",
            },
            {
                "prefect.resource.id": "related-2",
                "prefect.resource.role": "role-1",
                "prefect.resource.name": "Related 2",
            },
            {
                "prefect.resource.id": "related-3",
                "prefect.resource.role": "role-2",
                # deliberately lacks a name
            },
        ],
        id=uuid4(),
    )
    assert event.resource.name == "Hello!"
    assert [related.name for related in event.related] == [
        "Related 1",
        "Related 2",
        None,
    ]


def test_server_events_default_received(start_of_test: DateTime):
    event = ReceivedEvent(
        occurred=pendulum.now("UTC"),
        event="hello",
        resource={"prefect.resource.id": "hello"},
        id=uuid4(),
    )
    assert start_of_test <= event.received <= pendulum.now("UTC")


def test_server_events_can_be_received_from_client_events(start_of_test: DateTime):
    client_event = Event(
        occurred=pendulum.now("UTC"),
        event="hello",
        resource={"prefect.resource.id": "hello"},
        related=[
            {"prefect.resource.id": "related-1", "prefect.resource.role": "role-1"},
        ],
        id=uuid4(),
    )

    server_event = client_event.receive()

    assert isinstance(server_event, ReceivedEvent)

    assert server_event.occurred == client_event.occurred
    assert server_event.event == client_event.event
    assert server_event.resource == client_event.resource
    assert server_event.related == client_event.related
    assert server_event.id == client_event.id
    assert start_of_test <= server_event.received <= pendulum.now("UTC")


def test_json_representation():
    event = ReceivedEvent(
        occurred=pendulum.now("UTC"),
        event="hello",
        resource={"prefect.resource.id": "hello"},
        related=[
            {"prefect.resource.id": "related-1", "prefect.resource.role": "role-1"},
            {"prefect.resource.id": "related-2", "prefect.resource.role": "role-1"},
            {"prefect.resource.id": "related-3", "prefect.resource.role": "role-2"},
        ],
        payload={"hello": "world"},
        id=uuid4(),
        received=pendulum.now("UTC"),
    )

    jsonified = json.loads(event.json().encode())

    assert jsonified == {
        "occurred": event.occurred.isoformat(),
        "event": "hello",
        "resource": {"prefect.resource.id": "hello"},
        "related": [
            {"prefect.resource.id": "related-1", "prefect.resource.role": "role-1"},
            {"prefect.resource.id": "related-2", "prefect.resource.role": "role-1"},
            {"prefect.resource.id": "related-3", "prefect.resource.role": "role-2"},
        ],
        "payload": {"hello": "world"},
        "id": str(event.id),
        "follows": None,
        "received": event.received.isoformat(),
    }