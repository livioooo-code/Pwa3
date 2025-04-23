from datetime import datetime
import json
import uuid
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db

class Courier(UserMixin, db.Model):
    """Model representing a courier user"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    api_key = db.Column(db.String(64), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # User can have many assigned routes
    assigned_routes = db.relationship('CourierRouteAssignment', backref='courier', lazy=True, cascade="all, delete-orphan")
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def regenerate_api_key(self):
        self.api_key = str(uuid.uuid4())
        return self.api_key
        
    def __repr__(self):
        return f"<Courier {self.username}>"

class Route(db.Model):
    """Model representing an optimized route"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    total_distance = db.Column(db.Float, nullable=False)  # in km
    total_time = db.Column(db.String(20), nullable=False)  # stored as string like "2h 30m"
    
    # Store coordinates as JSON string
    coordinates_json = db.Column(db.Text, nullable=False)
    
    # Relationship with locations
    locations = db.relationship('Location', backref='route', lazy=True, cascade="all, delete-orphan")
    
    # Route assignments
    assigned_couriers = db.relationship('CourierRouteAssignment', backref='route', lazy=True, cascade="all, delete-orphan")
    
    @property
    def coordinates(self):
        """Deserialize coordinates from JSON string"""
        return json.loads(self.coordinates_json)
    
    @coordinates.setter
    def coordinates(self, coords):
        """Serialize coordinates to JSON string"""
        self.coordinates_json = json.dumps(coords)
    
    def to_dict(self):
        """Convert route to dictionary for API responses"""
        locations_list = []
        for loc in sorted(self.locations, key=lambda x: x.position):
            locations_list.append(loc.to_dict())
            
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at.isoformat(),
            'total_distance': self.total_distance,
            'total_time': self.total_time,
            'coordinates': self.coordinates,
            'locations': locations_list
        }
    
    def __repr__(self):
        return f'<Route {self.id}: {self.name or "Unnamed Route"}>'


class Location(db.Model):
    """Model representing a location in a route"""
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('route.id'), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    street = db.Column(db.String(100), nullable=False)
    number = db.Column(db.String(20), nullable=True)
    position = db.Column(db.Integer, nullable=False)  # Order in the route
    formatted_address = db.Column(db.String(255), nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    category = db.Column(db.String(50), default='home')  # home, office, pickup_point, business, other
    time_window_start = db.Column(db.Time, nullable=True)  # Time window for delivery start
    time_window_end = db.Column(db.Time, nullable=True)    # Time window for delivery end
    estimated_duration = db.Column(db.Integer, default=10)  # Estimated duration of stop in minutes
    
    # Delivery status tracking
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, failed
    delivery_notes = db.Column(db.Text, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    def to_dict(self):
        """Convert location to dictionary for API responses"""
        return {
            'id': self.id,
            'position': self.position,
            'address': {
                'city': self.city,
                'street': self.street,
                'number': self.number,
                'formatted': self.formatted_address
            },
            'coordinates': {
                'latitude': self.latitude,
                'longitude': self.longitude
            },
            'category': self.category,
            'time_window': {
                'start': self.time_window_start.isoformat() if self.time_window_start else None,
                'end': self.time_window_end.isoformat() if self.time_window_end else None
            },
            'estimated_duration': self.estimated_duration,
            'status': self.status,
            'delivery_notes': self.delivery_notes,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

    def __repr__(self):
        return f'<Location {self.id}: {self.street} {self.number}, {self.city}>'

class CourierRouteAssignment(db.Model):
    """Model representing assignment of routes to couriers"""
    id = db.Column(db.Integer, primary_key=True)
    courier_id = db.Column(db.Integer, db.ForeignKey('courier.id'), nullable=False)
    route_id = db.Column(db.Integer, db.ForeignKey('route.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Route status tracking
    status = db.Column(db.String(20), default='assigned')  # assigned, in_progress, completed, canceled
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Assignment Courier:{self.courier_id} to Route:{self.route_id}>"
