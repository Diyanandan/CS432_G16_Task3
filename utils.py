# utils.py
import mysql.connector
import logging
from datetime import datetime

# Database configurations
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
    """Establish and return a DB connection."""
    config = db_config_cism if cims else db_config_proj
    return mysql.connector.connect(**config)

def validate_session(session_token):
    """
    Validate the session token in the centralized Login table.
    Returns the login row (as a dict) if valid, or None if invalid/expired.
    """
    try:
        conn = get_db_connection(cims=True)
        cursor = conn.cursor(dictionary=True)
        current_time = int(datetime.now().timestamp())
        cursor.execute(
            "SELECT * FROM Login WHERE Session = %s AND Expiry > %s",
            (session_token, current_time)
        )
        result = cursor.fetchone()
        return result
    except mysql.connector.Error as e:
        logging.error(f"Error validating session: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def is_admin(session_token):
    """Return True if the session token is valid and belongs to an admin."""
    login_row = validate_session(session_token)
    if login_row and login_row.get("Role", "").lower() == "admin":
        return True
    return False

def log_unauthorized_access(action, details):
    """Log unauthorized access attempts."""
    logging.warning(f"Unauthorized attempt for {action}: {details}")
