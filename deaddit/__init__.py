from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///deaddit.db'
db = SQLAlchemy(app)

from .models import Post, Comment, Subdeaddit
with app.app_context():
    db.create_all()

from .routes import *
from .api import *