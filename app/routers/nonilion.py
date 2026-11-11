from fastapi import APIRouter, Request, HTTPException
from app.schemas import (
    NonilionWebhookPayload,
    NonilionMessageResponse,
    NonilionPairRequest,
    NonilionPairResponse,
    NonilionStatusResponse
)
from app.services.nonilion_adapter import (
    handle_nonilion_webhook,
    pair_with_room,
    get_nonilion_status,
    poller_instance
)

router = APIRouter(prefix="/nonilion")

@router.post("/webhook", response_model=NonilionMessageResponse, summary="Nonilion Bot API Ingress Webhook")
async def nonilion_webhook(payload: NonilionWebhookPayload, request: Request):
    """
    Ingress endpoint for Nonilion office events.
    Receives user mentions, chat prompts, and queries; delegates them to Veritas AI Master Agent;
    returns structured chat response with evidence score, claims breakdown, and downloadable PDF report.
    """
    base_url = str(request.base_url).rstrip("/")
    return handle_nonilion_webhook(payload, base_url=base_url)


@router.post("/pair", response_model=NonilionPairResponse, summary="Pair bot using Nonilion room pairing code")
def pair_bot(request: NonilionPairRequest):
    """
    Handles the one-time pairing code obtained from Nonilion room's robot button in the Agents dock.
    """
    return pair_with_room(request)


@router.get("/status", response_model=NonilionStatusResponse, summary="Get Nonilion connection & poller status")
def status():
    """
    Returns connection, room pairing, and poller state.
    """
    return get_nonilion_status()


@router.post("/poller/start", summary="Start background polling worker for Nonilion")
def start_poller():
    """
    Activates background polling loop for environments where public webhook URL cannot be reached.
    """
    poller_instance.start()
    return {"status": "started", "polling_active": True}


@router.post("/poller/stop", summary="Stop background polling worker for Nonilion")
def stop_poller():
    """
    Stops background polling worker.
    """
    poller_instance.stop()
    return {"status": "stopped", "polling_active": False}

