from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, Response, send_file
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
from dotenv import load_dotenv
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import random
import re
import csv
import secrets
from html import escape as html_escape
from urllib.parse import urlparse
from io import StringIO, BytesIO
from werkzeug.utils import secure_filename
from functools import wraps
import qrcode
import threading
import time

load_dotenv()

app = Flask(__name__)

def _build_db_url():
    url = os.environ.get('DATABASE_URL', '')
    if url:
        # Normalize provider-supplied postgres:// URLs (Render, Heroku, etc.)
        if url.startswith('postgres://'):
            return url.replace('postgres://', 'postgresql+psycopg2://', 1)
        if url.startswith('postgresql://'):
            return url.replace('postgresql://', 'postgresql+psycopg2://', 1)
        return url
    host = os.environ.get('DB_HOST', 'localhost')
    port = os.environ.get('DB_PORT', '5432')
    user = os.environ.get('DB_USER', 'wedding_user')
    password = os.environ.get('DB_PASS', 'wedding_password')
    name = os.environ.get('DB_NAME', 'wedding_db')
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"

_secret_key = os.environ.get('SECRET_KEY', '')
if not _secret_key:
    _secret_key = secrets.token_hex(32)
    print("WARNING: SECRET_KEY env var not set - sessions will not persist across restarts. Set it in your .env file.")

app.config['SECRET_KEY'] = _secret_key
# Lax stops other sites from sending the session cookie on cross-site POSTs (basic CSRF defence).
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SQLALCHEMY_DATABASE_URI'] = _build_db_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

# Mail is configured at runtime from the database (WeddingConfig).
# These are empty bootstrap defaults only.
app.config['MAIL_SERVER'] = ''
app.config['MAIL_PORT'] = 25
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = ''
app.config['MAIL_PASSWORD'] = ''
app.config['MAIL_DEFAULT_SENDER'] = ('Wedding', '')

