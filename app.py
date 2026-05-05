from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
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

# ================= AUTOMATIC POLICE ALERT FUNCTION =================
def send_police_alert(vehicle_number, rfid_tag, location="Toll Plaza", reason="STOLEN VEHICLE DETECTED"):
    """Send automatic alerts to police via multiple channels"""
    
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
    
    # Method 1: Telegram Bot
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
    
    # Method 2: Email
    if SENDER_EMAIL and SENDER_PASSWORD and POLICE_EMAIL:
        try:
            msg = MIMEText(message)
            msg['Subject'] = f'🚨 POLICE ALERT - Stolen Vehicle {vehicle_number}'
            msg['From'] = SENDER_EMAIL
            msg['To'] = POLICE_EMAIL
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
            print(f"✅ Email alert sent for {vehicle_number}")
            alert_sent = True
        except Exception as e:
            print(f"Email failed: {e}")
    
    # Method 3: SMS via Email Gateway
    if POLICE_SMS_EMAIL and SENDER_EMAIL and SENDER_PASSWORD:
        try:
            sms_msg = MIMEText(f"ALERT: Stolen vehicle {vehicle_number} at {location}!")
            sms_msg['Subject'] = 'POLICE ALERT'
            sms_msg['From'] = SENDER_EMAIL
            sms_msg['To'] = POLICE_SMS_EMAIL
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(sms_msg)
            server.quit()
            print(f"✅ SMS alert sent for {vehicle_number}")
            alert_sent = True
        except Exception as e:
            print(f"SMS failed: {e}")
    
    # Method 4: Webhook
    if POLICE_WEBHOOK_URL:
        try:
            webhook_data = {
                "alert_type": "stolen_vehicle",
                "vehicle_number": vehicle_number,
                "rfid_tag": rfid_tag,
                "location": location,
                "timestamp": alert_time,
                "severity": "HIGH"
            }
            requests.post(POLICE_WEBHOOK_URL, json=webhook_data, timeout=5)
            print(f"✅ Webhook alert sent for {vehicle_number}")
            alert_sent = True
        except Exception as e:
            print(f"Webhook failed: {e}")
    
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

