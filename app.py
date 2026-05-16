from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, flash
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import hashlib
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'toll_system_secret_key_2025')
app.config['DEBUG'] = False

# ================= SUPABASE CONFIGURATION =================
SUPABASE_HOST = os.environ.get('SUPABASE_HOST')
SUPABASE_PORT = os.environ.get('SUPABASE_PORT', '5432')
SUPABASE_USER = os.environ.get('SUPABASE_USER')
SUPABASE_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
SUPABASE_DB = os.environ.get('SUPABASE_DB', 'postgres')

TOLL_AMOUNT = float(os.environ.get('TOLL_AMOUNT', '1.50'))

# ================= DATABASE CONNECTION =================
def get_db_connection():
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
        return conn
    except Exception as e:
        print(f"Database error: {e}")
        return None

# ================= INITIALIZE DATABASE =================
def init_db():
    conn = get_db_connection()
    if not conn:
        print("⚠️ Database not available")
        return
    
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE,
            password VARCHAR(255),
            role VARCHAR(20)
        )
    """)
    
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
    
    conn.commit()
    
    # Create admin user if not exists
    cursor.execute("SELECT * FROM users WHERE username='admin'")
    if not cursor.fetchone():
        admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
        cursor.execute("""
            INSERT INTO users (username, password, role) 
            VALUES (%s, %s, %s)
        """, ("admin", admin_hash, "admin"))
        conn.commit()
        print("✅ Admin user created")
    
    # Insert test vehicles if none
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO vehicles (vehicle_number, rfid_tag, owner_name, vehicle_type, balance) 
            VALUES 
                ('ABX001', '0A036432', 'Inno Mashefu', 'car', 50.00),
                ('CAR002', '1122334455', 'John Doe', 'car', 25.50),
                ('TRUCK001', 'AABBCCDDEE', 'Jane Smith', 'truck', 100.00)
        """)
        conn.commit()
        print("✅ Test vehicles added")
    
    cursor.close()
    conn.close()
    print("✅ Database initialized")

