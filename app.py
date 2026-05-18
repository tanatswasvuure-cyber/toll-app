from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, flash
from functools import wraps
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import hashlib
import os
import requests

app = Flask(__name__)
CORS(app)  # Allow all origins to access your API
app.secret_key = os.environ.get('SECRET_KEY', 'toll_system_secret_key_2025')

# ================= SUPABASE (POSTGRESQL) CONFIGURATION =================
SUPABASE_HOST = os.environ.get('SUPABASE_HOST')
SUPABASE_PORT = os.environ.get('SUPABASE_PORT', '5432')
SUPABASE_USER = os.environ.get('SUPABASE_USER')
SUPABASE_PASSWORD = os.environ.get('SUPABASE_PASSWORD')
SUPABASE_DB = os.environ.get('SUPABASE_DB', 'postgres')

TOLL_AMOUNT = float(os.environ.get('TOLL_AMOUNT', '1.50'))

# ================= POLICE ALERT CONFIGURATION (REDUCED) =================
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

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

# ================= AUTOMATIC POLICE ALERT FUNCTION (REDUCED) =================
def send_police_alert(vehicle_number, rfid_tag, location="Toll Plaza", reason="STOLEN VEHICLE DETECTED"):
    """Send automatic alerts to police via Telegram only"""
    
    alert_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    message = f"""
🚨 POLICE EMERGENCY ALERT 🚨

Vehicle: {vehicle_number}
RFID Tag: {rfid_tag}
Location: {location}
Time: {alert_time}
Reason: {reason}

ACTION: Vehicle marked as stolen - Intercept immediately!
"""
    
    alert_sent = False
    
    # Method 1: Telegram Bot (Only method kept)
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(telegram_url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            }, timeout=5)
            print(f"✅ Telegram alert sent for {vehicle_number}")
            alert_sent = True
        except Exception as e:
            print(f"Telegram failed: {e}")
    
    # Always log to database
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO system_logs (action, username, details) 
            VALUES (%s, %s, %s)
        """, ("AUTOMATIC_POLICE_ALERT", "SYSTEM", f"Vehicle {vehicle_number} detected at {location} - {reason}"))
        conn.commit()
        cursor.close()
        conn.close()
    
    return alert_sent

# ================= INITIALIZE DATABASE AND TABLES =================
def init_db():
    """Create all tables in Supabase if they don't exist"""
    conn = get_db_connection()
    if not conn:
        print("⚠️ Database not available - will use memory mode for testing")
        return
    
    cursor = conn.cursor()
    
    # Vehicles table with balance column
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
    
    # Transactions table
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
    
    # Stolen vehicles table
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
    
    # System logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id SERIAL PRIMARY KEY,
            action VARCHAR(100),
            username VARCHAR(50),
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Police alerts table
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
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE,
            password VARCHAR(255),
            role VARCHAR(20)
        )
    """)
    
    conn.commit()
    
    # Create default admin
    cursor.execute("SELECT * FROM users WHERE username='admin'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (username, password, role) 
            VALUES (%s, %s, %s)
        """, ("admin", hashlib.sha256("admin123".encode()).hexdigest(), "admin"))
        conn.commit()
    
    cursor.close()
    conn.close()
    print("✅ Supabase database initialized successfully!")

# Call init_db when app starts
init_db()

# ================= LOGIN HTML =================
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

