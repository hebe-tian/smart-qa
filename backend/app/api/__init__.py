"""API package - register all blueprints."""
from app.api.auth import auth_bp
from app.api.requirements import requirements_bp
from app.api.qa import qa_bp
from app.api.modules import modules_bp
from app.api.cases import cases_bp
from app.api.generate import generate_bp
from app.api.regenerate import regenerate_bp
from app.api.tasks import tasks_bp
from app.api.ai_config import ai_config_bp
from app.api.call_logs import call_logs_bp
from app.api.analytics import analytics_bp
from app.api.export import export_bp
from app.api.rag import rag_bp
from app.api.kbqa import kbqa_bp
from app.api.code import code_bp
from app.api.sop import sop_bp


def register_blueprints(app):
    """Register all API blueprints to the Flask app."""
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(requirements_bp, url_prefix="/api/requirements")
    app.register_blueprint(qa_bp, url_prefix="/api/qa")
    app.register_blueprint(modules_bp, url_prefix="/api/modules")
    app.register_blueprint(cases_bp, url_prefix="/api/cases")
    app.register_blueprint(generate_bp, url_prefix="/api/generate")
    app.register_blueprint(regenerate_bp, url_prefix="/api/regenerate")
    app.register_blueprint(tasks_bp, url_prefix="/api/tasks")
    app.register_blueprint(ai_config_bp, url_prefix="/api/ai-config")
    app.register_blueprint(call_logs_bp, url_prefix="/api/call-logs")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")
    app.register_blueprint(export_bp, url_prefix="/api/export")
    app.register_blueprint(rag_bp, url_prefix="/api/rag")
    app.register_blueprint(kbqa_bp, url_prefix="/api/kbqa")
    app.register_blueprint(code_bp, url_prefix="/api/code")
    app.register_blueprint(sop_bp, url_prefix="/api/sop")
