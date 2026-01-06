"""Google OAuth authentication for the trading dashboard."""

import os
from functools import wraps
from flask import Blueprint, redirect, url_for, session, jsonify, request
from flask_dance.contrib.google import make_google_blueprint, google
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from loguru import logger


# Get OAuth credentials from environment
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
AUTHORIZED_EMAILS = os.getenv("AUTHORIZED_EMAILS", "").split(",")  # Comma-separated list


class User(UserMixin):
    """Simple user model for Flask-Login."""
    def __init__(self, email: str, name: str = "", picture: str = ""):
        self.id = email
        self.email = email
        self.name = name
        self.picture = picture


# In-memory user storage (for simplicity)
users = {}

# Login manager setup
login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID (email)."""
    return users.get(user_id)


def create_google_blueprint(app):
    """Create and register Google OAuth blueprint.
    
    Args:
        app: Flask application instance
        
    Returns:
        Google OAuth blueprint
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        logger.warning("Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
        return None
    
    google_bp = make_google_blueprint(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scope=["openid", "email", "profile"],
        redirect_to="auth.callback"
    )
    
    return google_bp


def is_email_authorized(email: str) -> bool:
    """Check if email is in the authorized list.
    
    Args:
        email: User's email address
        
    Returns:
        True if authorized
    """
    # If no authorized emails configured, allow all
    if not AUTHORIZED_EMAILS or AUTHORIZED_EMAILS == [""]:
        return True
    
    return email.lower() in [e.lower().strip() for e in AUTHORIZED_EMAILS]


# Auth blueprint for routes
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login")
def login():
    """Redirect to Google OAuth login."""
    if not google.authorized:
        return redirect(url_for("google.login"))
    return redirect("/")


@auth_bp.route("/callback")
def callback():
    """Handle OAuth callback from Google."""
    if not google.authorized:
        return jsonify({"error": "Not authorized"}), 401
    
    try:
        # Get user info from Google
        resp = google.get("/oauth2/v2/userinfo")
        if not resp.ok:
            return jsonify({"error": "Failed to get user info"}), 400
        
        user_info = resp.json()
        email = user_info.get("email", "")
        name = user_info.get("name", "")
        picture = user_info.get("picture", "")
        
        # Check if email is authorized
        if not is_email_authorized(email):
            logger.warning(f"Unauthorized login attempt: {email}")
            return jsonify({
                "error": "Unauthorized",
                "message": f"Email {email} is not authorized to access this application."
            }), 403
        
        # Create/update user
        user = User(email=email, name=name, picture=picture)
        users[email] = user
        login_user(user)
        
        logger.info(f"User logged in: {email}")
        
        # Redirect to frontend
        return redirect("/")
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return jsonify({"error": str(e)}), 500


@auth_bp.route("/logout")
def logout():
    """Log out the current user."""
    if current_user.is_authenticated:
        logger.info(f"User logged out: {current_user.email}")
    logout_user()
    session.clear()
    return redirect("/")


@auth_bp.route("/me")
def get_current_user():
    """Get current user info."""
    if not current_user.is_authenticated:
        return jsonify({"authenticated": False}), 401
    
    return jsonify({
        "authenticated": True,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture
    })


def require_auth(f):
    """Decorator to require authentication for API endpoints.
    
    For API endpoints, returns JSON error instead of redirecting.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            # Check if it's an API request
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


def init_auth(app):
    """Initialize authentication for the Flask app.
    
    Args:
        app: Flask application instance
    """
    # Set secret key for sessions
    app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())
    
    # Initialize login manager
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access the trading dashboard."
    
    # Register auth blueprint
    app.register_blueprint(auth_bp)
    
    # Create and register Google blueprint if configured
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        google_bp = create_google_blueprint(app)
        if google_bp:
            app.register_blueprint(google_bp, url_prefix="/login")
        logger.info("Google OAuth configured successfully")
    else:
        logger.warning("Google OAuth not configured - authentication disabled")
