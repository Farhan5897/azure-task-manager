"""
Task Manager Web App - Azure Project 2
Built with Flask + Azure SQL Database
"""
import os
import pyodbc
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime

app = Flask(__name__)

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
# CREATE TABLE (runs once on startup)
# ============================================================

def init_db():
    """Create the Tasks table if it doesn't exist, and migrate if needed."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create table if not exists
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='tasks' AND xtype='U')
            CREATE TABLE tasks (
                id INT IDENTITY(1,1) PRIMARY KEY,
                title NVARCHAR(200) NOT NULL,
                description NVARCHAR(500),
                is_complete BIT DEFAULT 0,
                priority NVARCHAR(20) DEFAULT 'medium',
                created_at DATETIME DEFAULT GETDATE()
            )
        """)

        # Add priority column if table exists but column doesn't
        cursor.execute("""
            IF NOT EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'tasks' AND COLUMN_NAME = 'priority'
            )
            ALTER TABLE tasks ADD priority NVARCHAR(20) DEFAULT 'medium'
        """)

        conn.commit()
        cursor.close()
        conn.close()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Database init error: {e}")


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    """Display all tasks with dashboard stats."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, description, is_complete, created_at, priority
            FROM tasks ORDER BY
                is_complete ASC,
                CASE priority
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END,
                created_at DESC
        """)
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

        return render_template('index.html', tasks=tasks, stats=stats)
    except Exception as e:
        stats = {'total':0,'completed':0,'pending':0,'high':0,'medium':0,'low':0,'pct':0}
        return render_template('index.html', tasks=[], stats=stats, error=str(e))


@app.route('/add', methods=['POST'])
def add_task():
    """Add a new task."""
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    priority = request.form.get('priority', 'medium')

    if title:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (title, description, priority) VALUES (?, ?, ?)",
                (title, description, priority)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error adding task: {e}")

    return redirect(url_for('index'))


@app.route('/toggle/<int:task_id>')
def toggle_task(task_id):
    """Toggle a task's completion status."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tasks SET is_complete = CASE WHEN is_complete = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (task_id,)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error toggling task: {e}")

    return redirect(url_for('index'))


@app.route('/delete/<int:task_id>')
def delete_task(task_id):
    """Delete a task."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
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
