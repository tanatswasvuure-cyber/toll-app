from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, flash
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import hashlib
import os
import requests
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'toll_system_secret_key_2025')

# ================= SUPABASE (POSTGRESQL) CONFIGURATION =================
SUPABASE_HOST = os.environ.get('SUPABASE_HOST')
SUPABASE_PORT = os.environ.get('SUPABASE_PORT', '5432')
SUPABASE_USER = os.environ.get('SUPABASE_USER')
SUPABASE_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
SUPABASE_DB = os.environ.get('SUPABASE_DB', 'postgres')

TOLL_AMOUNT = float(os.environ.get('TOLL_AMOUNT', '1.50'))

# ================= POLICE ALERT CONFIGURATION =================
POLICE_SMS_EMAIL = os.environ.get('POLICE_SMS_EMAIL', '')
POLICE_EMAIL = os.environ.get('POLICE_EMAIL', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', '')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
POLICE_WEBHOOK_URL = os.environ.get('POLICE_WEBHOOK_URL', '')

# ================= LOGIN DECORATOR =================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ================= DATABASE CONNECTION FUNCTION =================
def get_db_connection():
    """Connect to Supabase (PostgreSQL) database"""
    try:
        if not all([SUPABASE_HOST, SUPABASE_USER, SUPABASE_PASSWORD]):
            print("⚠️ Missing Supabase environment variables")
            return None
        
        conn = psycopg2.connect(
            host=SUPABASE_HOST,
            port=int(SUPABASE_PORT),
            user=SUPABASE_USER,
            password=SUPABASE_PASSWORD,
            database=SUPABASE_DB,
            connect_timeout=10
        )
        print(f"✅ Connected to Supabase at {SUPABASE_HOST}:{SUPABASE_PORT}")
        return conn
    except Exception as e:
        print(f"Database error: {e}")
        return None

# ================= FIXED: DATABASE INITIALIZATION =================
def init_db():
    """Create all tables in Supabase if they don't exist"""
    conn = get_db_connection()
    if not conn:
        print("⚠️ Database not available - will use memory mode for testing")
        return
    
    cursor = conn.cursor()
    
    # Create tables (same as your SQL)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id SERIAL PRIMARY KEY,
            vehicle_number VARCHAR(50) UNIQUE,
            rfid_tag VARCHAR(100) UNIQUE,
            owner_name VARCHAR(100),
            vehicle_type VARCHAR(50),
            owner_phone VARCHAR(20),
            balance DECIMAL(10,2) DEFAULT 0,
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            rfid_tag VARCHAR(100),
            vehicle_number VARCHAR(50),
            amount DECIMAL(10,2),
            status VARCHAR(50),
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stolen_vehicles (
            id SERIAL PRIMARY KEY,
            vehicle_number VARCHAR(50),
            rfid_tag VARCHAR(100),
            owner_contact VARCHAR(20),
            police_station VARCHAR(100),
            status VARCHAR(20) DEFAULT 'ACTIVE',
            reported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id SERIAL PRIMARY KEY,
            action VARCHAR(100),
            username VARCHAR(50),
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS police_alerts (
            id SERIAL PRIMARY KEY,
            vehicle_number VARCHAR(50),
            alert_type VARCHAR(50),
            message TEXT,
            acknowledged BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE,
            password VARCHAR(255),
            role VARCHAR(20)
        )
    """)
    
    conn.commit()
    
    # FIXED: Create default admin with correct hash
    cursor.execute("SELECT * FROM users WHERE username='admin'")
    if not cursor.fetchone():
        # This hash matches 'admin123'
        admin_hash = '8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918'
        cursor.execute("""
            INSERT INTO users (username, password, role) 
            VALUES (%s, %s, %s)
        """, ("admin", admin_hash, "admin"))
        conn.commit()
        print("✅ Admin user created (admin/admin123)")
    else:
        print("✅ Admin user already exists")
    
    # Insert test vehicles if none exist
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    vehicle_count = cursor.fetchone()[0]
    if vehicle_count == 0:
        cursor.execute("""
            INSERT INTO vehicles (vehicle_number, rfid_tag, owner_name, vehicle_type, balance) 
            VALUES 
                ('ABX001', '0A036432', 'Inno Mashefu', 'car', 50.00),
                ('CAR002', '1122334455', 'John Doe', 'car', 25.50),
                ('TRUCK001', 'AABBCCDDEE', 'Jane Smith', 'truck', 100.00)
            ON CONFLICT (vehicle_number) DO NOTHING
        """)
        conn.commit()
        print("✅ Test vehicles added")
    
    cursor.close()
    conn.close()
    print("✅ Database initialization complete")

# ================= FIXED: LOGIN ROUTE WITH DEBUGGING =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Hash the password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        print(f"🔐 Login attempt - Username: {username}")
        print(f"Generated hash: {hashed_password}")
        
        conn = get_db_connection()
        if not conn:
            flash('Database connection error. Please try again.', 'danger')
            return render_template_string(LOGIN_HTML)
        
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # First, check if users table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'users'
                )
            """)
            table_exists = cursor.fetchone()['exists']
            
            if not table_exists:
                flash('System not initialized. Please contact administrator.', 'danger')
                cursor.close()
                conn.close()
                return render_template_string(LOGIN_HTML)
            
            # Find user
            cursor.execute("""
                SELECT id, username, role 
                FROM users 
                WHERE username = %s AND password = %s
            """, (username, hashed_password))
            
            user = cursor.fetchone()
            
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                flash(f'Welcome back, {username}!', 'success')
                return redirect(url_for('dashboard'))
            else:
                # Check if user exists but password wrong
                cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
                user_exists = cursor.fetchone()
                if user_exists:
                    flash('Invalid password', 'danger')
                else:
                    flash('Invalid username', 'danger')
            
            cursor.close()
        except Exception as e:
            print(f"Login error: {e}")
            flash('An error occurred. Please try again.', 'danger')
        finally:
            conn.close()
    
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML)

