from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
from datetime import datetime
import os
import collections

# Import custom modules
from database import get_db_connection, init_db, DB_FILE, hash_password, generate_id
from ml_model import predict_student_outcome

app = Flask(__name__)
# Enable CORS for all routes so frontend can call the API during development
CORS(app)

frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Run initialization to ensure DB exists and is seeded
if not os.path.exists(DB_FILE):
    init_db()

# ==========================================
# AUTH ENDPOINTS
# ==========================================

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    
    # Required fields for all users
    required = ['name', 'email', 'password', 'role', 'department']
    if not all(k in data for k in required):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
    conn = get_db_connection()
    c = conn.cursor()
    
    # Check if email exists
    c.execute('SELECT id FROM users WHERE email = ?', (data['email'],))
    if c.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Email already registered'}), 409
        
    user_id = generate_id()
    now_str = datetime.now().isoformat()
    
    # Optional fields based on role
    rollNo = data.get('rollNo', None)
    semester = data.get('semester', None)
    subject = data.get('subject', None)
    
    try:
        c.execute('''
            INSERT INTO users (id, name, email, password, role, department, rollNo, semester, subject, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, data['name'], data['email'], hash_password(data['password']), 
              data['role'], data['department'], rollNo, semester, subject, now_str))
        conn.commit()
        
        # Return user object without password
        c.execute('SELECT id, name, email, role, department, rollNo, semester, subject FROM users WHERE id = ?', (user_id,))
        user = dict(c.fetchone())
        return jsonify({'success': True, 'user': user}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    if 'email' not in data or 'password' not in data:
        return jsonify({'success': False, 'message': 'Missing credentials'}), 400
        
    conn = get_db_connection()
    c = conn.cursor()
    
    # Find user
    c.execute('''
        SELECT id, name, email, role, department, rollNo, semester, subject 
        FROM users 
        WHERE email = ? AND password = ?
    ''', (data['email'], hash_password(data['password'])))
    
    user = c.fetchone()
    conn.close()
    
    if user:
        return jsonify({'success': True, 'user': dict(user)})
    else:
        return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

# ==========================================
# STUDENT/USER ENDPOINTS
# ==========================================

@app.route('/api/students', methods=['GET'])
def get_students():
    dept = request.args.get('department')
    conn = get_db_connection()
    c = conn.cursor()
    
    query = 'SELECT id, name, email, department, rollNo, semester FROM users WHERE role = "student"'
    params = []
    
    if dept and dept != 'all':
        query += ' AND department = ?'
        params.append(dept)
        
    c.execute(query, params)
    students = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify(students)

# ==========================================
# ATTENDANCE ENDPOINTS
# ==========================================

def get_student_records(conn, student_id):
    """Helper to get student attendance records sorted by date"""
    c = conn.cursor()
    c.execute('''
        SELECT id, date, status, markedBy, markedAt
        FROM attendance
        WHERE studentId = ?
        ORDER BY date ASC
    ''', (student_id,))
    return [dict(row) for row in c.fetchall()]

def calculate_student_stats(records):
    """Calculate basic attendance stats from records"""
    total = len(records)
    if total == 0:
        return {'percentage': 0, 'present': 0, 'absent': 0, 'total': 0}
        
    present = sum(1 for r in records if r['status'] == 'present')
    return {
        'percentage': round((present / total) * 100),
        'present': present,
        'absent': total - present,
        'total': total
    }

@app.route('/api/attendance', methods=['POST'])
def mark_bulk_attendance():
    """Mark attendance for multiple students on a specific date"""
    data = request.json
    
    if not all(k in data for k in ['date', 'teacherId', 'entries']):
        return jsonify({'error': 'Missing required fields'}), 400
        
    date = data['date']
    teacher_id = data['teacherId']
    entries = data['entries'] # List of {"studentId": "...", "status": "present/absent"}
    
    conn = get_db_connection()
    c = conn.cursor()
    now_str = datetime.now().isoformat()
    
    try:
        for entry in entries:
            student_id = entry['studentId']
            status = entry['status']
            
            # Delete any existing record for this date and student
            c.execute('DELETE FROM attendance WHERE studentId = ? AND date = ?', (student_id, date))
            
            # Insert new record
            a_id = generate_id()
            c.execute('''
                INSERT INTO attendance (id, studentId, date, status, markedBy, markedAt)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (a_id, student_id, date, status, teacher_id, now_str))
            
        conn.commit()
        return jsonify({'success': True, 'count': len(entries)})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/attendance/date/<date>', methods=['GET'])
