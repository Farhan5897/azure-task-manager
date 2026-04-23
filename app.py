"""
Task Manager Web App - Azure Project 2
Built with Flask + Azure SQL Database
Features: User Auth, Priority, Status Dashboard, Due Dates & Scheduling
Guest mode: anyone can use it, login to save your tasks
"""
import os
import time
import pyodbc
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'farhan-task-manager-secret-key-2026')


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection(retries=3, delay=5):
    """Connect to Azure SQL with retry logic for serverless cold starts."""
    conn_str = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server={os.environ.get('SQL_SERVER', 'your-server.database.windows.net')};"
        f"Database={os.environ.get('SQL_DATABASE', 'taskmanagerdb')};"
        f"Uid={os.environ.get('SQL_USERNAME', 'adminfarhan')};"
        f"Pwd={os.environ.get('SQL_PASSWORD', 'your-password')};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
        f"Connection Timeout=30;"
    )
    for attempt in range(retries):
        try:
            return pyodbc.connect(conn_str)
        except pyodbc.Error as e:
            if attempt < retries - 1:
                print(f"DB connection attempt {attempt + 1} failed, retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise e


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():
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

        # Create tasks table
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='tasks' AND xtype='U')
            CREATE TABLE tasks (
                id INT IDENTITY(1,1) PRIMARY KEY,
                title NVARCHAR(200) NOT NULL,
                description NVARCHAR(500),
                is_complete BIT DEFAULT 0,
                priority NVARCHAR(20) DEFAULT 'medium',
                due_date DATE NULL,
                user_id INT NULL,
                session_id NVARCHAR(100) NULL,
                created_at DATETIME DEFAULT GETDATE(),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Migrations for existing tables
        for col, col_type, default in [
            ('priority', 'NVARCHAR(20)', "'medium'"),
            ('user_id', 'INT', 'NULL'),
            ('due_date', 'DATE', 'NULL'),
            ('session_id', 'NVARCHAR(100)', 'NULL'),
        ]:
            cursor.execute(f"""
                IF NOT EXISTS (
                    SELECT * FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'tasks' AND COLUMN_NAME = '{col}'
                )
                ALTER TABLE tasks ADD {col} {col_type} DEFAULT {default}
            """)

        conn.commit()
        cursor.close()
        conn.close()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Database init error: {e}")


# ============================================================
# HELPERS
# ============================================================

def is_logged_in():
    return 'user_id' in session


def get_guest_id():
    """Get or create a guest session ID for anonymous users."""
    if 'guest_id' not in session:
        import uuid
        session['guest_id'] = str(uuid.uuid4())
    return session['guest_id']


def get_task_filter():
    """Returns (column, value) for filtering tasks based on auth state."""
    if is_logged_in():
        return ('user_id', session['user_id'])
    else:
        return ('session_id', get_guest_id())


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if is_logged_in():
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

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
            cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return render_template('register.html', error='Username or email already taken.', username=username, email=email)

            password_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)", (username, email, password_hash))
            conn.commit()

            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            new_user_id = user[0]

            # Transfer guest tasks to the new account
            guest_id = session.get('guest_id')
            if guest_id:
                cursor.execute(
                    "UPDATE tasks SET user_id = ?, session_id = NULL WHERE session_id = ?",
                    (new_user_id, guest_id)
                )
                conn.commit()

            session['user_id'] = new_user_id
            session['username'] = username
            session.pop('guest_id', None)

            cursor.close()
            conn.close()
            return redirect(url_for('index'))
        except Exception as e:
            return render_template('register.html', error=f'Registration failed: {e}', username=username, email=email)

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            return render_template('login.html', error='Please fill in all fields.', username=username)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ? OR email = ?", (username, username))
            user = cursor.fetchone()

            if user and check_password_hash(user[2], password):
                # Transfer guest tasks to logged-in account
                guest_id = session.get('guest_id')
                if guest_id:
                    cursor.execute(
                        "UPDATE tasks SET user_id = ?, session_id = NULL WHERE session_id = ?",
                        (user[0], guest_id)
                    )
                    conn.commit()

                session['user_id'] = user[0]
                session['username'] = user[1]
                session.pop('guest_id', None)

                cursor.close()
                conn.close()
                return redirect(url_for('index'))
            else:
                cursor.close()
                conn.close()
                return render_template('login.html', error='Invalid username or password.', username=username)
        except Exception as e:
            return render_template('login.html', error=f'Login failed: {e}', username=username)

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ============================================================
# TASK ROUTES (open to everyone)
# ============================================================