# ================= DASHBOARD HTML WITH SIDEBAR =================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Smart Toll System - Dashboard</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: #f0f2f5;
            overflow-x: hidden;
        }
        
        /* Sidebar Styles */
        .sidebar {
            position: fixed;
            left: 0;
            top: 0;
            width: 260px;
            height: 100%;
            background: linear-gradient(135deg, #1a1f3e 0%, #0a0e27 100%);
            color: white;
            transition: all 0.3s;
            z-index: 100;
            overflow-y: auto;
        }
        
        .sidebar-header {
            padding: 20px;
            text-align: center;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        
        .sidebar-header h3 {
            font-size: 20px;
            margin-bottom: 5px;
        }
        
        .sidebar-header p {
            font-size: 12px;
            opacity: 0.7;
        }
        
        .sidebar-menu {
            padding: 20px 0;
        }
        
        .menu-item {
            padding: 12px 25px;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 12px;
            color: rgba(255,255,255,0.8);
        }
        
        .menu-item:hover {
            background: rgba(255,255,255,0.1);
            padding-left: 30px;
        }
        
        .menu-item.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-left: 4px solid white;
        }
        
        .menu-item i {
            width: 24px;
            font-size: 18px;
        }
        
        .user-info {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
            font-size: 14px;
        }
        
        /* Main Content */
        .main-content {
            margin-left: 260px;
            padding: 20px;
            min-height: 100vh;
        }
        
        /* Top Bar */
        .top-bar {
            background: white;
            padding: 15px 25px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }
        
        .page-title {
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }
        
        .logout-btn {
            background: #ef4444;
            color: white;
            padding: 8px 20px;
            border-radius: 8px;
            text-decoration: none;
            transition: all 0.3s;
        }
        
        .logout-btn:hover {
            background: #dc2626;
        }
        
        /* Stats Cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }
        
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            transition: transform 0.3s;
        }
        
        .stat-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }
        
        .stat-title {
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
        }
        
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            color: #333;
        }
        
        .stat-card.alert .stat-value {
            color: #ef4444;
        }
        
        /* Content Panels */
        .content-panel {
            display: none;
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
        }
        
        .content-panel.active {
            display: block;
        }
        
        .panel-title {
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 20px;
            color: #333;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }
        
        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }
        
        th {
            background: #f8f9fa;
            color: #555;
            font-weight: 600;
        }
        
        .status-paid {
            color: #10b981;
            font-weight: bold;
        }
        
        .status-denied {
            color: #ef4444;
            font-weight: bold;
        }
        
        /* Forms */
        input, select {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 15px;
            font-size: 14px;
        }
        
        button {
            background: #667eea;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: 500;
        }
        
        button:hover {
            background: #5a67d8;
            transform: translateY(-1px);
        }
        
        .btn-danger {
            background: #ef4444;
        }
        
        .btn-danger:hover {
            background: #dc2626;
        }
        
        .btn-success {
            background: #10b981;
        }
        
        .btn-success:hover {
            background: #059669;
        }
        
        .btn-warning {
            background: #f59e0b;
        }
        
        .btn-sm {
            padding: 5px 12px;
            font-size: 12px;
        }
        
        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: white;
            border-radius: 12px;
            padding: 25px;
            width: 90%;
            max-width: 400px;
        }
        
        .modal-header {
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 20px;
            color: #333;
        }
        
        .modal-buttons {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }
        
        .modal-buttons button {
            flex: 1;
        }
        
        /* Search */
        .search-box {
            margin-bottom: 20px;
        }
        
        .search-box input {
            margin-bottom: 0;
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: #f1f1f1;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #667eea;
            border-radius: 4px;
        }
        
        @media (max-width: 768px) {
            .sidebar {
                width: 70px;
            }
            .sidebar-header h3, .sidebar-header p, .menu-item span {
                display: none;
            }
            .main-content {
                margin-left: 70px;
            }
            .menu-item i {
                margin: 0;
            }
        }
    </style>