# ================= SIMPLE LOGIN HTML =================
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Login</title>
    <style>
        body {
            font-family: Arial;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 0;
        }
        .login-box {
            background: white;
            padding: 40px;
            border-radius: 20px;
            width: 350px;
            text-align: center;
        }
        input {
            width: 100%;
            padding: 10px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        button {
            width: 100%;
            padding: 10px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
        .alert {
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .alert-danger { background: #fee; color: #dc2626; }
        .alert-success { background: #efe; color: #16a34a; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🚗 Toll System</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, message in messages %}
                <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
        {% endwith %}
        <form method="POST">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        <p style="margin-top: 20px; font-size: 12px;">admin / admin123</p>
    </div>
</body>
</html>
"""

# ================= SIMPLE DASHBOARD HTML =================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard</title>
    <style>
        body {
            font-family: Arial;
            background: #f0f2f5;
            margin: 0;
            padding: 20px;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        button, .logout-btn {
            background: #ef4444;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background: #f8f9fa;
        }
        .btn-success {
            background: #10b981;
        }
    </style>
</head>
<body>
    <div class="header">
        <h2>🚗 Smart Toll System</h2>
        <div>
            👤 {{ session.username }} ({{ session.role }})
            <a href="/logout" class="logout-btn" style="margin-left: 10px;">Logout</a>
        </div>
    </div>
    
    <div class="card">
        <h3>System Status</h3>
        <p>✅ Toll system is running on Render.com</p>
        <p>💰 Toll Amount: $1.50</p>
        <p>📊 Database: Connected to Supabase</p>
    </div>
    
    <div class="card">
        <h3>API Endpoints</h3>
        <ul>
            <li>POST /api/rfid - Process RFID tag</li>
            <li>GET /api/vehicles - List vehicles</li>
            <li>GET /api/transactions - List transactions</li>
        </ul>
    </div>
</body>
</html>
"""

# ================= LOGIN DECORATOR =================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ================= ROUTES =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT id, username, role FROM users WHERE username=%s AND password=%s", (username, password))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
        
        flash('Invalid username or password', 'danger')
    
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML)

# ================= API ENDPOINTS =================
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/api/rfid', methods=['POST'])
def handle_rfid():
    try:
        data = request.json
        rfid_tag = data.get('rfid_tag')
        
        if not rfid_tag:
            return jsonify({"status": "ERROR", "message": "No RFID tag"}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"status": "ERROR", "message": "Database unavailable"}), 500
        
        cursor = conn.cursor()
        
        # Check if stolen
        cursor.execute("SELECT vehicle_number FROM stolen_vehicles WHERE rfid_tag=%s AND status='ACTIVE'", (rfid_tag,))
        stolen = cursor.fetchone()
        if stolen:
            cursor.execute("""
                INSERT INTO transactions (rfid_tag, vehicle_number, amount, status, time) 
                VALUES (%s, %s, %s, %s, NOW())
            """, (rfid_tag, stolen[0], TOLL_AMOUNT, "DENIED-STOLEN"))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({"status": "DENIED", "message": "STOLEN VEHICLE"})
        
        # Check vehicle
        cursor.execute("""
            SELECT vehicle_number, vehicle_type, COALESCE(balance, 0) as balance 
            FROM vehicles WHERE rfid_tag=%s AND status='active'
        """, (rfid_tag,))
        vehicle = cursor.fetchone()
        
        if not vehicle:
            cursor.close()
            conn.close()
            return jsonify({"status": "DENIED", "message": "Unknown vehicle"})
        
        vehicle_number, vehicle_type, balance = vehicle
        price = TOLL_AMOUNT * 2 if vehicle_type == "Truck" else TOLL_AMOUNT * 1.5 if vehicle_type == "Bus" else TOLL_AMOUNT
        
        if balance < price:
            cursor.execute("""
                INSERT INTO transactions (rfid_tag, vehicle_number, amount, status, time) 
                VALUES (%s, %s, %s, %s, NOW())
            """, (rfid_tag, vehicle_number, price, "INSUFFICIENT"))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({"status": "DENIED", "message": f"Insufficient balance. Need ${price}, have ${balance}"})
        
        # Process payment
        new_balance = balance - price
        cursor.execute("UPDATE vehicles SET balance = %s WHERE rfid_tag = %s", (new_balance, rfid_tag))
        cursor.execute("""
            INSERT INTO transactions (rfid_tag, vehicle_number, amount, status, time) 
            VALUES (%s, %s, %s, %s, NOW())
        """, (rfid_tag, vehicle_number, price, "APPROVED"))
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "APPROVED",
            "vehicle": vehicle_number,
            "amount": price,
            "balance_remaining": new_balance
        })
        
    except Exception as e:
        print(f"RFID error: {e}")
        return jsonify({"status": "ERROR", "message": str(e)}), 500

@app.route('/api/vehicles', methods=['GET'])
@login_required
def get_vehicles():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify([])
        
        cursor = conn.cursor()
        cursor.execute("SELECT id, vehicle_number, rfid_tag, owner_name, vehicle_type, balance FROM vehicles WHERE status='active'")
        data = [{"id": r[0], "vehicle_number": r[1], "rfid_tag": r[2], "owner_name": r[3], "vehicle_type": r[4], "balance": float(r[5])} for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(data)
    except Exception as e:
        print(f"Vehicles error: {e}")
        return jsonify([])

@app.route('/api/transactions', methods=['GET'])
@login_required
def get_transactions():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify([])
        
        cursor = conn.cursor()
        cursor.execute("SELECT vehicle_number, amount, status, TO_CHAR(time, 'HH24:MI:SS') FROM transactions ORDER BY id DESC LIMIT 20")
        data = [{"vehicle_number": r[0], "amount": float(r[1]), "status": r[2], "time": r[3]} for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(data)
    except Exception as e:
        print(f"Transactions error: {e}")
        return jsonify([])

@app.route('/api/stolen_alerts', methods=['GET'])
def stolen_alerts():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify([])
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT vehicle_number, TO_CHAR(time, 'HH24:MI:SS') as time
            FROM transactions 
            WHERE status='DENIED-STOLEN' AND time > NOW() - INTERVAL '1 hour'
            ORDER BY time DESC
            LIMIT 10
        """)
        data = [{"vehicle_number": r[0], "time": r[1]} for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(data)
    except Exception as e:
        print(f"Stolen alerts error: {e}")
        return jsonify([])

# ================= ERROR HANDLERS =================
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500

# ================= START APP =================
if __name__ == "__main__":
    print("🔄 Initializing database...")
    init_db()
    print("🚀 Starting Flask app...")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
