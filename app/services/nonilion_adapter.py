"""
Nonilion Bot API & Ingress Adapter
Provides:
1. One-time pairing code handling (pairing with Nonilion room / office dock)
2. Ingress webhook handling for Nonilion room mentions & direct messages
3. Formatted chat message formatting (executive summary + evidence score + citations + PDF download link)
4. Background polling worker for environments behind NAT/firewall without public webhooks
"""

import time
import threading
import datetime
import requests
from typing import Dict, Any, Optional, List
from app.config import settings
from app.schemas import (
    NonilionWebhookPayload,
    NonilionMessageResponse,
    NonilionPairRequest,
    NonilionPairResponse,
    NonilionStatusResponse,
    MasterOrchestrationRequest,
    MasterOrchestrationResponse
)
from app.services.master_agent import run_master_orchestration

class NonilionState:
    def __init__(self):
        self.paired: bool = bool(settings.nonilion_pairing_code and settings.nonilion_room_id)
        self.room_id: Optional[str] = settings.nonilion_room_id or None
        self.bot_name: str = settings.nonilion_bot_name
        self.pairing_code: Optional[str] = settings.nonilion_pairing_code or None
        self.polling_active: bool = False
        self.last_poll_at: Optional[str] = None
        self.poller_thread: Optional[threading.Thread] = None
        self.processed_message_ids: set = set()

nonilion_state = NonilionState()

def pair_with_room(pair_req: NonilionPairRequest) -> NonilionPairResponse:
    """
    Handles Nonilion one-time pairing code handshake.
    Pairs the Veritas AI bot to the specified office/room.
    """
    nonilion_state.pairing_code = pair_req.pairing_code
    nonilion_state.room_id = pair_req.room_id or "room-default"
    nonilion_state.paired = True

    # If Nonilion API token or remote endpoint is configured, notify Nonilion API
    if settings.nonilion_bot_token and settings.nonilion_api_url:
        try:
            url = f"{settings.nonilion_api_url}/bots/pair"
            headers = {"Authorization": f"Bearer {settings.nonilion_bot_token}", "Content-Type": "application/json"}
            requests.post(url, json={
                "pairing_code": pair_req.pairing_code,
                "room_id": nonilion_state.room_id,
                "bot_name": nonilion_state.bot_name
            }, headers=headers, timeout=10)
        except Exception:
            pass

    return NonilionPairResponse(
        status="paired",
        room_id=nonilion_state.room_id,
        bot_name=nonilion_state.bot_name,
        paired_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


def format_nonilion_reply(orchestration: MasterOrchestrationResponse, base_url: str = "") -> NonilionMessageResponse:
    """
    Formats the Master Agent orchestration result into Nonilion chat message standards:
    - Clear, emoji-assisted executive summary
    - Heuristic evidence-strength badge and points
    - Verified vs Disputed claims summary
    - Citations and traceable document links
    - Link to download executive PDF report
    """
    lines = []
    
    if orchestration.clarification_needed:
        lines.append(f"🔍 **Veritas AI — Clarification Needed**")
        lines.append(f"{orchestration.clarification_prompt}")
        return NonilionMessageResponse(
            text="\n\n".join(lines),
            attachments=[],
            status_update="clarification_needed"
        )

    score = orchestration.evidence_strength.overall_score
    score_emoji = "🟢" if score >= 75 else ("🟡" if score >= 45 else "🔴")

    lines.append(f"🤖 **Veritas AI Evidence Report** &nbsp;|&nbsp; {score_emoji} **Evidence Strength:** {score}/100 *(Heuristic)*")
    lines.append(f"*{orchestration.evidence_strength.explanation}*")
    lines.append("")
    lines.append("### 📋 Executive Summary")
    lines.append(orchestration.executive_summary)
    lines.append("")
    
    if orchestration.claims:
        lines.append("### 🔬 Material Claims & Verification Status")
        for c in orchestration.claims:
            icon = "✅" if c.status.value == "verified" else ("⚠️" if c.status.value == "partially_supported" else "❌")
            lines.append(f"- {icon} **[{c.status.value.upper()}]** {c.statement} *({c.rubric_score}/100 pts)*")

    if orchestration.citations:
        lines.append("")
        lines.append("### 🔗 Citations & Grounded Sources")
        for cit in orchestration.citations[:5]:
            lines.append(f"- {cit}")

    if orchestration.limitations:
        lines.append("")
        lines.append("### ⚠️ Disclosed Limitations & Uncertainty")
        for lim in orchestration.limitations[:3]:
            lines.append(f"- {lim}")

    attachments = []
    if orchestration.pdf_download_url:
        full_pdf_url = f"{base_url}{orchestration.pdf_download_url}" if base_url else orchestration.pdf_download_url
        lines.append("")
        lines.append(f"📄 **Download Full Executive Verification PDF:** [Download PDF]({full_pdf_url})")
        attachments.append(full_pdf_url)

    return NonilionMessageResponse(
        text="\n".join(lines),
        attachments=attachments,
        status_update="completed",
        report_id=orchestration.report_id
    )


def handle_nonilion_webhook(payload: NonilionWebhookPayload, base_url: str = "") -> NonilionMessageResponse:
    """
    Ingress point for Nonilion webhook events.
    Parses room message, executes Master Agent orchestration, and sends back formatted response.
    """
    clean_text = payload.text.strip()
    # Strip bot mentions if present e.g. @VeritasAI or @veritas
    import re
    cleaned_query = re.sub(r"@\w+", "", clean_text).strip()
    if not cleaned_query:
        cleaned_query = clean_text

    orch_req = MasterOrchestrationRequest(
        query=cleaned_query,
        include_web=True,
        include_knowledge_base=True,
        generate_pdf=True,
        room_id=payload.room_id
    )
    result = run_master_orchestration(orch_req)
    return format_nonilion_reply(result, base_url=base_url)


def post_message_to_nonilion_room(room_id: str, message: NonilionMessageResponse):
    """
    Sends message to Nonilion Bot API room endpoint.
    """
    if not settings.nonilion_bot_token or not settings.nonilion_api_url:
        return
    url = f"{settings.nonilion_api_url}/rooms/{room_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.nonilion_bot_token}",
        "Content-Type": "application/json"
    }
    try:
        requests.post(url, json={
            "text": message.text,
            "attachments": message.attachments,
            "bot_name": nonilion_state.bot_name
        }, headers=headers, timeout=10)
    except Exception:
        pass


