"""User authentication for the trading dashboard.

Supports both email/password and Google OAuth authentication.
"""

import os
import re
from datetime import datetime
from functools import wraps
from flask import Blueprint, redirect, url_for, session, jsonify, request
from flask_dance.contrib.google import make_google_blueprint, google
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from loguru import logger

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    logger.warning("bcrypt not available, password hashing disabled")


# Get OAuth credentials from environment
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")


class FlaskUser(UserMixin):
    """User wrapper for Flask-Login."""
    
    def __init__(self, user_data):
        self.id = user_data.get('email')
        self.email = user_data.get('email')
        self.name = user_data.get('name', '')
        self.picture = user_data.get('picture', '')
        self.auth_provider = user_data.get('auth_provider', 'local')
        self.db_id = user_data.get('id')


# In-memory user cache (backed by database)
user_cache = {}

# Login manager setup
login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID (email)."""
    if user_id in user_cache:
        return user_cache[user_id]
    
    # Try to load from database
    try:
        from utils.database_sql import get_db_session
        from models.user import User as DBUser
        
        db = get_db_session()
        db_user = db.query(DBUser).filter(DBUser.email == user_id).first()
        if db_user:
            flask_user = FlaskUser(db_user.to_dict())
            user_cache[user_id] = flask_user
            db.close()
            return flask_user
        db.close()
    except Exception as e:
        logger.error(f"Error loading user from database: {e}")
    
    return None


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    if not BCRYPT_AVAILABLE:
        raise RuntimeError("bcrypt is required for password hashing")
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    if not BCRYPT_AVAILABLE:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception:
        return False


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    return True, ""


def create_google_blueprint(app):
    """Create and register Google OAuth blueprint."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        logger.warning("Google OAuth not configured")
        return None
    
    google_bp = make_google_blueprint(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scope=["openid", "email", "profile"],
        redirect_to="auth.google_callback"
    )
    
    return google_bp


# Auth blueprint for routes
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new user with email and password."""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        name = data.get('name', '').strip()
        
        # Validate email
        if not email or not validate_email(email):
            return jsonify({"error": "Invalid email address"}), 400
        
        # Validate password
        valid, message = validate_password(password)
        if not valid:
            return jsonify({"error": message}), 400
        
        # Check if user already exists
        from utils.database_sql import get_db_session
        from models.user import User as DBUser
        
        db = get_db_session()
        existing_user = db.query(DBUser).filter(DBUser.email == email).first()
        
        if existing_user:
            db.close()
            return jsonify({"error": "Email already registered"}), 409
        
        # Create new user
        password_hash = hash_password(password)
        new_user = DBUser(
            email=email,
            password_hash=password_hash,
            name=name or email.split('@')[0],
            auth_provider='local',
            is_active=True,
            email_verified=False
        )
        
        db.add(new_user)
        db.commit()
        
        # Log in the new user
        flask_user = FlaskUser(new_user.to_dict())
        user_cache[email] = flask_user
        login_user(flask_user)
        
        logger.info(f"New user registered: {email}")
        db.close()
        
        return jsonify({
            "success": True,
            "message": "Registration successful",
            "user": {
                "email": email,
                "name": new_user.name,
                "authenticated": True
            }
        }), 201
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({"error": "Registration failed. Please try again."}), 500


@auth_bp.route("/login", methods=["POST"])
def login():
    """Login with email and password."""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        
        # Find user
        from utils.database_sql import get_db_session
        from models.user import User as DBUser
        
        db = get_db_session()
        user = db.query(DBUser).filter(DBUser.email == email).first()
        
        if not user:
            db.close()
            return jsonify({"error": "Invalid email or password"}), 401
        
        # Check if user has a password (not Google-only)
        if not user.password_hash:
            db.close()
            return jsonify({
                "error": "This account uses Google Sign-In. Please sign in with Google."
            }), 401
        
        # Verify password
        if not verify_password(password, user.password_hash):
            db.close()
            return jsonify({"error": "Invalid email or password"}), 401
        
        # Check if account is active
        if not user.is_active:
            db.close()
            return jsonify({"error": "Account is disabled"}), 403
        
        # Update last login
        user.update_last_login()
        db.commit()
        
        # Log in user
        flask_user = FlaskUser(user.to_dict())
        user_cache[email] = flask_user
        login_user(flask_user)
        
        logger.info(f"User logged in: {email}")
        db.close()
        
        return jsonify({
            "success": True,
            "authenticated": True,
            "email": user.email,
            "name": user.name,
            "picture": user.picture_url
        })
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({"error": "Login failed. Please try again."}), 500


@auth_bp.route("/google")
def google_login():
    """Redirect to Google OAuth login."""
    if not google.authorized:
        return redirect(url_for("google.login"))
    return redirect("/")


@auth_bp.route("/google/callback")
def google_callback():
    """Handle OAuth callback from Google."""
    if not google.authorized:
        return jsonify({"error": "Not authorized"}), 401
    
    try:
        # Get user info from Google
        resp = google.get("/oauth2/v2/userinfo")
        if not resp.ok:
            return jsonify({"error": "Failed to get user info"}), 400
        
        user_info = resp.json()
        email = user_info.get("email", "").lower()
        name = user_info.get("name", "")
        picture = user_info.get("picture", "")
        
        # Get or create user in database
        from utils.database_sql import get_db_session
        from models.user import User as DBUser
        
        db = get_db_session()
        user = db.query(DBUser).filter(DBUser.email == email).first()
        
        if user:
            # Update existing user
            user.name = name or user.name
            user.picture_url = picture
            if user.auth_provider == 'local':
                user.auth_provider = 'both'  # Now supports both methods
            user.update_last_login()
        else:
            # Create new Google user
            user = DBUser(
                email=email,
                name=name,
                picture_url=picture,
                auth_provider='google',
                is_active=True,
                email_verified=True  # Google emails are verified
            )
            db.add(user)
        
        db.commit()
        
        # Log in user
        flask_user = FlaskUser(user.to_dict())
        user_cache[email] = flask_user
        login_user(flask_user)
        
        logger.info(f"Google user logged in: {email}")
        db.close()
        
        # Redirect to frontend
        return redirect("/")
        
    except Exception as e:
        logger.error(f"Google OAuth callback error: {e}")
        return jsonify({"error": str(e)}), 500


@auth_bp.route("/logout")
def logout():
    """Log out the current user."""
    if current_user.is_authenticated:
        email = current_user.email
        user_cache.pop(email, None)
        logger.info(f"User logged out: {email}")
    
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
        "picture": current_user.picture,
        "auth_provider": current_user.auth_provider
    })


def require_auth(f):
    """Decorator to require authentication for API endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


def init_auth(app):
    """Initialize authentication for the Flask app."""
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
        logger.warning("Google OAuth not configured - Google Sign-In disabled")
    
    # Initialize database
    try:
        from utils.database_sql import init_db
        init_db()
    except Exception as e:
        logger.warning(f"Database initialization deferred: {e}")
