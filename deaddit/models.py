from deaddit import db
from datetime import datetime


class Subdeaddit(db.Model):
    name = db.Column(db.String(50), primary_key=True)
    description = db.Column(db.Text)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    upvote_count = db.Column(db.Integer, default=0)
    content = db.Column(db.Text)
    subdeaddit_name = db.Column(db.String(50), db.ForeignKey("subdeaddit.name"), nullable=False)
    user = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    subdeaddit = db.relationship("Subdeaddit", backref=db.backref("posts", lazy=True))


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comment.id"), nullable=True)
    content = db.Column(db.Text)
    upvote_count = db.Column(db.Integer, default=0)
    user = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
