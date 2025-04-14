from flask import Flask, request, jsonify, send_from_directory 
import mysql.connector
import logging
import os
import uuid
from datetime import datetime, timedelta
import ShowScholarships  # Custom class to handle the logic
import ShowClgDetails
from Apply_Scholarship import ApplyScholarship
import ShowBankDetails
import ShowAlumni
import ShowStats
from utils import get_db_connection, validate_session, log_change_to_db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'CS'  # Update this in production

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='app.log',
    filemode='a'
)

# Database Configuration
db_config_proj = {
    "host": "10.0.116.125",
    "user": "cs432g16",
    "password": "LbNXp7Tz",
    "database": "cs432g16"
}

db_config_cism = {
    "host": "10.0.116.125",
    "user": "cs432g16", 
    "password": "LbNXp7Tz",
    "database": "cs432cims"
}

def get_db_connection(cims=True):
    """Establish a database connection."""
    if cims:
        return mysql.connector.connect(**db_config_cism)
    else:
        return mysql.connector.connect(**db_config_proj)

@app.route('/show_scholarship', methods=['GET'])
def show_scholarship():
    print(" /show_scholarship route hit")
    try:
        conn = get_db_connection(cims=False)
        print("Connected to cs432g16")
        scholarship = ShowScholarships.ShowScholarships(logging, conn)
        return scholarship.response()
    except Exception as e:
        print(f" ERROR in /show_scholarship: {e}")
        return f"<h3>Server Error: {e}</h3>", 500

@app.route('/', methods=['GET'])
def frontend():
    return send_from_directory(os.getcwd(), 'index.html')

@app.route('/api/hello', methods=['GET'])
def hello():
    return jsonify({"message": "Welcome to the Scholarship API"}), 200

@app.route('/show_colleges', methods=['GET'])
def show_colleges():
    college = ShowClgDetails.ShowClgDetails(logging, get_db_connection(cims=False))
    return college.response()

