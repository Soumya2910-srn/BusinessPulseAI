from flask import Flask, redirect, url_for, render_template, flash, session, request
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
from rag_chat import build_vector_store, get_rag_response
from flask_mail import Mail, Message
from email_validator import validate_email, EmailNotValidError

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
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
mail = Mail(app)

def send_otp_email(to_email, otp, subject='Your OTP for BusinessPulse AI'):
    print(f"[OTP DEBUG] Generated OTP for {to_email}: {otp}")
    try:
        msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[to_email])
        msg.body = f'Your One-Time Password is: {otp}\n\nPlease use this to complete your action. It expires in 90 seconds.'
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
    
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

# Initialize Database
with app.app_context():
    db.create_all()

# ─── Decorators ─────────────────────────────────────────────────────────────

def login_required(f):
    """Redirect unauthenticated users to the login page."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
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

# Auth Routes 

@app.route('/')
def landingpage():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template("landingpage.html")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    form = Signup()
    if form.validate_on_submit():
        raw_email = form.email.data.strip()
        try:
            valid_info = validate_email(raw_email, check_deliverability=True)
            email = valid_info.normalized
        except EmailNotValidError:
            flash('Please enter a valid email account.', 'error')
            return render_template('signup.html', form=form)

        existing_username = User.query.filter_by(username=form.username.data.strip()).first()
        if existing_username:
            flash('Username already exists. Please choose a different username.', 'error')
            return render_template('signup.html', form=form)

        existing_email = User.query.filter_by(email=email).first()
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

        if send_otp_email(email, otp, subject='Verify your BusinessPulse AI Account'):
            flash(f'An OTP has been sent to {email}. Please verify to complete account setup.', 'success')
            return redirect(url_for('verify_otp'))
        else:
            flash('Unable to deliver OTP. Please enter a valid, active email account.', 'error')
            session.pop('otp', None)
            session.pop('signup_data', None)

    # Flash form errors if any
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"{error}", 'error')

    return render_template("signup.html", form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    form = Login()
    if form.validate_on_submit():
        raw_email = form.email.data.strip()
        try:
            valid_info = validate_email(raw_email, check_deliverability=True)
            email = valid_info.normalized
        except EmailNotValidError:
            flash('Please enter a valid email account.', 'error')
            return render_template('login.html', form=form)

        user = User.query.filter_by(email=email).first()
        if user:
            # Generate OTP
            otp = str(random.randint(100000, 999999))
            session['otp'] = otp
            session['otp_time'] = datetime.utcnow().timestamp()
            session['login_data'] = {
                'user_id': user.id,
                'username': user.username
            }
            session['login_email'] = user.email
            session.pop('signup_data', None)

            if send_otp_email(user.email, otp, subject='Your BusinessPulse AI Login OTP'):
                flash(f'Login OTP has been sent to {user.email}.', 'success')
                return redirect(url_for('verify_otp'))
            else:
                flash('Unable to deliver OTP. Please enter a valid, active email account.', 'error')
                session.pop('otp', None)
                session.pop('login_data', None)
                session.pop('login_email', None)
        else:
            flash('Account not found. Please enter a valid email account or create an account.', 'error')

    # Flash form errors if any
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"{error}", 'error')

    return render_template("login.html", form=form)
@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

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
                is_first_user = User.query.count() == 0
                new_user = User(
                    username=data['username'],
                    email=data['email'],
                    password='',
                    role='admin' if is_first_user else 'user'
                )
                db.session.add(new_user)
                db.session.commit()
                session.pop('otp', None)
                session.pop('otp_time', None)
                session.pop('login_data', None)
                session.pop('login_email', None)

                # Direct login on first-time account creation
                session['user_id'] = new_user.id
                session['username'] = new_user.username
                return redirect(url_for('dashboard'))

            # Login flow
            elif 'login_data' in session:
                data = session.pop('login_data')
                session['user_id'] = data['user_id']
                session['username'] = data['username']
                session.pop('otp', None)
                session.pop('otp_time', None)
                session.pop('login_email', None)
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
    flash('Logged out successfully.', 'success')
    return redirect(url_for('landingpage'))

if __name__ == "__main__":
    app.run(debug=True)
