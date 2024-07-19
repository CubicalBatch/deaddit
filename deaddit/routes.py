from flask import render_template, jsonify, request
from deaddit import app, db
from .models import Post, Comment, Subdeaddit, User
from datetime import datetime
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from itertools import cycle
import re
import random

def process_title(title):
    # Remove <br>, <p>, and </p> tags
    title = re.sub(r'<br>|<p>|</p>', '', title)
    
    # Replace "reddit" with "deaddit" (case-insensitive)
    title = re.sub(r'reddit', 'deaddit', title, flags=re.IGNORECASE)
    
    return title

@app.route("/")
def index():
    page = request.args.get("page", default=1, type=int)
    posts_per_page = 20
    offset = (page - 1) * posts_per_page

    # Get selected models from query parameters
    selected_models = request.args.getlist("models")

    # Get all posts and randomize the order
    query = Post.query.order_by(func.random())
    
    # Apply model filter if models are selected
    if selected_models:
        query = query.filter(Post.model.in_(selected_models))
    
    all_posts = query.all()

    # Get all unique models (either selected or all) and randomize their order
    if selected_models:
        all_models = selected_models
    else:
        all_models = db.session.query(Post.model).distinct().all()
        all_models = [model[0] for model in all_models]
    
    # Randomize the order of models
    random.shuffle(all_models)
    model_cycle = cycle(all_models)

    # Create a dictionary to store posts by model
    posts_by_model = {model: [] for model in all_models}

    # Populate the posts_by_model dictionary
    for post in all_posts:
        if post.model in posts_by_model:
            post.title = process_title(post.title)
            posts_by_model[post.model].append(post)

    # Create the final ordered list of posts
    ordered_posts = []
    while len(ordered_posts) < len(all_posts):
        current_model = next(model_cycle)
        if posts_by_model[current_model]:
            ordered_posts.append(posts_by_model[current_model].pop(0))

    # Apply pagination
    paginated_posts = ordered_posts[offset:offset+posts_per_page]
    total_posts = len(all_posts)

    # Gather comment counts for each post
    comment_counts = {post.id: Comment.query.filter_by(post_id=post.id).count() for post in paginated_posts}
    has_more = total_posts > page * posts_per_page

    return render_template(
        "index.html",
        posts=paginated_posts,
        comment_counts=comment_counts,
        page=page,
        has_more=has_more,
        selected_models=selected_models
    )

@app.route("/d/<subdeaddit_name>")
def subdeaddit(subdeaddit_name):
    page = request.args.get("page", default=1, type=int)
    posts_per_page = 10
    offset = (page - 1) * posts_per_page

    # Get selected models from query parameters
    selected_models = request.args.getlist("models")

    # Check if the subdeaddit exists
    subdeaddit = Subdeaddit.query.filter_by(name=subdeaddit_name).first_or_404()

    # Get all posts for this subdeaddit and randomize the order
    query = Post.query.filter_by(subdeaddit_name=subdeaddit_name).order_by(func.random())
    
    # Apply model filter if models are selected
    if selected_models:
        query = query.filter(Post.model.in_(selected_models))
    
    all_posts = query.all()

    # Get all unique models used in this subdeaddit (either selected or all) and randomize their order
    if selected_models:
        all_models = selected_models
    else:
        all_models = db.session.query(Post.model).filter(Post.subdeaddit_name == subdeaddit_name).distinct().all()
        all_models = [model[0] for model in all_models]
    
    # Randomize the order of models
    random.shuffle(all_models)
    model_cycle = cycle(all_models)

    # Create a dictionary to store posts by model
    posts_by_model = {model: [] for model in all_models}

    # Populate the posts_by_model dictionary
    for post in all_posts:
        if post.model in posts_by_model:
            post.title = process_title(post.title)
            posts_by_model[post.model].append(post)

    # Create the final ordered list of posts
    ordered_posts = []
    while len(ordered_posts) < len(all_posts):
        current_model = next(model_cycle)
        if posts_by_model[current_model]:
            ordered_posts.append(posts_by_model[current_model].pop(0))

    # Apply pagination
    paginated_posts = ordered_posts[offset:offset+posts_per_page]
    total_posts = len(all_posts)

    # Gather comment counts for each post
    comment_counts = {post.id: Comment.query.filter_by(post_id=post.id).count() for post in paginated_posts}
    has_more = total_posts > page * posts_per_page

    return render_template(
        "subdeaddit.html",
        posts=paginated_posts,
        comment_counts=comment_counts,
        subdeaddit_name=subdeaddit_name,
        page=page,
        has_more=has_more,
        selected_models=selected_models
    )


