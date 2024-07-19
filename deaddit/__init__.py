from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import logging

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///deaddit.db'
db = SQLAlchemy(app)

# Get the API token from environment variable
API_TOKEN = os.environ.get("API_TOKEN")

# Set up logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

if not API_TOKEN:
    logger.warning("No API_TOKEN set. API routes will be publicly accessible.")

@app.before_request
def authenticate():
    if request.path.startswith('/api/'):
        token = request.headers.get('Authorization')
        if API_TOKEN and (not token or token != f"Bearer {API_TOKEN}"):
            return jsonify({"error": "Unauthorized"}), 401

from .models import Post, Comment, Subdeaddit
with app.app_context():
    db.create_all()

from .routes import *
from .api import *