</head>
<body>
    <!-- Sidebar -->
    <div class="sidebar">
        <div class="sidebar-header">
            <h3>🚗 Toll System</h3>
            <p>Smart Toll Management</p>
        </div>
        <div class="sidebar-menu">
            <div class="menu-item active" onclick="showPanel('dashboard')">
                <i>📊</i> <span>Dashboard</span>
            </div>
            <div class="menu-item" onclick="showPanel('vehicles')">
                <i>🚗</i> <span>Vehicles</span>
            </div>
            <div class="menu-item" onclick="showPanel('transactions')">
                <i>📝</i> <span>Transactions</span>
            </div>
            <div class="menu-item" onclick="showPanel('register')">
                <i>➕</i> <span>Register Vehicle</span>
            </div>
            <div class="menu-item" onclick="showPanel('stolen')">
                <i>⚠️</i> <span>Stolen Vehicles</span>
            </div>
            <div class="menu-item" onclick="showPanel('alerts')">
                <i>🚨</i> <span>Police Alerts</span>
            </div>
        </div>
        <div class="user-info">
            <div>👤 {{ session.username }}</div>
            <div style="font-size: 11px; opacity: 0.7;">{{ session.role }}</div>
        </div>
    </div>
    
    <!-- Main Content -->
    <div class="main-content">
        <div class="top-bar">
            <div class="page-title" id="pageTitle">Dashboard</div>
            <a href="{{ url_for('logout') }}" class="logout-btn">🚪 Logout</a>
        </div>
        
        <!-- Dashboard Panel -->
        <div id="dashboardPanel" class="content-panel active">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-title">Total Vehicles</div>
                    <div class="stat-value" id="statVehicles">0</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Today's Transactions</div>
                    <div class="stat-value" id="statTransactions">0</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Today's Revenue</div>
                    <div class="stat-value" id="statRevenue">$0</div>
                </div>
                <div class="stat-card alert">
                    <div class="stat-title">Stolen Vehicles</div>
                    <div class="stat-value" id="statStolen">0</div>
                </div>
            </div>
            
            <div class="panel-title">Recent Transactions</div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr><th>Vehicle</th><th>Amount</th><th>Status</th><th>Time</th>
                    </thead>
                    <tbody id="recentTransactions"></tbody>
                </table>
            </div>
        </div>
        
        <!-- Vehicles Panel -->
        <div id="vehiclesPanel" class="content-panel">
            <div class="panel-title">Registered Vehicles</div>
            <div class="search-box">
                <input type="text" id="searchVehicles" placeholder="🔍 Search vehicles..." onkeyup="filterVehicles()">
            </div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr><th>Vehicle</th><th>RFID</th><th>Owner</th><th>Type</th><th>Balance</th><th>Actions</th>
                    </thead>
                    <tbody id="vehiclesList"></tbody>
                </table>
            </div>
        </div>
        
        <!-- Transactions Panel -->
        <div id="transactionsPanel" class="content-panel">
            <div class="panel-title">All Transactions</div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr><th>Vehicle</th><th>Amount</th><th>Status</th><th>Time</th>
                    </thead>
                    <tbody id="allTransactions"></tbody>
                </table>
            </div>
        </div>
        
        <!-- Register Panel -->
        <div id="registerPanel" class="content-panel">
            <div class="panel-title">Register New Vehicle</div>
            <form id="registerForm">
                <input type="text" name="vehicle_number" placeholder="Vehicle Number" required>
                <input type="text" name="rfid_tag" placeholder="RFID Tag" required>
                <input type="text" name="owner_name" placeholder="Owner Name" required>
                <select name="vehicle_type">
                    <option>Car</option><option>Bus</option><option>Truck</option><option>Bike</option>
                </select>
                <input type="number" name="initial_balance" placeholder="Initial Balance ($)" step="0.01" value="0">
                <button type="submit">Register Vehicle</button>
            </form>
        </div>
        
        <!-- Stolen Panel -->
        <div id="stolenPanel" class="content-panel">
            <div class="panel-title">⚠️ Report Stolen Vehicle</div>
            <form id="stolenForm">
                <input type="text" name="vehicle_number" placeholder="Vehicle Number" required>
                <input type="text" name="rfid_tag" placeholder="RFID Tag" required>
                <input type="text" name="owner_contact" placeholder="Owner Contact">
                <button type="submit" class="btn-danger">🚨 Report Stolen - Alert Police</button>
            </form>
            <br><br>
            <div class="panel-title">Active Stolen Vehicles</div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr><th>Vehicle</th><th>RFID</th><th>Date</th><th>Action</th>
                    </thead>
                    <tbody id="stolenList"></tbody>
                </table>
            </div>
        </div>
        
        <!-- Alerts Panel -->
        <div id="alertsPanel" class="content-panel">
            <div class="panel-title">🚨 Police Alert History</div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr><th>Time</th><th>Vehicle</th><th>Alert Type</th><th>Status</th>
                    </thead>
                    <tbody id="alertsList"></tbody>
                </table>
            </div>
        </div>
    </div>
    
    <!-- Add Money Modal -->
    <div id="topupModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">💰 Add Money to Vehicle</div>
            <input type="hidden" id="topupVehicleNumber">
            <input type="text" id="topupVehicleDisplay" readonly style="background:#f5f5f5;">
            <input type="number" id="topupAmount" placeholder="Enter amount ($)" step="0.01" min="1">
            <div class="modal-buttons">
                <button onclick="processTopup()" class="btn-success">Add Money</button>
                <button onclick="closeTopupModal()" class="btn-danger">Cancel</button>
            </div>
        </div>
    </div>
    
    <script>
        let currentTopupVehicle = null;
        
        function showPanel(panel) {
            document.querySelectorAll('.menu-item').forEach(item => {
                item.classList.remove('active');
            });
            event.target.closest('.menu-item').classList.add('active');
            
            document.querySelectorAll('.content-panel').forEach(p => {
                p.classList.remove('active');
            });
            
            document.getElementById(panel + 'Panel').classList.add('active');
            
            const titles = {
                'dashboard': 'Dashboard',
                'vehicles': 'Vehicles Management',
                'transactions': 'Transaction History',
                'register': 'Register Vehicle',
                'stolen': 'Stolen Vehicles',
                'alerts': 'Police Alerts'
            };
            document.getElementById('pageTitle').innerText = titles[panel] || panel;
            
            if(panel === 'vehicles') loadVehicles();
            if(panel === 'stolen') loadStolen();
            if(panel === 'alerts') loadAlertHistory();
            if(panel === 'transactions') loadAllTransactions();
        }
        
        function showTopupModal(vehicleNumber) {
            currentTopupVehicle = vehicleNumber;
            document.getElementById('topupVehicleDisplay').value = vehicleNumber;
            document.getElementById('topupAmount').value = '';
            document.getElementById('topupModal').classList.add('active');
        }
        
        function closeTopupModal() {
            document.getElementById('topupModal').classList.remove('active');
        }
        
        function processTopup() {
            const amount = document.getElementById('topupAmount').value;
            if (!amount || amount <= 0) {
                alert('Please enter a valid amount');
                return;
            }
            
            fetch('/api/topup', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    vehicle_number: currentTopupVehicle,
                    amount: parseFloat(amount)
                })
            }).then(r => r.json()).then(d => {
                alert(d.message);
                closeTopupModal();
                loadVehicles();
                loadStats();
            });
        }
        
        function loadStats() {
            fetch('/api/stats').then(r=>r.json()).then(d=>{
                document.getElementById('statVehicles').innerText = d.vehicles || 0;
                document.getElementById('statTransactions').innerText = d.today_transactions || 0;
                document.getElementById('statRevenue').innerText = '$' + (d.today_revenue || 0).toFixed(2);
                document.getElementById('statStolen').innerText = d.stolen_alerts_today || 0;
            });
        }
        
        function loadRecentTransactions() {
            fetch('/api/transactions').then(r=>r.json()).then(d=>{
                const tbody = document.getElementById('recentTransactions');
                tbody.innerHTML = '';
                d.slice(0, 10).forEach(t=>{
                    const statusClass = t.status.toLowerCase().includes('stolen') ? 'status-denied' : 'status-paid';
                    tbody.innerHTML += `<tr>
                        <td>${t.vehicle_number}</td>
                        <td>$${t.amount}</td>
                        <td class="${statusClass}">${t.status}</td>
                        <td>${t.time}</td>
                    </tr>`;
                });
            });
        }
        
        function loadAllTransactions() {
            fetch('/api/transactions').then(r=>r.json()).then(d=>{
                const tbody = document.getElementById('allTransactions');
                tbody.innerHTML = '';
                d.forEach(t=>{
                    const statusClass = t.status.toLowerCase().includes('stolen') ? 'status-denied' : 'status-paid';
                    tbody.innerHTML += `<tr>
                        <td>${t.vehicle_number}</td>
                        <td>$${t.amount}</td>
                        <td class="${statusClass}">${t.status}</td>
                        <td>${t.time}</td>
                    </tr>`;
                });
            });
        }
        
        function loadVehicles() {
            fetch('/api/vehicles').then(r=>r.json()).then(d=>{
                const tbody = document.getElementById('vehiclesList');
                tbody.innerHTML = '';
                d.forEach(v=>{
                    tbody.innerHTML += `<tr>
                        <td><strong>${v.vehicle_number}</strong></td>
                        <td><code>${v.rfid_tag}</code></td>
                        <td>${v.owner_name || '-'}</td>
                        <td>${v.vehicle_type || '-'}</td>
                        <td class="${v.balance < 5 ? 'status-denied' : 'status-paid'}">$${parseFloat(v.balance).toFixed(2)}</td>
                        <td>
                            <button onclick="showTopupModal('${v.vehicle_number}')" class="btn-success btn-sm" style="margin-right:5px;">💰 Add</button>
                            <button onclick="deleteVehicle(${v.id})" class="btn-danger btn-sm">Delete</button>
                        </td>
                    `;
                });
            });
        }
        
        function filterVehicles() {
            const search = document.getElementById('searchVehicles').value.toLowerCase();
            const rows = document.querySelectorAll('#vehiclesList tr');
            rows.forEach(row => {
                row.style.display = row.innerText.toLowerCase().includes(search) ? '' : 'none';
            });
        }
        
        function loadStolen() {
            fetch('/api/stolen_vehicles').then(r=>r.json()).then(d=>{
                const tbody = document.getElementById('stolenList');
                tbody.innerHTML = '';
                d.forEach(s=>{
                    tbody.innerHTML += `<tr>
                        <td>${s.vehicle_number}</td>
                        <td><code>${s.rfid_tag}</code></td>
                        <td>${s.reported_date}</td>
                        <td><button onclick="markRecovered('${s.vehicle_number}')" class="btn-warning btn-sm">Mark Recovered</button></td>
                    `;
                });
            });
        }
        
        function loadAlertHistory() {
            fetch('/api/alert_history').then(r=>r.json()).then(d=>{
                const tbody = document.getElementById('alertsList');
                tbody.innerHTML = '';
                d.forEach(a=>{
                    tbody.innerHTML += `<tr>
                        <td>${a.time}</td>
                        <td>${a.vehicle_number}</td>
                        <td>${a.alert_type}</td>
                        <td class="${a.status === 'sent' ? 'status-paid' : 'status-denied'}">${a.status}</td>
                    `;
                });
            });
        }
        
        function deleteVehicle(id) {
            if(confirm('Delete this vehicle?')) {
                fetch('/api/delete_vehicle', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({id: id})
                }).then(() => loadVehicles());
            }
        }
        
        function markRecovered(vehicle) {
            if(confirm(`Mark ${vehicle} as recovered?`)) {
                fetch('/api/mark_recovered', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({vehicle_number: vehicle})
                }).then(() => loadStolen());
            }
        }
        
        document.getElementById('registerForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            fetch('/api/register_vehicle', {
                method: 'POST',
                body: JSON.stringify(Object.fromEntries(formData)),
                headers: {'Content-Type': 'application/json'}
            }).then(r=>r.json()).then(d=>{
                alert(d.message);
                e.target.reset();
                loadVehicles();
                loadStats();
            });
        });
        
        document.getElementById('stolenForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            fetch('/api/report_stolen', {
                method: 'POST',
                body: JSON.stringify(Object.fromEntries(formData)),
                headers: {'Content-Type': 'application/json'}
            }).then(r=>r.json()).then(d=>{
                alert(d.message + ' Police have been automatically alerted!');
                e.target.reset();
                loadStolen();
                loadStats();
            });
        });
        
        // Initial load
        loadStats();
        loadRecentTransactions();
        loadVehicles();
        loadStolen();
        
        // Auto refresh every 5 seconds
        setInterval(() => {
            loadStats();
            loadRecentTransactions();
        }, 5000);
    </script>
