"""Initialize database: create all tables and default admin user."""
from app import create_app
from app.extensions import db
from app.models.user import User
from app.config import Config


def init_database():
    app = create_app()
    with app.app_context():
        db.create_all()

        if User.query.count() == 0:
            admin = User(username=Config.DEFAULT_ADMIN_USERNAME)
            admin.set_password(Config.DEFAULT_ADMIN_PASSWORD)
            db.session.add(admin)
            db.session.commit()
            print(f"Default admin created: {admin.username} / {Config.DEFAULT_ADMIN_PASSWORD}")
        else:
            print("Database already has users. Skipping admin creation.")

        print("Database initialized successfully.")


if __name__ == "__main__":
    init_database()