def get_attendance_by_date(date):
    """Get all attendance records for a specific date"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT studentId, status FROM attendance WHERE date = ?', (date,))
    records = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(records)

@app.route('/api/attendance/student/<student_id>', methods=['GET'])
def get_student_attendance(student_id):
    """Get all attendance records and stats for one student"""
    conn = get_db_connection()
    records = get_student_records(conn, student_id)
    stats = calculate_student_stats(records)
    conn.close()
    
    return jsonify({
        'records': records,
        'stats': stats
    })

@app.route('/api/attendance/all-stats', methods=['GET'])
def get_all_student_stats():
    """Get statistics for all students (used by teacher dashboard)"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT id, name, department, rollNo FROM users WHERE role="student"')
    students = [dict(row) for row in c.fetchall()]
    
    # Fetch all attendance records once for efficiency
    c.execute('SELECT studentId, status FROM attendance')
    all_attendance = c.fetchall()
    conn.close()
    
    # Map attendance by student
    attendance_map = collections.defaultdict(list)
    for row in all_attendance:
        attendance_map[row['studentId']].append({'status': row['status']})
        
    # Calculate stats for each student
    for student in students:
        records = attendance_map[student['id']]
        stats = calculate_student_stats(records)
        student.update(stats)
        
    return jsonify(students)

@app.route('/api/attendance/summary', methods=['GET'])
def get_overall_summary():
    """Get top level stats (Total Students, Avg Attendance, At-Risk Count)"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Total students
    c.execute('SELECT COUNT(*) FROM users WHERE role="student"')
    total_students = c.fetchone()[0]
    
    # Get all stats to calculate avg and at-risk
    c.execute('SELECT id FROM users WHERE role="student"')
    student_ids = [row[0] for row in c.fetchall()]
    
    total_percentage_sum = 0
    at_risk_count = 0
    
    for s_id in student_ids:
        records = get_student_records(conn, s_id)
        stats = calculate_student_stats(records)
        pct = stats['percentage']
        total_percentage_sum += pct
        if pct < 75:
            at_risk_count += 1
            
    conn.close()
    
    avg_attendance = round(total_percentage_sum / total_students) if total_students > 0 else 0
    
    return jsonify({
        'totalStudents': total_students,
        'avgAttendance': avg_attendance,
        'atRisk': at_risk_count
    })

@app.route('/api/attendance/departments', methods=['GET'])
def get_department_stats():
    """Get average attendance per department"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT id, department FROM users WHERE role="student"')
    students = c.fetchall()
    
    dept_map = collections.defaultdict(list)
    for student in students:
        s_id = student['id']
        dept = student['department']
        records = get_student_records(conn, s_id)
        stats = calculate_student_stats(records)
        dept_map[dept].append(stats['percentage'])
        
    conn.close()
    
    results = []
    for dept, pcts in dept_map.items():
        if pcts:
            results.append({
                'department': dept,
                'avgAttendance': round(sum(pcts) / len(pcts)),
                'studentCount': len(pcts)
            })
            
    return jsonify(results)

# ==========================================
# NOTIFICATIONS ENDPOINTS
# ==========================================

