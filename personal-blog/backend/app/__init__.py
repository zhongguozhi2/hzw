from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate

from .config import Config
from .models import db
from .routes import api_bp

migrate = Migrate()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)

    app.register_blueprint(api_bp, url_prefix='/api')

    @app.get('/health')
    def health_check():
        return {'status': 'ok'}

    with app.app_context():
        db.create_all()

    return app
