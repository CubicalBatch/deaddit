from flask import render_template, jsonify, request
from deaddit import app, db
from .models import Post, Comment, Subdeaddit
from datetime import datetime, timedelta

from sqlalchemy import func


@app.route("/api/ingest", methods=["POST"])
def ingest():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    posts = data.get("posts", [])
    comments = data.get("comments", [])
    subdeaddits = data.get("subdeaddits", [])
    added = []

    # Validate and create posts
    for post_data in posts:
        title = post_data.get("title")
        content = post_data.get("content")
        upvote_count = post_data.get("upvote_count")
        user = post_data.get("user")
        subdeaddit_name = post_data.get("subdeaddit")

        if not all([title, content, upvote_count, user, subdeaddit_name]):
            return jsonify({"error": "Invalid post data"}), 400

        # Check if the subdeaddit exists
        subdeaddit = Subdeaddit.query.filter_by(name=subdeaddit_name).first()
        if not subdeaddit:
            return jsonify({"error": f"Subdeaddit '{subdeaddit_name}' does not exist"}), 400

        post = Post(title=title, content=content, upvote_count=upvote_count, user=user, subdeaddit=subdeaddit)
        added.append(title)
        db.session.add(post)

    # Validate and create comments
    for comment_data in comments:
        post_id = comment_data.get("post_id")
        parent_id = comment_data.get("parent_id")
        content = comment_data.get("content")
        upvote_count = comment_data.get("upvote_count")
        user = comment_data.get("user")

        if not all([post_id, content, upvote_count, user]):
            return jsonify({"error": "Invalid comment data"}), 400

        comment = Comment(post_id=post_id, parent_id=parent_id, content=content, upvote_count=upvote_count, user=user)
        added.append(content)
        db.session.add(comment)
        
    # Validate and create subdeaddits
    for subdeaddit_data in subdeaddits:
        name = subdeaddit_data.get("name")
        description = subdeaddit_data.get("description")

        if not all([name, description]):
            return jsonify({"error": "Invalid subdeaddit data"}), 400

        subdeaddit = Subdeaddit(name=name, description=description)
        added.append(name)
        db.session.add(subdeaddit)

    db.session.commit()

    return jsonify({"message": "Posts and comments created successfully", "added": added}), 201

@app.route("/api/subdeaddits", methods=["GET"])
def api_subdeaddits():
    """
    Retrieves a list of subdeaddits.

    Returns:
        A JSON response containing a list of subdeaddits with their names and descriptions.
    """
    subdeaddits = Subdeaddit.query.all()
    subdeaddit_list = []
    for subdeaddit in subdeaddits:
        subdeaddit_data = {
            "name": subdeaddit.name,
            "description": subdeaddit.description
        }
        subdeaddit_list.append(subdeaddit_data)
        
    response = {"subdeaddits": subdeaddit_list}
    return jsonify(response)

from datetime import datetime, timedelta
from flask import request, jsonify

@app.route("/api/posts", methods=["GET"])
def api_posts():
    subdeaddit_name = request.args.get("subdeaddit")
    days = request.args.get("days", type=int)  # Days since post creation
    max_comments = request.args.get("max_comments", type=int)  # Maximum number of comments
    limit = request.args.get("limit", default=50, type=int)  # Maximum number of posts to return

    query = Post.query

    # Filter by Subdeaddit if provided
    if subdeaddit_name:
        subdeaddit = Subdeaddit.query.filter_by(name=subdeaddit_name).first()
        if not subdeaddit:
            return jsonify({"error": f"Subdeaddit '{subdeaddit_name}' does not exist"}), 404
        query = query.filter(Post.subdeaddit == subdeaddit)

    # Filter by date if days parameter is provided
    if days is not None:
        date_limit = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Post.created_at >= date_limit)

    # Add sorting
    query = query.order_by(Post.created_at.desc())

    # Execute query and limit results
    posts = query.limit(limit).all()

    # Build response data, filtering by comment count if required
    post_data = []
    for post in posts:
        comment_count = Comment.query.filter_by(post_id=post.id).count()

        # Apply max_comments filter if provided
        if max_comments is not None and comment_count > max_comments:
            continue

        post_info = {
            "id": post.id,
            "subdeaddit": post.subdeaddit.name,
            "title": post.title,
            "content": post.content,
            "comment_count": comment_count,
            "created_at": post.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
        post_data.append(post_info)

    return jsonify({"posts": post_data})


@app.route("/api/post/<post_id>", methods=["GET"])
def api_post(post_id):
    if not post_id:
        return jsonify({"error": "Post ID is required"}), 400
    
    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": f"Post with ID {post_id} does not exist"}), 404
    
    comment_count = Comment.query.filter_by(post_id=post.id).count()
    
    comments = Comment.query.filter_by(post_id=post.id).all()
    comment_tree = build_comment_tree(comments)
    
    post_data = {
        "id": post.id,
        "subdeaddit": post.subdeaddit.name,
        "title": post.title,
        "content": post.content.replace("reddit", "deaddit"),
        "comment_count": comment_count,
        "comments": comment_tree
    }
    
    return jsonify(post_data)

def build_comment_tree(comments):
    comment_map = {comment.id: comment for comment in comments}
    comment_tree = []
    
    for comment in comments:
        if comment.parent_id == '':
            comment_tree.append(format_comment(comment, comment_map))
    
    return comment_tree

def format_comment(comment, comment_map):
    formatted_comment = {
        "id": comment.id,
        "user": comment.user,
        "content": comment.content.replace("reddit", "deaddit"),
        "replies": []
    }
    
    for reply_id, reply_comment in comment_map.items():
        if reply_comment.parent_id == comment.id:
            formatted_comment["replies"].append(format_comment(reply_comment, comment_map))
    
    return formatted_comment