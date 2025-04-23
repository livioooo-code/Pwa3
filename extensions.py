"""
This file contains all the Flask extensions instances that will be initialized in app.py
"""
import logging
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Create extensions instances
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Zaloguj się, aby mieć dostęp do tej strony.'
login_manager.login_message_category = 'warning'