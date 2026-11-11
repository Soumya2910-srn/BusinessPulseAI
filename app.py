from flask import Flask, redirect, url_for, render_template, flash, session, request, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from form import Login, Signup, ProfileUpdateForm
import pymysql
import os
import json
import random
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
import pandas as pd
from rag_chat import build_vector_store, get_rag_response
from ai_insights import generate_ai_insights
from forecasting import generate_complete_forecast, simulate_forecast_scenario
from flask_mail import Mail, Message
from email_validator import validate_email, EmailNotValidError
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()
app = Flask(__name__)

@app.template_filter('inr_format')
def inr_format(value):
    try:
        value = int(float(value))
        s = str(value)
        if len(s) <= 3:
            return s
        res = s[-3:]
        s = s[:-3]
        while len(s) > 2:
            res = s[-2:] + "," + res
            s = s[:-2]
        res = s + "," + res
        return res
    except (ValueError, TypeError):
        return value

app.config['SECRET_KEY'] = '084c798ae26ad8bb088a191feb8224f772'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Flask-Mail configuration
mail_port = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = mail_port
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'True' if mail_port == 465 else 'False') == 'True'
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True' if mail_port == 587 else 'False') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
mail = Mail(app)

def send_otp_email(to_email, otp, subject='Your OTP for BusinessPulse AI'):
    print(f"[OTP DEBUG] Generated OTP for {to_email}: {otp}")
    username = app.config.get('MAIL_USERNAME')
    password = app.config.get('MAIL_PASSWORD')
    server = app.config.get('MAIL_SERVER', 'smtp.gmail.com')
    port = int(app.config.get('MAIL_PORT', 587))
    
    # 1. Primary: Direct smtplib with explicit SSL context & 15s timeout
    try:
        msg = MIMEMultipart()
        msg['From'] = f"BusinessPulse AI <{username}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        body = f"""Hello,\nYour One-Time Password (OTP) for BusinessPulse AI is: {otp}\n\nThis code expires in 90 seconds. Please enter it to complete verification.\n\nIf you did not request this code, please ignore this email.\n\nBest regards,\nBusinessPulse AI Team"""
        msg.attach(MIMEText(body, 'plain'))
        
        context = ssl.create_default_context()
        with smtplib.SMTP(server, port, timeout=15) as s:
            s.starttls(context=context)
            s.login(username, password)
            s.send_message(msg)
        print(f"[OTP] Successfully sent OTP email to {to_email} via direct SMTP!")
        return True, None
    except Exception as e:
        print(f"[OTP] Direct SMTP attempt failed ({e}), trying Flask-Mail fallback...")
    
    # 2. Fallback: Flask-Mail
    try:
        fmsg = Message(subject, sender=username, recipients=[to_email])
        fmsg.body = f'Your One-Time Password is: {otp}\n\nPlease use this to complete your action. It expires in 90 seconds.'
        mail.send(fmsg)
        return True, None
    except Exception as e2:
        print(f"Error sending email via Flask-Mail fallback: {e2}")
        return False, str(e2)
    
# Database connection setup
# Attempts MySQL database connection; falls back to local SQLite if MySQL server is unavailable
db_created = False
try:
    conn = pymysql.connect(host='localhost', user='root', password='1234', port=3306, connect_timeout=3)
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS businessdb")
    cursor.close()
    conn.close()
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:1234@localhost:3306/businessdb'
    db_created = True
except Exception as e:
    print(f"MySQL connection unavailable ({e}). Using local SQLite database.")
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Models 

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=True, default='')
    role = db.Column(db.String(20), nullable=False, default='user')  # 'user' or 'admin'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Analysis History Model for saving generated visualizations
class AnalysisHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    prev_filename = db.Column(db.String(120), nullable=True)
    curr_filename = db.Column(db.String(120), nullable=True)
    prev_revenue = db.Column(db.Float, default=0.0)
    curr_revenue = db.Column(db.Float, default=0.0)
    revenue_growth = db.Column(db.Float, default=0.0)
    units_growth = db.Column(db.Float, default=0.0)
    customers_growth = db.Column(db.Float, default=0.0)
    forecasted_revenue = db.Column(db.Float, default=0.0)
    analytics_json = db.Column(db.Text, nullable=False)

# Master Admin Email configuration
ADMIN_EMAILS = {'businesspukseaiadmin@gmail.com', 'businesspulseaiadmin@gmail.com'}

def is_admin_email(email_str):
    if not email_str:
        return False
    return email_str.strip().lower() in ADMIN_EMAILS

# Initialize Database and Seed Admin User
def seed_admin_user():
    try:
        master_email = 'businesspukseaiadmin@gmail.com'
        existing = User.query.filter(User.email.ilike(master_email)).first()
        if not existing:
            master_admin = User(
                username='Admin',
                email=master_email,
                password='',
                role='admin'
            )
            db.session.add(master_admin)
            db.session.commit()
            print(f"[INIT] Seeded Master Admin user: {master_email} (Role: admin)")
        elif existing.role != 'admin':
            existing.role = 'admin'
            db.session.commit()
            print(f"[INIT] Elevated {master_email} to admin role.")
    except Exception as e:
        print(f"[INIT] Note on admin seed: {e}")

with app.app_context():
    db.create_all()
    seed_admin_user()

# ─── Decorators ─────────────────────────────────────────────────────────────

def login_required(f):
    """Redirect unauthenticated users to the login page."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return {'status': 'error', 'message': 'Authentication required.'}, 401
            flash('Please login to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Allow only admin users; redirect others with an error."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'error')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

# ─── Helper Functions ────────────────────────────────────────────────────────

def get_user_analytics(user_id):
    """Retrieves analytics from database history or session."""
    if user_id:
        latest = AnalysisHistory.query.filter_by(user_id=user_id).order_by(AnalysisHistory.created_at.desc()).first()
        if latest:
            try:
                return json.loads(latest.analytics_json)
            except Exception as e:
                print(f"Error parsing analytics_json: {e}")
    return session.get('analytics')

# Auth Routes 

def get_post_auth_redirect():
    """Direct admins to the Admin Panel and standard users to the main Dashboard."""
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user and user.role == 'admin':
            return redirect(url_for('admin_panel'))
        return redirect(url_for('dashboard'))
    return None

@app.route('/')
def landingpage():
    auth_redirect = get_post_auth_redirect()
    if auth_redirect:
        return auth_redirect
    return render_template("landingpage.html")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    auth_redirect = get_post_auth_redirect()
    if auth_redirect:
        return auth_redirect
    form = Signup()
    if form.validate_on_submit():
        raw_email = form.email.data.strip()
        try:
            valid_info = validate_email(raw_email, check_deliverability=False)
            email = valid_info.normalized
        except EmailNotValidError:
            flash('Please enter a valid email format.', 'error')
            return render_template('signup.html', form=form)
        except Exception:
            email = raw_email.lower()

        existing_username = User.query.filter_by(username=form.username.data.strip()).first()
        if existing_username:
            flash('Username already exists. Please choose a different username.', 'error')
            return render_template('signup.html', form=form)

        existing_email = User.query.filter(User.email.ilike(email)).first()
        if existing_email:
            flash('An account with this email already exists. Please sign in directly.', 'error')
            return render_template('signup.html', form=form)

        # Generate OTP
        otp = str(random.randint(100000, 999999))
        session['otp'] = otp
        session['otp_time'] = datetime.utcnow().timestamp()
        session['signup_data'] = {
            'username': form.username.data.strip(),
            'email': email
        }
        session.pop('login_data', None)
        session.pop('login_email', None)

        subject = 'Verify your BusinessPulse AI Account'
        if is_admin_email(email):
            subject = 'Verify your BusinessPulse AI Administrator Account'

        sent, err_msg = send_otp_email(email, otp, subject=subject)
        if sent:
            flash(f'An OTP has been sent to {email}. Please verify to complete account setup.', 'success')
        else:
            flash(f'An OTP has been generated for {email}. (Dev mode: OTP is {otp} — check your server console).', 'info')
        return redirect(url_for('verify_otp'))

    # Flash form errors if any
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"{error}", 'error')

    return render_template("signup.html", form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    auth_redirect = get_post_auth_redirect()
    if auth_redirect:
        return auth_redirect
    form = Login()
    if form.validate_on_submit():
        raw_email = form.email.data.strip()
        try:
            valid_info = validate_email(raw_email, check_deliverability=False)
            email = valid_info.normalized
        except EmailNotValidError:
            flash('Please enter a valid email format.', 'error')
            return render_template('login.html', form=form)
        except Exception:
            email = raw_email.lower()

        user = User.query.filter(User.email.ilike(email)).first()
        # If the master admin email is entered and not yet registered in database, auto-provision
        if not user and is_admin_email(email):
            base_un = 'Admin'
            if User.query.filter_by(username=base_un).first():
                base_un = f"Admin_{random.randint(100, 999)}"
            user = User(
                username=base_un,
                email=email.lower(),
                password='',
                role='admin'
            )
            db.session.add(user)
            db.session.commit()
            print(f"[AUTH] Auto-created master admin account for {email}")

        if user:
            # Enforce admin role if this is an admin email
            if is_admin_email(user.email) and user.role != 'admin':
                user.role = 'admin'
                db.session.commit()

            # Generate OTP
            otp = str(random.randint(100000, 999999))
            session['otp'] = otp
            session['otp_time'] = datetime.utcnow().timestamp()
            session['login_data'] = {
                'user_id': user.id,
                'username': user.username,
                'role': user.role
            }
            session['login_email'] = user.email
            session.pop('signup_data', None)

            subject = 'Your BusinessPulse AI Admin Login OTP' if user.role == 'admin' else 'Your BusinessPulse AI Login OTP'
            sent, err_msg = send_otp_email(user.email, otp, subject=subject)
            if sent:
                flash(f'Login OTP has been sent to {user.email}.', 'success')
            else:
                flash(f'Login OTP generated for {user.email}. (Dev mode: OTP is {otp} — check your server console).', 'info')
            return redirect(url_for('verify_otp'))
        else:
            flash('Account not found. Please enter a valid registered email account or create an account.', 'error')

    # Flash form errors if any
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"{error}", 'error')

    return render_template("login.html", form=form)

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    auth_redirect = get_post_auth_redirect()
    if auth_redirect:
        return auth_redirect

    if request.method == 'GET':
        if 'otp' not in session and 'signup_data' not in session and 'login_data' not in session:
            return redirect(url_for('login'))

    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()

        # Check if OTP expired (90 seconds)
        otp_time = session.get('otp_time', 0)
        if datetime.utcnow().timestamp() - otp_time > 90:
            flash('OTP has expired. Please try again.', 'error')
            is_signup = 'signup_data' in session
            session.pop('otp', None)
            session.pop('otp_time', None)
            session.pop('signup_data', None)
            session.pop('login_data', None)
            session.pop('login_email', None)
            return redirect(url_for('signup' if is_signup else 'login'))

        if 'otp' in session and session['otp'] == entered_otp:
            # Signup flow: create account and direct login
            if 'signup_data' in session:
                data = session.pop('signup_data')
                is_admin = is_admin_email(data['email']) or (User.query.count() == 0)
                new_user = User(
                    username=data['username'],
                    email=data['email'],
                    password='',
                    role='admin' if is_admin else 'user'
                )
                db.session.add(new_user)
                db.session.commit()
                session.pop('otp', None)
                session.pop('otp_time', None)
                session.pop('login_data', None)
                session.pop('login_email', None)

                # Direct login on account creation
                session['user_id'] = new_user.id
                session['username'] = new_user.username
                session['role'] = new_user.role

                if new_user.role == 'admin':
                    flash(f'Welcome, Administrator {new_user.username}! Navigated to the Admin Dashboard.', 'success')
                    return redirect(url_for('admin_panel'))
                flash(f'Welcome to BusinessPulse AI, {new_user.username}!', 'success')
                return redirect(url_for('dashboard'))

            # Login flow
            elif 'login_data' in session:
                data = session.pop('login_data')
                user = User.query.get(data['user_id'])
                if user:
                    if is_admin_email(user.email) and user.role != 'admin':
                        user.role = 'admin'
                        db.session.commit()
                    session['user_id'] = user.id
                    session['username'] = user.username
                    session['role'] = user.role
                    session.pop('otp', None)
                    session.pop('otp_time', None)
                    session.pop('login_email', None)

                    if user.role == 'admin':
                        flash(f'Welcome to Admin Dashboard, Administrator {user.username}!', 'success')
                        return redirect(url_for('admin_panel'))
                    flash(f'Welcome back, {user.username}!', 'success')
                    return redirect(url_for('dashboard'))
        else:
            flash('Invalid OTP. Please check the 6-digit code and try again.', 'error')

    return render_template('verify_otp.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    flash('BusinessPulse AI uses passwordless OTP authentication. Enter your email to log in directly.', 'info')
    return redirect(url_for('login'))

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    flash('BusinessPulse AI uses passwordless OTP authentication. Enter your email to log in directly.', 'info')
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('analytics', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('landingpage'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    profile_form = ProfileUpdateForm(obj=user)

    analysis_count = AnalysisHistory.query.filter_by(user_id=user_id).count()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_profile' and profile_form.validate_on_submit():
            new_username = profile_form.username.data
            existing = User.query.filter(User.username == new_username, User.id != user_id).first()
            if existing:
                flash('That username is already taken.', 'error')
            else:
                user.username = new_username
                db.session.commit()
                session['username'] = new_username
                flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile'))

        # Flash validation errors
        for field, errors in profile_form.errors.items():
            for error in errors:
                flash(f"{error}", 'error')

    return render_template('profile.html', user=user, profile_form=profile_form,
                           analysis_count=analysis_count)

# Admin Routes 

@app.route('/admin')
@admin_required
def admin_panel():
    current_user = User.query.get(session['user_id'])
    all_users = User.query.order_by(User.created_at.asc()).all()
    user_stats = {}
    for u in all_users:
        user_stats[u.id] = AnalysisHistory.query.filter_by(user_id=u.id).count()
    
    total_analyses = AnalysisHistory.query.count()
    all_records = AnalysisHistory.query.order_by(AnalysisHistory.created_at.desc()).all()
    
    # Platform totals
    total_revenue_sum = sum(a.curr_revenue or 0.0 for a in all_records)
    total_forecast_sum = sum(a.forecasted_revenue or 0.0 for a in all_records)
    
    user_map = {u.id: u for u in all_users}
    analyses_display = []
    for a in all_records[:50]:
        analyses_display.append({
            'record': a,
            'user': user_map.get(a.user_id)
        })

    system_info = {
        'db_engine': 'MySQL' if 'mysql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite (Embedded)',
        'mail_server': app.config.get('MAIL_SERVER', 'smtp.gmail.com'),
        'mail_port': app.config.get('MAIL_PORT', 587),
        'mail_user': app.config.get('MAIL_USERNAME') or 'smtp.gmail.com',
        'master_admin': 'businesspukseaiadmin@gmail.com',
        'gemini_configured': bool(os.environ.get('GEMINI_API_KEY'))
    }

    return render_template('admin.html',
                           users=all_users,
                           user_stats=user_stats,
                           current_user=current_user,
                           total_analyses=total_analyses,
                           total_revenue_sum=total_revenue_sum,
                           total_forecast_sum=total_forecast_sum,
                           analyses_display=analyses_display,
                           system_info=system_info,
                           is_admin_email=is_admin_email)

@app.route('/admin/toggle_role/<int:user_id>', methods=['POST'])
@admin_required
def toggle_role(user_id):
    user = User.query.get_or_404(user_id)
    # Prevent admin from demoting themselves
    if user.id == session['user_id']:
        return {'status': 'error', 'message': 'You cannot change your own role.'}, 400
    if is_admin_email(user.email):
        return {'status': 'error', 'message': 'The Master Admin account role is protected and cannot be demoted.'}, 400
    user.role = 'user' if user.role == 'admin' else 'admin'
    db.session.commit()
    return {'status': 'success', 'new_role': user.role, 'message': f'Role updated to {user.role}.'}, 200

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if user_id == session['user_id']:
        return {'status': 'error', 'message': 'You cannot delete your own account.'}, 400
    user = User.query.get_or_404(user_id)
    if is_admin_email(user.email):
        return {'status': 'error', 'message': 'The Master Admin account is protected and cannot be deleted.'}, 400
    # Delete user's history records too
    AnalysisHistory.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    return {'status': 'success', 'message': f'User {user.username} deleted successfully.'}, 200

@app.route('/admin/export_users_csv')
@admin_required
def admin_export_users_csv():
    import io, csv
    from flask import Response
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['User ID', 'Username', 'Email', 'Role', 'Total Analyses Run', 'Registration Date'])
    all_users = User.query.order_by(User.id.asc()).all()
    for u in all_users:
        count = AnalysisHistory.query.filter_by(user_id=u.id).count()
        writer.writerow([
            u.id,
            u.username,
            u.email,
            u.role,
            count,
            u.created_at.strftime('%Y-%m-%d %H:%M:%S') if u.created_at else 'N/A'
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=BusinessPulse_Admin_Users_Audit.csv'}
    )

@app.route('/admin/export_analyses_csv')
@admin_required
def admin_export_analyses_csv():
    import io, csv
    from flask import Response
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Analysis ID', 'User ID', 'Username', 'User Email', 'Previous Dataset File', 'Current Dataset File', 'Previous Revenue (INR)', 'Current Revenue (INR)', 'Revenue Growth (%)', 'Forecasted Revenue (INR)', 'Created At'])
    records = AnalysisHistory.query.order_by(AnalysisHistory.created_at.desc()).all()
    user_map = {u.id: u for u in User.query.all()}
    for r in records:
        u = user_map.get(r.user_id)
        writer.writerow([
            r.id,
            r.user_id,
            u.username if u else 'Deleted User',
            u.email if u else 'N/A',
            r.prev_filename or 'N/A',
            r.curr_filename or 'N/A',
            r.prev_revenue,
            r.curr_revenue,
            r.revenue_growth,
            r.forecasted_revenue,
            r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else 'N/A'
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=BusinessPulse_System_Analyses_Log.csv'}
    )

# ─── Core App Routes ─────────────────────────────────────────────────────────

REQUIRED_COLUMNS = {'Date', 'Product_Category', 'Units_Sold', 'Unit_Price', 'Revenue', 'Marketing_Spend', 'New_Customers'}

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    history_list = AnalysisHistory.query.filter_by(user_id=user_id).order_by(AnalysisHistory.created_at.desc()).all()
    return render_template("dashboard.html", user=user, history_list=history_list)

@app.route('/upload_datasets', methods=['POST'])
def upload_datasets():
    if 'user_id' not in session:
        return {'status': 'error', 'message': 'Unauthorized. Please login.'}, 401
    
    if 'prev_month_file' not in request.files or 'curr_month_file' not in request.files:
        return {'status': 'error', 'message': 'Both Previous Month and Current Month files are required.'}, 400

    prev_file = request.files['prev_month_file']
    curr_file = request.files['curr_month_file']

    if not prev_file.filename or not curr_file.filename:
        return {'status': 'error', 'message': 'No selected file found for one or both datasets.'}, 400

    from train_model import train_model, clean_and_process_dataframe
    ml_models = train_model()

    def process_and_clean_file(file_obj, label):
        file_obj.seek(0)
        try:
            filename = file_obj.filename.lower()
            if filename.endswith('.csv'):
                df = pd.read_csv(file_obj)
            elif filename.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file_obj)
            else:
                return None, f"Unsupported file format for {label}."
        except Exception as e:
            return None, f"Error reading {label}: {str(e)}"
            
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            return None, f"{label} is missing required column(s): {', '.join(missing)}"
            
        df = clean_and_process_dataframe(df)
        return df, "Valid"

    df_prev, msg_prev = process_and_clean_file(prev_file, "Previous Month Dataset")
    if df_prev is None:
        return {'status': 'error', 'message': msg_prev}, 400

    df_curr, msg_curr = process_and_clean_file(curr_file, "Current Month Dataset")
    if df_curr is None:
        return {'status': 'error', 'message': msg_curr}, 400

    def process_metrics(df):
        revenue = round(float(df['Revenue'].sum()), 2)
        units = int(df['Units_Sold'].sum())
        marketing = round(float(df['Marketing_Spend'].sum()), 2)
        customers = int(df['New_Customers'].sum())
        profit = round(revenue - marketing, 2)
        
        category_stats = {}
        for cat, group in df.groupby('Product_Category'):
            rev = round(float(group['Revenue'].sum()), 2)
            u = int(group['Units_Sold'].sum())
            mkt = round(float(group['Marketing_Spend'].sum()), 2)
            prof = round(rev - mkt, 2)
            avg_p = round(rev / u, 2) if u > 0 else 0.0
            category_stats[str(cat)] = {
                'revenue': rev, 'units': u, 'profit': prof, 'avg_price': avg_p
            }

        return {
            'revenue': revenue, 'units': units, 'marketing': marketing,
            'customers': customers, 'profit': profit,
            'category_stats': category_stats,
            'category_revenue': {k: v['revenue'] for k, v in category_stats.items()}
        }

    prev_metrics = process_metrics(df_prev)
    curr_metrics = process_metrics(df_curr)

    # 1. Run AI Insights Engine (Section 7)
    try:
        insights_data = generate_ai_insights(df_curr, df_prev)
    except Exception as e:
        print(f"Error generating AI insights: {e}")
        insights_data = {}

    # 2. Run Comprehensive Forecasting Engine (Section 8)
    try:
        forecasting_data = generate_complete_forecast(df_curr, df_prev)
        forecasted_rev = forecasting_data['sales_forecast']['next_month_forecast']
    except Exception as e:
        print(f"Error generating forecasts: {e}")
        forecasted_rev = round(ml_models['model_rev'].predict(curr_metrics['marketing'] * 1.1), 2) if ml_models else 0.0
        forecasting_data = {
            'sales_forecast': {'next_month_forecast': forecasted_rev},
            'demand_forecast': {},
            'inventory_forecast': {}
        }

    # Categories list for comparison chart
    all_categories = sorted(list(set(prev_metrics['category_stats'].keys()).union(curr_metrics['category_stats'].keys())))
    prev_cat_data = [prev_metrics['category_stats'].get(cat, {}).get('revenue', 0) for cat in all_categories]
    curr_cat_data = [curr_metrics['category_stats'].get(cat, {}).get('revenue', 0) for cat in all_categories]
    
    prev_cat_profit = [prev_metrics['category_stats'].get(cat, {}).get('profit', 0) for cat in all_categories]
    curr_cat_profit = [curr_metrics['category_stats'].get(cat, {}).get('profit', 0) for cat in all_categories]

    curr_cat_units = [curr_metrics['category_stats'].get(cat, {}).get('units', 0) for cat in all_categories]

    # Live Market Price Integration
    def fetch_live_prices(categories):
        from rag_chat import get_gemini_api_key
        api_key = get_gemini_api_key()
        if not api_key:
            return {}
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import StrOutputParser
            import re
            
            llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=api_key, temperature=0.1)
            prompt = ChatPromptTemplate.from_template(
                "Estimate the current live market price in Indian Rupees (INR) for these items: {categories}. "
                "Return ONLY a valid JSON object. Keys are item names, values are numbers (floats). Do not include any text, markdown, or backticks outside the JSON. Example: {{\"Gold\": 65000.0}}"
            )
            chain = prompt | llm | StrOutputParser()
            response = chain.invoke({"categories": ", ".join(categories)})
            
            cleaned = re.sub(r'```(?:json)?|`', '', response).strip()
            return json.loads(cleaned)
        except Exception as e:
            print("Failed to fetch live prices:", e)
            return {}
            
    live_prices = fetch_live_prices(all_categories)
    
    for cat in all_categories:
        hist_avg = curr_metrics['category_stats'][cat]['avg_price']
        avg_units = curr_metrics['category_stats'][cat]['units']
        
        live_price = live_prices.get(cat, hist_avg)
        try:
            live_price = float(live_price)
        except:
            live_price = hist_avg
            
        proj_rev = round(live_price * avg_units, 2)
        curr_metrics['category_stats'][cat]['live_price'] = round(live_price, 2)
        curr_metrics['category_stats'][cat]['projected_revenue'] = proj_rev

    # Monthly Trends
    combined_df = pd.concat([df_prev, df_curr])
    if 'Date' in combined_df.columns:
        combined_df['Month'] = combined_df['Date'].dt.strftime('%b %Y')
        trend_group = combined_df.groupby('Month').agg({'Revenue': 'sum', 'Marketing_Spend': 'sum', 'New_Customers': 'sum', 'Date': 'first'}).sort_values('Date')
        trend_months = trend_group.index.tolist()
        trend_revenue = [round(float(x), 2) for x in trend_group['Revenue']]
        trend_profit = [round(float(r - m), 2) for r, m in zip(trend_group['Revenue'], trend_group['Marketing_Spend'])]
        trend_customers = [int(x) for x in trend_group['New_Customers']]
    else:
        trend_months, trend_revenue, trend_profit, trend_customers = [], [], [], []

    analytics_data = {
        'summary': {
            'prev_revenue': prev_metrics['revenue'],
            'curr_revenue': curr_metrics['revenue'],
            'revenue_growth': round(((curr_metrics['revenue'] - prev_metrics['revenue']) / prev_metrics['revenue'] * 100) if prev_metrics['revenue'] else 0, 1),
            'prev_profit': prev_metrics['profit'],
            'curr_profit': curr_metrics['profit'],
            'profit_growth': round(((curr_metrics['profit'] - prev_metrics['profit']) / prev_metrics['profit'] * 100) if prev_metrics['profit'] else 0, 1),
            'prev_units': prev_metrics['units'],
            'curr_units': curr_metrics['units'],
            'units_growth': round(((curr_metrics['units'] - prev_metrics['units']) / prev_metrics['units'] * 100) if prev_metrics['units'] else 0, 1),
            'prev_customers': prev_metrics['customers'],
            'curr_customers': curr_metrics['customers'],
            'customers_growth': round(((curr_metrics['customers'] - prev_metrics['customers']) / prev_metrics['customers'] * 100) if prev_metrics['customers'] else 0, 1),
            'prev_marketing': prev_metrics['marketing'],
            'curr_marketing': curr_metrics['marketing'],
            'forecasted_revenue': forecasted_rev
        },
        'charts': {
            'categories': all_categories,
            'prev_cat_data': prev_cat_data,
            'curr_cat_data': curr_cat_data,
            'prev_cat_profit': prev_cat_profit,
            'curr_cat_profit': curr_cat_profit,
            'curr_cat_units': curr_cat_units,
            'trend_months': trend_months,
            'trend_revenue': trend_revenue,
            'trend_profit': trend_profit,
            'trend_customers': trend_customers
        },
        'category_stats': curr_metrics['category_stats'],
        'insights': insights_data,
        'forecasting': forecasting_data
    }
    # Save uploaded files for RAG vector indexing
    prev_filename = f"user_{session['user_id']}_prev_{prev_file.filename}"
    curr_filename = f"user_{session['user_id']}_curr_{curr_file.filename}"
    prev_path = os.path.join(app.config['UPLOAD_FOLDER'], prev_filename)
    curr_path = os.path.join(app.config['UPLOAD_FOLDER'], curr_filename)
    
    df_prev.to_csv(prev_path, index=False)
    df_curr.to_csv(curr_path, index=False)

    # Build RAG Vector Store with FAISS
    try:
        build_vector_store(session['user_id'], prev_path, curr_path)
    except Exception as e:
        print(f"Error building vector store: {e}")

    # Save to AnalysisHistory Database
    try:
        new_history = AnalysisHistory(
            user_id=session.get('user_id'),
            prev_filename=prev_file.filename,
            curr_filename=curr_file.filename,
            prev_revenue=prev_metrics['revenue'],
            curr_revenue=curr_metrics['revenue'],
            revenue_growth=analytics_data['summary']['revenue_growth'],
            units_growth=analytics_data['summary']['units_growth'],
            customers_growth=analytics_data['summary']['customers_growth'],
            forecasted_revenue=forecasted_rev,
            analytics_json=json.dumps(analytics_data)
        )
        db.session.add(new_history)
        db.session.commit()
        session['latest_analysis_id'] = new_history.id
        session.pop('analytics', None)
    except Exception as e:
        print(f"Error saving analysis history: {e}")
        # Keep in session as emergency fallback if DB commit fails
        session['analytics'] = analytics_data

    return {
        'status': 'success',
        'message': 'Datasets uploaded, AI insights synthesized, and multi-period forecasts generated!',
        'redirect_url': url_for('visualizations_page'),
        'analytics': analytics_data
    }, 200

@app.route('/chat')
@login_required
def chat_page():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    analytics = get_user_analytics(user_id)
    return render_template("chat.html", user=user, analytics=analytics)

@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'user_id' not in session:
        return {'status': 'error', 'message': 'Unauthorized'}, 401
    
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    if not message:
        return {'status': 'error', 'message': 'Empty message'}, 400

    user_id = session.get('user_id')
    analytics = get_user_analytics(user_id)
            
    summary = analytics.get('summary', {}) if analytics else {}
    insights = analytics.get('insights', {}) if analytics else {}
    forecasting = analytics.get('forecasting', {}) if analytics else {}

    # Call RAG Chatbot with enhanced context
    try:
        reply = get_rag_response(user_id, message, ml_summary=summary, insights=insights, forecasting=forecasting)
        return {'status': 'success', 'response': reply}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500

@app.route('/api/analysis', methods=['GET'])
@app.route('/api/analysis/<int:analysis_id>', methods=['GET'])
def api_get_analysis(analysis_id=None):
    user_id = session.get('user_id')
    if not user_id:
        return {'status': 'error', 'message': 'Authentication required. Please log in.'}, 401

    if analysis_id:
        record = AnalysisHistory.query.filter_by(id=analysis_id, user_id=user_id).first()
        if not record:
            return {'status': 'error', 'message': 'Analysis record not found'}, 404
        return {
            'status': 'success',
            'analysis': {
                'id': record.id,
                'created_at': record.created_at.isoformat() if record.created_at else None,
                'prev_filename': record.prev_filename,
                'curr_filename': record.curr_filename,
                'summary': {
                    'curr_revenue': record.curr_revenue,
                    'prev_revenue': record.prev_revenue,
                    'revenue_growth': record.revenue_growth,
                    'units_growth': record.units_growth,
                    'customers_growth': record.customers_growth,
                    'forecasted_revenue': record.forecasted_revenue
                }
            }
        }, 200

    records = AnalysisHistory.query.filter_by(user_id=user_id).order_by(AnalysisHistory.created_at.desc()).all()
    analyses = []
    for r in records:
        analyses.append({
            'id': r.id,
            'created_at': r.created_at.isoformat() if r.created_at else None,
            'prev_filename': r.prev_filename,
            'curr_filename': r.curr_filename,
            'summary': {
                'curr_revenue': r.curr_revenue,
                'prev_revenue': r.prev_revenue,
                'revenue_growth': r.revenue_growth,
                'units_growth': r.units_growth,
                'customers_growth': r.customers_growth,
                'forecasted_revenue': r.forecasted_revenue
            }
        })

    return {'status': 'success', 'analyses': analyses}, 200
        
@app.route('/visualizations')
@login_required
def visualizations_page():
    # Check if a specific history ID was requested
    history_id = request.args.get('history_id')
    user_id = session.get('user_id')
    current_user = User.query.get(user_id)
    selected_record = None

    if history_id:
        if current_user and current_user.role == 'admin':
            record = AnalysisHistory.query.filter_by(id=history_id).first()
        else:
            record = AnalysisHistory.query.filter_by(id=history_id, user_id=user_id).first()

        if record:
            analytics = json.loads(record.analytics_json)
            selected_record = record
        else:
            analytics = get_user_analytics(user_id)
    else:
        analytics = get_user_analytics(user_id)

    if not analytics:
        flash('No dataset found. Please upload your datasets on the dashboard to view visualizations.', 'info')
        return redirect(url_for('dashboard'))

    # Fetch user's saved history list
    history_list = AnalysisHistory.query.filter_by(user_id=user_id).order_by(AnalysisHistory.created_at.desc()).all()
    if not selected_record and history_list:
        selected_record = history_list[0]
    
    return render_template("visualizations.html", analytics=analytics, history_list=history_list, selected_record=selected_record, user=current_user)

# ─── Task 7: AI Insights Engine API Endpoints ────────────────────────────────

@app.route('/api/insights', methods=['GET'])
@login_required
def api_get_insights():
    """
    Returns structured AI insights for the current or latest session:
    Executive Summary, Revenue Trends, Growth Opportunities, Low Performing Products,
    Customer Insights, Risk Analysis, and Smart Recommendations.
    """
    user_id = session.get('user_id')
    analytics = get_user_analytics(user_id)

    if not analytics or 'insights' not in analytics:
        return {'status': 'error', 'message': 'No dataset uploaded yet. Please upload your datasets on the dashboard.'}, 404

    insights = analytics.get('insights', {})
    return {
        'status': 'success',
        'engine': insights.get('engine', 'statistical_heuristic_engine'),
        'insights': insights
    }, 200

@app.route('/api/insights/generate', methods=['POST'])
@login_required
def api_generate_insights():
    """
    Forces regeneration of AI insights on-demand for the current user's datasets.
    """
    user_id = session.get('user_id')
    
    upload_dir = app.config['UPLOAD_FOLDER']
    curr_files = [f for f in os.listdir(upload_dir) if f.startswith(f"user_{user_id}_curr_")]
    prev_files = [f for f in os.listdir(upload_dir) if f.startswith(f"user_{user_id}_prev_")]

    if not curr_files:
        return {'status': 'error', 'message': 'No uploaded datasets found. Please upload datasets on the dashboard first.'}, 400

    curr_path = os.path.join(upload_dir, curr_files[-1])
    prev_path = os.path.join(upload_dir, prev_files[-1]) if prev_files else None
    df_curr = pd.read_csv(curr_path)
    df_prev = pd.read_csv(prev_path) if prev_path and os.path.exists(prev_path) else None

    try:
        new_insights = generate_ai_insights(df_curr, df_prev)
        latest = AnalysisHistory.query.filter_by(user_id=user_id).order_by(AnalysisHistory.created_at.desc()).first()
        if latest:
            data = json.loads(latest.analytics_json)
            data['insights'] = new_insights
            latest.analytics_json = json.dumps(data)
            db.session.commit()

        return {
            'status': 'success',
            'message': 'AI insights successfully regenerated.',
            'insights': new_insights
        }, 200
    except Exception as e:
        return {'status': 'error', 'message': f"Failed to regenerate insights: {str(e)}"}, 500

# ─── Task 8: Forecasting API Endpoints ───────────────────────────────────────

@app.route('/api/forecast', methods=['GET'])
@login_required
def api_get_forecast():
    """
    Returns full multi-period forecasting data:
    1. Sales & Revenue Forecast (multi-month, bounds, marketing elasticity)
    2. Demand Forecast (category unit velocity, growth trajectory, demand share)
    3. Inventory Forecast (daily run rates, safety stock, ROP, stockout alerts, restock quantities)
    """
    user_id = session.get('user_id')
    analytics = get_user_analytics(user_id)

    if not analytics or 'forecasting' not in analytics:
        return {'status': 'error', 'message': 'No dataset uploaded yet. Please upload your datasets on the dashboard.'}, 404

    forecasting = analytics.get('forecasting', {})
    return {
        'status': 'success',
        'sales_forecast': forecasting.get('sales_forecast', {}),
        'demand_forecast': forecasting.get('demand_forecast', {}),
        'inventory_forecast': forecasting.get('inventory_forecast', {})
    }, 200

@app.route('/api/forecast/simulate', methods=['POST'])
@login_required
def api_simulate_forecast():
    """
    What-if simulation engine. Accepts custom parameters:
    - marketing_budget (float): Revised marketing spend
    - lead_time_days (int): Revised supplier lead time
    - growth_adjustment_pct (float): Target growth adjustment
    Recalculates sales, demand, and inventory replenishment requirements dynamically.
    """
    user_id = session.get('user_id')
    data = request.get_json() or {}

    marketing_budget = data.get('marketing_budget')
    if marketing_budget is not None:
        try:
            marketing_budget = float(marketing_budget)
        except ValueError:
            marketing_budget = None

    lead_time_days = data.get('lead_time_days', 10)
    try:
        lead_time_days = int(lead_time_days)
    except ValueError:
        lead_time_days = 10

    growth_adjustment = data.get('growth_adjustment_pct', 0.0)
    try:
        growth_adjustment = float(growth_adjustment)
    except ValueError:
        growth_adjustment = 0.0

    upload_dir = app.config['UPLOAD_FOLDER']
    curr_files = [f for f in os.listdir(upload_dir) if f.startswith(f"user_{user_id}_curr_")]
    prev_files = [f for f in os.listdir(upload_dir) if f.startswith(f"user_{user_id}_prev_")]

    if not curr_files:
        return {'status': 'error', 'message': 'No uploaded datasets found. Please upload datasets on the dashboard first to run simulations.'}, 400

    curr_path = os.path.join(upload_dir, curr_files[-1])
    prev_path = os.path.join(upload_dir, prev_files[-1]) if prev_files else None
    df_curr = pd.read_csv(curr_path)
    df_prev = pd.read_csv(prev_path) if prev_path and os.path.exists(prev_path) else None

    try:
        sim_results = simulate_forecast_scenario(
            df_curr,
            df_prev=df_prev,
            marketing_budget=marketing_budget,
            lead_time_days=lead_time_days,
            growth_adjustment_pct=growth_adjustment
        )
        return {
            'status': 'success',
            'simulation_parameters': {
                'marketing_budget': marketing_budget,
                'lead_time_days': lead_time_days,
                'growth_adjustment_pct': growth_adjustment
            },
            'simulation': sim_results
        }, 200
    except Exception as e:
        return {'status': 'error', 'message': f"Simulation error: {str(e)}"}, 500

@app.route('/api/inventory/forecast', methods=['GET'])
@login_required
def api_inventory_forecast():
    """
    Specialized endpoint returning inventory metrics:
    Stockout risk status, days of stock remaining, safety stock, reorder point,
    and recommended batch replenishment order details per SKU category.
    """
    user_id = session.get('user_id')
    analytics = get_user_analytics(user_id)

    if not analytics or 'forecasting' not in analytics:
        return {'status': 'error', 'message': 'No dataset uploaded yet. Please upload your datasets on the dashboard.'}, 404

    inv_forecast = analytics.get('forecasting', {}).get('inventory_forecast', {})
    return {
        'status': 'success',
        'inventory_forecast': inv_forecast
    }, 200

# ─── Report Export & Anomaly / Stockout Notification Endpoints ───────────────

@app.route('/api/export/csv')
@login_required
def api_export_csv():
    """Generates and downloads a structured executive business summary CSV."""
    import io, csv
    from flask import Response
    user_id = session.get('user_id')
    analytics = get_user_analytics(user_id)
    if not analytics:
        flash('No analytics data available to export.', 'error')
        return redirect(url_for('dashboard'))

    output = io.StringIO()
    writer = csv.writer(output)

    # 1. Executive Summary
    writer.writerow(['BUSINESS PULSE AI - EXECUTIVE SUMMARY & ANALYTICS REPORT'])
    writer.writerow([])
    summary = analytics.get('summary', {})
    writer.writerow(['EXECUTIVE KPI SUMMARY'])
    writer.writerow(['Metric', 'Previous Month', 'Current Month', 'Growth / Momentum'])
    writer.writerow(['Total Revenue (INR)', summary.get('prev_revenue', 0), summary.get('curr_revenue', 0), f"{summary.get('revenue_growth', 0)}%"])
    writer.writerow(['Units Sold', summary.get('prev_units', 0), summary.get('curr_units', 0), f"{summary.get('units_growth', 0)}%"])
    writer.writerow(['New Customers', summary.get('prev_customers', 0), summary.get('curr_customers', 0), f"{summary.get('customers_growth', 0)}%"])
    writer.writerow(['Marketing Spend (INR)', summary.get('prev_marketing', 0), summary.get('curr_marketing', 0), ''])
    writer.writerow(['ML Projected Revenue Growth', '', '', f"{summary.get('ml_projected_growth', 0)}%"])
    writer.writerow([])

    # 2. Category Performance
    writer.writerow(['PRODUCT CATEGORY PERFORMANCE BREAKDOWN'])
    writer.writerow(['Category', 'Revenue (INR)', 'Units Sold', 'Average Unit Price (INR)', 'Estimated Profit (INR)'])
    curr_cats = analytics.get('current_month', {}).get('category_stats', {})
    for cat, stats in curr_cats.items():
        writer.writerow([cat, stats.get('revenue', 0), stats.get('units', 0), stats.get('avg_price', 0), stats.get('profit', 0)])
    writer.writerow([])

    # 3. Revenue Forecast Projections
    writer.writerow(['REVENUE FORECAST PROJECTIONS'])
    writer.writerow(['Forecast Horizon', 'Conservative (INR)', 'Expected (INR)', 'Optimistic (INR)'])
    rev_fc = analytics.get('forecasting', {}).get('revenue_forecast', {})
    for h, vals in rev_fc.items():
        writer.writerow([f"{h} Days", vals.get('conservative', 0), vals.get('expected', 0), vals.get('optimistic', 0)])
    writer.writerow([])

    # 4. Inventory Health & Optimization
    writer.writerow(['INVENTORY OPTIMIZATION & STOCK HEALTH'])
    writer.writerow(['Category', 'Daily Velocity (Units/Day)', 'Days of Stock Remaining', 'Stockout Risk Status', 'Safety Stock', 'Reorder Point (ROP)', 'Recommended Reorder Quantity', 'Restock Capital Required (INR)'])
    inv_fc = analytics.get('forecasting', {}).get('inventory_forecast', {})
    for cat, item in inv_fc.items():
        writer.writerow([
            cat,
            item.get('daily_run_rate', 0),
            item.get('days_of_stock_remaining', 0),
            item.get('stockout_risk_status', 'Unknown'),
            item.get('safety_stock', 0),
            item.get('reorder_point', 0),
            item.get('recommended_reorder_qty', 0),
            item.get('restock_capital_required', 0)
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=BusinessPulse_Analytics_Summary.csv'}
    )

@app.route('/analysis/<int:history_id>/export_pdf')
@app.route('/analysis/latest/export_pdf', defaults={'history_id': None})
@app.route('/export_pdf', defaults={'history_id': None})
@login_required
def export_analysis_pdf(history_id):
    """
    Exports a comprehensive, professional executive PDF report for a particular analysis run.
    Validates ownership or admin privileges before streaming the PDF.
    """
    user_id = session.get('user_id')
    current_user = User.query.get(user_id)
    
    if history_id is None:
        history_id = request.args.get('history_id', type=int)

    if history_id:
        if current_user and current_user.role == 'admin':
            record = AnalysisHistory.query.filter_by(id=history_id).first()
        else:
            record = AnalysisHistory.query.filter_by(id=history_id, user_id=user_id).first()
    else:
        record = AnalysisHistory.query.filter_by(user_id=user_id).order_by(AnalysisHistory.created_at.desc()).first()

    if not record:
        flash('Selected analysis record not found or access denied.', 'error')
        return redirect(url_for('visualizations_page'))

    # Load owner user for report branding
    owner_user = User.query.get(record.user_id) if record.user_id else current_user

    try:
        from pdf_report_generator import generate_analysis_pdf_bytes
        pdf_bytes = generate_analysis_pdf_bytes(record, user=owner_user)
        
        as_attachment = request.args.get('preview') != '1'
        filename = f"BusinessPulse_Analysis_{record.id}_Report.pdf"
        disposition = 'attachment' if as_attachment else 'inline'
        
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'{disposition}; filename={filename}',
                'Cache-Control': 'no-cache, no-store, must-revalidate'
            }
        )
    except Exception as e:
        print(f"Error generating PDF report for analysis {record.id}: {e}")
        flash(f"Failed to generate PDF report: {e}", "error")
        return redirect(url_for('visualizations_page', history_id=record.id))

@app.route('/api/alerts/send_stockout_email', methods=['POST'])
@login_required
def api_send_stockout_email():
    """Triggers an email notification warning of categories with critical stockout risk."""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    analytics = get_user_analytics(user_id)
    if not analytics or 'forecasting' not in analytics:
        return {'status': 'error', 'message': 'No inventory forecast data available.'}, 400

    inv_fc = analytics.get('forecasting', {}).get('inventory_forecast', {})
    critical_items = []
    for cat, item in inv_fc.items():
        days_rem = item.get('days_of_stock_remaining', 999)
        risk = item.get('stockout_risk_status', '')
        if risk == 'Critical' or (isinstance(days_rem, (int, float)) and days_rem < 7):
            critical_items.append({
                'category': cat,
                'days': days_rem,
                'rop': item.get('reorder_point', 0),
                'rec_order': item.get('recommended_reorder_qty', 0),
                'capital': item.get('restock_capital_required', 0)
            })

    if not critical_items:
        return {'status': 'info', 'message': 'Inventory health is stable. No critical stockout warnings detected.'}, 200

    lines = [f"• {it['category']}: {it['days']} days remaining. Reorder Quantity: {it['rec_order']} units (Capital: INR {it['capital']:,.2f})" for it in critical_items]
    items_text = "\n".join(lines)
    subject = f"⚠️ Critical Inventory Stockout Warning ({len(critical_items)} Categories at Risk)"
    body = f"""Hello {user.username},\n\nThe BusinessPulse AI Inventory Monitor has identified {len(critical_items)} category/categories approaching imminent stockout:\n\n{items_text}\n\nPlease take immediate replenishment action to prevent revenue loss.\n\nBest regards,\nBusinessPulse AI Team"""

    # Dispatch email
    username = app.config.get('MAIL_USERNAME')
    password = app.config.get('MAIL_PASSWORD')
    server = app.config.get('MAIL_SERVER', 'smtp.gmail.com')
    port = int(app.config.get('MAIL_PORT', 587))
    try:
        msg = MIMEMultipart()
        msg['From'] = f"BusinessPulse AI Alerts <{username}>"
        msg['To'] = user.email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        context = ssl.create_default_context()
        with smtplib.SMTP(server, port, timeout=15) as s:
            s.starttls(context=context)
            s.login(username, password)
            s.send_message(msg)
        print(f"[ALERT] Stockout alert email sent to {user.email}")
        return {'status': 'success', 'message': f'Stockout alert notification successfully dispatched to {user.email}!'}, 200
    except Exception as e:
        print(f"[ALERT FALLBACK] Could not send via SMTP ({e}). Dev mode notification logged.")
        return {'status': 'success', 'message': f'Stockout alert generated for {user.email} (Email logged to server console).'}, 200

if __name__ == "__main__":
    app.run(debug=True)