class NonilionPoller:
    """
    Background polling worker for Nonilion Bot API.
    Polls Nonilion room events when public webhooks are not available.
    """
    def __init__(self, interval: int = 5):
        self.interval = interval
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.running = True
        nonilion_state.polling_active = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        nonilion_state.polling_active = False

    def _poll_loop(self):
        while self.running:
            nonilion_state.last_poll_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if nonilion_state.paired and nonilion_state.room_id and settings.nonilion_bot_token:
                try:
                    url = f"{settings.nonilion_api_url}/rooms/{nonilion_state.room_id}/messages?unread=true"
                    headers = {"Authorization": f"Bearer {settings.nonilion_bot_token}"}
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        messages = data.get("messages", [])
                        for msg in messages:
                            msg_id = msg.get("id")
                            if msg_id and msg_id not in nonilion_state.processed_message_ids:
                                nonilion_state.processed_message_ids.add(msg_id)
                                text = msg.get("text", "")
                                if f"@{nonilion_state.bot_name.lower()}" in text.lower() or msg.get("direct", False):
                                    payload = NonilionWebhookPayload(
                                        event="message.created",
                                        room_id=nonilion_state.room_id,
                                        sender_id=msg.get("sender_id"),
                                        text=text
                                    )
                                    reply = handle_nonilion_webhook(payload)
                                    post_message_to_nonilion_room(nonilion_state.room_id, reply)
                except Exception:
                    pass
            time.sleep(self.interval)

poller_instance = NonilionPoller(interval=settings.nonilion_poll_interval_seconds)

def get_nonilion_status() -> NonilionStatusResponse:
    return NonilionStatusResponse(
        connected=bool(nonilion_state.paired),
        paired=nonilion_state.paired,
        room_id=nonilion_state.room_id,
        bot_name=nonilion_state.bot_name,
        polling_active=nonilion_state.polling_active,
        last_poll_at=nonilion_state.last_poll_at
    )
