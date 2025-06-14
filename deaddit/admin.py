"""
Admin interface for Deaddit content management.
Provides web-based UI for job management and content generation.
"""

from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from loguru import logger
from sqlalchemy import desc

from deaddit import db
from deaddit.config import Config
from deaddit.jobs import cancel_job, create_job, get_job_status, get_queue_stats
from deaddit.models import (
    Comment,
    GenerationTemplate,
    Job,
    JobStatus,
    JobType,
    Post,
    Subdeaddit,
    User,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    """Decorator to check admin authentication when API_TOKEN is set."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get API_TOKEN from environment
        import os

        api_token = os.environ.get("API_TOKEN")

        # If no API_TOKEN is set, allow access
        if not api_token:
            return f(*args, **kwargs)

        # Check if user is authenticated
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin.login"))

        return f(*args, **kwargs)

    return decorated_function


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """Admin login page."""
    import os

    api_token = os.environ.get("API_TOKEN")

    # If no API_TOKEN is set, redirect to dashboard
    if not api_token:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        provided_token = request.form.get("api_token")

        if provided_token == api_token:
            session["admin_authenticated"] = True
            session.permanent = True
            flash("Successfully authenticated!", "success")
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Invalid API token.", "error")

    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():
    """Admin logout."""
    session.pop("admin_authenticated", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("admin.login"))


@admin_bp.route("/")
@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    """Admin dashboard with overview statistics."""

    # Get basic content statistics
    stats = {
        "total_posts": Post.query.count(),
        "total_comments": Comment.query.count(),
        "total_users": User.query.count(),
        "total_subdeaddits": Subdeaddit.query.count(),
    }

    # Get recent activity (last 24 hours)
    since_yesterday = datetime.utcnow() - timedelta(days=1)

    # Count recent completed user creation jobs as proxy for new users
    recent_user_jobs = Job.query.filter(
        Job.created_at >= since_yesterday,
        Job.type == JobType.CREATE_USER,
        Job.status == JobStatus.COMPLETED,
    ).count()

    recent_stats = {
        "posts_24h": Post.query.filter(Post.created_at >= since_yesterday).count(),
        "comments_24h": Comment.query.filter(
            Comment.created_at >= since_yesterday
        ).count(),
        "users_24h": recent_user_jobs,
    }

    # Get job statistics
    job_stats = {
        "total_jobs": Job.query.count(),
        "pending_jobs": Job.query.filter_by(status=JobStatus.PENDING).count(),
        "running_jobs": Job.query.filter_by(status=JobStatus.RUNNING).count(),
        "completed_jobs": Job.query.filter_by(status=JobStatus.COMPLETED).count(),
        "failed_jobs": Job.query.filter_by(status=JobStatus.FAILED).count(),
    }

    # Get recent jobs
    recent_jobs = Job.query.order_by(desc(Job.created_at)).limit(10).all()

    # Get queue statistics (handle Redis not available)
    try:
        queue_stats = get_queue_stats()
    except Exception as e:
        logger.warning(f"Could not get queue stats: {e}")
        queue_stats = {
            "high_priority": {"pending": 0, "failed": 0},
            "normal": {"pending": 0, "failed": 0},
            "low_priority": {"pending": 0, "failed": 0},
        }

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_stats=recent_stats,
        job_stats=job_stats,
        recent_jobs=recent_jobs,
        queue_stats=queue_stats,
    )


@admin_bp.route("/generate")
@admin_required
def generate():
    """Content generation management page."""
    templates = GenerationTemplate.query.all()
    subdeaddits = Subdeaddit.query.all()

    # Check if default data has been loaded
    default_data_loaded = Config.get("DEFAULT_DATA_LOADED", "false") == "true"

    return render_template(
        "admin/generate.html",
        templates=templates,
        subdeaddits=subdeaddits,
        default_data_loaded=default_data_loaded,
    )


@admin_bp.route("/generate/subdeaddit", methods=["POST"])
@admin_required
def generate_subdeaddit():
    """Create a job to generate subdeaddits."""

    count = int(request.form.get("count", 1))
    model = request.form.get("model")
    wait = int(request.form.get("wait", 0))
    priority = int(request.form.get("priority", 5))

    parameters = {"count": count, "wait": wait}
    if model:
        parameters["model"] = model

    job = create_job(
        job_type=JobType.CREATE_SUBDEADDIT,
        parameters=parameters,
        priority=priority,
        total_items=count,
    )

    flash(f"Subdeaddit generation job created (ID: {job.id})", "success")
    return redirect(url_for("admin.jobs"))


@admin_bp.route("/generate/user", methods=["POST"])
@admin_required
def generate_user():
    """Create a job to generate users."""

    count = int(request.form.get("count", 1))
    model = request.form.get("model")
    wait = int(request.form.get("wait", 0))
    priority = int(request.form.get("priority", 5))

    parameters = {"count": count, "wait": wait}
    if model:
        parameters["model"] = model

    job = create_job(
        job_type=JobType.CREATE_USER,
        parameters=parameters,
        priority=priority,
        total_items=count,
    )

    flash(f"User generation job created (ID: {job.id})", "success")
    return redirect(url_for("admin.jobs"))


@admin_bp.route("/generate/post", methods=["POST"])
@admin_required
def generate_post():
    """Create a job to generate posts."""

    count = int(request.form.get("count", 1))
    subdeaddit = request.form.get("subdeaddit")
    replies = request.form.get("replies", "5-10")
    model = request.form.get("model")
    wait = int(request.form.get("wait", 0))
    priority = int(request.form.get("priority", 5))

    parameters = {"count": count, "wait": wait, "replies": replies}
    if subdeaddit:
        parameters["subdeaddit"] = subdeaddit
    if model:
        parameters["model"] = model

    job = create_job(
        job_type=JobType.CREATE_POST,
        parameters=parameters,
        priority=priority,
        total_items=count,
    )

    flash(f"Post generation job created (ID: {job.id})", "success")
    return redirect(url_for("admin.jobs"))


@admin_bp.route("/generate/comment", methods=["POST"])
@admin_required
def generate_comment():
    """Create a job to generate comments."""

    count = int(request.form.get("count", 1))
    post_id = request.form.get("post_id")
    subdeaddit = request.form.get("subdeaddit")
    model = request.form.get("model")
    wait = int(request.form.get("wait", 0))
    priority = int(request.form.get("priority", 5))

    parameters = {"count": count, "wait": wait}
    if post_id:
        parameters["post_id"] = int(post_id)
    if subdeaddit:
        parameters["subdeaddit"] = subdeaddit
    if model:
        parameters["model"] = model

    job = create_job(
        job_type=JobType.CREATE_COMMENT,
        parameters=parameters,
        priority=priority,
        total_items=count,
    )

    flash(f"Comment generation job created (ID: {job.id})", "success")
    return redirect(url_for("admin.jobs"))


@admin_bp.route("/jobs")
@admin_required
def jobs():
    """Job management page."""

    # Get filter parameters
    status_filter = request.args.get("status")
    type_filter = request.args.get("type")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))

    # Build query
    query = Job.query

    if status_filter:
        query = query.filter(Job.status == JobStatus(status_filter))

    if type_filter:
        query = query.filter(Job.type == JobType(type_filter))

    # Order by creation date (newest first)
    query = query.order_by(desc(Job.created_at))

    # Paginate
    jobs_pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get available filter options
    job_types = [jt.value for jt in JobType]
    job_statuses = [js.value for js in JobStatus]

    return render_template(
        "admin/jobs.html",
        jobs=jobs_pagination.items,
        pagination=jobs_pagination,
        job_types=job_types,
        job_statuses=job_statuses,
        current_status=status_filter,
        current_type=type_filter,
    )


@admin_bp.route("/jobs/<int:job_id>")
@admin_required
def job_detail(job_id):
    """Job detail page."""
    job = Job.query.get_or_404(job_id)

    # Find related jobs (same type, created around the same time)
    time_window = timedelta(hours=24)
    related_jobs = (
        Job.query.filter(
            Job.id != job.id,
            Job.type == job.type,
            Job.created_at >= job.created_at - time_window,
            Job.created_at <= job.created_at + time_window,
        )
        .order_by(desc(Job.created_at))
        .limit(10)
        .all()
    )

    return render_template(
        "admin/job_detail.html",
        job=job,
        related_jobs=related_jobs,
        User=User,
        Post=Post,
        Comment=Comment,
        Subdeaddit=Subdeaddit,
    )


@admin_bp.route("/jobs/<int:job_id>/cancel", methods=["POST"])
@admin_required
def cancel_job_route(job_id):
    """Cancel a job."""
    if cancel_job(job_id):
        flash(f"Job {job_id} cancelled successfully", "success")
    else:
        flash(f"Could not cancel job {job_id}", "error")

    return redirect(url_for("admin.job_detail", job_id=job_id))


@admin_bp.route("/jobs/<int:job_id>/retry", methods=["POST"])
@admin_required
def retry_job_route(job_id):
    """Retry a failed job."""
    original_job = Job.query.get_or_404(job_id)

    if original_job.status not in [JobStatus.FAILED, JobStatus.CANCELLED]:
        flash("Only failed or cancelled jobs can be retried", "error")
        return redirect(url_for("admin.job_detail", job_id=job_id))

    # Create a new job with the same parameters
    new_job = create_job(
        job_type=original_job.type,
        parameters=original_job.parameters,
        priority=original_job.priority,
        total_items=original_job.total_items,
    )

    flash(f"Job retried as new job #{new_job.id}", "success")
    return redirect(url_for("admin.job_detail", job_id=new_job.id))


@admin_bp.route("/api/jobs/<int:job_id>/status")
@admin_required
def job_status_api(job_id):
    """API endpoint to get job status (for real-time updates)."""
    status = get_job_status(job_id)
    if status:
        return jsonify(status)
    else:
        return jsonify({"error": "Job not found"}), 404


@admin_bp.route("/api/jobs/stats")
@admin_required
def jobs_stats_api():
    """API endpoint to get job statistics."""
    try:
        stats = get_queue_stats()
    except Exception as e:
        logger.warning(f"Could not get queue stats: {e}")
        stats = {
            "scheduler_running": False,
            "total_jobs": 0,
            "pending_jobs": 0,
            "running_jobs": 0,
        }

    # Add database job counts
    stats["database"] = {
        "pending": Job.query.filter_by(status=JobStatus.PENDING).count(),
        "running": Job.query.filter_by(status=JobStatus.RUNNING).count(),
        "completed": Job.query.filter_by(status=JobStatus.COMPLETED).count(),
        "failed": Job.query.filter_by(status=JobStatus.FAILED).count(),
    }

    return jsonify(stats)


@admin_bp.route("/content")
@admin_required
def content():
    """Content management page."""

    # Get content statistics
    content_stats = {
        "posts": Post.query.count(),
        "comments": Comment.query.count(),
        "users": User.query.count(),
        "subdeaddits": Subdeaddit.query.count(),
    }

    # Get recent content
    recent_posts = Post.query.order_by(desc(Post.created_at)).limit(10).all()
    recent_comments = Comment.query.order_by(desc(Comment.created_at)).limit(10).all()

    return render_template(
        "admin/content.html",
        content_stats=content_stats,
        recent_posts=recent_posts,
        recent_comments=recent_comments,
    )


@admin_bp.route("/analytics")
@admin_required
def analytics():
    """Analytics and insights page."""

    # Get generation metrics over time
    # This is a placeholder - in a real implementation, you'd want more sophisticated analytics

    # Model usage statistics
    model_stats = {}
    for model in db.session.query(Post.model).distinct():
        if model[0]:
            count = Post.query.filter_by(model=model[0]).count()
            model_stats[model[0]] = count

    # Daily generation counts (last 30 days)
    daily_stats = []
    for i in range(30):
        date = datetime.utcnow() - timedelta(days=i)
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start + timedelta(days=1)

        posts_count = Post.query.filter(
            Post.created_at >= date_start, Post.created_at < date_end
        ).count()

        comments_count = Comment.query.filter(
            Comment.created_at >= date_start, Comment.created_at < date_end
        ).count()

        daily_stats.append(
            {
                "date": date_start.strftime("%Y-%m-%d"),
                "posts": posts_count,
                "comments": comments_count,
            }
        )

    daily_stats.reverse()  # Show oldest to newest

    return render_template(
        "admin/analytics.html", model_stats=model_stats, daily_stats=daily_stats
    )


@admin_bp.route("/settings")
@admin_required
def settings():
    """Settings and configuration page."""

    # Get current configuration from database
    all_settings = Config.get_all_settings()

    config = {
        "openai_api_url": all_settings["OPENAI_API_URL"]["value"],
        "openai_model": all_settings["OPENAI_MODEL"]["value"],
        "api_base_url": all_settings["API_BASE_URL"]["value"],
        "models": all_settings["MODELS"]["value"],
        "api_token_set": all_settings["API_TOKEN"]["value"] == "***set***",
        "openai_key_set": all_settings["OPENAI_KEY"]["value"]
        != "your_openrouter_api_key"
        and bool(all_settings["OPENAI_KEY"]["value"]),
        "all_settings": all_settings,
    }

    return render_template("admin/settings.html", config=config)


@admin_bp.route("/api/system-info")
@admin_required
def system_info_api():
    """API endpoint to get system information."""
    import sys

    import apscheduler
    import flask
    import sqlalchemy

    return jsonify(
        {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "flask_version": flask.__version__,
            "sqlalchemy_version": sqlalchemy.__version__,
            "apscheduler_version": apscheduler.__version__,
        }
    )


@admin_bp.route("/api/save-config", methods=["POST"])
@admin_required
def save_config_api():
    """API endpoint to save configuration to database."""
    try:
        data = request.get_json()

        # Save configuration values to database
        endpoint_url = None
        if data.get("openai_api_url"):
            endpoint_url = data["openai_api_url"].rstrip("/")
            Config.set("OPENAI_API_URL", endpoint_url)

        # Handle per-endpoint API key storage
        if data.get("openai_key"):
            if endpoint_url:
                Config.set_api_key_for_endpoint(endpoint_url, data["openai_key"])
            else:
                # If no endpoint URL, use current endpoint
                current_endpoint = Config.get("OPENAI_API_URL")
                if current_endpoint:
                    Config.set_api_key_for_endpoint(
                        current_endpoint, data["openai_key"]
                    )
                else:
                    Config.set("OPENAI_KEY", data["openai_key"])

        if data.get("openai_model"):
            Config.set("OPENAI_MODEL", data["openai_model"])
        if data.get("api_base_url"):
            Config.set("API_BASE_URL", data["api_base_url"].rstrip("/"))
        if data.get("models"):
            Config.set("MODELS", data["models"])

        # Return updated config
        current_endpoint = Config.get("OPENAI_API_URL")
        config = {
            "openai_api_url": current_endpoint or "Not set",
            "openai_model": Config.get("OPENAI_MODEL", "Not set"),
            "api_base_url": Config.get("API_BASE_URL", "Not set"),
            "openai_key_set": bool(Config.get_api_key_for_endpoint(current_endpoint))
            and Config.get_api_key_for_endpoint(current_endpoint)
            != "your_openrouter_api_key",
        }

        return jsonify(
            {
                "success": True,
                "message": "Configuration saved to database successfully",
                "config": config,
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Failed to save configuration: {str(e)}"}
        )


@admin_bp.route("/api/test-connection", methods=["POST"])
@admin_required
def test_connection_api():
    """API endpoint to test AI service connection with custom parameters."""

    import requests

    try:
        data = request.get_json()
        api_url = data.get("api_url")
        api_key = data.get("api_key")

        if not api_url:
            return jsonify(
                {
                    "success": False,
                    "message": "API URL is required",
                    "status_code": None,
                }
            )

        # If no API key provided or masked key, try to use saved key for this endpoint
        if not api_key or api_key == "••••••••••••••••":
            api_key = Config.get_api_key_for_endpoint(api_url)
            if not api_key:
                return jsonify(
                    {
                        "success": False,
                        "message": "API key is required. Please enter a key or save one in settings first.",
                        "status_code": None,
                    }
                )

        # Test connection to AI service
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(
            f"{api_url.rstrip('/')}/models", headers=headers, timeout=10
        )

        if response.status_code == 200:
            return jsonify(
                {
                    "success": True,
                    "message": "Connection successful! AI service is reachable.",
                    "status_code": response.status_code,
                }
            )
        else:
            return jsonify(
                {
                    "success": False,
                    "message": "AI service returned an error response",
                    "status_code": response.status_code,
                }
            )

    except requests.exceptions.ConnectionError:
        return jsonify(
            {
                "success": False,
                "message": "Cannot connect to AI service. Check API URL.",
                "status_code": None,
            }
        )
    except requests.exceptions.Timeout:
        return jsonify(
            {
                "success": False,
                "message": "Connection timeout. AI service may be slow or unreachable.",
                "status_code": None,
            }
        )
    except Exception as e:
        return jsonify(
            {
                "success": False,
                "message": f"Connection test failed: {str(e)}",
                "status_code": None,
            }
        )


@admin_bp.route("/api/load-models", methods=["POST"])
@admin_required
def load_models_api():
    """API endpoint to load available models from AI service."""
    import requests

    try:
        data = request.get_json()
        api_url = data.get("api_url")
        api_key = data.get("api_key")

        if not api_url:
            return jsonify({"success": False, "message": "API URL is required"})

        # If no API key provided or masked key, try to use saved key for this endpoint
        if not api_key or api_key == "••••••••••••••••":
            api_key = Config.get_api_key_for_endpoint(api_url)
            if not api_key:
                return jsonify(
                    {
                        "success": False,
                        "message": "API key is required. Please enter a key or save one in settings first.",
                    }
                )

        # Get models from AI service
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(
            f"{api_url.rstrip('/')}/models", headers=headers, timeout=10
        )

        if response.status_code == 200:
            models_data = response.json()

            # Extract model names from response
            models = []
            if "data" in models_data:
                models = [model.get("id", "Unknown") for model in models_data["data"]]
            elif "models" in models_data:
                models = [
                    model.get("id", model.get("name", "Unknown"))
                    for model in models_data["models"]
                ]

            return jsonify(
                {
                    "success": True,
                    "models": models,
                    "message": f"Found {len(models)} models",
                }
            )
        else:
            return jsonify(
                {
                    "success": False,
                    "message": f"Failed to load models: HTTP {response.status_code}",
                }
            )

    except requests.exceptions.ConnectionError:
        return jsonify({"success": False, "message": "Cannot connect to AI service"})
    except requests.exceptions.Timeout:
        return jsonify({"success": False, "message": "Connection timeout"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error loading models: {str(e)}"})


@admin_bp.route("/api/get-endpoint-key", methods=["POST"])
@admin_required
def get_endpoint_key_api():
    """API endpoint to get the API key for a specific endpoint."""
    try:
        data = request.get_json()
        endpoint_url = data.get("endpoint_url")

        if not endpoint_url:
            return jsonify({"success": False, "message": "Endpoint URL is required"})

        api_key = Config.get_api_key_for_endpoint(endpoint_url)

        return jsonify(
            {
                "success": True,
                "api_key": api_key,
                "masked_key": "••••••••••••••••" if api_key else None,
                "has_key": bool(api_key),
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error getting endpoint key: {str(e)}"}
        )


@admin_bp.route("/api/clear-jobs", methods=["POST"])
@admin_required
def clear_jobs_api():
    """API endpoint to clear all jobs history."""
    try:
        # Get count of jobs before deletion for reporting
        job_count = Job.query.count()

        # Delete all jobs
        db.session.query(Job).delete()
        db.session.commit()

        logger.info(f"Cleared {job_count} jobs from history")

        return jsonify(
            {
                "success": True,
                "message": f"Successfully cleared {job_count} jobs from history",
            }
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to clear jobs history: {e}")
        return jsonify(
            {"success": False, "message": f"Failed to clear jobs history: {str(e)}"}
        )


@admin_bp.route("/api/load-default-data", methods=["POST"])
@admin_required
def load_default_data_api():
    """API endpoint to load default subdeaddits and users from JSON files."""
    import json
    import os

    try:
        # Get paths to the data files
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        subdeaddits_file = os.path.join(data_dir, "subdeaddits_base.json")
        users_file = os.path.join(data_dir, "users.json")

        subdeaddits_loaded = 0
        users_loaded = 0

        # Load subdeaddits
        if os.path.exists(subdeaddits_file):
            with open(subdeaddits_file) as f:
                subdeaddits_data = json.load(f)

            for subdeaddit_data in subdeaddits_data.get("subdeaddits", []):
                # Check if subdeaddit already exists
                existing = Subdeaddit.query.filter_by(
                    name=subdeaddit_data["name"]
                ).first()
                if not existing:
                    subdeaddit = Subdeaddit(
                        name=subdeaddit_data["name"],
                        description=subdeaddit_data["description"],
                    )
                    # Use the helper method to properly set post_types as JSON
                    subdeaddit.set_post_types(subdeaddit_data.get("post_types", []))
                    db.session.add(subdeaddit)
                    subdeaddits_loaded += 1

            logger.info(f"Loaded {subdeaddits_loaded} new subdeaddits")

        # Load users (limit to first 50 to avoid overwhelming the system)
        if os.path.exists(users_file):
            with open(users_file) as f:
                users_data = json.load(f)

            for user_data in users_data.get("users", [])[
                :50
            ]:  # Limit to first 50 users
                # Check if user already exists
                existing = User.query.filter_by(username=user_data["username"]).first()
                if not existing:
                    user = User(
                        username=user_data["username"],
                        bio=user_data["bio"],
                        age=user_data["age"],
                        gender=user_data["gender"],
                        education=user_data["education"],
                        occupation=user_data["occupation"],
                        interests=json.dumps(
                            user_data["interests"]
                        ),  # Convert list to JSON string
                        personality_traits=json.dumps(
                            user_data["personality_traits"]
                        ),  # Convert list to JSON string
                        writing_style=user_data["writing_style"],
                        model=user_data.get("model", "default"),
                    )
                    db.session.add(user)
                    users_loaded += 1

            logger.info(f"Loaded {users_loaded} new users")

        # Commit all changes
        db.session.commit()

        # Mark default data as loaded
        Config.set("DEFAULT_DATA_LOADED", "true")

        return jsonify(
            {
                "success": True,
                "message": f"Successfully loaded {subdeaddits_loaded} subdeaddits and {users_loaded} users",
                "subdeaddits_loaded": subdeaddits_loaded,
                "users_loaded": users_loaded,
            }
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to load default data: {e}")
        return jsonify(
            {"success": False, "message": f"Failed to load default data: {str(e)}"}
        )


@admin_bp.route("/api/hide-default-data", methods=["POST"])
@admin_required
def hide_default_data_api():
    """API endpoint to hide the default data section permanently."""
    try:
        # Mark default data as loaded to hide the section
        Config.set("DEFAULT_DATA_LOADED", "true")

        return jsonify(
            {"success": True, "message": "Default data section will no longer be shown"}
        )

    except Exception as e:
        logger.error(f"Failed to hide default data section: {e}")
        return jsonify(
            {
                "success": False,
                "message": f"Failed to hide default data section: {str(e)}",
            }
        )