# ================= ENHANCED DASHBOARD HTML =================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Smart Toll System - Police Alerts</title>
    <style>
        body { font-family: Arial; background: #0a0e27; color: white; margin: 0; padding: 20px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center; font-size: 24px; }
        .container { max-width: 1200px; margin: auto; }
        .stats { display: grid; grid-template-columns: repeat(5,1fr); gap: 20px; margin: 20px 0; }
        .card { background: #1a1f3e; padding: 20px; border-radius: 10px; text-align: center; }
        .card h2 { font-size: 32px; color: #667eea; }
        .alert-card { background: #1a1f3e; padding: 20px; border-radius: 10px; text-align: center; border: 2px solid #ef4444; }
        .alert-card h2 { font-size: 32px; color: #ef4444; }
        table { width: 100%; background: #1a1f3e; border-radius: 10px; padding: 20px; }
        th, td { padding: 10px; text-align: left; }
        th { color: #667eea; }
        .status-paid { color: #4ade80; }
        .status-denied { color: #f87171; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab { background: #1a1f3e; padding: 10px 20px; border-radius: 10px; cursor: pointer; }
        .tab.active { background: #667eea; }
        input, select { width: 100%; padding: 10px; background: #0a0e27; border: 1px solid #2a2f4e; color: white; border-radius: 5px; margin-bottom: 10px; }
        button { background: #667eea; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
        .btn-danger { background: #ef4444; }
        .btn-warning { background: #f59e0b; }
        .panic-btn { position: fixed; bottom: 20px; right: 20px; background: #ef4444; padding: 15px 25px; border-radius: 50px; cursor: pointer; font-weight: bold; animation: pulse 1s infinite; }
        @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
        .alert-notification { position: fixed; top: 20px; right: 20px; background: #ef4444; padding: 15px; border-radius: 10px; z-index: 1000; max-width: 350px; border-left: 5px solid #ff0000; animation: slideIn 0.3s ease; }
        @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    </style>
</head>
<body>
    <div class="header">🚗 SMART TOLL SYSTEM WITH AUTOMATIC POLICE ALERTS 🚨</div>
    <div class="container">
        <div class="stats">
            <div class="card"><h2 id="vehicles">0</h2><p>Vehicles</p></div>
            <div class="card"><h2 id="today">0</h2><p>Today's Transactions</p></div>
            <div class="card"><h2 id="revenue">$0</h2><p>Revenue</p></div>
            <div class="alert-card"><h2 id="alerts">0</h2><p>Alerts Today</p></div>
            <div class="alert-card"><h2 id="policeAlerts">0</h2><p>Police Notified</p></div>
        </div>
        
        <div class="tabs">
            <div class="tab active" onclick="showTab('transactions')">📊 Transactions</div>
            <div class="tab" onclick="showTab('vehicles')">🚗 Vehicles</div>
            <div class="tab" onclick="showTab('register')">📝 Register</div>
            <div class="tab" onclick="showTab('stolen')">⚠️ Stolen Vehicles</div>
            <div class="tab" onclick="showTab('alerts')">🚨 Police Alerts Log</div>
        </div>
        
        <div id="transactionsTab">
            <h3>Recent Transactions</h3>
            <table><thead><tr><th>Vehicle</th><th>Amount</th><th>Status</th><th>Time</th></tr></thead><tbody id="transactionsList"></tbody></table>
        </div>
        
        <div id="vehiclesTab" style="display:none;">
            <h3>Registered Vehicles</h3>
            <input type="text" id="searchInput" placeholder="Search...">
            <table><thead><tr><th>Vehicle</th><th>RFID</th><th>Owner</th><th>Type</th><th>Action</th></tr></thead><tbody id="vehiclesList"></tbody></table>
        </div>
        
        <div id="registerTab" style="display:none;">
            <h3>Register Vehicle</h3>
            <form id="registerForm">
                <input type="text" name="vehicle_number" placeholder="Vehicle Number" required>
                <input type="text" name="rfid_tag" placeholder="RFID Tag" required>
                <input type="text" name="owner_name" placeholder="Owner Name" required>
                <select name="vehicle_type"><option>Car</option><option>Bus</option><option>Truck</option><option>Bike</option></select>
                <button type="submit">Register</button>
            </form>
        </div>
        
        <div id="stolenTab" style="display:none;">
            <h3>⚠️ Report Stolen Vehicle (Automatic Police Alert will be sent)</h3>
            <form id="stolenForm">
                <input type="text" name="vehicle_number" placeholder="Vehicle Number" required>
                <input type="text" name="rfid_tag" placeholder="RFID Tag" required>
                <input type="text" name="owner_contact" placeholder="Owner Contact">
                <button type="submit" class="btn-danger">Report Stolen - Alert Police</button>
            </form>
            <br>
            <h3>Stolen Vehicles List (Active Alerts)</h3>
            <table><thead><tr><th>Vehicle</th><th>RFID</th><th>Date</th><th>Status</th><th>Action</th></tr></thead><tbody id="stolenList"></tbody></table>
        </div>
        
        <div id="alertsTab" style="display:none;">
            <h3>📋 Police Alert History</h3>
            <table><thead><tr><th>Time</th><th>Vehicle</th><th>Alert Type</th><th>Status</th><th>Acknowledged</th></tr></thead><tbody id="alertsList"></tbody></table>
        </div>
    </div>
    
    <div class="panic-btn" onclick="triggerPanic()">🚨 PANIC - ALERT POLICE 🚨</div>
    
    <script>
        let lastAlertCount = 0;
        
        function checkStolenAlerts() {
            fetch('/api/stolen_alerts')
                .then(res => res.json())
                .then(data => {
                    if(data.length > lastAlertCount) {
                        const newAlerts = data.slice(lastAlertCount);
                        newAlerts.forEach(alert => {
                            showPoliceNotification(alert.vehicle_number, alert.time);
                        });
                    }
                    lastAlertCount = data.length;
                });
        }
        
        function showPoliceNotification(vehicle, time) {
            const notification = document.createElement('div');
            notification.className = 'alert-notification';
            notification.innerHTML = `
                <strong>🚨 AUTOMATIC POLICE ALERT 🚨</strong><br>
                <strong>Vehicle:</strong> ${vehicle}<br>
                <strong>Time:</strong> ${time}<br>
                <strong>Status:</strong> STOLEN VEHICLE DETECTED<br>
                <strong>Action:</strong> Police have been notified automatically!<br>
                <button onclick="this.parentElement.remove()" style="margin-top:10px;">Acknowledge</button>
            `;
            document.body.appendChild(notification);
            
            const audio = new Audio('data:audio/wav;base64,U3RlYWx0aCBzb3VuZA==');
            audio.play().catch(e => console.log);
            
            if (Notification.permission === "granted") {
                new Notification("🚨 POLICE ALERT!", {
                    body: `Stolen vehicle ${vehicle} detected at toll plaza! Police notified.`,
                    icon: "https://cdn-icons-png.flaticon.com/512/190/190411.png"
                });
            }
            
            setTimeout(() => notification.remove(), 15000);
        }
        
        function showTab(tab) {
            document.getElementById('transactionsTab').style.display = 'none';
            document.getElementById('vehiclesTab').style.display = 'none';
            document.getElementById('registerTab').style.display = 'none';
            document.getElementById('stolenTab').style.display = 'none';
            document.getElementById('alertsTab').style.display = 'none';
            document.getElementById(tab + 'Tab').style.display = 'block';
            if(tab === 'vehicles') loadVehicles();
            if(tab === 'stolen') loadStolen();
            if(tab === 'alerts') loadAlertHistory();
        }
        
        function loadStats() {
            fetch('/api/stats').then(r=>r.json()).then(d=>{
                document.getElementById('vehicles').innerText=d.vehicles;
                document.getElementById('today').innerText=d.today_transactions;
                document.getElementById('revenue').innerText='$'+d.today_revenue;
                document.getElementById('alerts').innerText=d.stolen_alerts_today;
                document.getElementById('policeAlerts').innerText=d.police_alerts_sent || 0;
            });
        }
        
        function loadTransactions() {
            fetch('/api/transactions').then(r=>r.json()).then(d=>{
                const tbody = document.getElementById('transactionsList');
                tbody.innerHTML = '';
                d.forEach(t=>{
                    const statusClass = t.status.toLowerCase().includes('stolen') ? 'status-denied' : 'status-paid';
                    tbody.innerHTML += `<tr><td>${t.vehicle_number}</td><td>$${t.amount}</td><td class="${statusClass}">${t.status}</td><td>${t.time}</td></tr>`;
                });
            });
        }
        
        function loadVehicles() {
            fetch('/api/vehicles').then(r=>r.json()).then(d=>{
                const tbody = document.getElementById('vehiclesList');
                tbody.innerHTML = '';
                d.forEach(v=>{
                    tbody.innerHTML += `<tr><td>${v.vehicle_number}</td><td>${v.rfid_tag}</td><td>${v.owner_name||'-'}</td><td>${v.vehicle_type||'-'}</td><td><button onclick="deleteVehicle(${v.id})" class="btn-danger">Delete</button></td></tr>`;
                });
            });
        }
        
        function loadStolen() {
            fetch('/api/stolen_vehicles').then(r=>r.json()).then(d=>{
                const tbody = document.getElementById('stolenList');
                tbody.innerHTML = '';
                d.forEach(s=>{
                    tbody.innerHTML += `<tr><td>${s.vehicle_number}</td><td>${s.rfid_tag}</td><td>${s.reported_date}</td><td><span class="status-denied">ACTIVE ALERT</span></td><td><button onclick="markRecovered('${s.vehicle_number}')" class="btn-warning">Mark Recovered</button></td></tr>`;
                });
            });
        }
        
        function loadAlertHistory() {
            fetch('/api/alert_history').then(r=>r.json()).then(d=>{
                const tbody = document.getElementById('alertsList');
                tbody.innerHTML = '';
                d.forEach(a=>{
                    tbody.innerHTML += `<tr><td>${a.time}</td><td>${a.vehicle_number}</td><td>${a.alert_type}</td><td><span class="${a.status === 'sent' ? 'status-paid' : 'status-denied'}">${a.status}</span></td><td>${a.acknowledged ? '✅ Yes' : '⏳ Pending'}</td></tr>`;
                });
            });
        }
        
        function markRecovered(vehicle) {
            if(confirm(`Mark ${vehicle} as recovered? Police alert will be cancelled.`)) {
                fetch('/api/mark_recovered', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({vehicle_number: vehicle})
                }).then(() => loadStolen());
            }
        }
        
        function deleteVehicle(id) {
            if(confirm('Delete this vehicle?')) {
                fetch('/api/delete_vehicle', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:id})})
                .then(()=>loadVehicles());
            }
        }
        
        function triggerPanic() {
            if(confirm('🚨 EMERGENCY PANIC! This will alert ALL police units! 🚨')) {
                fetch('/api/panic_alert', {method:'POST'})
                .then(()=>{
                    showPoliceNotification('EMERGENCY PANIC', new Date().toLocaleTimeString());
                    alert('Police have been notified of emergency!');
                });
            }
        }
        
        function searchVehicles() {
            const search = document.getElementById('searchInput').value.toLowerCase();
            const rows = document.querySelectorAll('#vehiclesList tr');
            rows.forEach(row=>{row.style.display=row.innerText.toLowerCase().includes(search)?'': 'none';});
        }
        
        document.getElementById('registerForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            fetch('/api/register_vehicle', {method:'POST', body:JSON.stringify(Object.fromEntries(formData)), headers:{'Content-Type':'application/json'}})
            .then(r=>r.json()).then(d=>alert(d.message));
        });
        
        document.getElementById('stolenForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            fetch('/api/report_stolen', {method:'POST', body:JSON.stringify(Object.fromEntries(formData)), headers:{'Content-Type':'application/json'}})
            .then(r=>r.json()).then(d=>{
                alert(d.message + ' Police have been automatically alerted!');
                loadStolen();
            });
        });
        
        if (Notification.permission === "default") {
            Notification.requestPermission();
        }
        
        loadStats(); loadTransactions(); loadStolen();
        setInterval(()=>{loadStats(); loadTransactions(); checkStolenAlerts();}, 3000);
        checkStolenAlerts();
    </script>
</body>
</html>
"""

# ================= API ROUTES =================
@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/stats")
def get_stats():
    conn = get_db_connection()
    if not conn:
        return jsonify({"vehicles":0, "today_transactions":0, "today_revenue":0, "stolen_alerts_today":0, "police_alerts_sent":0})
    
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    vehicles = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE DATE(time)=CURRENT_DATE")
    today_tx = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE DATE(time)=CURRENT_DATE")
    today_revenue = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM system_logs WHERE action='POLICE_ALERT' AND DATE(timestamp)=CURRENT_DATE")
    stolen_alerts = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM system_logs WHERE action='AUTOMATIC_POLICE_ALERT' AND DATE(timestamp)=CURRENT_DATE")
    police_alerts = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    return jsonify({"vehicles":vehicles, "today_transactions":today_tx, "today_revenue":float(today_revenue), "stolen_alerts_today":stolen_alerts, "police_alerts_sent":police_alerts})

@app.route("/api/transactions")
def get_transactions():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT vehicle_number, amount, status, TO_CHAR(time, 'HH24:MI:SS') 
        FROM transactions 
        ORDER BY id DESC LIMIT 20
    """)
    data = [{"vehicle_number":r[0], "amount":float(r[1]), "status":r[2], "time":r[3]} for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route("/api/vehicles")
def get_vehicles():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, vehicle_number, rfid_tag, owner_name, vehicle_type FROM vehicles")
    data = [{"id":r[0], "vehicle_number":r[1], "rfid_tag":r[2], "owner_name":r[3], "vehicle_type":r[4]} for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route("/api/register_vehicle", methods=["POST"])
def register_vehicle():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({"message":"Database error"})
    
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO vehicles (vehicle_number, rfid_tag, owner_name, vehicle_type, owner_phone) 
        VALUES (%s, %s, %s, %s, %s)
    """, (data['vehicle_number'], data['rfid_tag'], data['owner_name'], data['vehicle_type'], data.get('owner_phone', '')))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Vehicle registered!"})

@app.route("/api/delete_vehicle", methods=["POST"])
def delete_vehicle():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({"message":"Database error"})
    
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vehicles WHERE id=%s", (data['id'],))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Deleted"})

@app.route("/api/report_stolen", methods=["POST"])
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
    
    cursor.execute("DELETE FROM vehicles WHERE vehicle_number=%s", (data['vehicle_number'],))
    conn.commit()
    cursor.close()
    conn.close()
    
    send_police_alert(data['vehicle_number'], data['rfid_tag'], "Via Report Stolen", "VEHICLE MARKED STOLEN")
    
    return jsonify({"message": "Vehicle marked stolen! Police have been automatically alerted."})

@app.route("/api/stolen_vehicles")
def get_stolen():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT vehicle_number, rfid_tag, TO_CHAR(reported_date, 'YYYY-MM-DD') 
        FROM stolen_vehicles 
        WHERE status='ACTIVE'
    """)
    data = [{"vehicle_number":r[0], "rfid_tag":r[1], "reported_date":str(r[2])} for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route("/api/stolen_alerts")
def get_stolen_alerts():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT vehicle_number, TO_CHAR(time, 'HH24:MI:SS') 
        FROM transactions 
        WHERE status='DENIED-STOLEN' AND time > NOW() - INTERVAL '1 hour'
        ORDER BY time DESC
    """)
    data = [{"vehicle_number":r[0], "time":r[1]} for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route("/api/alert_history")
def get_alert_history():
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TO_CHAR(timestamp, 'HH24:MI:SS'), details, action, 'sent' as status, false as acknowledged
        FROM system_logs 
        WHERE action IN ('POLICE_ALERT', 'AUTOMATIC_POLICE_ALERT')
        ORDER BY timestamp DESC LIMIT 20
    """)
    data = [{"time":r[0], "vehicle_number":r[1].split()[-1] if r[1] else "Unknown", "alert_type":r[2], "status":r[3], "acknowledged":r[4]} for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route("/api/mark_recovered", methods=["POST"])
def mark_recovered():
    data = request.json    conn = get_db_connection()
    if not conn:
        return jsonify({"message":"Database error"})
    
    cursor = conn.cursor()
    cursor.execute("UPDATE stolen_vehicles SET status='RECOVERED' WHERE vehicle_number=%s", (data['vehicle_number'],))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Vehicle marked as recovered"})

@app.route("/api/rfid", methods=["POST"])
def handle_rfid():
    data = request.json
    rfid_tag = data.get("rfid_tag")
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "ERROR", "reason": "Database unavailable"})
    
    cursor = conn.cursor()
    
    # Check if stolen
    cursor.execute("SELECT vehicle_number FROM stolen_vehicles WHERE rfid_tag=%s AND status='ACTIVE'", (rfid_tag,))
    stolen = cursor.fetchone()
    if stolen:
        vehicle_number = stolen[0]
        cursor.execute("""
            INSERT INTO transactions (rfid_tag, vehicle_number, amount, status) 
            VALUES (%s, %s, %s, %s)
        """, (rfid_tag, vehicle_number, TOLL_AMOUNT, "DENIED-STOLEN"))
        conn.commit()
        cursor.close()
        conn.close()
        
        send_police_alert(vehicle_number, rfid_tag, "Main Toll Plaza", "STOLEN VEHICLE ATTEMPTED TOLL PASSAGE")
        
        return jsonify({"status": "DENIED", "reason": "STOLEN VEHICLE - POLICE AUTOMATICALLY ALERTED"})
    
    # Check if registered with balance
    cursor.execute("""
        SELECT vehicle_number, owner_name, vehicle_type, COALESCE(balance, 0) as balance 
        FROM vehicles 
        WHERE rfid_tag=%s
    """, (rfid_tag,))
    vehicle = cursor.fetchone()
    
    if vehicle:
        vehicle_number, owner, vehicle_type, balance = vehicle
        price = TOLL_AMOUNT * 2 if vehicle_type == "Truck" else TOLL_AMOUNT * 1.5 if vehicle_type == "Bus" else TOLL_AMOUNT
        
        # Check balance
        if balance < price:
            cursor.execute("""
                INSERT INTO transactions (rfid_tag, vehicle_number, amount, status) 
                VALUES (%s, %s, %s, %s)
            """, (rfid_tag, vehicle_number, price, "INSUFFICIENT_BALANCE"))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({
                "status": "DENIED", 
                "reason": f"Insufficient balance. Need ${price}, have ${balance}"
            })
        
        # Sufficient balance - deduct amount
        new_balance = balance - price
        cursor.execute("UPDATE vehicles SET balance = %s WHERE rfid_tag = %s", (new_balance, rfid_tag))
        
        cursor.execute("""
            INSERT INTO transactions (rfid_tag, vehicle_number, amount, status) 
            VALUES (%s, %s, %s, %s)
        """, (rfid_tag, vehicle_number, price, "PAID"))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            "status": "APPROVED", 
            "vehicle": vehicle_number, 
            "amount": price, 
            "vehicle_type": vehicle_type,
            "balance_remaining": new_balance
        })
    else:
        cursor.close()
        conn.close()
        return jsonify({"status": "DENIED", "reason": "UNKNOWN VEHICLE"})

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
    print("📱 Access Dashboard: http://localhost:5000")
    print("🔑 Login: admin / admin123")
    print("💰 Toll Amount: $1.50 USD")
    print("="*60)
    print("\n🚨 AUTOMATIC POLICE ALERT SYSTEM ACTIVE!")
    print("   • Stolen vehicles trigger automatic police alerts")
    print("   • Telegram/Email/SMS notifications supported")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
