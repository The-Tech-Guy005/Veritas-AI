import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["capabilities"]["master_agent"] is True
    assert data["capabilities"]["deterministic_rubric"] is True

def test_root():
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert "Veritas AI" in data["name"]
    assert "endpoints" in data

def test_master_decompose_endpoint():
    res = client.post("/master/decompose", json={
        "query": "Evaluate the feasibility of sodium-ion battery energy storage for microgrids"
    })
    assert res.status_code == 200
    data = res.json()
    assert "plan" in data
    assert len(data["plan"]["subtasks"]) >= 3
    assert data["plan"]["detected_domain"] == "energy"

def test_master_verify_endpoint():
    res = client.post("/master/verify", json={
        "claims": ["Sodium-ion batteries show lower material costs than lithium-ion"],
        "evidence": [
            {
                "source_title": "Energy Storage Tech Report",
                "url_or_id": "https://www.nrel.gov/sodium-ion.html",
                "source_type": "web",
                "publication_date": "2025-04-12",
                "passage": "Sodium-ion batteries show lower material costs than lithium-ion equivalents.",
                "authority_level": "high"
            },
            {
                "source_title": "Bloomberg Energy Review",
                "url_or_id": "https://www.bloomberg.com/news/sodium-batteries",
                "publication_date": "2025-05-18",
                "passage": "Material costs for sodium-ion batteries are significantly lower than lithium-ion.",
                "authority_level": "high"
            }
        ]
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["claims"]) == 1
    assert data["claims"][0]["status"] == "verified"
    assert data["evidence_strength"]["overall_score"] >= 80

def test_master_orchestrate_endpoint():
    res = client.post("/master/orchestrate", json={
        "query": "What are the trade-offs of sodium-ion versus lithium-ion energy storage?",
        "include_web": False,
        "include_knowledge_base": False,
        "generate_pdf": True
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert "executive_summary" in data
    assert "final_synthesis" in data
    assert data["report_id"] is not None
    assert data["pdf_download_url"] is not None

    # Test downloading the generated PDF
    pdf_res = client.get(data["pdf_download_url"])
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 1000

def test_nonilion_endpoints():
    # Pair bot
    pair_res = client.post("/nonilion/pair", json={
        "pairing_code": "NONILION-HACK-2026",
        "room_id": "hackathon-main-room"
    })
    assert pair_res.status_code == 200
    assert pair_res.json()["status"] == "paired"

    # Status
    status_res = client.get("/nonilion/status")
    assert status_res.status_code == 200
    assert status_res.json()["paired"] is True

    # Webhook
    webhook_res = client.post("/nonilion/webhook", json={
        "event": "message.created",
        "room_id": "hackathon-main-room",
        "sender_id": "judge-1",
        "text": "@VeritasAI Analyze grid-scale hydrogen storage safety standards"
    })
    assert webhook_res.status_code == 200
    data = webhook_res.json()
    assert data["status_update"] == "completed"
    assert "Evidence Strength" in data["text"]

    # Poller controls
    start_res = client.post("/nonilion/poller/start")
    assert start_res.status_code == 200
    assert start_res.json()["polling_active"] is True

    stop_res = client.post("/nonilion/poller/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["polling_active"] is False