# ================= TEST ENDPOINT (Remove after testing) =================
@app.route('/test-db')
def test_db():
    """Test database connection and show users"""
    conn = get_db_connection()
    if not conn:
        return "❌ Database connection failed"
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Check users table
    cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='users')")
    users_table = cursor.fetchone()['exists']
    
    result = "<h2>Database Status</h2>"
    result += f"<p>Users table exists: {users_table}</p>"
    
    if users_table:
        cursor.execute("SELECT username, role FROM users")
        users = cursor.fetchall()
        result += f"<p>Users found: {len(users)}</p>"
        for user in users:
            result += f"<p> - {user['username']} ({user['role']})</p>"
    
    cursor.close()
    conn.close()
    
    return result

# ================= REMAINING API ROUTES (same as your code) =================
# ... (keep all your existing API routes: /api/topup, /api/stats, /api/transactions, 
#      /api/vehicles, /api/register_vehicle, /api/delete_vehicle, /api/report_stolen,
#      /api/stolen_vehicles, /api/mark_recovered, /api/alert_history, /api/rfid)

# [INSERT ALL YOUR EXISTING API ROUTES HERE - they are correct]

# ================= LOGIN HTML (same as your code) =================
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Toll System Login</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }
        .login-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .login-header h2 {
            color: #333;
            font-size: 28px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
        }
        input {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 14px;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
        }
        button:hover {
            transform: translateY(-2px);
        }
        .alert {
            padding: 12px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .alert-danger {
            background: #fee2e2;
            color: #dc2626;
            border: 1px solid #fecaca;
        }
        .alert-success {
            background: #dcfce7;
            color: #16a34a;
            border: 1px solid #bbf7d0;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h2>🚗 Toll System</h2>
            <p>Login to access dashboard</p>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" placeholder="Enter username" required autofocus>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" placeholder="Enter password" required>
            </div>
            <button type="submit">Login</button>
        </form>
        
        <div style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
            <p>Demo: admin / admin123</p>
        </div>
    </div>
</body>
</html>
"""

# ================= DASHBOARD HTML (keep your existing one) =================
# [INSERT YOUR DASHBOARD_HTML HERE - it's correct]

# Initialize database when app starts
print("🔄 Initializing database...")
init_db()
print("🚀 Starting Flask app...")

if __name__ == "__main__":
    print("="*60)
    print("🚗 SMART TOLL SYSTEM WITH SUPABASE 🚨")
    print("="*60)
    print("📱 Access Dashboard: http://localhost:5000/login")
    print("🔑 Login: admin / admin123")
    print("💰 Toll Amount: $1.50 USD")
    print("="*60)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)  # debug=False for Render
