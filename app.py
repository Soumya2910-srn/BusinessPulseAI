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
    return render_template('admin.html', users=all_users, user_stats=user_stats,
                           current_user=current_user, total_analyses=total_analyses)

@app.route('/admin/toggle_role/<int:user_id>', methods=['POST'])
@admin_required
def toggle_role(user_id):
    user = User.query.get_or_404(user_id)
    # Prevent admin from demoting themselves
    if user.id == session['user_id']:
        return {'status': 'error', 'message': 'You cannot change your own role.'}, 400
    user.role = 'user' if user.role == 'admin' else 'admin'
    db.session.commit()
    return {'status': 'success', 'new_role': user.role, 'message': f'Role updated to {user.role}.'}, 200

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if user_id == session['user_id']:
        return {'status': 'error', 'message': 'You cannot delete your own account.'}, 400
    user = User.query.get_or_404(user_id)
    # Delete user's history records too
    AnalysisHistory.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    return {'status': 'success', 'message': f'User {user.username} deleted successfully.'}, 200
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

    import pandas as pd
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

    # Use ML model predictions for upcoming month forecast
    forecasted_rev = round(ml_models['model_rev'].predict(curr_metrics['marketing'] * 1.1), 2) if ml_models else 0.0

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
            import json
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
        # Sort chronologically by converting back to datetime for sorting
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
        'category_stats': curr_metrics['category_stats']
    }
    session['analytics'] = analytics_data

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
    except Exception as e:
        print(f"Error saving analysis history: {e}")

    return {
        'status': 'success',
        'message': 'Datasets uploaded, ML model trained & visualization saved to history!',
        'redirect_url': url_for('visualizations_page'),
        'analytics': analytics_data
    }, 200
    
if __name__ == "__main__":
    app.run(debug=True)
