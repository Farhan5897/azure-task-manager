"""
Task Manager Web App - Azure Project 2
Built with Flask + Azure SQL Database
Features: User Authentication, Priority Tasks, Status Dashboard
"""
import os
import pyodbc
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'farhan-task-manager-secret-key-2026')


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():
    """Connect to Azure SQL Database using ODBC driver."""
    conn_str = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server={os.environ.get('SQL_SERVER', 'your-server.database.windows.net')};"
        f"Database={os.environ.get('SQL_DATABASE', 'taskmanagerdb')};"
        f"Uid={os.environ.get('SQL_USERNAME', 'adminfarhan')};"
        f"Pwd={os.environ.get('SQL_PASSWORD', 'your-password')};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
    )
    return pyodbc.connect(conn_str)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():
    """Create tables if they don't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create users table
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='users' AND xtype='U')
            CREATE TABLE users (
                id INT IDENTITY(1,1) PRIMARY KEY,
                username NVARCHAR(50) NOT NULL UNIQUE,
                email NVARCHAR(200) NOT NULL UNIQUE,
                password_hash NVARCHAR(500) NOT NULL,
                created_at DATETIME DEFAULT GETDATE()
            )
        """)

        # Create tasks table with user_id
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='tasks' AND xtype='U')
            CREATE TABLE tasks (
                id INT IDENTITY(1,1) PRIMARY KEY,
                title NVARCHAR(200) NOT NULL,
                description NVARCHAR(500),
                is_complete BIT DEFAULT 0,
                priority NVARCHAR(20) DEFAULT 'medium',
                user_id INT,
                created_at DATETIME DEFAULT GETDATE(),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Migration: add priority column if missing
        cursor.execute("""
            IF NOT EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'tasks' AND COLUMN_NAME = 'priority'
            )
            ALTER TABLE tasks ADD priority NVARCHAR(20) DEFAULT 'medium'
        """)

        # Migration: add user_id column if missing
        cursor.execute("""
            IF NOT EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'tasks' AND COLUMN_NAME = 'user_id'
            )
            ALTER TABLE tasks ADD user_id INT NULL
        """)

        conn.commit()
        cursor.close()
        conn.close()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Database init error: {e}")


# ============================================================
# AUTH DECORATOR
# ============================================================

def login_required(f):
    """Decorator to protect routes — redirects to login if not authenticated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        # Validation
        if not username or not email or not password:
            return render_template('register.html', error='All fields are required.', username=username, email=email)

        if len(username) < 3:
            return render_template('register.html', error='Username must be at least 3 characters.', username=username, email=email)

        if len(password) < 6:
            return render_template('register.html', error='Password must be at least 6 characters.', username=username, email=email)

        if password != confirm:
            return render_template('register.html', error='Passwords do not match.', username=username, email=email)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Check if username or email already exists
            cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return render_template('register.html', error='Username or email already taken.', username=username, email=email)

            # Create user
            password_hash = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, password_hash)
            )
            conn.commit()

            # Auto-login after registration
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            session['user_id'] = user[0]
            session['username'] = username

            cursor.close()
            conn.close()
            return redirect(url_for('index'))

        except Exception as e:
            return render_template('register.html', error=f'Registration failed: {e}', username=username, email=email)

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            return render_template('login.html', error='Please fill in all fields.', username=username)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ? OR email = ?",
                (username, username)
            )
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user and check_password_hash(user[2], password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                return redirect(url_for('index'))
            else:
                return render_template('login.html', error='Invalid username or password.', username=username)

        except Exception as e:
            return render_template('login.html', error=f'Login failed: {e}', username=username)

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Log the user out."""
    session.clear()
    return redirect(url_for('login'))


# ============================================================
# TASK ROUTES (all protected)
# ============================================================

@app.route('/')
@login_required
def index():
    """Display user's tasks with dashboard stats."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, description, is_complete, created_at, priority
            FROM tasks
            WHERE user_id = ?
            ORDER BY
                is_complete ASC,
                CASE priority
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END,
                created_at DESC
        """, (session['user_id'],))
        tasks = cursor.fetchall()
        cursor.close()
        conn.close()

        # Build dashboard stats
        total = len(tasks)
        completed = sum(1 for t in tasks if t[3])
        pending = total - completed
        high = sum(1 for t in tasks if (t[5] or 'medium') == 'high' and not t[3])
        medium = sum(1 for t in tasks if (t[5] or 'medium') == 'medium' and not t[3])
        low = sum(1 for t in tasks if (t[5] or 'medium') == 'low' and not t[3])
        pct = round((completed / total) * 100) if total > 0 else 0

        stats = {
            'total': total,
            'completed': completed,
            'pending': pending,
            'high': high,
            'medium': medium,
            'low': low,
            'pct': pct,
        }

        return render_template('index.html', tasks=tasks, stats=stats, username=session.get('username'))
    except Exception as e:
        stats = {'total':0,'completed':0,'pending':0,'high':0,'medium':0,'low':0,'pct':0}
        return render_template('index.html', tasks=[], stats=stats, error=str(e), username=session.get('username'))


@app.route('/add', methods=['POST'])
@login_required
def add_task():
    """Add a new task for the logged-in user."""
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    priority = request.form.get('priority', 'medium')

    if title:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (title, description, priority, user_id) VALUES (?, ?, ?, ?)",
                (title, description, priority, session['user_id'])
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error adding task: {e}")

    return redirect(url_for('index'))


@app.route('/toggle/<int:task_id>')
@login_required
def toggle_task(task_id):
    """Toggle a task's completion status (only if owned by user)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tasks SET is_complete = CASE WHEN is_complete = 1 THEN 0 ELSE 1 END WHERE id = ? AND user_id = ?",
            (task_id, session['user_id'])
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error toggling task: {e}")

    return redirect(url_for('index'))


@app.route('/delete/<int:task_id>')
@login_required
def delete_task(task_id):
    """Delete a task (only if owned by user)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, session['user_id']))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error deleting task: {e}")

    return redirect(url_for('index'))


# ============================================================
# INITIALIZE DB ON STARTUP
# ============================================================
init_db()

if __name__ == '__main__':
    app.run(debug=True)