@app.route("/Apply_Scholarship", methods=["POST"])
def apply_scholarship():
    print(" /Apply_Scholarship route hit")
    try:
        conn = get_db_connection(cims=False)
        print("Connected to database")
        data = request.get_json()
        application = ApplyScholarship(logging, conn, data)
        return jsonify(application.response())
    except Exception as e:
        print(f"ERROR in /Apply_Scholarship: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route("/generate_app_id", methods=["GET"])
def generate_app_id():
    try:
        conn = get_db_connection(cims=False)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(Application_ID) FROM Application")  # Match your insert
        result = cursor.fetchone()
        next_id = (result[0] or 0) + 1
        cursor.close()
        return jsonify({"Application_ID": next_id})
    except Exception as e:
        print(f"Error generating application ID: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/create_member', methods=['POST'])
def create_member():
    data = request.get_json()

    username = data.get('username')
    memberid = data.get('id')         # Used as memberid in login table
    emailid = data.get('emailid')
    dob = data.get('dob')

    if not all([username, memberid, emailid, dob]):
        return jsonify({"error": "Missing fields"}), 400

    try:
        conn = get_db_connection(cims=True)  # Members table assumed in cs432cims
        cursor = conn.cursor()

        # Insert into Members table
        cursor.execute("""
            INSERT INTO members (UserName, ID, emailID, DoB)
            VALUES (%s, %s, %s, %s)
        """, (username, memberid, emailid, dob))

        # Insert default credentials into login table
        cursor.execute("""
            INSERT INTO Login (Password, MemberID, Session, Expiry, Role)
            VALUES (%s, %s, NULL, NULL, %s)
        """, ('admin123', memberid, 'admin'))

        conn.commit()
        return jsonify({"message": "Member and login created successfully"}), 201

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

@app.route('/authUser', methods=['POST'])
def auth_user():
    data = request.get_json()
    member_id = data.get('member_id')
    password = data.get('password')

    if not member_id or not password:
        return jsonify({"error": "Missing MemberID or Password"}), 400

    try:
        conn = get_db_connection(cims=True)
        cursor = conn.cursor(dictionary=True)

        # Validate credentials
        cursor.execute("SELECT * FROM Login WHERE MemberID = %s AND Password = %s", (member_id, password))
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Invalid MemberID or Password"}), 401

        # Generate new session token and expiry timestamp (as INT)
        session_token = str(uuid.uuid4())
        expiry_time = int((datetime.now() + timedelta(hours=1)).timestamp())

        # Update session in the login table
        cursor.execute("""
            UPDATE Login
            SET Session = %s, Expiry = %s
            WHERE MemberID = %s
        """, (session_token, expiry_time, member_id))
        conn.commit()

        return jsonify({
            "message": "Login successful",
            "session_token": session_token,
            "expiry": expiry_time,
            "role": user['Role']
        }), 200

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

# Helper function to check admin authorization
def is_admin_authorized(session_token):
    try:
        conn = get_db_connection(cims=True)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT Role FROM Login
            WHERE Session = %s AND Expiry > %s
        """, (session_token, int(datetime.now().timestamp())))

        result = cursor.fetchone()
        return result and result['Role'] == 'admin'

    except mysql.connector.Error as e:
        logging.error(f"Authorization check failed: {e}")
        return False

    finally:
        cursor.close()
        conn.close()

# ADMIN: Add a new member (similar to create_member but admin-authenticated)
@app.route('/admin/add_member', methods=['POST'])
def admin_add_member():
    session_token = request.headers.get('Authorization')
    if not is_admin_authorized(session_token):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    username = data.get('username')
    memberid = data.get('id')
    emailid = data.get('emailid')
    dob = data.get('dob')
    role = data.get('role', 'member')  # Optional role

    if not all([username, memberid, emailid, dob]):
        return jsonify({"error": "Missing fields"}), 400

    try:
        conn = get_db_connection(cims=True)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO members (UserName, ID, emailID, DoB)
            VALUES (%s, %s, %s, %s)
        """, (username, memberid, emailid, dob))

        cursor.execute("""
            INSERT INTO Login (Password, MemberID, Session, Expiry, Role)
            VALUES (%s, %s, NULL, NULL, %s)
        """, ('default123', memberid, role))

        conn.commit()
        return jsonify({"message": "Member added by admin successfully"}), 201

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

@app.route('/admin/access_data', methods=['GET'])
def admin_access_data():
    session_token = request.headers.get('Authorization')

    # Only allow access to admins
    if not is_admin_authorized(session_token):
        return jsonify({"error": "Unauthorized"}), 403

    try:
        # Example: fetch all members as sample protected data
        conn = get_db_connection(cims=True)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM members")
        data = cursor.fetchall()

        return jsonify({
            "message": "Admin access granted",
            "data": data
        }), 200

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()
# ADMIN: Delete a member
@app.route('/admin/delete_member/<member_id>', methods=['DELETE'])
def admin_delete_member(member_id):
    session_token = request.headers.get('Authorization')
    if not is_admin_authorized(session_token):
        return jsonify({"error": "Unauthorized"}), 403

    try:
        conn = get_db_connection(cims=True)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM Login WHERE MemberID = %s", (member_id,))
        cursor.execute("DELETE FROM members WHERE ID = %s", (member_id,))

        conn.commit()
        return jsonify({"message": f"Member {member_id} deleted successfully"}), 200

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

# ADMIN: Get all member details
@app.route('/admin/get_members', methods=['GET'])
def admin_get_members():
    session_token = request.headers.get('Authorization')
    if not is_admin_authorized(session_token):
        return jsonify({"error": "Unauthorized"}), 403

    try:
        conn = get_db_connection(cims=True)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM members")
        members = cursor.fetchall()

        return jsonify(members), 200

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

# ADMIN: Update member details
@app.route('/admin/update_member/<member_id>', methods=['PUT'])
def admin_update_member(member_id):
    session_token = request.headers.get('Authorization')
    if not is_admin_authorized(session_token):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    username = data.get('username')
    emailid = data.get('emailid')
    dob = data.get('dob')

    if not any([username, emailid, dob]):
        return jsonify({"error": "No update fields provided"}), 400

    try:
        conn = get_db_connection(cims=True)
        cursor = conn.cursor()

        if username:
            cursor.execute("UPDATE members SET UserName = %s WHERE ID = %s", (username, member_id))
        if emailid:
            cursor.execute("UPDATE members SET emailID = %s WHERE ID = %s", (emailid, member_id))
        if dob:
            cursor.execute("UPDATE members SET DoB = %s WHERE ID = %s", (dob, member_id))

        conn.commit()
        return jsonify({"message": f"Member {member_id} updated successfully"}), 200

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    memberID = data.get("memberID")
    password = data.get("password")

    if memberID == admin_credentials["memberID"] and password == admin_credentials["password"]:
        token = "dummy_admin_token"
        return jsonify({"message": "Login successful", "token": token, "role": "admin"})
    else:
        return jsonify({"error": "Invalid admin credentials"}), 401

# Dummy route to get members (only if token matches)
@app.route('/admin/get_members', methods=['GET'])
def get_members():
    token = request.headers.get("Authorization")
    if token != "dummy_admin_token":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        conn = get_db_connection(cims=True)  # Note: cims=True for cs432cims
        cursor = conn.cursor(dictionary=True)  # returns results as dicts

        cursor.execute("SELECT * FROM members")
        members = cursor.fetchall()

        cursor.close()
        conn.close()
        return jsonify(members)
    except Exception as e:
        print(f"Error fetching members: {e}")
        return jsonify({"error": "Failed to fetch members"}), 500

@app.route('/member.html')
def serve_member_page():
    return send_from_directory(os.getcwd(), 'member.html')

@app.route('/admin.html')
def serve_admin_page():
    return send_from_directory(os.getcwd(), 'admin.html')

@app.route('/show_bank_details', methods=['GET'])
def show_banks():
    college = ShowBankDetails.ShowBankDetails(logging, get_db_connection(cims=False))
    return college.response()



@app.route('/show_alumni_details', methods=['GET'])
def show_alumni():
    college = ShowAlumni.ShowAlumni(logging, get_db_connection(cims=False))
    return college.response()

@app.route('/show_stats_details', methods=['GET'])
def show_stats():
    college = ShowStats.ShowStats(logging, get_db_connection(cims=False))
    return college.response()


if __name__ == '__main__':
    try:
        conn = get_db_connection(cims=False)  # ⚠ Connect to correct DB
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE()")
        logging.info(f"Connected to database: {cursor.fetchone()[0]}")
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"DB connection failed on startup: {e}")

    app.run(debug=True)


