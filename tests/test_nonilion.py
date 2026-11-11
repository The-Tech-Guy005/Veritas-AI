import pytest
from app.services.nonilion_adapter import (
    pair_with_room,
    handle_nonilion_webhook,
    get_nonilion_status,
    nonilion_state
)
from app.schemas import NonilionPairRequest, NonilionWebhookPayload

def test_nonilion_pairing_handshake():
    req = NonilionPairRequest(pairing_code="DEMO-PAIR-9988", room_id="room-hackathon-1")
    resp = pair_with_room(req)
    assert resp.status == "paired"
    assert resp.room_id == "room-hackathon-1"
    assert nonilion_state.paired is True

    status = get_nonilion_status()
    assert status.paired is True
    assert status.room_id == "room-hackathon-1"

def test_nonilion_webhook_handling():
    payload = NonilionWebhookPayload(
        event="message.created",
        room_id="room-hackathon-1",
        sender_id="user-123",
        text="@VeritasAI What are the recent efficiency advancements in perovskite solar cells?"
    )
    reply = handle_nonilion_webhook(payload, base_url="http://localhost:8000")
    assert reply.status_update == "completed"
    assert "Evidence Strength" in reply.text
    assert reply.report_id is not None
    assert len(reply.attachments) > 0

def test_nonilion_webhook_clarification_handling():
    payload = NonilionWebhookPayload(
        event="message.created",
        room_id="room-hackathon-1",
        sender_id="user-123",
        text="@VeritasAI hi"
    )
    reply = handle_nonilion_webhook(payload)
    assert reply.status_update == "clarification_needed"
    assert "Clarification" in reply.text

