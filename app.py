from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
import mysql.connector
from datetime import datetime
import hashlib
import json
import os
import random

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'toll_system_secret_key_2025')

# ================= DATABASE CONFIGURATION FROM ENVIRONMENT =================
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_NAME = os.environ.get('DB_NAME', 'toll_system')

# ================= CURRENCY CONFIGURATION =================
TOLL_AMOUNT = float(os.environ.get('TOLL_AMOUNT', '1.50'))
CURRENCY_SYMBOL = "$"
CURRENCY_CODE = "USD"

# Database connection function with retry
def get_db_connection():
    try:
        db = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            autocommit=True,
            connect_timeout=10
        )
        return db
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

# Initialize database tables
def init_db():
    db = get_db_connection()
    if not db:
        print("❌ Cannot initialize database - check connection")
        return
    
    cursor = db.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            vehicle_number VARCHAR(50) UNIQUE,
            rfid_tag VARCHAR(100) UNIQUE,
            owner_name VARCHAR(100),
            vehicle_type VARCHAR(50),
            owner_phone VARCHAR(20),
            registered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            rfid_tag VARCHAR(100),
            vehicle_number VARCHAR(50),
            amount DECIMAL(10,2),
            status VARCHAR(50),
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stolen_vehicles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            vehicle_number VARCHAR(50),
            rfid_tag VARCHAR(100),
            owner_contact VARCHAR(20),
            reported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            action VARCHAR(100),
            user VARCHAR(50),
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE,
            password VARCHAR(255),
            role VARCHAR(20)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS traffic_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            vehicle_count INT,
            avg_speed FLOAT,
            peak_hour VARCHAR(10),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create default admin (password: admin123)
    cursor.execute("SELECT * FROM users WHERE username='admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                       ("admin", hashlib.sha256("admin123".encode()).hexdigest(), "admin"))
    
    db.commit()
    cursor.close()
    db.close()
    print("✅ Database initialized")

def process_rfid_scan(rfid_tag):
    db = get_db_connection()
    if not db:
        return {"status": "ERROR", "reason": "Database connection failed"}
    
    cursor = db.cursor()
    
    # Check if vehicle is stolen
    cursor.execute("SELECT vehicle_number FROM stolen_vehicles WHERE rfid_tag=%s", (rfid_tag,))
    stolen = cursor.fetchone()
    
    if stolen:
        vehicle_number = stolen[0]
        cursor.execute("""
            INSERT INTO transactions (rfid_tag, vehicle_number, amount, status) 
            VALUES (%s, %s, %s, %s)
        """, (rfid_tag, vehicle_number, TOLL_AMOUNT, "DENIED-STOLEN"))
        db.commit()
        
        cursor.execute("""
            INSERT INTO system_logs (action, user, details) 
            VALUES (%s, %s, %s)
        """, ("POLICE_ALERT", "SYSTEM", f"Stolen vehicle {vehicle_number} detected"))
        db.commit()
        
        cursor.close()
        db.close()
        return {"status": "DENIED", "reason": "STOLEN - POLICE ALERTED", "vehicle": vehicle_number}
    
    # Check if vehicle is registered
    cursor.execute("SELECT vehicle_number, owner_name, vehicle_type FROM vehicles WHERE rfid_tag=%s", (rfid_tag,))
    vehicle = cursor.fetchone()
    
    if vehicle:
        vehicle_number, owner, vehicle_type = vehicle
        
        price = TOLL_AMOUNT
        if vehicle_type == "Truck":
            price = TOLL_AMOUNT * 2
        elif vehicle_type == "Bus":
            price = TOLL_AMOUNT * 1.5
        
        cursor.execute("""
            INSERT INTO transactions (rfid_tag, vehicle_number, amount, status) 
            VALUES (%s, %s, %s, %s)
        """, (rfid_tag, vehicle_number, price, "PAID"))
        db.commit()
        
        cursor.close()
        db.close()
        return {"status": "APPROVED", "vehicle": vehicle_number, "owner": owner, "amount": price, "vehicle_type": vehicle_type}
    else:
        cursor.close()
        db.close()
        return {"status": "DENIED", "reason": "UNKNOWN VEHICLE"}

# Simple dashboard HTML (condensed for cloud)
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Smart Toll System</title>
    <style>
        body { font-family: Arial; background: #0a0e27; color: white; margin: 0; padding: 20px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center; font-size: 24px; }
        .container { max-width: 1200px; margin: auto; }
        .stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 20px; margin: 20px 0; }
        .card { background: #1a1f3e; padding: 20px; border-radius: 10px; text-align: center; }
        .card h2 { font-size: 32px; color: #667eea; }
        table { width: 100%; background: #1a1f3e; border-radius: 10px; padding: 20px; }
        th, td { padding: 10px; text-align: left; }
        th { color: #667eea; }
        .status-paid { color: #4ade80; }
        .status-denied { color: #f87171; }
        .panic-btn { position: fixed; bottom: 20px; right: 20px; background: #ef4444; padding: 15px 25px; border-radius: 50px; cursor: pointer; font-weight: bold; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab { background: #1a1f3e; padding: 10px 20px; border-radius: 10px; cursor: pointer; }
        .tab.active { background: #667eea; }
        input, select { width: 100%; padding: 10px; background: #0a0e27; border: 1px solid #2a2f4e; color: white; border-radius: 5px; margin-bottom: 10px; }
        button { background: #667eea; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
        .btn-danger { background: #ef4444; }
    </style>
</head>
<body>
    <div class="header">🚗 SMART TOLL SYSTEM - USD 💵</div>
    <div class="container">
        <div class="stats">
            <div class="card"><h2 id="vehicles">0</h2><p>Vehicles</p></div>
            <div class="card"><h2 id="today">0</h2><p>Today</p></div>
            <div class="card"><h2 id="revenue">$0</h2><p>Revenue</p></div>
            <div class="card"><h2 id="alerts">0</h2><p>Stolen Alerts</p></div>
        </div>
        
        <div class="tabs">
            <div class="tab active" onclick="showTab('transactions')">📊 Transactions</div>
            <div class="tab" onclick="showTab('vehicles')">🚗 Vehicles</div>
            <div class="tab" onclick="showTab('register')">📝 Register</div>
            <div class="tab" onclick="showTab('stolen')">⚠️ Stolen</div>
        </div>
        
        <div id="transactionsTab">
            <h3>Recent Transactions</h3>
            <table><thead><tr><th>Vehicle</th><th>Amount</th><th>Status</th><th>Time</th></tr></thead><tbody id="transactionsList"></tbody></table>
        </div>
        
        <div id="vehiclesTab" style="display:none;">
            <h3>Registered Vehicles</h3>
            <input type="text" id="searchInput" placeholder="Search..." onkeyup="searchVehicles()">
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
            <h3>Report Stolen</h3>
            <form id="stolenForm">
                <input type="text" name="vehicle_number" placeholder="Vehicle Number" required>
                <input type="text" name="rfid_tag" placeholder="RFID Tag" required>
                <button type="submit" class="btn-danger">Mark Stolen</button>
            </form>
            <br>
            <h3>Stolen Vehicles</h3>
            <table><thead><tr><th>Vehicle</th><th>RFID</th><th>Date</th><th>Action</th></tr></thead><tbody id="stolenList"></tbody></table>
        </div>
    </div>
    
    <div class="panic-btn" onclick="triggerPanic()">🚨 PANIC</div>
    
    <script>
        function showTab(tab) {
            document.getElementById('transactionsTab').style.display = 'none';
            document.getElementById('vehiclesTab').style.display = 'none';
            document.getElementById('registerTab').style.display = 'none';
            document.getElementById('stolenTab').style.display = 'none';
            document.getElementById(tab + 'Tab').style.display = 'block';
            if(tab === 'vehicles') loadVehicles();
            if(tab === 'stolen') loadStolen();
        }
        
        function loadStats() {
            fetch('/api/stats').then(r=>r.json()).then(d=>{
                document.getElementById('vehicles').innerText=d.vehicles;
                document.getElementById('today').innerText=d.today_transactions;
                document.getElementById('revenue').innerText='$'+d.today_revenue;
                document.getElementById('alerts').innerText=d.stolen_alerts_today;
            });
        }
        
        function loadTransactions() {
            fetch('/api/transactions').then(r=>r.json()).then(d=>{
                const tbody = document.getElementById('transactionsList');
                tbody.innerHTML = '';
                d.forEach(t=>{
                    tbody.innerHTML += `<tr><td>${t.vehicle_number}</td><td>$${t.amount}</td><td class="status-${t.status.toLowerCase().includes('paid')?'paid':'denied'}">${t.status}</td><td>${t.time}</td></tr>`;
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
                    tbody.innerHTML += `<tr><td>${s.vehicle_number}</td><td>${s.rfid_tag}</td><td>${s.reported_date}</td><td><button onclick="alertPolice('${s.vehicle_number}')" class="btn-danger">Alert Police</button></td></tr>`;
                });
            });
        }
        
        function deleteVehicle(id) {
            if(confirm('Delete?')) fetch('/api/delete_vehicle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})}).then(()=>loadVehicles());
        }
        
        function alertPolice(vehicle) {
            fetch('/api/alert_police',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vehicle_number:vehicle})}).then(()=>alert('Police alerted!'));
        }
        
        function triggerPanic() {
            if(confirm('EMERGENCY!')) fetch('/api/panic_alert',{method:'POST'}).then(()=>alert('Police notified!'));
        }
        
        function searchVehicles() {
            const search = document.getElementById('searchInput').value.toLowerCase();
            const rows = document.querySelectorAll('#vehiclesList tr');
            rows.forEach(row=>{row.style.display=row.innerText.toLowerCase().includes(search)?'':'none';});
        }
        
        document.getElementById('registerForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            fetch('/api/register_vehicle', {method:'POST',body:JSON.stringify(Object.fromEntries(formData)),headers:{'Content-Type':'application/json'}}).then(r=>r.json()).then(d=>alert(d.message));
        });
        
        document.getElementById('stolenForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            fetch('/api/report_stolen', {method:'POST',body:JSON.stringify(Object.fromEntries(formData)),headers:{'Content-Type':'application/json'}}).then(r=>r.json()).then(d=>{alert(d.message);loadStolen();});
        });
        
        loadStats(); loadTransactions(); loadStolen();
        setInterval(()=>{loadStats(); loadTransactions();}, 5000);
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
    db = get_db_connection()
    if not db:
        return jsonify({"vehicles":0, "today_transactions":0, "today_revenue":0, "stolen_alerts_today":0})
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    vehicles = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE DATE(time)=CURDATE()")
    today_tx = cursor.fetchone()[0]
    cursor.execute("SELECT IFNULL(SUM(amount),0) FROM transactions WHERE DATE(time)=CURDATE()")
    today_revenue = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM system_logs WHERE action='POLICE_ALERT' AND DATE(timestamp)=CURDATE()")
    stolen_alerts = cursor.fetchone()[0]
    cursor.close()
    db.close()
    return jsonify({"vehicles":vehicles, "today_transactions":today_tx, "today_revenue":float(today_revenue), "stolen_alerts_today":stolen_alerts})

@app.route("/api/transactions")
def get_transactions():
    db = get_db_connection()
    if not db:
        return jsonify([])
    cursor = db.cursor()
    cursor.execute("SELECT vehicle_number, amount, status, DATE_FORMAT(time, '%H:%i:%s') FROM transactions ORDER BY id DESC LIMIT 20")
    data = [{"vehicle_number":r[0], "amount":float(r[1]), "status":r[2], "time":r[3]} for r in cursor.fetchall()]
    cursor.close()
    db.close()
    return jsonify(data)

@app.route("/api/vehicles")
def get_vehicles():
    db = get_db_connection()
    if not db:
        return jsonify([])
    cursor = db.cursor()
    cursor.execute("SELECT id, vehicle_number, rfid_tag, owner_name, vehicle_type FROM vehicles")
    data = [{"id":r[0], "vehicle_number":r[1], "rfid_tag":r[2], "owner_name":r[3], "vehicle_type":r[4]} for r in cursor.fetchall()]
    cursor.close()
    db.close()
    return jsonify(data)

@app.route("/api/register_vehicle", methods=["POST"])
def register_vehicle():
    data = request.json
    db = get_db_connection()
    if not db:
        return jsonify({"message":"Database error"})
    cursor = db.cursor()
    cursor.execute("INSERT INTO vehicles (vehicle_number, rfid_tag, owner_name, vehicle_type, owner_phone) VALUES (%s,%s,%s,%s,%s)",
                   (data['vehicle_number'], data['rfid_tag'], data['owner_name'], data['vehicle_type'], data.get('owner_phone', '')))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Vehicle registered!"})

@app.route("/api/delete_vehicle", methods=["POST"])
def delete_vehicle():
    data = request.json
    db = get_db_connection()
    if not db:
        return jsonify({"message":"Database error"})
    cursor = db.cursor()
    cursor.execute("DELETE FROM vehicles WHERE id=%s", (data['id'],))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Deleted"})

@app.route("/api/report_stolen", methods=["POST"])
def report_stolen():
    data = request.json
    db = get_db_connection()
    if not db:
        return jsonify({"message":"Database error"})
    cursor = db.cursor()
    cursor.execute("INSERT INTO stolen_vehicles (vehicle_number, rfid_tag, owner_contact) VALUES (%s,%s,%s)",
                   (data['vehicle_number'], data['rfid_tag'], data.get('owner_contact', '')))
    cursor.execute("DELETE FROM vehicles WHERE vehicle_number=%s", (data['vehicle_number'],))
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "Vehicle marked stolen!"})

@app.route("/api/stolen_vehicles")
def get_stolen():
    db = get_db_connection()
    if not db:
        return jsonify([])
    cursor = db.cursor()
    cursor.execute("SELECT vehicle_number, rfid_tag, DATE(reported_date) FROM stolen_vehicles")
    data = [{"vehicle_number":r[0], "rfid_tag":r[1], "reported_date":str(r[2])} for r in cursor.fetchall()]
    cursor.close()
    db.close()
    return jsonify(data)

@app.route("/api/stolen_alerts")
def get_stolen_alerts():
    db = get_db_connection()
    if not db:
        return jsonify([])
    cursor = db.cursor()
    cursor.execute("""
        SELECT vehicle_number, DATE_FORMAT(time, '%H:%i:%s') 
        FROM transactions 
        WHERE status='DENIED-STOLEN' AND time > DATE_SUB(NOW(), INTERVAL 1 HOUR)
        ORDER BY time DESC
    """)
    data = [{"vehicle_number":r[0], "time":r[1]} for r in cursor.fetchall()]
    cursor.close()
    db.close()
    return jsonify(data)

@app.route("/api/rfid", methods=["POST"])
def handle_rfid():
    data = request.json
    result = process_rfid_scan(data.get("rfid_tag"))
    return jsonify(result)

@app.route("/api/panic_alert", methods=["POST"])
def panic():
    db = get_db_connection()
    if db:
        cursor = db.cursor()
        cursor.execute("INSERT INTO system_logs (action, user, details) VALUES (%s,%s,%s)",
                       ("PANIC_ALERT", "admin", "Emergency panic button activated"))
        db.commit()
        cursor.close()
        db.close()
    return jsonify({"status": "panic_sent"})

@app.route("/api/alert_police", methods=["POST"])
def alert_police():
    data = request.json
    db = get_db_connection()
    if db:
        cursor = db.cursor()
        cursor.execute("INSERT INTO system_logs (action, user, details) VALUES (%s,%s,%s)",
                       ("MANUAL_POLICE_ALERT", "admin", f"Alert for {data.get('vehicle_number')}"))
        db.commit()
        cursor.close()
        db.close()
    return jsonify({"status": "alert_sent"})

if __name__ == "__main__":
    # Initialize database on startup
    print("="*60)
    print("🚗 SMART TOLL SYSTEM - Starting...")
    print("="*60)
    init_db()
    print("✅ Database ready")
    print("📱 Dashboard will be available at http://localhost:5000")
    print("="*60)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)