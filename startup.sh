#!/bin/bash
# This startup script tells Azure App Service how to run our Flask app.
# Gunicorn is a production-grade Python web server (Flask's built-in server is for development only).
gunicorn --bind=0.0.0.0:8000 app:app
