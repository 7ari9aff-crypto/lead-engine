"""Tests for AI pitch & outreach generation API endpoints."""
import pytest
from fastapi.testclient import TestClient

from lead_engine.api import pitch_api
from lead_engine.api.app import app
from lead_engine.db import Database


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "pitch_test.sqlite3")
    database.org_id = "org-test"
    return database


@pytest.fixture()
def client(db):
    def override_get_db(request=None):
        yield db

    app.dependency_overrides[pitch_api.get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(pitch_api.get_db, None)


def test_pitch_generate_direct(client):
    payload = {
        "name": "مجمع عيادات الابتسامة",
        "city": "الرياض",
        "domain": "smile-clinic.sa",
        "decision_maker": "دكتور خالد",
        "industry": "dental",
        "offer": "زيادة حجوزات المرضى وخفض الإلغاءات"
    }
    resp = client.post("/api/v1/pitch/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "cold_email_subject" in data
    assert "cold_email_body" in data
    assert "whatsapp_message" in data
    assert "hook" in data
    assert isinstance(data["pain_points"], list)
    assert len(data["pain_points"]) > 0
    # Check fallback or model returned Saudi/relevant content
    assert "الابتسامة" in data["cold_email_subject"] or "الابتسامة" in data["cold_email_body"]


def test_pitch_generate_for_lead(client, db):
    # Seed a lead in db
    db.conn.execute(
        "INSERT INTO leads (lead_id, name, city, domain, decision_maker, stage, score, organization_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("lead-123", "عيادة النخبة للأسنان", "جدة", "elitedental.com", "دكتور أحمد", "ACCEPTED", 88.0, "org-test")
    )
    db.conn.commit()

    resp = client.post("/api/v1/leads/lead-123/pitch")
    assert resp.status_code == 200
    data = resp.json()
    assert "cold_email_subject" in data
    assert "whatsapp_message" in data
    assert "النخبة" in data["cold_email_subject"] or "النخبة" in data["cold_email_body"]


def test_pitch_generate_lead_not_found(client):
    resp = client.post("/api/v1/leads/lead-nonexistent/pitch")
    assert resp.status_code == 404
