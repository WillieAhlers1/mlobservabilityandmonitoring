"""Chat API routes for the agentic interface."""

import re
import uuid

from flask import request, jsonify

from config_loader import config
from agentic.orchestrator import Orchestrator

# Module-level orchestrator (initialized on first request or at import)
_orchestrator: Orchestrator | None = None

# Max message length (security: prevent oversized payloads)
MAX_MESSAGE_LENGTH = 2000


def _get_orchestrator() -> Orchestrator:
    """Lazy-init the orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator(config.agentic)
    return _orchestrator


def _sanitize_input(text: str) -> str:
    """Basic input sanitization — strip control characters and excessive whitespace."""
    # Remove null bytes and other control characters (keep newlines, tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Collapse excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def register_routes(app):
    """Register chat API routes on the Flask app."""

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        """Handle a chat message and return the assistant's response."""
        if not config.agentic.get("enabled", False):
            return jsonify({"error": "Agentic interface is disabled."}), 403

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be JSON."}), 400

        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "Message field is required."}), 400

        if len(message) > MAX_MESSAGE_LENGTH:
            return jsonify({"error": f"Message exceeds {MAX_MESSAGE_LENGTH} characters."}), 400

        message = _sanitize_input(message)
        if not message:
            return jsonify({"error": "Message field is required."}), 400

        session_id = data.get("session_id") or request.cookies.get("chat_session_id") or str(uuid.uuid4())

        orchestrator = _get_orchestrator()
        result = orchestrator.chat(message=message, session_id=session_id)

        status = 200
        if result.get("error") == "rate_limited":
            status = 429

        response = jsonify({
            "response": result["response"],
            "tool_calls": result["tool_calls"],
            "suggestions": result["suggestions"],
            "data": result["data"],
            "session_id": session_id,
        })
        return response, status

    @app.route("/api/chat/history", methods=["GET"])
    def api_chat_history():
        """Return conversation history for the current session."""
        if not config.agentic.get("enabled", False):
            return jsonify({"error": "Agentic interface is disabled."}), 403

        session_id = request.args.get("session_id", "default")
        orchestrator = _get_orchestrator()
        history = orchestrator.get_history(session_id)
        return jsonify({"history": history, "session_id": session_id})

    @app.route("/api/chat/clear", methods=["POST"])
    def api_chat_clear():
        """Clear conversation history for a session."""
        if not config.agentic.get("enabled", False):
            return jsonify({"error": "Agentic interface is disabled."}), 403

        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id", "default")
        orchestrator = _get_orchestrator()
        orchestrator.clear_session(session_id)
        return jsonify({"status": "cleared", "session_id": session_id})
