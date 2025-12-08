# from flask import Flask, render_template, request, redirect, url_for, session, flash
# import sqlite3
# import uuid
# from datetime import datetime

# app = Flask(__name__)
# app.secret_key = 'any_secret_word_you_want' 
# DB = "petcare.db"

# # Database Connection Helper
# def get_db_connection():   # 
#     conn = sqlite3.connect(DB)
#     conn.row_factory = sqlite3.Row
#     return conn



# # --- ADMIN MODULE (Feature 3) ---

# @app.route('/admin_dashboard')
# def admin_dashboard():
#     # 1. Security Check
#     if 'user_id' not in session or session.get('role') != 'admin':
#         flash("Access Denied: Admins only.")
#         return redirect(url_for('login')) 
    
#     conn = get_db_connection()
    
#     # 2. Fetch pending clinics using the correct Schema columns
#     # We look for role='clinic' and is_verified=0
#     pending_clinics = conn.execute(
#         'SELECT * FROM users WHERE role = ? AND is_verified = ?', 
#         ('clinic', 0)
#     ).fetchall()
    
#     conn.close()
    
#     # 3. Render the HTML template
#     return render_template('admin_dashboard.html', clinics=pending_clinics)

# @app.route('/approve_clinic/<int:user_id>')
# def approve_clinic(user_id):
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
        
#     conn = get_db_connection()
#     # Update is_verified to 1
#     conn.execute('UPDATE users SET is_verified = 1 WHERE id = ?', (user_id,))
#     conn.commit()
#     conn.close()
    
#     flash("Clinic Approved Successfully!")
#     return redirect(url_for('admin_dashboard'))

# @app.route('/reject_clinic/<int:user_id>')
# def reject_clinic(user_id):
#     if 'user_id' not in session or session.get('role') != 'admin':
#         return redirect(url_for('login'))
        
#     conn = get_db_connection()
#     # Delete the user from the database
#     conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
#     conn.commit()
#     conn.close()
    
#     flash("Clinic Rejected.")
#     return redirect(url_for('admin_dashboard'))

# # -------------------- FEATURE 11: SUBSCRIPTION & PAYMENT SYSTEM --------------------
# # import sqlite3
# # import uuid
# # from datetime import datetime, timedelta
# # from flask import request, jsonify


# # # Create tables (if not exists)
# # def init_subscription_tables():
# #     conn = sqlite3.connect(DB)
# #     c = conn.cursor()

# #     # subscriptions table
# #     c.execute("""
# #         CREATE TABLE IF NOT EXISTS subscriptions (
# #             id TEXT PRIMARY KEY,
# #             user_email TEXT,
# #             plan TEXT,
# #             status TEXT,
# #             start_date TEXT,
# #             end_date TEXT,
# #             created_at TEXT
# #         )
# #     """)

# #     # payments table
# #     c.execute("""
# #         CREATE TABLE IF NOT EXISTS payments (
# #             id TEXT PRIMARY KEY,
# #             subscription_id TEXT,
# #             provider TEXT,
# #             amount REAL,
# #             currency TEXT,
# #             status TEXT,
# #             provider_txn_id TEXT,
# #             created_at TEXT
# #         )
# #     """)

# #     conn.commit()
# #     conn.close()


# # # Run table creation (Flask 3.x safe)
# # with app.app_context():
# #     init_subscription_tables()



# # # -------- 1️⃣ CREATE SUBSCRIPTION (start payment) --------
# # @app.route("/subscriptions/create", methods=["POST"])
# # def create_subscription():
# #     data = request.json

# #     user_email = data["user_email"]
# #     plan = data["plan"]     # monthly or yearly
# #     provider = "bkash"

# #     if plan not in ["monthly", "yearly"]:
# #         return jsonify({"error": "Invalid plan"})

# #     # Determine price
# #     amount = 200 if plan == "monthly" else 2000

# #     # Create IDs
# #     subscription_id = uuid.uuid4().hex
# #     payment_id = uuid.uuid4().hex

# #     created_at = datetime.utcnow().isoformat()

# #     conn = sqlite3.connect(DB)
# #     c = conn.cursor()

# #     # Insert subscription (PENDING until payment completes)
# #     c.execute("""
# #         INSERT INTO subscriptions (id, user_email, plan, status, start_date, end_date, created_at)
# #         VALUES (?, ?, ?, 'pending', NULL, NULL, ?)
# #     """, (subscription_id, user_email, plan, created_at))

