"""Phase 1 smoke tests — verify the FastAPI app boots, the error envelope works,
and basic validation is enforced. No business logic yet (that's Phase 2+)."""


def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "app" in body


def test_unknown_route_uses_envelope(client):
    """A request to a route that doesn't exist must still come back as JSON
    in our uniform error envelope (code=not_found, message=...)."""
    r = client.get("/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "not_found"
    assert "message" in body["error"]


def test_health_is_in_swagger(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/health" in paths


def test_openapi_metadata(client):
    """Verify the app title/version/description show up in the schema."""
    schema = client.get("/openapi.json").json()["info"]
    assert schema["title"] == "Factory Traffic Management API"
    assert schema["version"] == "1.0.0"
    assert "factory" in schema["description"].lower()


def test_validation_envelope_via_pydantic_directly():
    """Directly assert Pydantic v2 validation errors carry the fields we expect.
    Full HTTP-level 422 envelope is verified in Phase 3 once /api/sensor-events
    is wired up — for Phase 1 we just confirm the schema definitions are valid."""
    from app.schemas import VehicleEventIn

    # Valid event
    ok = VehicleEventIn(
        event_id="evt-1", junction_id="A", direction="NORTH",
        event_type="VEHICLE_ARRIVED", vehicle_id="vh-1",
        vehicle_type="TRUCK", sequence_no=1,
        timestamp="2026-10-08T10:00:00Z",
    )
    assert ok.event_id == "evt-1"

    # Invalid event_type triggers Pydantic validation
    import pydantic
    try:
        VehicleEventIn(
            event_id="evt-2", junction_id="A", direction="NORTH",
            event_type="NOPE", vehicle_id="vh-1",
            vehicle_type="TRUCK", sequence_no=1,
            timestamp="2026-10-08T10:00:00Z",
        )
    except pydantic.ValidationError as e:
        assert "event_type" in str(e)
    else:
        raise AssertionError("expected ValidationError for invalid event_type")


def test_ormbase_loads_from_attributes(db):
    """Confirm Pydantic ORM mode works against a real SQLAlchemy row."""
    from datetime import datetime, timezone

    from app.models import Junction
    from app.schemas import JunctionOut

    now = datetime.now(timezone.utc)
    j = Junction(
        id="A", name="Test",
        mode="AUTOMATIC", phase="ALL_RED",
        controller_status="UNKNOWN", manual_override_dir="",
        emergency_dir="",
        created_at=now, updated_at=now,
    )
    db.add(j)
    db.commit()
    db.refresh(j)

    out = JunctionOut.model_validate(j)
    assert out.id == "A"
    assert out.name == "Test"
    assert out.mode == "AUTOMATIC"
    assert out.controller_status == "UNKNOWN"