# Photo upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'photos')
FAVICON_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'favicon')
HERO_IMAGE_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'hero')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
FAVICON_EXTENSIONS = {'ico', 'png', 'jpg', 'jpeg', 'svg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024  #60MB max file size

# Ensure upload folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(FAVICON_FOLDER, exist_ok=True)
os.makedirs(HERO_IMAGE_FOLDER, exist_ok=True)

mail = Mail(app)

# Database Models

# Admin User Model
class AdminUser(UserMixin, db.Model):
    __tablename__ = 'admin_users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Wedding Configuration Model
class WeddingConfig(db.Model):
    __tablename__ = 'wedding_config'
    id = db.Column(db.Integer, primary_key=True)
    # Couple names
    bride = db.Column(db.String(200), nullable=False, default='Partner 1')
    groom = db.Column(db.String(200), nullable=False, default='Partner 2')
    # Wedding date/time
    wedding_date = db.Column(db.String(50), nullable=False, default='TBD')
    wedding_datetime = db.Column(db.DateTime, nullable=True)
    # Venue info
    venue = db.Column(db.String(500), nullable=False, default='TBD')
    city = db.Column(db.String(200), nullable=False, default='TBD')
    ceremony_location = db.Column(db.String(500), nullable=False, default='TBD')
    ceremony_time = db.Column(db.String(50), nullable=False, default='TBD')
    reception_location = db.Column(db.String(500), nullable=False, default='TBD')
    reception_time = db.Column(db.String(50), nullable=False, default='TBD')
    after_party_location = db.Column(db.String(500), nullable=True, default='TBD')
    after_party_time = db.Column(db.String(50), nullable=True, default='TBD')
    # Location coordinates (lat/lng from map picker)
    ceremony_lat = db.Column(db.Float, nullable=True)
    ceremony_lng = db.Column(db.Float, nullable=True)
    reception_lat = db.Column(db.Float, nullable=True)
    reception_lng = db.Column(db.Float, nullable=True)
    after_party_lat = db.Column(db.Float, nullable=True)
    after_party_lng = db.Column(db.Float, nullable=True)
    # Registry
    show_registry = db.Column(db.Boolean, default=False)
    registry_name = db.Column(db.String(500), nullable=True)
    registry_url = db.Column(db.String(1000), nullable=True)
    # Theme colors (hex values)
    primary_color = db.Column(db.String(7), nullable=False, default='#6D4846')
    primary_text_color = db.Column(db.String(7), nullable=False, default='#F5F1EE')
    accent_color = db.Column(db.String(7), nullable=False, default='#9C5B5B')
    nav_text_color = db.Column(db.String(7), nullable=False, default='#3F3631')
    button_color = db.Column(db.String(7), nullable=False, default='#6D4846')
    gold_accent = db.Column(db.String(7), nullable=False, default='#C9A87C')
    footer_background_color = db.Column(db.String(7), nullable=False, default='#211A17')
    footer_text_color = db.Column(db.String(7), nullable=False, default='#A89C95')
    show_footer_copyright = db.Column(db.Boolean, default=True)  # retained for DB compatibility, no longer exposed in UI
    # Event section toggles
    show_ceremony = db.Column(db.Boolean, default=True)
    show_reception = db.Column(db.Boolean, default=True)
    show_after_party = db.Column(db.Boolean, default=True)
    # Site info
    site_title = db.Column(db.String(500), nullable=False, default='Wedding Website')
    site_description = db.Column(db.Text, nullable=True)
    footer_domain = db.Column(db.String(200), nullable=True)
    site_layout = db.Column(db.String(50), nullable=False, default='classic')
    # Email settings
    mail_contact_email = db.Column(db.String(200), nullable=False, default='contact@wedding.com')
    mail_sender_name = db.Column(db.String(200), nullable=False, default='Wedding')
    # SMTP settings
    mail_smtp_server = db.Column(db.String(200), nullable=True)
    mail_smtp_port = db.Column(db.Integer, nullable=True)  # None = use default
    mail_use_ssl = db.Column(db.Boolean, default=True)  # legacy, superseded by mail_security
    mail_auth_enabled = db.Column(db.Boolean, default=True)  # False = plain unauthenticated SMTP
    mail_security = db.Column(db.String(20), default='tls')  # 'tls' (SSL/465) or 'starttls' (587)
    mail_smtp_username = db.Column(db.String(200), nullable=True)
    mail_smtp_password = db.Column(db.String(500), nullable=True)
    mail_sender_email = db.Column(db.String(200), nullable=True)
    # Site protection
    site_password_protected = db.Column(db.Boolean, default=False)
    site_password = db.Column(db.String(500), nullable=True)
    # Admin panel link in public nav
    show_admin_link = db.Column(db.Boolean, default=True)
    # Favicon
    favicon_filename = db.Column(db.String(200), nullable=True)
    # Hero image
    hero_image_filename = db.Column(db.String(200), nullable=True)
    hero_image_overlay_opacity = db.Column(db.Float, default=0.4)
    hero_image_blur = db.Column(db.Integer, default=0)
    hero_image_brightness = db.Column(db.Integer, default=100)
    hero_image_position = db.Column(db.String(50), default='center center')
    # Twitch stream
    twitch_enabled = db.Column(db.Boolean, default=False)
    twitch_channel = db.Column(db.String(200), nullable=True)
    # Photo challenge
    photo_challenge_enabled = db.Column(db.Boolean, default=True)
    photo_challenge_unlock_mode = db.Column(db.String(20), default='wedding_day')  # 'wedding_day' or 'custom'
    photo_challenge_unlock_date = db.Column(db.DateTime, nullable=True)
    # Timezone for unlock/wedding-day comparisons
    timezone = db.Column(db.String(50), nullable=False, default=lambda: os.environ.get('DEFAULT_TIMEZONE', 'UTC'))
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Challenge Model
class Challenge(db.Model):
    __tablename__ = 'challenges'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Existing models (unchanged)
class ChallengeAssignment(db.Model):
    __tablename__ = 'challenge_assignments'
    id = db.Column(db.Integer, primary_key=True)
    guest_name = db.Column(db.String(200), nullable=False, index=True)
    challenge = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PhotoSubmission(db.Model):
    __tablename__ = 'photo_submissions'
    id = db.Column(db.Integer, primary_key=True)
    guest_name = db.Column(db.String(200), nullable=False, index=True)
    challenge = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class RSVPSubmission(db.Model):
    __tablename__ = 'rsvp_submissions'
    id = db.Column(db.Integer, primary_key=True)
    names = db.Column(db.String(500), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    address = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(200), nullable=False)
    unique_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    rsvp_confirmed = db.Column(db.Boolean, default=False)
    rsvp_confirmed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def ensure_wedding_config_columns():
    """Add missing WeddingConfig columns for environments without migrations."""
    from sqlalchemy import inspect as sa_inspect
    try:
        existing = {col['name'] for col in sa_inspect(db.engine).get_columns('wedding_config')}
    except Exception:
        return  # table doesn't exist yet; db.create_all() above handles initial creation

    alter_statements = {
        'primary_text_color': "ALTER TABLE wedding_config ADD COLUMN primary_text_color VARCHAR(7) NOT NULL DEFAULT '#F5F1EE'",
        'nav_text_color': "ALTER TABLE wedding_config ADD COLUMN nav_text_color VARCHAR(7) NOT NULL DEFAULT '#3F3631'",
        'button_color': "ALTER TABLE wedding_config ADD COLUMN button_color VARCHAR(7) NOT NULL DEFAULT '#6D4846'",
        'footer_background_color': "ALTER TABLE wedding_config ADD COLUMN footer_background_color VARCHAR(7) NOT NULL DEFAULT '#211A17'",
        'footer_text_color': "ALTER TABLE wedding_config ADD COLUMN footer_text_color VARCHAR(7) NOT NULL DEFAULT '#A89C95'",
        'show_footer_copyright': "ALTER TABLE wedding_config ADD COLUMN show_footer_copyright BOOLEAN NOT NULL DEFAULT TRUE",
        'show_ceremony': "ALTER TABLE wedding_config ADD COLUMN show_ceremony BOOLEAN NOT NULL DEFAULT TRUE",
        'show_reception': "ALTER TABLE wedding_config ADD COLUMN show_reception BOOLEAN NOT NULL DEFAULT TRUE",
        'show_after_party': "ALTER TABLE wedding_config ADD COLUMN show_after_party BOOLEAN NOT NULL DEFAULT TRUE",
        'site_layout': "ALTER TABLE wedding_config ADD COLUMN site_layout VARCHAR(50) NOT NULL DEFAULT 'classic'",
        'show_registry': "ALTER TABLE wedding_config ADD COLUMN show_registry BOOLEAN NOT NULL DEFAULT FALSE",
        'registry_name': "ALTER TABLE wedding_config ADD COLUMN registry_name VARCHAR(500)",
        'registry_url': "ALTER TABLE wedding_config ADD COLUMN registry_url VARCHAR(1000)",
        'show_admin_link': "ALTER TABLE wedding_config ADD COLUMN show_admin_link BOOLEAN NOT NULL DEFAULT TRUE",
        'mail_smtp_server': "ALTER TABLE wedding_config ADD COLUMN mail_smtp_server VARCHAR(200)",
        'mail_smtp_port': "ALTER TABLE wedding_config ADD COLUMN mail_smtp_port INT",
        'mail_use_ssl': "ALTER TABLE wedding_config ADD COLUMN mail_use_ssl BOOLEAN NOT NULL DEFAULT TRUE",
        'mail_auth_enabled': "ALTER TABLE wedding_config ADD COLUMN mail_auth_enabled BOOLEAN NOT NULL DEFAULT TRUE",
        'mail_security': "ALTER TABLE wedding_config ADD COLUMN mail_security VARCHAR(20) NOT NULL DEFAULT 'tls'",
        'mail_smtp_username': "ALTER TABLE wedding_config ADD COLUMN mail_smtp_username VARCHAR(200)",
        'mail_smtp_password': "ALTER TABLE wedding_config ADD COLUMN mail_smtp_password VARCHAR(500)",
        'mail_sender_email': "ALTER TABLE wedding_config ADD COLUMN mail_sender_email VARCHAR(200)",
        'favicon_filename': "ALTER TABLE wedding_config ADD COLUMN favicon_filename VARCHAR(200)",
        'after_party_time': "ALTER TABLE wedding_config ADD COLUMN after_party_time VARCHAR(50)",
        'ceremony_lat': "ALTER TABLE wedding_config ADD COLUMN ceremony_lat DOUBLE PRECISION",
        'ceremony_lng': "ALTER TABLE wedding_config ADD COLUMN ceremony_lng DOUBLE PRECISION",
        'reception_lat': "ALTER TABLE wedding_config ADD COLUMN reception_lat DOUBLE PRECISION",
        'reception_lng': "ALTER TABLE wedding_config ADD COLUMN reception_lng DOUBLE PRECISION",
        'after_party_lat': "ALTER TABLE wedding_config ADD COLUMN after_party_lat DOUBLE PRECISION",
        'after_party_lng': "ALTER TABLE wedding_config ADD COLUMN after_party_lng DOUBLE PRECISION",
        'photo_challenge_enabled': "ALTER TABLE wedding_config ADD COLUMN photo_challenge_enabled BOOLEAN NOT NULL DEFAULT TRUE",
        'photo_challenge_unlock_mode': "ALTER TABLE wedding_config ADD COLUMN photo_challenge_unlock_mode VARCHAR(20) NOT NULL DEFAULT 'wedding_day'",
        'photo_challenge_unlock_date': "ALTER TABLE wedding_config ADD COLUMN photo_challenge_unlock_date TIMESTAMP",
        'timezone': "ALTER TABLE wedding_config ADD COLUMN timezone VARCHAR(50) NOT NULL DEFAULT 'UTC'",
        'hero_image_filename': "ALTER TABLE wedding_config ADD COLUMN hero_image_filename VARCHAR(200)",
        'hero_image_overlay_opacity': "ALTER TABLE wedding_config ADD COLUMN hero_image_overlay_opacity FLOAT NOT NULL DEFAULT 0.4",
        'hero_image_blur': "ALTER TABLE wedding_config ADD COLUMN hero_image_blur INT NOT NULL DEFAULT 0",
        'hero_image_brightness': "ALTER TABLE wedding_config ADD COLUMN hero_image_brightness INT NOT NULL DEFAULT 100",
        'hero_image_position': "ALTER TABLE wedding_config ADD COLUMN hero_image_position VARCHAR(50) NOT NULL DEFAULT 'center center'",
    }

    with db.engine.connect() as connection:
        for column_name, alter_sql in alter_statements.items():
            if column_name not in existing:
                connection.execute(text(alter_sql))
        connection.commit()

def time_to_input_value(time_str):
    """Convert a display time string like '2:00 PM' to HH:MM for <input type='time'>."""
    if not time_str or time_str.upper().strip() in ('TBD', 'N/A', ''):
        return ''
    for fmt in ('%I:%M %p', '%I:%M%p', '%H:%M'):
        try:
            return datetime.strptime(time_str.strip().upper(), fmt).strftime('%H:%M')
        except ValueError:
            continue
    return ''


def time_from_input_value(time_str):
    """Convert HH:MM from <input type='time'> to display format '2:00 PM'."""
    if not time_str:
        return 'TBD'
    try:
        formatted = datetime.strptime(time_str, '%H:%M').strftime('%I:%M %p')
        return formatted.lstrip('0') or formatted
    except ValueError:
        return time_str


def is_mail_configured():
    """Return True only when an SMTP server has been explicitly configured."""
    return bool(app.config.get('MAIL_SERVER', '').strip())


def apply_mail_config(wed_cfg):
    """Push WeddingConfig SMTP settings into Flask-Mail's app.config."""
    if not wed_cfg:
        return
    if wed_cfg.mail_smtp_server:
        app.config['MAIL_SERVER'] = wed_cfg.mail_smtp_server

    # Determine auth and security mode
    auth_enabled = wed_cfg.mail_auth_enabled if wed_cfg.mail_auth_enabled is not None else True
    security = (wed_cfg.mail_security or 'tls').lower()

    if not auth_enabled:
        # Plain unauthenticated SMTP (port 25)
        app.config['MAIL_USE_SSL'] = False
        app.config['MAIL_USE_TLS'] = False
        app.config['MAIL_USERNAME'] = None
        app.config['MAIL_PASSWORD'] = None
        default_port = 25
    elif security == 'starttls':
        app.config['MAIL_USE_SSL'] = False
        app.config['MAIL_USE_TLS'] = True
        default_port = 587
    else:  # 'tls' (SSL)
        app.config['MAIL_USE_SSL'] = True
        app.config['MAIL_USE_TLS'] = False
        default_port = 465

    app.config['MAIL_PORT'] = wed_cfg.mail_smtp_port or default_port

    if auth_enabled:
        if wed_cfg.mail_smtp_username:
            app.config['MAIL_USERNAME'] = wed_cfg.mail_smtp_username
        if wed_cfg.mail_smtp_password:
            app.config['MAIL_PASSWORD'] = wed_cfg.mail_smtp_password

    sender_email = wed_cfg.mail_sender_email or (wed_cfg.mail_smtp_username if auth_enabled else '') or ''
    app.config['MAIL_DEFAULT_SENDER'] = (wed_cfg.mail_sender_name or 'Wedding', sender_email)
    if wed_cfg.mail_contact_email:
        app.config['CONTACT_EMAIL'] = wed_cfg.mail_contact_email


# Create tables - retry loop handles race conditions when an existing
# postgres volume causes a brief delay before the DB accepts connections.
with app.app_context():
    for _attempt in range(1, 11):
        try:
            db.create_all()
            ensure_wedding_config_columns()
            apply_mail_config(WeddingConfig.query.first())
            break
        except Exception as _e:
            if _attempt < 10:
                print(f"Database not ready (attempt {_attempt}/10): {_e}", flush=True)
                time.sleep(3)
            else:
                print(f"ERROR: Could not initialise database after 10 attempts: {_e}", flush=True)
                raise

# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))

def get_wedding_config():
    """Get wedding configuration from database."""
    return WeddingConfig.query.first()

def setup_required():
    """True when initial admin setup has not been completed yet."""
    return AdminUser.query.count() == 0

@app.after_request
def set_security_headers(response):
    """Baseline browser hardening headers."""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return response

@app.before_request
def redirect_to_setup_if_needed():
    """Redirect any request to the setup wizard until an admin account exists."""
    if request.endpoint in ('admin_setup', 'static'):
        return
    if setup_required():
        return redirect(url_for('admin_setup'))

def compute_couple_initials(wed_cfg):
    """Build nav initials from configured couple names."""
    groom = (wed_cfg.groom if wed_cfg and wed_cfg.groom else 'A').strip()
    bride = (wed_cfg.bride if wed_cfg and wed_cfg.bride else 'B').strip()
    groom_initial = groom[0].upper() if groom else 'A'
    bride_initial = bride[0].upper() if bride else 'B'
    return f"{groom_initial} & {bride_initial}"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_unique_code():
    """Generate a unique code for RSVP confirmation"""
    while True:
        code = secrets.token_urlsafe(8)  # Generates URL-safe random string
        # Check if code already exists
        existing = RSVPSubmission.query.filter_by(unique_code=code).first()
        if not existing:
            return code

def _safe_color(value, default):
    """Return value if it is a plain hex colour, otherwise default."""
    return value if value and re.fullmatch(r'#[0-9A-Fa-f]{3,8}', value) else default


def is_safe_redirect_target(target):
    """Only allow redirects to a path on this site (blocks //evil.com, https://evil.com, /\\evil.com)."""
    if not target or not target.startswith('/') or target.startswith('//') or '\\' in target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc


def build_wedding_email_template(recipient_name, heading, message_text='', include_disclaimer=True):
    """Build a wedding-themed email body used for guest communication."""
    wed_cfg = get_wedding_config()
    if not wed_cfg:
        return "<p>Error loading wedding configuration</p>"
    
    # Everything interpolated below is escaped: guest names arrive from the
    # public Save the Date form and must not be able to inject HTML into emails.
    esc = html_escape
    recipient_name = esc(recipient_name)
    heading = esc(heading)
    bride = esc(wed_cfg.bride)
    groom = esc(wed_cfg.groom)
    wedding_date = esc(wed_cfg.wedding_date)
    venue = esc(wed_cfg.venue)
    city = esc(wed_cfg.city)
    primary_color = _safe_color(wed_cfg.primary_color, '#6D4846')
    accent_color = _safe_color(wed_cfg.accent_color, '#9C5B5B')
    gold_accent = _safe_color(wed_cfg.gold_accent, '#D4AF37')

    message_section = ''
    if message_text.strip():
        formatted_message = esc(message_text.strip()).replace('\n', '<br>')
        message_section = f"""
                            <p style=\"margin: 0 0 20px 0; font-size: 16px;\">{formatted_message}</p>
"""

    footer_row = ''
    if include_disclaimer:
        footer_row = """
                    <tr>
                        <td style=\"background-color: #f8f9f8; padding: 20px 40px; text-align: center; border-top: 1px solid #e9ecef;\">
                            <p style=\"font-size: 12px; color: #6c757d; margin: 0;\">This is an automated email. If you have any questions, please reply to this email.</p>
                        </td>
                    </tr>
"""

    # Calculate gradient colors
    gradient_start = primary_color
    gradient_end = accent_color

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
</head>
<body style=\"margin: 0; padding: 0; font-family: 'Montserrat', Arial, sans-serif; background-color: #f8f9f8; color: #2c3e50; line-height: 1.6;\">
    <table role=\"presentation\" style=\"width: 100%; border-collapse: collapse;\">
        <tr>
            <td style=\"padding: 40px 20px;\">
                <table role=\"presentation\" style=\"max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);\">
                    <tr>
                        <td style=\"background: linear-gradient(135deg, {gradient_start} 0%, {gradient_end} 100%); padding: 50px 40px; text-align: center;\">
                            <h1 style=\"font-family: 'Cormorant Garamond', Georgia, serif; font-size: 42px; color: #ffffff; margin: 0 0 10px 0; font-weight: 600;\">{groom} & {bride}</h1>
                            <p style=\"font-family: 'Cormorant Garamond', Georgia, serif; font-size: 24px; color: #ffffff; margin: 0 0 15px 0; opacity: 0.95;\">Are Getting Married!</p>
                            <div style=\"width: 60px; height: 2px; background-color: {gold_accent}; margin: 0 auto;\"></div>
                        </td>
                    </tr>
                    <tr>
                        <td style=\"padding: 40px;\">
                            <h2 style=\"font-family: 'Cormorant Garamond', Georgia, serif; font-size: 28px; color: {primary_color}; margin: 0 0 20px 0; text-align: center;\">{heading}</h2>
                            <p style=\"margin: 0 0 20px 0; font-size: 16px;\">Dear {recipient_name},</p>
{message_section}
                            <table role=\"presentation\" style=\"width: 100%; background-color: #f8f9f8; border-radius: 8px; margin: 30px 0;\">
                                <tr>
                                    <td style=\"padding: 25px; text-align: center;\">
                                        <p style=\"font-family: 'Cormorant Garamond', Georgia, serif; font-size: 20px; color: {primary_color}; margin: 0 0 15px 0; font-weight: 600;\">Wedding Details</p>
                                        <table role=\"presentation\" style=\"width: 100%;\">
                                            <tr>
                                                <td style=\"padding: 10px; text-align: center; width: 50%;\">
                                                    <p style=\"font-size: 24px; margin: 0;\">📅</p>
                                                    <p style=\"font-size: 14px; color: #6c757d; margin: 5px 0 0 0; font-weight: 600;\">WHEN</p>
                                                    <p style=\"font-size: 16px; color: #2c3e50; margin: 5px 0 0 0;\">{wedding_date}</p>
                                                </td>
                                                <td style=\"padding: 10px; text-align: center; width: 50%;\">
                                                    <p style=\"font-size: 24px; margin: 0;\">📍</p>
                                                    <p style=\"font-size: 14px; color: #6c757d; margin: 5px 0 0 0; font-weight: 600;\">WHERE</p>
                                                    <p style=\"font-size: 16px; color: #2c3e50; margin: 5px 0 0 0;\">{venue}</p>
                                                    <p style=\"font-size: 14px; color: #6c757d; margin: 3px 0 0 0;\">{city}</p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                            <p style=\"margin: 30px 0 0 0; font-size: 16px;\">With love,</p>
                            <p style=\"font-family: 'Cormorant Garamond', Georgia, serif; font-size: 24px; color: {primary_color}; margin: 5px 0 0 0;\">{groom} & {bride}</p>
                        </td>
                    </tr>
{footer_row}
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

    return html_body

def now_local():
    """Return the current time as a naive datetime in the configured wedding timezone."""
    cfg = get_wedding_config()
    tz_name = (cfg.timezone or 'UTC') if cfg else 'UTC'
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo('UTC')
    return datetime.now(tz).replace(tzinfo=None)


def is_wedding_day():
    """Check if it's the wedding day or after"""
    wed_cfg = get_wedding_config()
    if not wed_cfg or not wed_cfg.wedding_datetime:
        return False
    return now_local() >= wed_cfg.wedding_datetime


def get_photo_challenge_unlock_dt():
    """Return the datetime when the photo challenge unlocks (never None - falls back to far future)."""
    wed_cfg = get_wedding_config()
    if not wed_cfg:
        return datetime(2099, 12, 31)
    mode = wed_cfg.photo_challenge_unlock_mode or 'wedding_day'
    if mode == 'custom' and wed_cfg.photo_challenge_unlock_date:
        return wed_cfg.photo_challenge_unlock_date
    # Default: use wedding datetime
    return wed_cfg.wedding_datetime or datetime(2099, 12, 31)


def is_photo_challenge_unlocked():
    """Return True if the photo challenge unlock datetime has been reached."""
    return now_local() >= get_photo_challenge_unlock_dt()

def get_time_until_wedding():
    """Get time remaining until wedding"""
    wed_cfg = get_wedding_config()
    if not wed_cfg or not wed_cfg.wedding_datetime:
        return datetime.now()
    return wed_cfg.wedding_datetime

def check_site_password():
    """Check if site password protection is enabled and user is authenticated"""
    wed_cfg = get_wedding_config()
    if not wed_cfg or not wed_cfg.site_password_protected:
        return True
    return session.get('site_authenticated', False)

def require_site_password(f):
    """Decorator to require site password if protection is enabled"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not check_site_password():
            return redirect(url_for('site_login', next=request.full_path.rstrip('?')))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/site-login', methods=['GET', 'POST'])
def site_login():
    """Site password protection login page"""
    wed_cfg = get_wedding_config()
    
    # If protection is disabled, redirect to home
    if not wed_cfg or not wed_cfg.site_password_protected:
        return redirect(url_for('home'))
    
    next_page = request.args.get('next')
    if not is_safe_redirect_target(next_page):
        next_page = url_for('home')

    # If already authenticated, redirect to next page or home
    if session.get('site_authenticated', False):
        return redirect(next_page)
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        stored = wed_cfg.site_password or ''

        if stored.startswith(('scrypt:', 'pbkdf2:')):
            authenticated = check_password_hash(stored, password)
        else:
            # Legacy plaintext value from older installs; constant-time compare.
            authenticated = bool(stored) and secrets.compare_digest(password.encode(), stored.encode())

        if authenticated:
            session['site_authenticated'] = True
            session.permanent = True  # Keep session across browser restarts
            return redirect(next_page)
        else:
            flash('Incorrect password. Please try again.', 'error')
    
    return render_template('site_login.html')

@app.route('/')
@require_site_password
def home():
    """Home page with wedding information"""
    wed_cfg = get_wedding_config()
    return render_template('home.html', wedding_config=wed_cfg)

@app.route('/details')
@require_site_password
def details():
    """Wedding details page"""
    wed_cfg = get_wedding_config()

    if not wed_cfg:
        return redirect(url_for('home'))

    if not any([wed_cfg.show_ceremony, wed_cfg.show_reception, wed_cfg.show_after_party]):
        flash('Event details are currently hidden.', 'error')
        return redirect(url_for('home'))

    return render_template('details.html', wedding_config=wed_cfg)

@app.route('/stream')
@require_site_password
def stream():
    """Live stream page"""
    wed_cfg = get_wedding_config()
    if not wed_cfg or not wed_cfg.twitch_enabled:
        return redirect(url_for('home'))
    domain = ''
    if wed_cfg.footer_domain:
        domain = wed_cfg.footer_domain.strip().lower()
        domain = domain.removeprefix('https://').removeprefix('http://').rstrip('/')
    return render_template('stream.html', wedding_config=wed_cfg, twitch_parent=domain or 'localhost')

@app.route('/photo-challenge')
@require_site_password
def photo_challenge():
    """Photo challenge landing page"""
    wed_cfg = get_wedding_config()
    if not wed_cfg or not wed_cfg.photo_challenge_enabled:
        return redirect(url_for('home'))
    unlock_dt = get_photo_challenge_unlock_dt()
    is_unlocked = is_photo_challenge_unlocked()
    return render_template('photo_challenge.html',
                           wedding_datetime=unlock_dt,
                           is_unlocked=is_unlocked)

@app.route('/api/get-challenge', methods=['POST'])
@require_site_password
def get_challenge():
    """Get a random photo challenge for a guest"""
    if not is_photo_challenge_unlocked():
        return jsonify({'success': False, 'message': 'Photo challenges are not available yet!'}), 403

    data = request.get_json()
    guest_name = data.get('name', '').strip()
    exclude = data.get('exclude', [])  # challenge names to skip (used for reroll)

    if not guest_name:
        return jsonify({'success': False, 'message': 'Please enter your name'}), 400

    available_challenges = Challenge.query.all()

    if not available_challenges:
        return jsonify({'success': False, 'message': 'No challenges available'}), 500

    candidates = [c for c in available_challenges if c.name not in exclude] or available_challenges
    challenge = random.choice(candidates).name

    # Record in DB for admin visibility
    assignment = ChallengeAssignment(guest_name=guest_name, challenge=challenge)
    db.session.add(assignment)
    db.session.commit()

    return jsonify({
        'success': True,
        'challenge': challenge,
        'guest_name': guest_name
    })

@app.route('/api/upload-photo', methods=['POST'])
@require_site_password
def upload_photo():
    """Upload photo challenge submission"""
    if not is_photo_challenge_unlocked():
        return jsonify({'success': False, 'message': 'Photo uploads are not available yet!'}), 403
    
    if 'photo' not in request.files:
        return jsonify({'success': False, 'message': 'No photo provided'}), 400
    
    file = request.files['photo']
    guest_name = request.form.get('guest_name', '').strip()
    challenge = request.form.get('challenge', '').strip()
    
    if not guest_name or not challenge:
        return jsonify({'success': False, 'message': 'Missing guest name or challenge'}), 400
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        # Create safe filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = secure_filename(guest_name.replace(' ', '_'))
        filename = f"{safe_name}_{timestamp}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save file
        file.save(filepath)
        
        # Save submission to database
        submission = PhotoSubmission(
            guest_name=guest_name,
            challenge=challenge,
            filename=filename
        )
        db.session.add(submission)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Photo uploaded successfully! Check out the gallery to see everyone\'s photos.'
        })
    
    return jsonify({'success': False, 'message': 'Invalid file type. Please upload an image.'}), 400

@app.route('/gallery')
@require_site_password
def gallery():
    """Photo gallery page"""
    wed_cfg = get_wedding_config()
    if not wed_cfg or not wed_cfg.photo_challenge_enabled:
        return redirect(url_for('home'))
    unlock_dt = get_photo_challenge_unlock_dt()
    is_unlocked = is_photo_challenge_unlocked()

    submissions = []
    if is_unlocked:
        db_submissions = PhotoSubmission.query.order_by(PhotoSubmission.created_at.desc()).all()
        submissions = [{
            'guest_name': s.guest_name,
            'challenge': s.challenge,
            'filename': s.filename,
            'timestamp': s.created_at.strftime('%Y%m%d_%H%M%S')
        } for s in db_submissions]

    return render_template('gallery.html',
                           wedding_datetime=unlock_dt,
                           is_unlocked=is_unlocked,
                           submissions=submissions)

@app.route('/qr/save')
def generate_save_qr():
    """Generate QR code for the /save route (standard resolution for web display)"""
    # Generate the full URL for the /save route
    save_url = url_for('rsvp', _external=True)
    
    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(save_url)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to BytesIO
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

@app.route('/qr/save/download')
def download_save_qr():
    """Generate high-resolution QR code for the /save route (for printing)"""
    # Generate the full URL for the /save route
    save_url = url_for('rsvp', _external=True)
    
    # Create high-resolution QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # Higher error correction for printing
        box_size=20,  # Larger box size for better print quality
        border=8,     # Larger border
    )
    qr.add_data(save_url)
    qr.make(fit=True)
    
    # Create high-resolution image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to BytesIO
    img_io = BytesIO()
    img.save(img_io, 'PNG', optimize=False)  # Don't optimize to keep quality
    img_io.seek(0)
    
    return send_file(
        img_io,
        mimetype='image/png',
        as_attachment=True,
        download_name='save-the-date-qr-code.png'
    )

@app.route('/save', methods=['GET', 'POST'])
def rsvp():
    """Save the Date form - collects guest information for later RSVP"""
    if request.method == 'POST':
        names = request.form.get('names', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        email = request.form.get('email', '').strip()
        
        # Validate form data
        if not all([names, phone, address, email]):
            flash('Please fill in all required fields.', 'error')
            wed_cfg = get_wedding_config()
            return render_template('rsvp.html', wedding_config=wed_cfg)
        
        # Generate unique code for this guest
        unique_code = generate_unique_code()
        
        # Save to database
        try:
            rsvp_submission = RSVPSubmission(
                names=names,
                phone=phone,
                address=address,
                email=email,
                unique_code=unique_code,
                rsvp_confirmed=False
            )
            db.session.add(rsvp_submission)
            db.session.commit()
        except Exception as e:
            print(f"Error saving Save the Date to database: {e}")
            flash('Sorry, there was an error submitting your information. Please try again later.', 'error')
            wed_cfg = get_wedding_config()
            return render_template('rsvp.html', wedding_config=wed_cfg)
        
        # Try to send email notification (non-blocking - don't fail if email fails)
        if not is_mail_configured():
            print("Info: No SMTP server configured - skipping Save the Date notification email")
        else:
            try:
                admin_url = url_for('admin_rsvp', _external=True)
                confirm_url = url_for('rsvp_confirm', code=unique_code, _external=True)
                wed_cfg = get_wedding_config()
                couple_names = f"{wed_cfg.groom} & {wed_cfg.bride}" if wed_cfg else 'The Couple'
                msg = Message(
                    subject=f"New Save the Date - {names}",
                    recipients=[app.config['CONTACT_EMAIL']],
                    body=f"""
New Save the Date submission for {couple_names}

Name(s): {names}
Phone: {phone}
Address: {address}
Email: {email}
Unique Code: {unique_code}

Their RSVP confirmation link: {confirm_url}

View all submissions: {admin_url}
(Use your site password to login)

Submitted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    """,
                    reply_to=email
                )
                mail.send(msg)
            except Exception as e:
                # Log email error but don't fail the submission
                print(f"Warning: Failed to send Save the Date notification email: {e}")
        
        flash('Thank you! Your details have been saved. We\'ll send you an invitation with your personalized RSVP link closer to the date.', 'success')
        return redirect(url_for('home'))
    
    wed_cfg = get_wedding_config()
    return render_template('rsvp.html', wedding_config=wed_cfg)

@app.route('/rsvp/confirm/<code>', methods=['GET', 'POST'])
def rsvp_confirm(code):
    """RSVP confirmation page - accessed via unique QR code"""
    # Find the guest by unique code
    guest = RSVPSubmission.query.filter_by(unique_code=code).first()
    
    if not guest:
        flash('Invalid RSVP link. Please contact us if you need assistance.', 'error')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        # Confirm RSVP
        guest.rsvp_confirmed = True
        guest.rsvp_confirmed_at = datetime.utcnow()

        try:
            db.session.commit()
        except Exception as e:
            print(f"Error confirming RSVP: {e}")
            flash('Sorry, there was an error confirming your RSVP. Please try again.', 'error')
            wed_cfg = get_wedding_config()
            return render_template('rsvp_confirm.html', guest=guest, confirmed=False, wedding_config=wed_cfg)

        # Send notification emails in a background thread so the page
        # responds immediately - SMTP connections can take several seconds.
        def send_rsvp_emails(guest_id):
            with app.app_context():
                if not is_mail_configured():
                    print("Info: No SMTP server configured - skipping RSVP confirmation emails")
                    return
                g = RSVPSubmission.query.get(guest_id)
                if not g:
                    return
                wed_cfg = get_wedding_config()
                bride  = wed_cfg.bride  if wed_cfg else 'Partner 1'
                groom  = wed_cfg.groom  if wed_cfg else 'Partner 2'
                wedding_date = wed_cfg.wedding_date if wed_cfg else 'TBD'
                venue        = wed_cfg.venue        if wed_cfg else 'TBD'

                # Admin notification
                try:
                    admin_url = url_for('admin_rsvp', _external=True)
                    msg = Message(
                        subject=f"RSVP Confirmed - {g.names}",
                        recipients=[app.config['CONTACT_EMAIL']],
                        body=(
                            f"{g.names} has confirmed their RSVP!\n\n"
                            f"Name(s): {g.names}\nPhone: {g.phone}\n"
                            f"Address: {g.address}\nEmail: {g.email}\n\n"
                            f"Confirmed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                            f"View all RSVPs: {admin_url}"
                        ),
                        reply_to=g.email,
                    )
                    mail.send(msg)
                except Exception as e:
                    print(f"Warning: Failed to send RSVP admin notification email: {e}")

                # Guest confirmation
                try:
                    html_body = build_wedding_email_template(
                        recipient_name=g.names,
                        heading='Thank You for Your RSVP!',
                        message_text=(
                            "Thank you so much for confirming your RSVP! We are thrilled that "
                            "you'll be joining us to celebrate our special day.\n\n"
                            "We can't wait to see you there and share this joyful occasion with you!"
                        ),
                    )
                    plain_body = (
                        f"Dear {g.names},\n\n"
                        "Thank you so much for confirming your RSVP! "
                        "We are thrilled that you'll be joining us to celebrate our special day.\n\n"
                        f"Date: {wedding_date}\nVenue: {venue}\n\n"
                        "We can't wait to see you there!\n\n"
                        f"With love,\n{groom} & {bride}\n\n---\n"
                        "This is an automated confirmation email."
                    )
                    guest_msg = Message(
                        subject=f"Thank You for Your RSVP - {bride} & {groom}'s Wedding",
                        recipients=[g.email],
                        body=plain_body,
                        html=html_body,
                    )
                    mail.send(guest_msg)
                except Exception as e:
                    print(f"Warning: Failed to send RSVP confirmation email to guest: {e}")

        threading.Thread(target=send_rsvp_emails, args=(guest.id,), daemon=True).start()

        flash('Thank you for confirming your RSVP! We can\'t wait to celebrate with you! 🎉', 'success')
        wed_cfg = get_wedding_config()
        return render_template('rsvp_confirm.html', guest=guest, confirmed=True, wedding_config=wed_cfg)
    
    wed_cfg = get_wedding_config()
    return render_template('rsvp_confirm.html', guest=guest, confirmed=guest.rsvp_confirmed, wedding_config=wed_cfg)

@app.route('/rsvp/admin/login', methods=['GET', 'POST'])
def rsvp_admin_login():
    """Login page for RSVP admin"""
    if request.method == 'POST':
        password = request.form.get('password', '')
        correct_password = config.get('site_protection', {}).get('password')
        
        if password == correct_password:
            session['rsvp_admin_authenticated'] = True
            return redirect(url_for('rsvp_admin'))
        else:
            flash('Incorrect password. Please try again.', 'error')
    
    return render_template('rsvp_admin_login.html')

@app.route('/rsvp/admin')
def rsvp_admin():
    """Password-protected admin view of all RSVP submissions"""
    # Check if authenticated via session
    if not session.get('rsvp_admin_authenticated', False):
        return redirect(url_for('rsvp_admin_login'))
    
    # Get all RSVPs
    rsvps = RSVPSubmission.query.order_by(RSVPSubmission.created_at.desc()).all()
    
    return render_template('rsvp_admin.html', rsvps=rsvps, email_form={})

@app.route('/rsvp/admin/bulk-email', methods=['POST'])
def rsvp_admin_bulk_email():
    """Preview or send email to RSVP guests, or send ad-hoc to one address."""
    if not session.get('rsvp_admin_authenticated', False):
        return redirect(url_for('rsvp_admin_login'))

    action = request.form.get('action', 'send')
    is_ajax_preview = (
        action == 'preview'
        and request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )
    subject = request.form.get('subject', '').strip()
    message_text = request.form.get('message', '').strip()
    confirmed_only = request.form.get('confirmed_only') == 'on'
    unconfirmed_only = request.form.get('unconfirmed_only') == 'on'
    ad_hoc_email = request.form.get('ad_hoc_email', '').strip()
    ad_hoc_name_raw = request.form.get('ad_hoc_name', '').strip()
    ad_hoc_name = ad_hoc_name_raw or 'Guest'

    email_form = {
        'subject': subject,
        'message': message_text,
        'confirmed_only': confirmed_only,
        'unconfirmed_only': unconfirmed_only,
        'ad_hoc_email': ad_hoc_email,
        'ad_hoc_name': ad_hoc_name_raw,
    }

    wed_cfg = get_wedding_config()
    default_subject = f"A Message From {wed_cfg.groom if wed_cfg else 'Our Wedding'} & {wed_cfg.bride if wed_cfg else 'Our Wedding'}"
    subject = subject or default_subject

    if not message_text:
        error_message = 'Please provide an email message.'
        if is_ajax_preview:
            return jsonify({'success': False, 'message': error_message}), 400
        flash(error_message, 'error')
        return redirect(url_for('rsvp_admin'))

    if confirmed_only and unconfirmed_only:
        error_message = 'Please choose either confirmed-only or unconfirmed-only, not both.'
        if is_ajax_preview:
            return jsonify({'success': False, 'message': error_message}), 400
        flash(error_message, 'error')
        return redirect(url_for('rsvp_admin'))

    if action == 'preview':
        preview_html = build_wedding_email_template(
            recipient_name=ad_hoc_name,
            heading='A Message From Us',
            message_text=message_text,
            include_disclaimer=False
        )

        if is_ajax_preview:
            return jsonify({
                'success': True,
                'email_preview_html': preview_html,
                'email_preview_subject': subject,
                'email_preview_recipient': ad_hoc_name,
            })

        return render_template(
            'rsvp_admin.html',
            rsvps=RSVPSubmission.query.order_by(RSVPSubmission.created_at.desc()).all(),
            email_preview_html=preview_html,
            email_preview_subject=subject,
            email_preview_recipient=ad_hoc_name,
            email_form=email_form,
        )

    if ad_hoc_email:
        recipients = [
            {
                'name': ad_hoc_name,
                'email': ad_hoc_email
            }
        ]
    else:
        query = RSVPSubmission.query
        if confirmed_only:
            query = query.filter_by(rsvp_confirmed=True)
        elif unconfirmed_only:
            query = query.filter_by(rsvp_confirmed=False)

        recipients = [
            {
                'name': guest.names,
                'email': guest.email
            }
            for guest in query.order_by(RSVPSubmission.names.asc()).all()
        ]

    placeholder_count = 0
    filtered_recipients = []
    for recipient in recipients:
        email = (recipient.get('email') or '').strip()
        if not email:
            continue

        # Ignore placeholder addresses used for test data.
        if email.lower().endswith('@fake.com'):
            placeholder_count += 1
            continue

        filtered_recipients.append({
            'name': recipient.get('name', 'Guest'),
            'email': email
        })

    recipients = filtered_recipients

    if not recipients:
        if placeholder_count:
            flash('No valid recipients found. Placeholder addresses ending in @fake.com were ignored.', 'error')
        else:
            flash('No guests matched your selected email filter.', 'error')
        return redirect(url_for('rsvp_admin'))

    sent_count = 0
    failed_count = 0
    bride = config['wedding']['bride']
    groom = config['wedding']['groom']
    for recipient in recipients:
        try:
            html_body = build_wedding_email_template(
                recipient_name=recipient['name'],
                heading='A Message From Us',
                message_text=message_text,
                include_disclaimer=False
            )

            plain_body = f"""Dear {recipient['name']},

{message_text}

With love,
{groom} & {bride}
"""

            if not is_mail_configured():
                print("Info: No SMTP server configured - skipping bulk email")
                failed_count += 1
                continue
            guest_msg = Message(
                subject=subject,
                recipients=[recipient['email']],
                body=plain_body,
                html=html_body
            )
            mail.send(guest_msg)
            sent_count += 1
        except Exception as e:
            failed_count += 1
            print(f"Warning: Failed to send bulk email to {recipient['email']}: {e}")

    if sent_count == 0:
        flash('No bulk emails were sent. Please check your mail configuration and try again.', 'error')
    elif failed_count:
        flash(
            f'Bulk email sent to {sent_count} guest(s). Failed for {failed_count} guest(s).',
            'success'
        )
    else:
        flash(f'Bulk email sent successfully to {sent_count} guest(s).', 'success')

    return redirect(url_for('rsvp_admin'))

@app.route('/rsvp/admin/logout')
def rsvp_admin_logout():
    """Logout from RSVP admin"""
    session.pop('rsvp_admin_authenticated', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))

@app.route('/rsvp/admin/export')
def rsvp_admin_export():
    """Export RSVPs to CSV"""
    # Check if authenticated via session
    if not session.get('rsvp_admin_authenticated', False):
        return redirect(url_for('rsvp_admin_login'))
    
    # Get all RSVPs
    rsvps = RSVPSubmission.query.order_by(RSVPSubmission.created_at.desc()).all()
    
    # Create CSV in memory
    si = StringIO()
    writer = csv.writer(si)
    
    # Write header
    writer.writerow(['ID', 'Name(s)', 'Phone', 'Address', 'Email', 'Unique Code', 'RSVP Confirmed', 'Confirmed At', 'Submitted At'])
    
    # Write data
    for rsvp in rsvps:
        writer.writerow([
            rsvp.id,
            rsvp.names,
            rsvp.phone,
            rsvp.address,
            rsvp.email,
            rsvp.unique_code,
            'Yes' if rsvp.rsvp_confirmed else 'No',
            rsvp.rsvp_confirmed_at.strftime('%Y-%m-%d %H:%M:%S') if rsvp.rsvp_confirmed_at else '',
            rsvp.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    # Create response
    output = si.getvalue()
    si.close()
    
    # Generate filename with current date
    filename = f"rsvp_submissions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/qr/rsvp/<code>')
def generate_guest_qr(code):
    """Generate QR code for a specific guest's RSVP confirmation link"""
    # Generate the full URL for the guest's confirmation page
    confirm_url = url_for('rsvp_confirm', code=code, _external=True)
    
    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(confirm_url)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to BytesIO
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

@app.context_processor
def inject_template_globals():
    """Inject global values used across templates."""
    wed_cfg = get_wedding_config()

    if wed_cfg:
        groom = wed_cfg.groom or 'Partner 2'
        bride = wed_cfg.bride or 'Partner 1'
        site_title = wed_cfg.site_title or f"{groom} & {bride} Wedding"
        footer_domain = wed_cfg.footer_domain or 'domain name'
        theme_primary_color = wed_cfg.primary_color or '#6D4846'
        theme_primary_text_color = wed_cfg.primary_text_color or '#F5F1EE'
        theme_accent_color = wed_cfg.accent_color or '#9C5B5B'
        theme_highlight_color = wed_cfg.gold_accent or '#C9A87C'
        theme_nav_text_color = wed_cfg.nav_text_color or '#3F3631'
        theme_button_color = wed_cfg.button_color or theme_primary_color
        footer_background_color = wed_cfg.footer_background_color or '#211A17'
        footer_text_color = wed_cfg.footer_text_color or '#A89C95'
        site_layout = wed_cfg.site_layout or 'classic'
        show_details_tab = any([wed_cfg.show_ceremony, wed_cfg.show_reception, wed_cfg.show_after_party])
        show_admin_link = wed_cfg.show_admin_link if wed_cfg.show_admin_link is not None else True
        twitch_enabled = wed_cfg.twitch_enabled if wed_cfg.twitch_enabled is not None else False
        photo_challenge_enabled = wed_cfg.photo_challenge_enabled if wed_cfg.photo_challenge_enabled is not None else True
    else:
        groom = 'Partner 1'
        bride = 'Partner 2'
        site_title = 'Our Wedding'
        footer_domain = 'example.com'
        theme_primary_color = '#6D4846'
        theme_primary_text_color = '#F5F1EE'
        theme_accent_color = '#9C5B5B'
        theme_highlight_color = '#C9A87C'
        theme_nav_text_color = '#3F3631'
        theme_button_color = '#6D4846'
        footer_background_color = '#211A17'
        footer_text_color = '#A89C95'
        site_layout = 'classic'
        show_details_tab = True
        show_admin_link = True
        twitch_enabled = False
        photo_challenge_enabled = True

    if site_layout not in {'classic', 'editorial', 'minimal', 'romantic', 'luxe'}:
        site_layout = 'classic'

    icon_weight = {
        'classic':   'ph',
        'romantic':  'ph',
        'editorial': 'ph-light',
        'minimal':   'ph-light',
        'luxe':      'ph-thin',
    }.get(site_layout, 'ph')

    return {
        'current_year': datetime.now().year,
        'site_title': site_title,
        'couple_names': f"{groom} & {bride}",
        'couple_initials': compute_couple_initials(wed_cfg),
        'footer_domain': footer_domain,
        'theme_primary_color': theme_primary_color,
        'theme_primary_text_color': theme_primary_text_color,
        'theme_accent_color': theme_accent_color,
        'theme_highlight_color': theme_highlight_color,
        'theme_nav_text_color': theme_nav_text_color,
        'theme_button_color': theme_button_color,
        'footer_background_color': footer_background_color,
        'footer_text_color': footer_text_color,
        'site_layout': site_layout,
        'icon_weight': icon_weight,
        'show_details_tab': show_details_tab,
        'show_admin_link': show_admin_link,
        'twitch_enabled': twitch_enabled,
        'photo_challenge_enabled': photo_challenge_enabled,
    }

# ==================== ADMIN ROUTES ====================

def admin_required(f):
    """Decorator to require admin login"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access the admin panel.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/setup', methods=['GET', 'POST'])
def admin_setup():
    """First-time setup wizard - create admin user and initial wedding config"""
    # Check if setup is needed (no admin users and no wedding config)
    admin_count = AdminUser.query.count()
    wedding_config_count = WeddingConfig.query.count()
    
    # If setup is complete, redirect to admin login
    if admin_count > 0 and wedding_config_count > 0:
        return redirect(url_for('admin_login'))

    # Once an admin exists, the remaining setup steps belong to that admin only.
    # Without this, anyone could re-submit step 1 and create their own admin
    # account while the wedding config is still missing.
    if admin_count > 0 and not current_user.is_authenticated:
        flash('Please log in to finish setting up your wedding.', 'error')
        return redirect(url_for('admin_login'))

    setup_token = os.environ.get('SETUP_TOKEN', '')

    if request.method == 'POST':
        step = request.form.get('step', '1')

        # Step 1: Create Admin User
        if step == '1':
            if admin_count > 0:
                return redirect(url_for('admin_setup'))

            if setup_token and not secrets.compare_digest(
                    request.form.get('setup_token', '').encode(), setup_token.encode()):
                flash('Invalid setup token', 'error')
                return render_template('admin/setup.html', step=1, require_setup_token=True)

            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            if not email or not password or not confirm_password:
                flash('Please fill in all fields', 'error')
                return render_template('admin/setup.html', step=1, require_setup_token=bool(setup_token))
            
            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return render_template('admin/setup.html', step=1, require_setup_token=bool(setup_token))
            
            if AdminUser.query.filter_by(email=email).first():
                flash('Email already registered', 'error')
                return render_template('admin/setup.html', step=1, require_setup_token=bool(setup_token))
            
            # Create admin user
            admin = AdminUser(email=email)
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()

            # Log the new admin in so step 2 is tied to their session.
            login_user(admin)
            flash('Admin user created! Now let\'s set up your wedding details.', 'success')
            return redirect(url_for('admin_setup'))

        # Step 2: Create Wedding Config (only the logged-in admin, checked above)
        elif step == '2':
            if admin_count == 0:
                return redirect(url_for('admin_setup'))

            bride = request.form.get('bride', '').strip()
            groom = request.form.get('groom', '').strip()
            wedding_date_str = request.form.get('wedding_date', '')
            wedding_time = request.form.get('wedding_time', '14:00')
            venue = request.form.get('venue', '').strip()
            city = request.form.get('city', '').strip()
            tz_val = request.form.get('timezone', os.environ.get('DEFAULT_TIMEZONE', 'UTC')).strip()
            try:
                ZoneInfo(tz_val)
            except Exception:
                tz_val = 'UTC'

            if not all([bride, groom, wedding_date_str, venue, city]):
                flash('Please fill in all required fields', 'error')
                return render_template('admin/setup.html', step=2,
                                       default_tz=os.environ.get('DEFAULT_TIMEZONE', 'UTC'))

            try:
                # Parse wedding datetime
                wedding_datetime = datetime.strptime(f"{wedding_date_str} {wedding_time}", '%Y-%m-%d %H:%M')

                # Create wedding config
                wedding_cfg = WeddingConfig(
                    bride=bride,
                    groom=groom,
                    wedding_date=wedding_date_str,
                    wedding_datetime=wedding_datetime,
                    venue=venue,
                    city=city,
                    ceremony_location=venue,
                    reception_location=venue,
                    primary_text_color='#F5F1EE',
                    nav_text_color='#3F3631',
                    button_color='#6D4846',
                    footer_background_color='#211A17',
                    footer_text_color='#A89C95',
                    show_ceremony=True,
                    show_reception=True,
                    show_after_party=True,
                    site_title=f"{groom} & {bride} Wedding",
                    site_layout='classic',
                    timezone=tz_val,
                )
                db.session.add(wedding_cfg)
                db.session.commit()

                flash('Wedding configuration created! Setup is complete.', 'success')
                return render_template('admin/setup.html', step=3)
            except Exception as e:
                flash(f'Error creating wedding configuration: {str(e)}', 'error')
                return render_template('admin/setup.html', step=2,
                                       default_tz=os.environ.get('DEFAULT_TIMEZONE', 'UTC'))
    
    # Determine which step to show
    admin_count = AdminUser.query.count()
    if admin_count == 0:
        step = 1
    else:
        step = 2

    return render_template('admin/setup.html', step=step,
                           require_setup_token=bool(setup_token),
                           default_tz=os.environ.get('DEFAULT_TIMEZONE', 'UTC'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if setup_required():
        return redirect(url_for('admin_setup'))

    # Send admins back to the wizard if wedding setup was never finished.
    post_login_endpoint = 'admin_dashboard' if get_wedding_config() else 'admin_setup'

    if current_user.is_authenticated:
        return redirect(url_for(post_login_endpoint))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        admin = AdminUser.query.filter_by(email=email).first()

        if admin and admin.check_password(password):
            admin.last_login = datetime.utcnow()
            db.session.commit()
            login_user(admin)
            flash('Welcome back!', 'success')
            return redirect(url_for(post_login_endpoint))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('admin/login.html', show_setup_link=False)

@app.route('/admin/logout')
@admin_required
def admin_logout():
    """Admin logout"""
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    wedding_cfg = get_wedding_config()
    rsvp_count = RSVPSubmission.query.count()
    confirmed_rsvp_count = RSVPSubmission.query.filter_by(rsvp_confirmed=True).count()
    photo_count = PhotoSubmission.query.count()
    challenge_count = Challenge.query.count()
    
    stats = {
        'rsvps_total': rsvp_count,
        'rsvps_confirmed': confirmed_rsvp_count,
        'photos': photo_count,
        'challenges': challenge_count
    }
    
    return render_template('admin/dashboard.html', wedding_config=wedding_cfg, stats=stats)

@app.route('/admin/wedding', methods=['GET', 'POST'])
@admin_required
def admin_wedding_settings():
    """Edit wedding settings"""
    wedding_cfg = get_wedding_config()
    
    if request.method == 'POST':
        try:
            wedding_cfg.bride = request.form.get('bride', wedding_cfg.bride)
            wedding_cfg.groom = request.form.get('groom', wedding_cfg.groom)
            wedding_cfg.wedding_date = request.form.get('wedding_date', wedding_cfg.wedding_date)
            wedding_time = request.form.get('wedding_time', '').strip()

            if not wedding_time:
                if wedding_cfg.wedding_datetime:
                    wedding_time = wedding_cfg.wedding_datetime.strftime('%H:%M')
                else:
                    wedding_time = '14:00'
            
            # Parse wedding datetime
            if wedding_cfg.wedding_date and wedding_time:
                wedding_cfg.wedding_datetime = datetime.strptime(f"{wedding_cfg.wedding_date} {wedding_time}", '%Y-%m-%d %H:%M')

            tz_val = request.form.get('timezone', 'UTC').strip()
            try:
                ZoneInfo(tz_val)
                wedding_cfg.timezone = tz_val
            except Exception:
                pass

            wedding_cfg.venue = request.form.get('venue', wedding_cfg.venue)
            wedding_cfg.city = request.form.get('city', wedding_cfg.city)
            wedding_cfg.ceremony_location = request.form.get('ceremony_location', wedding_cfg.ceremony_location)
            _ct = request.form.get('ceremony_time', '').strip()
            if _ct:
                wedding_cfg.ceremony_time = time_from_input_value(_ct)
            wedding_cfg.reception_location = request.form.get('reception_location', wedding_cfg.reception_location)
            _rt = request.form.get('reception_time', '').strip()
            if _rt:
                wedding_cfg.reception_time = time_from_input_value(_rt)
            wedding_cfg.after_party_location = request.form.get('after_party_location', wedding_cfg.after_party_location)
            _apt = request.form.get('after_party_time', '').strip()
            if _apt:
                wedding_cfg.after_party_time = time_from_input_value(_apt)

            # Location coordinates from map picker
            def _float_or_none(val):
                try:
                    return float(val) if val not in (None, '') else None
                except (TypeError, ValueError):
                    return None

            wedding_cfg.ceremony_lat = _float_or_none(request.form.get('ceremony_lat'))
            wedding_cfg.ceremony_lng = _float_or_none(request.form.get('ceremony_lng'))
            wedding_cfg.reception_lat = _float_or_none(request.form.get('reception_lat'))
            wedding_cfg.reception_lng = _float_or_none(request.form.get('reception_lng'))
            wedding_cfg.after_party_lat = _float_or_none(request.form.get('after_party_lat'))
            wedding_cfg.after_party_lng = _float_or_none(request.form.get('after_party_lng'))

            wedding_cfg.show_registry = 'show_registry' in request.form
            wedding_cfg.registry_name = request.form.get('registry_name', '').strip() or None
            wedding_cfg.registry_url = request.form.get('registry_url', '').strip() or None
            
            # Colors
            wedding_cfg.primary_color = request.form.get('primary_color', wedding_cfg.primary_color)
            wedding_cfg.primary_text_color = request.form.get('primary_text_color', wedding_cfg.primary_text_color)
            wedding_cfg.accent_color = request.form.get('accent_color', wedding_cfg.accent_color)
            wedding_cfg.nav_text_color = request.form.get('nav_text_color', wedding_cfg.nav_text_color)
            wedding_cfg.button_color = request.form.get('button_color', wedding_cfg.button_color)
            wedding_cfg.gold_accent = request.form.get('gold_accent', wedding_cfg.gold_accent)
            wedding_cfg.footer_background_color = request.form.get('footer_background_color', wedding_cfg.footer_background_color)
            wedding_cfg.footer_text_color = request.form.get('footer_text_color', wedding_cfg.footer_text_color)

            # Hero image display settings
            try:
                wedding_cfg.hero_image_overlay_opacity = max(0.0, min(1.0, int(request.form.get('hero_image_overlay_opacity', 40)) / 100))
            except (ValueError, TypeError):
                pass
            try:
                wedding_cfg.hero_image_blur = max(0, min(20, int(request.form.get('hero_image_blur', 0))))
            except (ValueError, TypeError):
                pass
            try:
                wedding_cfg.hero_image_brightness = max(50, min(150, int(request.form.get('hero_image_brightness', 100))))
            except (ValueError, TypeError):
                pass
            hero_pos = request.form.get('hero_image_position', 'center center')
            if hero_pos in {'center center', 'top center', 'bottom center', 'center left', 'center right'}:
                wedding_cfg.hero_image_position = hero_pos

            wedding_cfg.show_ceremony = 'show_ceremony' in request.form
            wedding_cfg.show_reception = 'show_reception' in request.form
            wedding_cfg.show_after_party = 'show_after_party' in request.form
            
            # Site info
            wedding_cfg.site_title = request.form.get('site_title', wedding_cfg.site_title)
            wedding_cfg.footer_domain = request.form.get('footer_domain', wedding_cfg.footer_domain)
            selected_layout = request.form.get('site_layout', wedding_cfg.site_layout or 'classic')
            valid_layouts = {'classic', 'editorial', 'minimal', 'romantic', 'luxe'}
            wedding_cfg.site_layout = selected_layout if selected_layout in valid_layouts else 'classic'
            
            # Twitch
            wedding_cfg.twitch_enabled = 'twitch_enabled' in request.form
            wedding_cfg.twitch_channel = request.form.get('twitch_channel', wedding_cfg.twitch_channel)

            # Photo challenge
            wedding_cfg.photo_challenge_enabled = 'photo_challenge_enabled' in request.form
            pc_mode = request.form.get('photo_challenge_unlock_mode', 'wedding_day')
            wedding_cfg.photo_challenge_unlock_mode = pc_mode if pc_mode in ('wedding_day', 'custom') else 'wedding_day'
            if pc_mode == 'custom':
                custom_dt_str = request.form.get('photo_challenge_unlock_date', '').strip()
                if custom_dt_str:
                    try:
                        wedding_cfg.photo_challenge_unlock_date = datetime.strptime(custom_dt_str, '%Y-%m-%dT%H:%M')
                    except ValueError:
                        pass  # keep existing value
            
            # Site protection
            wedding_cfg.site_password_protected = 'site_password_protected' in request.form
            new_password = request.form.get('site_password', '')
            if new_password:
                wedding_cfg.site_password = generate_password_hash(new_password)

            # Admin link
            wedding_cfg.show_admin_link = 'show_admin_link' in request.form

            # Mail / SMTP settings
            new_contact = request.form.get('mail_contact_email', '').strip()
            if new_contact:
                wedding_cfg.mail_contact_email = new_contact
            new_sender_name = request.form.get('mail_sender_name', '').strip()
            if new_sender_name:
                wedding_cfg.mail_sender_name = new_sender_name
            new_sender_email = request.form.get('mail_sender_email', '').strip()
            if new_sender_email:
                wedding_cfg.mail_sender_email = new_sender_email
            new_smtp_server = request.form.get('mail_smtp_server', '').strip()
            if new_smtp_server:
                wedding_cfg.mail_smtp_server = new_smtp_server

            # Auth / security / port
            wedding_cfg.mail_auth_enabled = 'mail_auth_enabled' in request.form
            security_val = request.form.get('mail_security', 'tls').strip().lower()
            wedding_cfg.mail_security = security_val if security_val in ('tls', 'starttls') else 'tls'

            # Port: only store override when the override checkbox is ticked
            if 'mail_port_override' in request.form:
                new_smtp_port = request.form.get('mail_smtp_port', '').strip()
                if new_smtp_port.isdigit():
                    wedding_cfg.mail_smtp_port = int(new_smtp_port)
            else:
                wedding_cfg.mail_smtp_port = None  # use protocol default

            if wedding_cfg.mail_auth_enabled:
                new_smtp_user = request.form.get('mail_smtp_username', '').strip()
                if new_smtp_user:
                    wedding_cfg.mail_smtp_username = new_smtp_user
                new_smtp_pass = request.form.get('mail_smtp_password', '').strip()
                if new_smtp_pass:
                    wedding_cfg.mail_smtp_password = new_smtp_pass

            db.session.commit()
            apply_mail_config(wedding_cfg)
            flash('Wedding settings saved successfully!', 'success')
        except Exception as e:
            flash(f'Error saving settings: {str(e)}', 'error')

    wedding_date_value = wedding_cfg.wedding_date or ''
    try:
        datetime.strptime(wedding_date_value, '%Y-%m-%d')
    except (TypeError, ValueError):
        wedding_date_value = wedding_cfg.wedding_datetime.strftime('%Y-%m-%d') if wedding_cfg.wedding_datetime else ''

    wedding_time_value = wedding_cfg.wedding_datetime.strftime('%H:%M') if wedding_cfg.wedding_datetime else '14:00'

    return render_template(
        'admin/wedding_settings.html',
        wedding_config=wedding_cfg,
        wedding_date_value=wedding_date_value,
        wedding_time_value=wedding_time_value,
        ceremony_time_value=time_to_input_value(wedding_cfg.ceremony_time),
        reception_time_value=time_to_input_value(wedding_cfg.reception_time),
        after_party_time_value=time_to_input_value(wedding_cfg.after_party_time),
    )

@app.route('/admin/favicon/upload', methods=['POST'])
@admin_required
def admin_favicon_upload():
    """Upload a custom site favicon"""
    if 'favicon' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('admin_wedding_settings') + '#tab-site')
    f = request.files['favicon']
    if not f or f.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('admin_wedding_settings') + '#tab-site')
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in FAVICON_EXTENSIONS:
        flash(f'Unsupported file type. Allowed: {", ".join(sorted(FAVICON_EXTENSIONS))}.', 'error')
        return redirect(url_for('admin_wedding_settings') + '#tab-site')
    # Remove previous favicon files
    for old in os.listdir(FAVICON_FOLDER):
        os.remove(os.path.join(FAVICON_FOLDER, old))
    filename = f'favicon.{ext}'
    f.save(os.path.join(FAVICON_FOLDER, filename))
    wed_cfg = get_wedding_config()
    wed_cfg.favicon_filename = filename
    db.session.commit()
    flash('Favicon updated.', 'success')
    return redirect(url_for('admin_wedding_settings') + '#tab-site')


@app.route('/admin/favicon/delete', methods=['POST'])
@admin_required
def admin_favicon_delete():
    """Remove the custom favicon"""
    wed_cfg = get_wedding_config()
    if wed_cfg.favicon_filename:
        path = os.path.join(FAVICON_FOLDER, wed_cfg.favicon_filename)
        if os.path.exists(path):
            os.remove(path)
        wed_cfg.favicon_filename = None
        db.session.commit()
    flash('Favicon removed.', 'success')
    return redirect(url_for('admin_wedding_settings') + '#tab-site')


@app.route('/admin/hero-image/upload', methods=['POST'])
@admin_required
def admin_hero_image_upload():
    """Upload a hero banner image"""
    if 'hero_image' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('admin_wedding_settings') + '#tab-appearance')
    f = request.files['hero_image']
    if not f or f.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('admin_wedding_settings') + '#tab-appearance')
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        flash(f'Unsupported file type. Allowed: {", ".join(sorted(ALLOWED_EXTENSIONS))}.', 'error')
        return redirect(url_for('admin_wedding_settings') + '#tab-appearance')
    wed_cfg = get_wedding_config()
    if wed_cfg.hero_image_filename:
        old = os.path.join(HERO_IMAGE_FOLDER, wed_cfg.hero_image_filename)
        if os.path.exists(old):
            os.remove(old)
    filename = f'hero.{ext}'
    f.save(os.path.join(HERO_IMAGE_FOLDER, filename))
    wed_cfg.hero_image_filename = filename
    db.session.commit()
    flash('Hero image updated.', 'success')
    return redirect(url_for('admin_wedding_settings') + '#tab-appearance')


@app.route('/admin/hero-image/delete', methods=['POST'])
@admin_required
def admin_hero_image_delete():
    """Remove the hero banner image"""
    wed_cfg = get_wedding_config()
    if wed_cfg.hero_image_filename:
        path = os.path.join(HERO_IMAGE_FOLDER, wed_cfg.hero_image_filename)
        if os.path.exists(path):
            os.remove(path)
        wed_cfg.hero_image_filename = None
        db.session.commit()
    flash('Hero image removed.', 'success')
    return redirect(url_for('admin_wedding_settings') + '#tab-appearance')


@app.route('/admin/challenges', methods=['GET', 'POST'])
@admin_required
def admin_challenges():
    """Manage photo challenges"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Challenge name is required', 'error')
            else:
                challenge = Challenge(name=name, description=description)
                db.session.add(challenge)
                db.session.commit()
                flash('Challenge added successfully!', 'success')
        
        elif action == 'delete':
            challenge_id = request.form.get('challenge_id')
            challenge = Challenge.query.get(challenge_id)
            if challenge:
                db.session.delete(challenge)
                db.session.commit()
                flash('Challenge deleted successfully!', 'success')
    
    challenges = Challenge.query.order_by(Challenge.sort_order).all()
    return render_template('admin/challenges.html', challenges=challenges)

@app.route('/admin/rsvp', methods=['GET'])
@admin_required
def admin_rsvp():
    """View all RSVPs"""
    rsvps = RSVPSubmission.query.order_by(RSVPSubmission.created_at.desc()).all()
    confirmed = RSVPSubmission.query.filter_by(rsvp_confirmed=True).count()
    pending = RSVPSubmission.query.filter_by(rsvp_confirmed=False).count()
    
    return render_template('admin/rsvp.html', rsvps=rsvps, confirmed=confirmed, pending=pending)

@app.route('/rsvp/admin/qr-codes')
@admin_required
def rsvp_admin_qr_codes():
    """Printable page with QR codes for all guests"""
    rsvps = RSVPSubmission.query.order_by(RSVPSubmission.names.asc()).all()
    wed_cfg = get_wedding_config()
    return render_template('admin/qr_codes.html', rsvps=rsvps, wedding_config=wed_cfg)

@app.route('/admin/rsvp/import', methods=['POST'])
@admin_required
def admin_rsvp_import():
    """Bulk import guests from a CSV file.

    Expected columns (case-insensitive, extras ignored):
        names     – required
        email     – optional
        phone     – optional
        address   – optional
    """
    if 'csv_file' not in request.files:
        flash('No file uploaded.', 'error')
        return redirect(url_for('admin_rsvp'))

    file = request.files['csv_file']
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('admin_rsvp'))

    if not file.filename.lower().endswith('.csv'):
        flash('Please upload a .csv file.', 'error')
        return redirect(url_for('admin_rsvp'))

    try:
        raw = file.stream.read().decode('utf-8-sig')
        stream = StringIO(raw, newline=None)
        reader = csv.DictReader(stream)

        if not reader.fieldnames:
            flash('The CSV file appears to be empty.', 'error')
            return redirect(url_for('admin_rsvp'))

        # Normalise header names: strip whitespace, lowercase
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

        if 'names' not in reader.fieldnames:
            flash('CSV must contain a "names" column.', 'error')
            return redirect(url_for('admin_rsvp'))

        imported = 0
        skipped = 0

        for row in reader:
            row = {k.strip().lower(): (v or '').strip() for k, v in row.items()}
            names = row.get('names', '')
            if not names:
                skipped += 1
                continue

            unique_code = generate_unique_code()
            submission = RSVPSubmission(
                names=names,
                phone=row.get('phone', ''),
                address=row.get('address', ''),
                email=row.get('email', ''),
                unique_code=unique_code,
                rsvp_confirmed=False,
            )
            db.session.add(submission)
            imported += 1

        db.session.commit()

        msg = f'Imported {imported} guest(s) successfully.'
        if skipped:
            msg += f' Skipped {skipped} row(s) with no name.'
        flash(msg, 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error importing CSV: {str(e)}', 'error')

    return redirect(url_for('admin_rsvp'))

@app.route('/admin/rsvp/delete/<int:rsvp_id>', methods=['POST'])
@admin_required
def admin_rsvp_delete(rsvp_id):
    """Delete a single RSVP submission"""
    guest = RSVPSubmission.query.get_or_404(rsvp_id)
    name = guest.names
    db.session.delete(guest)
    db.session.commit()
    flash(f'Guest "{name}" has been removed.', 'success')
    return redirect(url_for('admin_rsvp'))


@app.route('/admin/rsvp/export')
@admin_required
def admin_rsvp_export():
    """Export all RSVP submissions as a CSV file."""
    guests = RSVPSubmission.query.order_by(RSVPSubmission.created_at.asc()).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['names', 'email', 'phone', 'address', 'status', 'submitted'])
    for g in guests:
        writer.writerow([
            g.names,
            g.email or '',
            g.phone or '',
            g.address or '',
            'Confirmed' if g.rsvp_confirmed else 'Pending',
            g.created_at.strftime('%Y-%m-%d %H:%M:%S') if g.created_at else '',
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=rsvp_guests.csv'},
    )

@app.route('/admin/gallery', methods=['GET'])
@admin_required
def admin_gallery():
    """View all submitted photos"""
    submissions = PhotoSubmission.query.order_by(PhotoSubmission.created_at.desc()).all()
    return render_template('admin/gallery.html', submissions=submissions)


@app.route('/admin/gallery/delete/<int:photo_id>', methods=['POST'])
@admin_required
def admin_gallery_delete(photo_id):
    """Delete a photo submission"""
    submission = PhotoSubmission.query.get_or_404(photo_id)
    # Remove file from filesystem
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], submission.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.session.delete(submission)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/admin/gallery/download')
@admin_required
def admin_gallery_download():
    """Download all photos as a zip archive"""
    import zipfile
    submissions = PhotoSubmission.query.all()
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for submission in submissions:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], submission.filename)
            if os.path.exists(filepath):
                zf.write(filepath, submission.filename)
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='wedding_photos.zip'
    )


