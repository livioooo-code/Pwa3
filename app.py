import os
import logging
from flask import Flask
from extensions import db, login_manager
import models  # Import models to register them with SQLAlchemy

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Create application instance
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_courier_nav_secret")

# Configure database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions with the app
db.init_app(app)
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return models.Courier.query.get(int(user_id))

# Create database tables
with app.app_context():
    try:
        db.create_all()
        db_connected = True
        logging.info("Database tables created successfully")
    except Exception as e:
        db_connected = False
        logging.error(f"Error initializing database tables: {str(e)}")

# Import routes after application and extensions have been set up
from main import *