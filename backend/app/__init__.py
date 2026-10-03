"""Flask application factory."""
import os
import traceback
from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS
from app.config import Config, ensure_dirs
from app.extensions import db
from app.services.logging_service import get_logger, get_app_logger, get_error_logger


def create_app():
    """Create and configure the Flask application."""
    ensure_dirs()
    config = Config()

    app = Flask(
        __name__,
        static_folder=config.STATIC_FOLDER,
        static_url_path=config.STATIC_URL_PATH,
        template_folder=config.TEMPLATE_FOLDER,
    )
    app.config.from_object(config)

    # Database
    db.init_app(app)

    # CORS (not strictly needed since same-origin, but allow for dev)
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

    # Logging + middleware
    get_app_logger().info("Application starting up...")
    from app.core.middleware import LoggingMiddleware
    LoggingMiddleware(app)

    # Global error handlers — log full traceback to error.log, return JSON
    error_logger = get_error_logger()

    @app.errorhandler(500)
    def handle_500(e):
        error_logger.error(
            "Unhandled server error: %s %s\n%s",
            request.method, request.path,
            traceback.format_exc(),
        )
        return jsonify({"error": "Internal server error"}), 500

    @app.errorhandler(403)
    def handle_403(e):
        return jsonify({"error": "Forbidden: you do not have access to this resource"}), 403

    @app.errorhandler(Exception)
    def handle_all_exceptions(e):
        # Let Flask handle HTTP exceptions (404, 401, etc.) normally
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        error_logger.error(
            "Unhandled exception: %s %s\n%s",
            request.method, request.path,
            traceback.format_exc(),
        )
        return jsonify({"error": "Internal server error"}), 500

    # Register API blueprints
    from app.api import register_blueprints
    register_blueprints(app)

    # Guest guard: read-only enforcement for guest sessions
    from app.core.guest_guard import register_guest_guard
    register_guest_guard(app)

    # Enable SQLite WAL mode for concurrent read/write
    @app.before_request
    def enable_wal():
        try:
            db.session.execute(db.text("PRAGMA journal_mode=WAL"))
            db.session.execute(db.text("PRAGMA busy_timeout=5000"))
        except Exception:
            pass

    # Serve frontend HTML pages
    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/<path:filename>")
    def serve_frontend(filename):
        # Try to serve static file first, then HTML page
        if "." in filename and not filename.endswith(".html"):
            return send_from_directory(app.static_folder, filename)
        # HTML pages
        html_file = filename if filename.endswith(".html") else f"{filename}.html"
        file_path = os.path.join(app.static_folder, html_file)
        if os.path.exists(file_path):
            return send_from_directory(app.static_folder, html_file)
        return send_from_directory(app.static_folder, "index.html")

    # Create tables
    with app.app_context():
        from app import models  # noqa: F401
        db.create_all()

        # Migrate: add project_type column to existing tables (idempotent)
        for table_name in ["requirements", "embeddings"]:
            try:
                db.session.execute(db.text(
                    f"ALTER TABLE {table_name} ADD COLUMN project_type VARCHAR(20) DEFAULT 'production'"
                ))
                db.session.commit()
                get_app_logger().info("Migration: added project_type column to %s", table_name)
            except Exception:
                db.session.rollback()

        # Migrate: add missing columns to ai_configs table (idempotent)
        ai_config_columns = [
            ("embedding_model", "VARCHAR(100)"),
            ("connection_status", "VARCHAR(20) DEFAULT 'unknown'"),
            ("last_tested_at", "DATETIME"),
            ("updated_at", "DATETIME"),
            ("config_type", "VARCHAR(20) DEFAULT 'both'"),
        ]
        for col_name, col_type in ai_config_columns:
            try:
                db.session.execute(db.text(
                    f"ALTER TABLE ai_configs ADD COLUMN {col_name} {col_type}"
                ))
                db.session.commit()
                get_app_logger().info("Migration: added column %s to ai_configs", col_name)
            except Exception:
                db.session.rollback()

        # Migrate: add relative_path column to code_documents table (idempotent)
        try:
            db.session.execute(db.text(
                "ALTER TABLE code_documents ADD COLUMN relative_path VARCHAR(500)"
            ))
            db.session.commit()
            get_app_logger().info("Migration: added relative_path column to code_documents")
        except Exception:
            db.session.rollback()

        # Initialize default admin if no users exist
        from app.models.user import User
        if User.query.count() == 0:
            admin = User(
                username=config.DEFAULT_ADMIN_USERNAME,
            )
            admin.set_password(config.DEFAULT_ADMIN_PASSWORD)
            db.session.add(admin)
            db.session.commit()
            get_app_logger().info("Default admin user created: %s", admin.username)

        # Initialize (or upgrade) the default SOP template
        from app.models.sop import SopTemplate
        from app.services.sop_service import DEFAULT_SOP_TEMPLATE, LEGACY_MD_TEMPLATE_MARKER
        sop_template = SopTemplate.query.first()
        if sop_template is None:
            db.session.add(SopTemplate(id=1, content=DEFAULT_SOP_TEMPLATE))
            db.session.commit()
            get_app_logger().info("Default SOP template initialized")
        elif sop_template.content.startswith(LEGACY_MD_TEMPLATE_MARKER):
            # Upgrade legacy Markdown default to the plain-text default
            sop_template.content = DEFAULT_SOP_TEMPLATE
            db.session.commit()
            get_app_logger().info("Default SOP template upgraded to plain text")

    get_app_logger().info("Application ready on port %s", os.environ.get("PORT", 5000))
    return app