@app.route('/admin/users', methods=['GET', 'POST'])
@admin_required
def admin_users():
    """Manage admin users"""
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()

            if not email or not password:
                flash('Email and password are required.', 'error')
            elif password != confirm_password:
                flash('Passwords do not match.', 'error')
            elif len(password) < 8:
                flash('Password must be at least 8 characters.', 'error')
            elif AdminUser.query.filter_by(email=email).first():
                flash('An admin with that email already exists.', 'error')
            else:
                new_admin = AdminUser(email=email)
                new_admin.set_password(password)
                db.session.add(new_admin)
                db.session.commit()
                flash(f'Admin user {email} created successfully.', 'success')

        elif action == 'delete':
            user_id = request.form.get('user_id', type=int)
            if user_id == current_user.id:
                flash('You cannot delete your own account.', 'error')
            elif AdminUser.query.count() <= 1:
                flash('Cannot delete the last admin account.', 'error')
            else:
                user = AdminUser.query.get(user_id)
                if user:
                    db.session.delete(user)
                    db.session.commit()
                    flash(f'Admin user {user.email} deleted.', 'success')
                else:
                    flash('User not found.', 'error')

        elif action == 'reset_password':
            user_id = request.form.get('user_id', type=int)
            new_password = request.form.get('new_password', '').strip()
            confirm_new_password = request.form.get('confirm_new_password', '').strip()

            if user_id == current_user.id:
                flash('Use "Change Password" in the sidebar to update your own password.', 'error')
            elif not new_password:
                flash('New password is required.', 'error')
            elif len(new_password) < 8:
                flash('Password must be at least 8 characters.', 'error')
            elif new_password != confirm_new_password:
                flash('Passwords do not match.', 'error')
            else:
                user = AdminUser.query.get(user_id)
                if user:
                    user.set_password(new_password)
                    db.session.commit()
                    flash(f'Password for {user.email} has been reset.', 'success')
                else:
                    flash('User not found.', 'error')

        return redirect(url_for('admin_users'))

    users = AdminUser.query.order_by(AdminUser.created_at).all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/change-password', methods=['POST'])
@admin_required
def admin_change_password():
    """Change the currently logged-in admin's own password"""
    current_password = request.form.get('current_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_new_password = request.form.get('confirm_new_password', '').strip()

    if not current_user.check_password(current_password):
        flash('Current password is incorrect.', 'error')
    elif not new_password:
        flash('New password is required.', 'error')
    elif len(new_password) < 8:
        flash('New password must be at least 8 characters.', 'error')
    elif new_password != confirm_new_password:
        flash('New passwords do not match.', 'error')
    else:
        current_user.set_password(new_password)
        db.session.commit()
        flash('Password changed successfully.', 'success')

    return redirect(request.referrer or url_for('admin_dashboard'))

    users = AdminUser.query.order_by(AdminUser.created_at).all()
    return render_template('admin/users.html', users=users)


if __name__ == '__main__':
    # Development server only - use gunicorn in production.
    # The Werkzeug debugger allows code execution, so it is opt-in and the
    # server listens on localhost unless HOST is set explicitly.
    app.run(
        debug=os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes'),
        host=os.environ.get('HOST', '127.0.0.1'),
        port=int(os.environ.get('PORT', 5000)),
    )
