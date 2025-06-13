import logging
import os

from flask import Flask, jsonify, request
from flask_caching import Cache
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

app = Flask(__name__, static_folder="static")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///deaddit.db"
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Configure caching
app.config["CACHE_TYPE"] = "simple"  # Use simple in-memory cache for single-user app
app.config["CACHE_DEFAULT_TIMEOUT"] = 300  # 5 minutes default timeout

db = SQLAlchemy(app)
cache = Cache(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Get the API token from environment variable
API_TOKEN = os.environ.get("API_TOKEN")

# Set up logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

if not API_TOKEN:
    logger.warning("No API_TOKEN set. API routes will be publicly accessible.")


@app.before_request
def authenticate():
    if request.path.startswith("/api/ingest"):
        token = request.headers.get("Authorization")
        if API_TOKEN and (not token or token != f"Bearer {API_TOKEN}"):
            return jsonify({"error": "Unauthorized"}), 401


from .models import Comment, Post, Subdeaddit

with app.app_context():
    db.create_all()


# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({"error": "Resource not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500


@app.errorhandler(Exception)
def handle_exception(e):
    db.session.rollback()
    logger.error(f"Unhandled exception: {str(e)}")
    return jsonify({"error": "An unexpected error occurred"}), 500


from .api import *
from .routes import *
from .admin import admin_bp
from . import websocket  # Import WebSocket handlers

# Register admin blueprint
app.register_blueprint(admin_bp)
