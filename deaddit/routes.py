from flask import render_template, jsonify, request
from deaddit import app, db
from .models import Post, Comment, Subdeaddit
from datetime import datetime

from sqlalchemy import func


@app.route("/")
def index():
    page = request.args.get("page", default=1, type=int)
    posts_per_page = 20
    offset = (page - 1) * posts_per_page

    # Current time in UTC
    current_time = datetime.utcnow()

    # Calculate the hours difference using SQLite's strftime and julianday
    hours_difference = (func.julianday(current_time) - func.julianday(Post.created_at)) * 24

    # Calculate the score as upvotes divided by hours since creation
    # Using coalesce to handle division by zero by setting a minimum value of 1 hour
    score = Post.upvote_count / func.coalesce(hours_difference, 1.0)

    # Query posts ordered by the new score
    posts = Post.query.order_by(score.desc()).offset(offset).limit(posts_per_page).all()
    total_posts = Post.query.count()

    # Gather comment counts for each post
    comment_counts = {post.id: Comment.query.filter_by(post_id=post.id).count() for post in posts}
    has_more = total_posts > page * posts_per_page

    return render_template(
        "index.html",
        posts=posts,
        comment_counts=comment_counts,
        page=page,
        has_more=has_more,
    )


@app.route("/d/<subdeaddit_name>")
def subdeaddit(subdeaddit_name):
    page = request.args.get("page", default=1, type=int)
    posts_per_page = 10
    offset = (page - 1) * posts_per_page
    subdeaddit = Subdeaddit.query.get_or_404(subdeaddit_name)
    posts = (
        Post.query.filter_by(subdeaddit_name=subdeaddit_name)
        .order_by(Post.upvote_count.desc())
        .offset(offset)
        .limit(posts_per_page)
        .all()
    )
    total_posts = Post.query.filter_by(subdeaddit_name=subdeaddit_name).count()

    comment_counts = {}
    for post in posts:
        count = Comment.query.filter_by(post_id=post.id).count()
        comment_counts[post.id] = count

    has_more = total_posts > page * posts_per_page

    return render_template(
        "subdeaddit.html",
        posts=posts,
        comment_counts=comment_counts,
        subdeaddit_name=subdeaddit_name,
        page=page,
        has_more=has_more,
    )


@app.route("/d/<subdeaddit_name>/<int:post_id>")
def post(subdeaddit_name, post_id):
    post = Post.query.get_or_404(post_id)

    # Query root comments ordered by newest first
    root_comments = Comment.query.filter_by(post_id=post_id, parent_id="").order_by(Comment.upvote_count.desc()).all()

    # Build the comment tree
    comment_tree = build_comment_tree(root_comments)

    return render_template("post.html", post=post, comment_tree=comment_tree, subdeaddit_name=subdeaddit_name)


def build_comment_tree(comments, level=0):
    tree = []
    for comment in comments:
        # Create a dictionary for each comment with its properties and children
        comment_dict = {
            "id": comment.id,
            "content": comment.content,
            "upvote_count": comment.upvote_count,
            "user": comment.user,
            "created_at": comment.created_at,
            "level": level,
            "children": [],
        }

        # Query child comments of the current comment
        child_comments = Comment.query.filter_by(parent_id=comment.id).order_by(Comment.created_at).all()

        # Recursively build the comment tree for child comments
        comment_dict["children"] = build_comment_tree(child_comments, level + 1)

        tree.append(comment_dict)

    return tree


@app.route("/list_subdeaddit")
def list_subdeaddit():
    page = request.args.get("page", default=1, type=int)
    subdeaddits_per_page = 100

    # Count the number of posts for each subdeaddit
    subdeaddit_post_counts = (
        db.session.query(Subdeaddit.name, Subdeaddit.description, func.count(Post.id).label("post_count"))
        .outerjoin(Post)
        .group_by(Subdeaddit.name, Subdeaddit.description)
        .order_by(func.count(Post.id).desc())
    )

    # Paginate the results
    paginated_subdeaddits = subdeaddit_post_counts.paginate(page=page, per_page=subdeaddits_per_page)

    return render_template("list_subdeaddit.html", subdeaddits=paginated_subdeaddits)