</body>
</html>
"""

# ================= AUTHENTICATION ROUTES =================
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
                flash(f'Welcome back, {username}!', 'success')
                return redirect(url_for('dashboard'))
        
        flash('Invalid username or password', 'danger')
    
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

# ================= API ROUTES =================
@app.route("/api/topup", methods=["POST"])
@login_required
def topup_balance():
    """Add money to vehicle account"""
    try:
        data = request.json
        vehicle_number = data.get('vehicle_number')
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({"message": "Amount must be greater than 0"}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"message": "Database error"}), 500
        
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE vehicles 
            SET balance = COALESCE(balance, 0) + %s 
            WHERE vehicle_number = %s AND status = 'active'
        """, (amount, vehicle_number))
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"message": f"Vehicle {vehicle_number} not found"}), 404
        
        cursor.execute("SELECT balance FROM vehicles WHERE vehicle_number = %s", (vehicle_number,))
        new_balance = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT INTO system_logs (action, username, details) 
            VALUES (%s, %s, %s)
        """, ("TOP_UP", session['username'], f"Added ${amount} to {vehicle_number}"))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            "message": f"✅ Successfully added ${amount} to {vehicle_number}",
            "new_balance": float(new_balance)
        })
        
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500

@app.route("/api/stats")
@login_required
def get_stats():
    conn = get_db_connection()
    if not conn:
        return jsonify({"vehicles":0, "today_transactions":0, "today_revenue":0, "stolen_alerts_today":0, "police_alerts_sent":0})
    
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vehicles WHERE status='active'")
    vehicles = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE DATE(time)=CURRENT_DATE")
    today_tx = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE DATE(time)=CURRENT_DATE")
    today_revenue = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM stolen_vehicles WHERE status='ACTIVE'")
    stolen_alerts = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM system_logs WHERE action='AUTOMATIC_POLICE_ALERT' AND DATE(timestamp)=CURRENT_DATE")
    police_alerts = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    return jsonify({
        "vehicles": vehicles, 
        "today_transactions": today_tx, 
        "today_revenue": float(today_revenue), 
        "stolen_alerts_today": stolen_alerts, 
        "police_alerts_sent": police_alerts
    })

@app.route("/api/transactions")
@login_required
def get_transactions():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT vehicle_number, amount, status, TO_CHAR(time, 'HH24:MI:SS') as time 
        FROM transactions 
        ORDER BY id DESC LIMIT 50
    """)
    data = [{"vehicle_number":r[0], "amount":float(r[1]), "status":r[2], "time":r[3]} for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route("/api/vehicles")
@login_required
def get_vehicles():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, vehicle_number, rfid_tag, owner_name, vehicle_type, COALESCE(balance,0) as balance FROM vehicles WHERE status='active'")
    data = [{"id":r[0], "vehicle_number":r[1], "rfid_tag":r[2], "owner_name":r[3], "vehicle_type":r[4], "balance":float(r[5])} for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route("/api/register_vehicle", methods=["POST"])
@login_required
def register_vehicle():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({"message":"Database error"})
    
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO vehicles (vehicle_number, rfid_tag, owner_name, vehicle_type, owner_phone, balance) 
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (data['vehicle_number'], data['rfid_tag'], data['owner_name'], data['vehicle_type'], 
          data.get('owner_phone', ''), float(data.get('initial_balance', 0))))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "✅ Vehicle registered successfully!"})