@app.route('/')
def index():
    """Display tasks filtered by date. Works for guests and logged-in users."""
    try:
        filter_date_str = request.args.get('date', '')
        today = date.today()

        if filter_date_str:
            try:
                filter_date = datetime.strptime(filter_date_str, '%Y-%m-%d').date()
            except ValueError:
                filter_date = today
        else:
            filter_date = today

        col, val = get_task_filter()
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get tasks for the selected date
        if filter_date == today:
            cursor.execute(f"""
                SELECT id, title, description, is_complete, created_at, priority, due_date
                FROM tasks
                WHERE {col} = ? AND (due_date = ? OR due_date IS NULL)
                ORDER BY
                    is_complete ASC,
                    CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
                    created_at DESC
            """, (val, filter_date))
        else:
            cursor.execute(f"""
                SELECT id, title, description, is_complete, created_at, priority, due_date
                FROM tasks
                WHERE {col} = ? AND due_date = ?
                ORDER BY
                    is_complete ASC,
                    CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
                    created_at DESC
            """, (val, filter_date))

        tasks = cursor.fetchall()

        # Overdue count
        cursor.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE {col} = ? AND due_date < ? AND is_complete = 0
        """, (val, today))
        overdue_count = cursor.fetchone()[0]

        # Upcoming count
        cursor.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE {col} = ? AND due_date > ? AND is_complete = 0
        """, (val, today))
        upcoming_count = cursor.fetchone()[0]

        # All-time total
        cursor.execute(f"SELECT COUNT(*) FROM tasks WHERE {col} = ?", (val,))
        all_total = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        # Build stats
        total = len(tasks)
        completed = sum(1 for t in tasks if t[3])
        pending = total - completed
        high = sum(1 for t in tasks if (t[5] or 'medium') == 'high' and not t[3])
        medium = sum(1 for t in tasks if (t[5] or 'medium') == 'medium' and not t[3])
        low = sum(1 for t in tasks if (t[5] or 'medium') == 'low' and not t[3])
        pct = round((completed / total) * 100) if total > 0 else 0

        stats = {
            'total': total, 'completed': completed, 'pending': pending,
            'high': high, 'medium': medium, 'low': low, 'pct': pct,
            'overdue': overdue_count, 'upcoming': upcoming_count, 'all_total': all_total,
        }

        is_today = (filter_date == today)
        is_past = (filter_date < today)
        is_future = (filter_date > today)

        return render_template('index.html',
            tasks=tasks, stats=stats,
            username=session.get('username'),
            logged_in=is_logged_in(),
            filter_date=filter_date.strftime('%Y-%m-%d'),
            filter_date_display=filter_date.strftime('%b %d, %Y'),
            today=today.strftime('%Y-%m-%d'),
            is_today=is_today, is_past=is_past, is_future=is_future,
        )
    except Exception as e:
        stats = {'total':0,'completed':0,'pending':0,'high':0,'medium':0,'low':0,'pct':0,'overdue':0,'upcoming':0,'all_total':0}
        return render_template('index.html', tasks=[], stats=stats, error=str(e),
            username=session.get('username'), logged_in=is_logged_in(),
            filter_date=date.today().strftime('%Y-%m-%d'),
            filter_date_display=date.today().strftime('%b %d, %Y'),
            today=date.today().strftime('%Y-%m-%d'),
            is_today=True, is_past=False, is_future=False)


@app.route('/add', methods=['POST'])
def add_task():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    priority = request.form.get('priority', 'medium')
    due_date_str = request.form.get('due_date', '').strip()

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except ValueError:
            due_date = None

    if title:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            if is_logged_in():
                cursor.execute(
                    "INSERT INTO tasks (title, description, priority, due_date, user_id) VALUES (?, ?, ?, ?, ?)",
                    (title, description, priority, due_date, session['user_id'])
                )
            else:
                cursor.execute(
                    "INSERT INTO tasks (title, description, priority, due_date, session_id) VALUES (?, ?, ?, ?, ?)",
                    (title, description, priority, due_date, get_guest_id())
                )

            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error adding task: {e}")

    redirect_date = request.form.get('current_date', '')
    if redirect_date:
        return redirect(url_for('index', date=redirect_date))
    return redirect(url_for('index'))


@app.route('/toggle/<int:task_id>')
def toggle_task(task_id):
    try:
        col, val = get_task_filter()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE tasks SET is_complete = CASE WHEN is_complete = 1 THEN 0 ELSE 1 END WHERE id = ? AND {col} = ?",
            (task_id, val)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error toggling task: {e}")

    return redirect(request.referrer or url_for('index'))


@app.route('/delete/<int:task_id>')
def delete_task(task_id):
    try:
        col, val = get_task_filter()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM tasks WHERE id = ? AND {col} = ?", (task_id, val))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error deleting task: {e}")

    return redirect(request.referrer or url_for('index'))


# ============================================================
# INITIALIZE DB ON STARTUP
# ============================================================
init_db()

if __name__ == '__main__':
    app.run(debug=True)
