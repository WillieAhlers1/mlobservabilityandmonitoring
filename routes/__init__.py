"""Route modules for the ML Monitoring Platform."""

from routes.core import register_routes as register_core
from routes.onboard import register_routes as register_onboard
from routes.ingestion import register_routes as register_ingestion
from routes.settings import register_routes as register_settings


def register_all_routes(app):
    """Register all route modules on the Flask app."""
    register_core(app)
    register_onboard(app)
    register_ingestion(app)
    register_settings(app)