@app.route("/api/delete_vehicle", methods=["POST"])
@login_required
def delete_vehicle():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({"message":"Database error"})
    
    cursor = conn.cursor()
    cursor.execute("UPDATE vehicles SET status='deleted' WHERE id=%s", (data['id'],))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Deleted"})

@app.route("/api/report_stolen", methods=["POST"])
@login_required
def report_stolen():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({"message":"Database error"})
    
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO stolen_vehicles (vehicle_number, rfid_tag, owner_contact) 
        VALUES (%s, %s, %s)
    """, (data['vehicle_number'], data['rfid_tag'], data.get('owner_contact', '')))
    
    cursor.execute("UPDATE vehicles SET status='stolen' WHERE vehicle_number=%s", (data['vehicle_number'],))
    conn.commit()
    cursor.close()
    conn.close()
    
    send_police_alert(data['vehicle_number'], data['rfid_tag'], "Via Report Stolen", "VEHICLE MARKED STOLEN")
    
    return jsonify({"message": "🚨 Vehicle marked stolen! Police automatically alerted!"})

@app.route("/api/stolen_vehicles")
@login_required
def get_stolen():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT vehicle_number, rfid_tag, TO_CHAR(reported_date, 'YYYY-MM-DD') as reported_date
        FROM stolen_vehicles 
        WHERE status='ACTIVE'
    """)
    data = [{"vehicle_number":r[0], "rfid_tag":r[1], "reported_date":r[2]} for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route("/api/mark_recovered", methods=["POST"])
@login_required
def mark_recovered():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({"message":"Database error"})
    
    cursor = conn.cursor()
    cursor.execute("UPDATE stolen_vehicles SET status='RECOVERED' WHERE vehicle_number=%s", (data['vehicle_number'],))
    cursor.execute("UPDATE vehicles SET status='active' WHERE vehicle_number=%s", (data['vehicle_number'],))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Vehicle marked as recovered"})

@app.route("/api/alert_history")
@login_required
def get_alert_history():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TO_CHAR(timestamp, 'HH24:MI:SS') as time, details, action
        FROM system_logs 
        WHERE action IN ('AUTOMATIC_POLICE_ALERT', 'TOP_UP')
        ORDER BY timestamp DESC LIMIT 30
    """)
    data = [{"time":r[0], "vehicle_number":r[1].split()[-1] if r[1] else "Unknown", "alert_type":r[2], "status":"sent"} for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route("/api/rfid", methods=["POST"])
def handle_rfid():
    data = request.json
    
    # ── Validate input ──────────────────────────────────────────
    if not data or not data.get("rfid_tag"):
        return jsonify({"status": "ERROR", "reason": "No RFID tag provided"}), 400
    
    # Normalise tag: strip whitespace, uppercase — matches DB format
    rfid_tag = str(data.get("rfid_tag")).strip().upper()
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "ERROR", "reason": "Database unavailable"}), 500
    
    cursor = conn.cursor()
    
    try:
        # ── 1. STOLEN CHECK ─────────────────────────────────────
        cursor.execute("""
            SELECT vehicle_number 
            FROM stolen_vehicles 
            WHERE UPPER(TRIM(rfid_tag)) = %s 
            AND status = 'ACTIVE'
        """, (rfid_tag,))
        stolen = cursor.fetchone()
        
        if stolen:
            vehicle_number = stolen[0]
            # Record denied with ACTUAL toll amount (NO deduction from balance)
            cursor.execute("""
                INSERT INTO transactions 
                    (rfid_tag, vehicle_number, amount, status, time) 
                VALUES (%s, %s, %s, %s, NOW())
            """, (rfid_tag, vehicle_number, TOLL_AMOUNT, "DENIED-STOLEN"))
            conn.commit()
            
            send_police_alert(
                vehicle_number, rfid_tag,
                "Main Toll Plaza",
                "STOLEN VEHICLE ATTEMPTED TOLL PASSAGE"
            )
            return jsonify({
                "status": "DENIED",
                "reason": "STOLEN VEHICLE - POLICE AUTOMATICALLY ALERTED"
            })

        # ── 2. REGISTERED VEHICLE CHECK ─────────────────────────
        cursor.execute("""
            SELECT vehicle_number, owner_name, vehicle_type,
                   COALESCE(balance, 0) AS balance
            FROM vehicles
            WHERE UPPER(TRIM(rfid_tag)) = %s
            AND   LOWER(status) = 'active'
        """, (rfid_tag,))
        vehicle = cursor.fetchone()

        if not vehicle:
            # Unknown / unregistered — NO transaction record at all
            return jsonify({
                "status": "DENIED",
                "reason": "UNKNOWN VEHICLE - Not registered in system"
            })

        # ── 3. BALANCE CHECK ────────────────────────────────────
        vehicle_number, owner, vehicle_type, balance = vehicle

        # Toll pricing by vehicle type
        if vehicle_type and vehicle_type.lower() == "truck":
            price = round(TOLL_AMOUNT * 2, 2)
        elif vehicle_type and vehicle_type.lower() == "bus":
            price = round(TOLL_AMOUNT * 1.5, 2)
        else:
            price = round(TOLL_AMOUNT, 2)

        if balance < price:
            # ── INSUFFICIENT BALANCE — Record denied with actual amount, NO deduction ──
            cursor.execute("""
                INSERT INTO transactions 
                    (rfid_tag, vehicle_number, amount, status, time)
                VALUES (%s, %s, %s, %s, NOW())
            """, (rfid_tag, vehicle_number, price, "DENIED-INSUFFICIENT BALANCE"))
            conn.commit()
            return jsonify({
                "status": "DENIED",
                "reason": (
                    f"Insufficient balance. "
                    f"Toll fee: ${price:.2f} | "
                    f"Your balance: ${float(balance):.2f}"
                )
            })

        # ── 4. APPROVED — DEDUCT NOW ─────────────────────────────
        new_balance = round(float(balance) - price, 2)

        # Update balance
        cursor.execute("""
            UPDATE vehicles 
            SET balance = %s 
            WHERE UPPER(TRIM(rfid_tag)) = %s
        """, (new_balance, rfid_tag))

        # Log approved transaction with actual amount deducted
        cursor.execute("""
            INSERT INTO transactions 
                (rfid_tag, vehicle_number, amount, status, time)
            VALUES (%s, %s, %s, %s, NOW())
        """, (rfid_tag, vehicle_number, price, "APPROVED"))

        conn.commit()

        return jsonify({
            "status":            "APPROVED",
            "vehicle":           vehicle_number,
            "owner":             owner,
            "vehicle_type":      vehicle_type,
            "amount_deducted":   price,
            "balance_remaining": new_balance
        })

    except Exception as e:
        conn.rollback()
        print(f"❌ RFID handler error: {e}")
        return jsonify({
            "status": "ERROR",
            "reason": f"Server error: {str(e)}"
        }), 500

    finally:
        cursor.close()
        conn.close()

@app.route("/api/panic_alert", methods=["POST"])
def panic():
    send_police_alert("EMERGENCY", "PANIC_BUTTON", "Toll Management System", "PANIC BUTTON ACTIVATED - EMERGENCY")
    
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO system_logs (action, username, details) 
            VALUES (%s, %s, %s)
        """, ("PANIC_ALERT", "admin", "Emergency panic button activated - Police notified"))
        conn.commit()
        cursor.close()
        conn.close()
    return jsonify({"status": "panic_sent", "message": "Police have been notified!"})

@app.route("/api/alert_police", methods=["POST"])
def alert_police():
    data = request.json
    send_police_alert(data.get('vehicle_number'), data.get('rfid_tag', 'MANUAL'), "Via Dashboard", "MANUAL POLICE ALERT")
    
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO system_logs (action, username, details) 
            VALUES (%s, %s, %s)
        """, ("MANUAL_POLICE_ALERT", "admin", f"Manual alert for {data.get('vehicle_number')}"))
        conn.commit()
        cursor.close()
        conn.close()
    return jsonify({"status": "alert_sent", "message": "Police have been alerted!"})

if __name__ == "__main__":
    print("="*60)
    print("🚗 SMART TOLL SYSTEM WITH SUPABASE 🚨")
    print("="*60)
    print("💰 Toll Amount: $1.50 USD")
    print("="*60)
    print("\n✨ FEATURES:")
    print("   • Sidebar navigation menu")
    print("   • Add money directly from vehicles list")
    print("   • Telegram police alerts (only)")
    print("   • CORS enabled for external access")
    print("="*60)
    
    # Get port from environment variable (Render sets this automatically)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