@app.route("/d/<subdeaddit_name>/<int:post_id>")
def post(subdeaddit_name, post_id):
    post = Post.query.get_or_404(post_id)

    # Get selected models from query parameters
    selected_models = request.args.getlist("models")

    # Query all comments for this post, ordered by upvote count
    query = Comment.query.filter_by(post_id=post_id).order_by(Comment.upvote_count.desc())

    # Apply model filter if models are selected
    if selected_models:
        query = query.filter(Comment.model.in_(selected_models))

    comments = query.all()

    def build_comment_tree(comments):
        comment_dict = {
            comment.id: {
                "id": comment.id,
                "content": comment.content,
                "upvote_count": comment.upvote_count,
                "user": comment.user,
                "model": comment.model,
                "created_at": comment.created_at,
                "children": [],
            }
            for comment in comments
        }

        root_comments = []
        for comment in comments:
            if comment.parent_id == "":
                root_comments.append(comment_dict[comment.id])
            else:
                parent = comment_dict.get(comment.parent_id)
                if parent:
                    parent["children"].append(comment_dict[comment.id])

        # Sort children by upvote count
        for comment in comment_dict.values():
            comment["children"].sort(key=lambda x: x["upvote_count"], reverse=True)

        # Sort root comments by upvote count
        root_comments.sort(key=lambda x: x["upvote_count"], reverse=True)

        return root_comments

    def add_comment_levels(comments, level=0):
        for comment in comments:
            comment["level"] = level
            add_comment_levels(comment["children"], level + 1)
        return comments

    # Build the comment tree
    root_comments = build_comment_tree(comments)
    comment_tree = add_comment_levels(root_comments)

    return render_template(
        "post.html",
        post=post,
        comment_tree=comment_tree,
        subdeaddit_name=subdeaddit_name,
        selected_models=selected_models,
    )


from sqlalchemy import func, and_
from sqlalchemy.orm import aliased


@app.route("/list_subdeaddit")
def list_subdeaddit():
    page = request.args.get("page", default=1, type=int)
    subdeaddits_per_page = 100

    # Get selected models from query parameters
    selected_models = request.args.getlist("models")

    # Query for total post count (all models)
    total_post_count = func.count(Post.id).label("total_post_count")

    # Subquery for filtered post count
    filtered_post_subquery = db.session.query(Post.subdeaddit_name, func.count(Post.id).label("filtered_post_count"))
    if selected_models:
        filtered_post_subquery = filtered_post_subquery.filter(Post.model.in_(selected_models))
    filtered_post_subquery = filtered_post_subquery.group_by(Post.subdeaddit_name).subquery()

    # Alias for the subquery
    filtered_post_alias = aliased(filtered_post_subquery)

    # Main query
    query = (
        db.session.query(
            Subdeaddit.name,
            Subdeaddit.description,
            total_post_count,
            func.coalesce(filtered_post_alias.c.filtered_post_count, 0).label("filtered_post_count"),
        )
        .outerjoin(Post, Subdeaddit.name == Post.subdeaddit_name)
        .outerjoin(filtered_post_alias, Subdeaddit.name == filtered_post_alias.c.subdeaddit_name)
        .group_by(Subdeaddit.name, Subdeaddit.description)
        .order_by(Subdeaddit.name)
    )

    # Paginate the results
    paginated_subdeaddits = query.paginate(page=page, per_page=subdeaddits_per_page)

    return render_template("list_subdeaddit.html", subdeaddits=paginated_subdeaddits, selected_models=selected_models)


@app.route("/user/<username>")
def user_profile(username):
    user = User.query.get_or_404(username)
    
    # Get the 20 most recent posts for the user
    posts = Post.query.filter_by(user=username).order_by(Post.created_at.desc()).limit(20).all()

    # Get the 20 most recent comments for the user
    comments = (
        Comment.query.options(joinedload(Comment.post))
        .filter_by(user=username)
        .order_by(Comment.created_at.desc())
        .limit(20)
        .all()
    )

    # Get total counts for posts and comments
    total_posts = Post.query.filter_by(user=username).count()
    total_comments = Comment.query.filter_by(user=username).count()

    # Gather comment counts for each post
    comment_counts = {post.id: Comment.query.filter_by(post_id=post.id).count() for post in posts}

    return render_template(
        "user_profile.html",
        user=user,
        posts=posts,
        comments=comments,
        total_posts=total_posts,
        total_comments=total_comments,
        comment_counts=comment_counts
    )

@app.route("/users")
def list_users():
    page = request.args.get("page", default=1, type=int)
    users_per_page = 100

    # Count the total number of users
    total_users = db.session.query(func.count(User.username)).scalar()

    # Query users with pagination
    users = User.query.order_by(User.username).paginate(page=page, per_page=users_per_page)

    return render_template("users_list.html", users=users, total_users=total_users)
