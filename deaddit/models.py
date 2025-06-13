import json
from datetime import datetime

from deaddit import db


class Subdeaddit(db.Model):
    name = db.Column(db.String(50), primary_key=True)
    description = db.Column(db.Text)
    post_types = db.Column(db.Text)

    def get_post_types(self):
        return json.loads(self.post_types) if self.post_types else []

    def set_post_types(self, post_types_list):
        self.post_types = json.dumps(post_types_list)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    upvote_count = db.Column(db.Integer, default=0)
    content = db.Column(db.Text)
    subdeaddit_name = db.Column(
        db.String(50), db.ForeignKey("subdeaddit.name"), nullable=False, index=True
    )
    user = db.Column(
        db.String(50), db.ForeignKey("user.username"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    model = db.Column(db.String(100), index=True)
    post_type = db.Column(db.String(50), index=True)

    subdeaddit = db.relationship("Subdeaddit", backref=db.backref("posts", lazy=True))
    comments = db.relationship("Comment", back_populates="post", lazy="dynamic")


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(
        db.Integer, db.ForeignKey("post.id"), nullable=False, index=True
    )
    parent_id = db.Column(
        db.Integer, db.ForeignKey("comment.id"), nullable=True, index=True
    )
    content = db.Column(db.Text)
    upvote_count = db.Column(db.Integer, default=0, index=True)
    user = db.Column(
        db.String(50), db.ForeignKey("user.username"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    model = db.Column(db.String(100), index=True)

    post = db.relationship("Post", back_populates="comments")


class User(db.Model):
    username = db.Column(db.String(50), primary_key=True)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    bio = db.Column(db.Text)
    interests = db.Column(db.Text)
    occupation = db.Column(db.String(100))
    education = db.Column(db.String(100))
    writing_style = db.Column(db.Text)
    personality_traits = db.Column(db.Text)
    model = db.Column(db.String(100))

    posts = db.relationship("Post", backref="author", lazy="dynamic")
    comments = db.relationship("Comment", backref="author", lazy="dynamic")

    def get_interests(self):
        return json.loads(self.interests)

    def get_personality_traits(self):
        return json.loads(self.personality_traits)