# #     # Insert payment entry (also PENDING)
# #     c.execute("""
# #         INSERT INTO payments (id, subscription_id, provider, amount, currency, status, provider_txn_id, created_at)
# #         VALUES (?, ?, ?, ?, 'BDT', 'pending', NULL, ?)
# #     """, (payment_id, subscription_id, provider, amount, created_at))

# #     conn.commit()
# #     conn.close()

# #     return jsonify({
# #         "subscription_id": subscription_id,
# #         "payment_id": payment_id,
# #         "amount": amount,
# #         "currency": "BDT",
# #         "status": "pending"
# #     })



# # # -------- 2️⃣ SIMULATE PAYMENT CALLBACK (pretend bKash calls backend) --------
# # @app.route("/payments/simulate_callback", methods=["POST"])
# # def simulate_payment_callback():
# #     data = request.json

# #     payment_id = data["payment_id"]
# #     provider_txn_id = data["provider_txn_id"]
# #     status = data["status"]  # paid / failed / cancelled

# #     if status not in ["paid", "failed", "cancelled"]:
# #         return jsonify({"error": "Invalid payment status"}), 400

# #     conn = sqlite3.connect(DB)
# #     conn.row_factory = sqlite3.Row
# #     c = conn.cursor()

# #     # Find payment
# #     c.execute("SELECT * FROM payments WHERE id=?", (payment_id,))
# #     payment = c.fetchone()

# #     if not payment:
# #         return jsonify({"error": "Payment not found"})

# #     subscription_id = payment["subscription_id"]

# #     # Update payment row
# #     c.execute("""
# #         UPDATE payments SET status=?, provider_txn_id=?
# #         WHERE id=?
# #     """, (status, provider_txn_id, payment_id))

# #     # If payment successful → activate subscription
# #     if status == "paid":
# #         c.execute("SELECT plan FROM subscriptions WHERE id=?", (subscription_id,))
# #         sub = c.fetchone()

# #         plan = sub["plan"]

# #         start = datetime.utcnow()
# #         end = start + timedelta(days=30 if plan == "monthly" else 365)

# #         c.execute("""
# #             UPDATE subscriptions
# #             SET status='active', start_date=?, end_date=?
# #             WHERE id=?
# #         """, (start.isoformat(), end.isoformat(), subscription_id))

# #     else:
# #         # failed/cancelled
# #         c.execute("""
# #             UPDATE subscriptions
# #             SET status='cancelled'
# #             WHERE id=?
# #         """, (subscription_id,))

# #     conn.commit()
# #     conn.close()

# #     return jsonify({"result": "ok", "payment_status": status})



# # # -------- 3️⃣ GET SUBSCRIPTION DETAILS --------
# # @app.route("/subscriptions/<subscription_id>", methods=["GET"])
# # def get_subscription(subscription_id):
# #     conn = sqlite3.connect(DB)
# #     conn.row_factory = sqlite3.Row
# #     c = conn.cursor()

# #     c.execute("SELECT * FROM subscriptions WHERE id=?", (subscription_id,))
# #     sub = c.fetchone()

# #     conn.close()

# #     if not sub:
# #         return jsonify({"error": "Subscription not found"})

# #     return jsonify(dict(sub))



# # # -------- 4️⃣ CANCEL SUBSCRIPTION --------
# # @app.route("/subscriptions/<subscription_id>/cancel", methods=["POST"])
# # def cancel_subscription(subscription_id):
# #     conn = sqlite3.connect(DB)
# #     c = conn.cursor()

# #     c.execute("SELECT id FROM subscriptions WHERE id=?", (subscription_id,))
# #     row = c.fetchone()

# #     if not row:
# #         return jsonify({"error": "Subscription not found"})

# #     c.execute("""
# #         UPDATE subscriptions
# #         SET status='cancelled', end_date=?
# #         WHERE id=?
# #     """, (datetime.utcnow().isoformat(), subscription_id))

# #     conn.commit()
# #     conn.close()

# #     return jsonify({"status": "cancelled", "subscription_id": subscription_id})
# # # -------------------- Run Server --------------------
# # if __name__ == "__main__":
# #     app.run(debug=True, port=1003)