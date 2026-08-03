"""Agent trace handler.

Processes CTEs with event_type='trace' and writes to agent_traces + agent_trace_steps tables.
"""

import json
import sqlite3
import uuid
from ingestion.models import CanonicalTelemetryEvent


class TracesHandler:
    """Handles trace CTEs → agent_traces + agent_trace_steps tables."""

    target_table = "agent_traces"

    def write(self, db: sqlite3.Connection, cte: CanonicalTelemetryEvent,
              entity_id: str, value, mapping) -> None:
        """Write an agent trace and its steps to the database.

        Expected payload format:
            {
                "trace_id": "...",       # optional, auto-generated if missing
                "query": "...",
                "response": "...",
                "total_latency": 1200,   # ms
                "token_count": 500,
                "voice_score": 0.85,
                "policy_pass": true,
                "policy_note": "...",
                "steps": [
                    {"tool": "search", "action": "query", "latency_ms": 200, "status": "ok"},
                    ...
                ]
            }

        Args:
            db: SQLite connection.
            cte: The canonical telemetry event.
            entity_id: Resolved entity ID.
            value: Not used (payload carries structured data).
            mapping: The MappingDefinition used.
        """
        trace_id = cte.payload.get("trace_id", f"trace-{uuid.uuid4().hex[:12]}")
        query = cte.payload.get("query", "")
        response = cte.payload.get("response", "")
        total_latency = cte.payload.get("total_latency")
        token_count = cte.payload.get("token_count")
        voice_score = cte.payload.get("voice_score")
        policy_pass = cte.payload.get("policy_pass", True)
        policy_note = cte.payload.get("policy_note")

        # Insert the trace record (ignore duplicates by trace_id)
        try:
            db.execute(
                """INSERT INTO agent_traces
                   (entity_id, trace_id, timestamp, query, response,
                    total_latency, token_count, voice_score, policy_pass, policy_note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entity_id, trace_id, cte.timestamp, query, response,
                 total_latency, token_count, voice_score,
                 1 if policy_pass else 0, policy_note),
            )
        except sqlite3.IntegrityError:
            # Duplicate trace_id — skip
            return

        # Insert steps
        steps = cte.payload.get("steps", [])
        for i, step in enumerate(steps):
            db.execute(
                """INSERT INTO agent_trace_steps
                   (trace_id, step_order, tool, action, latency_ms, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (trace_id, i + 1,
                 step.get("tool", "unknown"),
                 step.get("action", ""),
                 step.get("latency_ms"),
                 step.get("status", "ok")),
            )

        db.commit()
