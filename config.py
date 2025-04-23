import os

# OpenRouteService API key - get it from environment variables
OPENROUTE_API_KEY = os.environ.get("OPENROUTE_API_KEY", "")

# API endpoints
OPENROUTE_GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
OPENROUTE_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"
OPENROUTE_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"

# Maximum number of locations the form can handle
MAX_LOCATIONS = 15

# Weather API configuration
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")
WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"

# Category icons mapping
CATEGORY_ICONS = {
    'home': 'fa-home',
    'office': 'fa-building',
    'business': 'fa-briefcase',
    'pickup_point': 'fa-box',
    'other': 'fa-map-marker-alt'
}

# Analytics dashboard settings
ANALYTICS_ENABLED = True