@app.route('/api/notifications', methods=['POST'])
def send_notification():
    """Send a notification (single or bulk for at-risk)"""
    data = request.json
    
    if not all(k in data for k in ['fromId', 'toId', 'message']):
        return jsonify({'error': 'Missing fields'}), 400
        
    conn = get_db_connection()
    c = conn.cursor()
    now_str = datetime.now().isoformat()
    msg_type = data.get('type', 'warning')
    
    try:
        sent_count = 0
        if data['toId'] == 'all-risk':
            # Send to all at-risk students
            c.execute('SELECT id FROM users WHERE role="student"')
            student_ids = [row[0] for row in c.fetchall()]
            
            for s_id in student_ids:
                records = get_student_records(conn, s_id)
                stats = calculate_student_stats(records)
                if stats['percentage'] < 75:
                    n_id = generate_id()
                    c.execute('''
                        INSERT INTO notifications (id, fromId, toId, message, type, createdAt)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (n_id, data['fromId'], s_id, data['message'], msg_type, now_str))
                    sent_count += 1
        else:
            # Send single
            n_id = generate_id()
            c.execute('''
                INSERT INTO notifications (id, fromId, toId, message, type, createdAt)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (n_id, data['fromId'], data['toId'], data['message'], msg_type, now_str))
            sent_count = 1
            
        conn.commit()
        return jsonify({'success': True, 'count': sent_count})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/notifications/user/<user_id>', methods=['GET'])
def get_user_notifications(user_id):
    """Get inbox for a user"""
    conn = get_db_connection()
    c = conn.cursor()
    # Join with users table to get sender name
    c.execute('''
        SELECT n.id, n.fromId, n.message, n.type, n.read, n.createdAt, u.name as fromName
        FROM notifications n
        LEFT JOIN users u ON n.fromId = u.id
        WHERE n.toId = ?
        ORDER BY n.createdAt DESC
    ''', (user_id,))
    notifs = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(notifs)

@app.route('/api/notifications/sent/<user_id>', methods=['GET'])
def get_sent_notifications(user_id):
    """Get outbox for a user (Teacher sent)"""
    conn = get_db_connection()
    c = conn.cursor()
    # Join with users to get recipient name
    c.execute('''
        SELECT n.id, n.toId, n.message, n.type, n.createdAt, u.name as toName
        FROM notifications n
        LEFT JOIN users u ON n.toId = u.id
        WHERE n.fromId = ?
        ORDER BY n.createdAt DESC
    ''', (user_id,))
    notifs = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(notifs)

@app.route('/api/notifications/read', methods=['PUT'])
def mark_notifications_read():
    """Mark single or all notifications as read"""
    data = request.json
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        if 'id' in data:
            c.execute('UPDATE notifications SET read = 1 WHERE id = ?', (data['id'],))
        elif 'userId' in data:
            c.execute('UPDATE notifications SET read = 1 WHERE toId = ?', (data['userId'],))
        else:
            return jsonify({'error': 'Must provide id or userId'}), 400
            
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

# ==========================================
# ML PREDICTION ENDPOINTS
# ==========================================

@app.route('/api/predict/student/<student_id>', methods=['GET'])
def get_student_prediction(student_id):
    """Run ML prediction for a single student."""
    conn = get_db_connection()
    records = get_student_records(conn, student_id)
    conn.close()
    
    prediction = predict_student_outcome(records)
    return jsonify(prediction)

@app.route('/api/predict/all', methods=['GET'])
def get_all_predictions():
    """Run ML prediction for all students."""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT id, name, department, rollNo FROM users WHERE role="student"')
    students = [dict(row) for row in c.fetchall()]
    
    results = []
    for student in students:
        records = get_student_records(conn, student['id'])
        prediction = predict_student_outcome(records)
        
        # Combine student info with prediction
        combined = dict(student)
        combined.update(prediction)
        results.append(combined)
        
    conn.close()
    
    # Sort by probability ascending (most critical first)
    results.sort(key=lambda x: x['probability'])
    
    return jsonify(results)

# ==========================================
# STATIC FRONTEND ROUTES
# ==========================================

@app.route('/')
def index():
    return send_from_directory(frontend_dir, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(frontend_dir, path)):
        return send_from_directory(frontend_dir, path)
    return send_from_directory(frontend_dir, 'index.html')

if __name__ == '__main__':
    # Initialize DB (and seed if empty) and train model if it doesn't exist
    init_db()
    try:
        import ml_model
        ml_model.load_model()
    except Exception as e:
        print(f"Warning: Failed to load/train ML model on startup: {e}")
        
    print("Starting AttendIQ API server on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', debug=True, port=5000)
