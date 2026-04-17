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
# This function creates a connection to Azure SQL Database.
# In production, you'd use environment variables (not hardcoded values)
# We'll configure these as App Settings in Azure App Service later.

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
# This ensures the Tasks table exists in the database.
# IF NOT EXISTS prevents errors if the table already exists.

def init_db():
    """Create the Tasks table if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='tasks' AND xtype='U')
            CREATE TABLE tasks (
                id INT IDENTITY(1,1) PRIMARY KEY,
                title NVARCHAR(200) NOT NULL,
                description NVARCHAR(500),
                is_complete BIT DEFAULT 0,
                created_at DATETIME DEFAULT GETDATE()
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Database init error: {e}")


# ============================================================
# ROUTES (the pages of your app)
# ============================================================

# --- READ: Show all tasks (homepage) ---
@app.route('/')
def index():
    """Display all tasks - this is the R in CRUD."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, is_complete, created_at FROM tasks ORDER BY created_at DESC")
        tasks = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('index.html', tasks=tasks)
    except Exception as e:
        return render_template('index.html', tasks=[], error=str(e))


# --- CREATE: Add a new task ---
@app.route('/add', methods=['POST'])
def add_task():
    """Add a new task - this is the C in CRUD."""
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()

    if title:  # Only add if title is not empty
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (title, description) VALUES (?, ?)",
                (title, description)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error adding task: {e}")

    return redirect(url_for('index'))


# --- UPDATE: Toggle task completion ---
@app.route('/toggle/<int:task_id>')
def toggle_task(task_id):
    """Toggle a task's completion status - this is the U in CRUD."""
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


# --- DELETE: Remove a task ---
@app.route('/delete/<int:task_id>')
def delete_task(task_id):
    """Delete a task - this is the D in CRUD."""
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
# START THE APP
# ============================================================
if __name__ == '__main__':
    init_db()  # Create table on startup
    app.run(debug=True)
