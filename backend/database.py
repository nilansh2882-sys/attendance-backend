import sqlite3
import os
import random
import hashlib
from datetime import datetime, timedelta

DB_FILE = 'attendiq.db'

DEPARTMENTS = ['CSE', 'ECE', 'ME', 'CE', 'IT', 'EEE']

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(pwd):
    # Simple hash for demo — NOT for production
    hash_val = 0
    for char in pwd:
        hash_val = ((hash_val << 5) - hash_val) + ord(char)
        hash_val |= 0
    return 'h_' + str(abs(hash_val)) + '36' # simple reproducible pseudo hash

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Enable foreign keys
    c.execute('PRAGMA foreign_keys = ON;')

    # Users Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT NOT NULL,
            rollNo TEXT,
            semester INTEGER,
            subject TEXT,
            createdAt TEXT NOT NULL
        )
    ''')

    # Attendance Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id TEXT PRIMARY KEY,
            studentId TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            markedBy TEXT NOT NULL,
            markedAt TEXT NOT NULL,
            FOREIGN KEY(studentId) REFERENCES users(id),
            FOREIGN KEY(markedBy) REFERENCES users(id)
        )
    ''')

    # Notifications Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            fromId TEXT NOT NULL,
            toId TEXT NOT NULL,
            message TEXT NOT NULL,
            type TEXT NOT NULL,
            read INTEGER DEFAULT 0,
            createdAt TEXT NOT NULL,
            FOREIGN KEY(fromId) REFERENCES users(id),
            FOREIGN KEY(toId) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    
    # Check if we need to seed
    c.execute('SELECT COUNT(*) FROM users')
    count = c.fetchone()[0]
    
    if count == 0:
        seed_data(conn)
        
    conn.close()

def generate_id():
    import uuid
    return uuid.uuid4().hex[:14]

def seed_data(conn):
    print("Seeding database with generated students and attendance data...")
    c = conn.cursor()
    now_str = datetime.now().isoformat()
    
    students = []
    firstNames = ['Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun', 'Sai', 'Reyansh', 'Ayaan', 'Krishna', 'Ishaan',
                  'Ananya', 'Diya', 'Myra', 'Sara', 'Aadhya', 'Isha', 'Kavya', 'Riya', 'Priya', 'Neha',
                  'Rohan', 'Karan', 'Amit', 'Rahul', 'Sneha']
    lastNames = ['Sharma', 'Patel', 'Kumar', 'Singh', 'Reddy', 'Gupta', 'Joshi', 'Verma', 'Nair', 'Das',
                 'Mehta', 'Iyer', 'Rao', 'Chopra', 'Bose', 'Pillai', 'Saxena', 'Malhotra', 'Tiwari', 'Banerjee',
                 'Mishra', 'Kapoor', 'Sinha', 'Khanna', 'Bhatt']

    # 1. Demo Teacher
    teacher_id = generate_id()
    c.execute('''
        INSERT INTO users (id, name, email, password, role, department, subject, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (teacher_id, 'Dr. Rajesh Kumar', 'teacher@demo.com', hash_password('demo123'), 'teacher', 'CSE', 'Data Structures', now_str))

    # 2. Demo Student
    demo_student_id = generate_id()
    students.append(demo_student_id)
    c.execute('''
        INSERT INTO users (id, name, email, password, role, department, rollNo, semester, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (demo_student_id, 'Demo Student', 'student@demo.com', hash_password('demo123'), 'student', 'CSE', 'CSE21099', 4, now_str))

    # 3. Insert 25 random students
    for i in range(25):
        s_id = generate_id()
        dept = DEPARTMENTS[i % len(DEPARTMENTS)]
        rollNo = f"{dept}{str(2021 + i // 6)[2:]}{str(i + 1).zfill(3)}"
        students.append(s_id)
        c.execute('''
            INSERT INTO users (id, name, email, password, role, department, rollNo, semester, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (s_id, f"{firstNames[i]} {lastNames[i]}", f"{firstNames[i].lower()}.{lastNames[i].lower()}@student.edu", hash_password('demo123'), 'student', dept, rollNo, random.randint(1,8), now_str))

    conn.commit()

    # 4. Generate 30 days of attendance
    today = datetime.now()
    
    for dayOffset in range(1, 31):
        date = today - timedelta(days=dayOffset)
        # Skip weekends
        if date.weekday() in [5, 6]: 
            continue
            
        date_str = date.strftime('%Y-%m-%d')
        date_iso = date.isoformat()
        
        for i, s_id in enumerate(students):
            # Vary attendance probability per student to create realistic patterns
            probability = 0.8
            if i < 5: probability = 0.95
            elif i < 10: probability = 0.82
            elif i < 15: probability = 0.72
            elif i < 20: probability = 0.60
            else: probability = 0.45
            
            is_present = random.random() < probability
            status = 'present' if is_present else 'absent'
            
            a_id = generate_id()
            c.execute('''
                INSERT INTO attendance (id, studentId, date, status, markedBy, markedAt)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (a_id, s_id, date_str, status, teacher_id, date_iso))
            
    conn.commit()
    print("Database seeding completed.")

if __name__ == '__main__':
    # Initialize the database if ran directly
    print("Initializing Database...")
    init_db()
    print("Database initialized successfully.")
