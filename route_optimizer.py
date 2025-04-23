import requests
import logging
import json
import math
import time
import random
from itertools import permutations
import config
from datetime import datetime, timedelta
import pytz
import math
import time
import random
import traffic_light_optimizer

def geocode_address(address):
    """Convert address to coordinates using OpenRouteService Geocoding API"""
    try:
        # Check if API key is available
        if not config.OPENROUTE_API_KEY:
            logging.warning("OpenRouteService API key not configured. Geocoding will not work.")
            return None
            
        params = {
            'api_key': config.OPENROUTE_API_KEY,
            'text': address
        }
        
        response = requests.get(config.OPENROUTE_GEOCODE_URL, params=params)
        
        # Check for API key errors
        if response.status_code == 401 or response.status_code == 403:
            logging.error("Invalid OpenRouteService API key. Please check your API key configuration.")
            return None
            
        response.raise_for_status()
        
        data = response.json()
        if data['features'] and len(data['features']) > 0:
            # Extract coordinates [longitude, latitude]
            coords = data['features'][0]['geometry']['coordinates']
            formatted_address = data['features'][0]['properties'].get('label', address)
            return {
                'coordinates': coords,
                'formatted_address': formatted_address
            }
        else:
            logging.error(f"No results found for address: {address}")
            return None
    except Exception as e:
        logging.error(f"Error geocoding address {address}: {str(e)}")
        return None

def get_distance_matrix(coordinates):
    """Get distance and duration matrix between all points using OpenRouteService API"""
    try:
        # Check if API key is available
        if not config.OPENROUTE_API_KEY:
            logging.warning("OpenRouteService API key not configured. Route optimization will not work.")
            return None
            
        headers = {
            'Authorization': config.OPENROUTE_API_KEY,
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json, application/geo+json, application/gpx+xml'
        }
        
        body = {
            'locations': coordinates,
            'metrics': ['distance', 'duration'],
            'units': 'km'
        }
        
        response = requests.post(
            config.OPENROUTE_MATRIX_URL,
            headers=headers,
            json=body
        )
        
        # Check for API key errors
        if response.status_code == 401 or response.status_code == 403:
            logging.error("Invalid OpenRouteService API key. Please check your API key configuration.")
            return None
            
        response.raise_for_status()
        
        data = response.json()
        return {
            'durations': data['durations'],
            'distances': data['distances']
        }
    except Exception as e:
        logging.error(f"Error getting distance matrix: {str(e)}")
        return None

def optimize_route(coordinates):
    """
    Enhanced route optimization with multiple algorithms
    Takes into account real-world parameters like traffic patterns
    """
    try:
        # Inicjalizacja zmiennych
        route_duration = 0
        best_route_indices = []
        
        if len(coordinates) <= 1:
            return coordinates, 0, 0
            
        # Get distance/duration matrix from API
        matrix = get_distance_matrix(coordinates)
        
        if not matrix:
            return None, 0, 0
            
        durations = matrix['durations']
        distances = matrix['distances']
        
        # Get current time to adjust for traffic patterns
        current_hour = datetime.now().hour
        
        # Traffic multiplier based on time of day
        # Higher during rush hours (7-9 AM, 4-6 PM)
        traffic_multipliers = []
        for i in range(len(coordinates)):
            for j in range(len(coordinates)):
                if i != j:
                    # Rush hour traffic adjustment
                    if 7 <= current_hour <= 9 or 16 <= current_hour <= 18:
                        # More traffic in city centers during rush hour
                        # Simple simulation based on distance from center
                        city_center_factor = min(1.0, distances[i][j] / 30.0)  # Assume >30km is outside urban center
                        traffic_multiplier = 1.0 + (0.3 * (1.0 - city_center_factor))
                    else:
                        traffic_multiplier = 1.0
                        
                    # Apply traffic multiplier to duration
                    durations[i][j] *= traffic_multiplier
        
        # For small number of points (<=6), use brute force for optimal solution
        if len(coordinates) <= 6:
            logging.debug("Using brute force optimization for small route")
            # Try all permutations starting with the first point
            start = 0
            min_duration = float('inf')
            best_route_indices = None
            
            # Generate all possible routes starting from the first location
            for perm in permutations(range(1, len(coordinates))):
                route = [start] + list(perm)
                
                # Calculate total duration for this route
                total_duration = 0
                for i in range(len(route) - 1):
                    from_idx = route[i]
                    to_idx = route[i + 1]
                    total_duration += durations[from_idx][to_idx]
                
                if total_duration < min_duration:
                    min_duration = total_duration
                    best_route_indices = route
                    
            # Add return to start if needed (currently commented out)
            # best_route_indices.append(start)
                
        elif len(coordinates) <= 12:
            logging.debug("Using enhanced nearest neighbor with 2-opt for medium route")
            # For medium size, use nearest neighbor then improve with 2-opt
            start = 0
            current = start
            route_indices = [current]
            unvisited = set(range(1, len(coordinates)))
            
            # Build initial solution with nearest neighbor
            while unvisited:
                # Find nearest unvisited location
                nearest = min(unvisited, key=lambda x: durations[current][x])
                route_indices.append(nearest)
                unvisited.remove(nearest)
                current = nearest
                
            # Improve solution with 2-opt swaps
            improved = True
            while improved:
                improved = False
                for i in range(1, len(route_indices) - 1):
                    for j in range(i + 1, len(route_indices)):
                        # Calculate current segment cost
                        current_cost = durations[route_indices[i-1]][route_indices[i]] + durations[route_indices[j-1]][route_indices[j]]
                        # Calculate cost after swap
                        new_cost = durations[route_indices[i-1]][route_indices[j-1]] + durations[route_indices[i]][route_indices[j]]
                        
                        if new_cost < current_cost:
                            # Reverse the segment for improvement
                            route_indices[i:j] = reversed(route_indices[i:j])
                            improved = True
                            break
                    if improved:
                        break
                        
            best_route_indices = route_indices
        
        else:
            logging.debug("Using hybrid algorithm for large route")
            # For larger sets, use a hybrid approach
            # First cluster points, then solve each cluster with nearest neighbor
            
            # Start with first point
            start = 0
            best_route_indices = [start]
            
            # Process remaining points in batches
            remaining = list(range(1, len(coordinates)))
            
            while remaining:
                current = best_route_indices[-1]
                
                # Find the closest point from remaining points
                closest = min(remaining, key=lambda x: durations[current][x])
                best_route_indices.append(closest)
                remaining.remove(closest)
                
                # Look ahead for possible improvements
                if len(remaining) >= 2:
                    # Try to find a point that would be a good next-next hop
                    for point in remaining:
                        # If this point is on the way to others, prioritize it
                        connecting_score = 0
                        for other in remaining:
                            if other != point:
                                # Check if point is "on the way" to other
                                direct = durations[current][other]
                                via_point = durations[current][point] + durations[point][other]
                                
                                # If going via this point doesn't add too much delay
                                if via_point < direct * 1.2:  # within 20% of direct route
                                    connecting_score += 1
                        
                        if connecting_score > 0:
                            # This point connects well to others
                            best_route_indices.append(point)
                            remaining.remove(point)
                            break
            
            # Calculate total duration
            route_duration = 0
            for i in range(len(best_route_indices) - 1):
                from_idx = best_route_indices[i]
                to_idx = best_route_indices[i + 1]
                route_duration += durations[from_idx][to_idx]
        
        # Convert route indices to coordinates
        optimized_route = [coordinates[i] for i in best_route_indices] if best_route_indices else []
        
        # Calculate total distance
        total_distance = 0
        if best_route_indices and distances:
            for i in range(len(best_route_indices) - 1):
                from_idx = best_route_indices[i]
                to_idx = best_route_indices[i + 1]
                total_distance += distances[from_idx][to_idx]
            
        # Convert seconds to hours:minutes format
        hours = int(route_duration / 3600) if best_route_indices else 0
        minutes = int((route_duration % 3600) / 60) if best_route_indices else 0
        time_str = f"{hours}h {minutes}m"
        
        # Round distance to 1 decimal place
        distance_str = f"{total_distance:.1f}"
        
        return optimized_route, time_str, distance_str
        
    except Exception as e:
        logging.error(f"Error optimizing route: {str(e)}")
        return None, 0, 0

def get_weather(coords):
    """Get current weather conditions for a location using OpenWeatherMap API"""
    try:
        # Check if API key is available
        if not config.WEATHER_API_KEY:
            logging.warning("Weather API key not configured. Weather data will not be available.")
            return None
            
        # Convert coordinates from [longitude, latitude] to [latitude, longitude]
        lat = coords[1]
        lon = coords[0]
        
        params = {
            'lat': lat,
            'lon': lon,
            'appid': config.WEATHER_API_KEY,
            'units': 'metric'  # Use metric units (Celsius, km/h)
        }
        
        response = requests.get(config.WEATHER_API_URL, params=params)
        
        # Check for API key errors
        if response.status_code == 401:
            logging.error("Invalid Weather API key. Please check your API key configuration.")
            return None
            
        response.raise_for_status()
        
        data = response.json()
        
        # Extract relevant weather information
        weather_data = {
            'condition': data['weather'][0]['main'],
            'description': data['weather'][0]['description'],
            'icon': data['weather'][0]['icon'],
            'temp': round(data['main']['temp']),
            'feels_like': round(data['main']['feels_like']),
            'humidity': data['main']['humidity'],
            'wind_speed': data['wind']['speed'],
            'location_name': data['name'],
            'updated_at': datetime.now().strftime('%H:%M'),
            'icon_url': f"https://openweathermap.org/img/wn/{data['weather'][0]['icon']}@2x.png"
        }
        
        # Add weather alerts if available
        if 'alerts' in data:
            weather_data['alerts'] = [{
                'event': alert['event'],
                'description': alert['description'],
                'start': datetime.fromtimestamp(alert['start']).strftime('%Y-%m-%d %H:%M'),
                'end': datetime.fromtimestamp(alert['end']).strftime('%Y-%m-%d %H:%M')
            } for alert in data['alerts']]
        else:
            weather_data['alerts'] = []
            
        return weather_data
    except Exception as e:
        logging.error(f"Error fetching weather data: {str(e)}")
        return None

def get_daylight_conditions(lat, lon, time=None):
    """
    Calculates daylight conditions for a specific location and time
    
    Args:
        lat: Latitude of the location
        lon: Longitude of the location
        time: Optional datetime object (defaults to current time)
    
    Returns:
        Dictionary with daylight information and light level (0-10)
        0 = pitch dark, 5 = twilight, 10 = full daylight
    """
    if time is None:
        time = datetime.now(pytz.UTC)
    else:
        # Ensure time is timezone aware
        if time.tzinfo is None:
            time = time.replace(tzinfo=pytz.UTC)
    
    try:
        # Get the current hour (0-23) to simplify logic
        current_hour = time.hour
        
        # Simplified approach based on hour of day
        if 6 <= current_hour < 8:  # Dawn
            light_level = 4
            status = "dawn"
        elif 8 <= current_hour < 12:  # Morning
            light_level = 8
            status = "morning"
        elif 12 <= current_hour < 17:  # Afternoon
            light_level = 9
            status = "afternoon"
        elif 17 <= current_hour < 19:  # Dusk
            light_level = 4
            status = "dusk"
        else:  # Night
            light_level = 1
            status = "night"
        
        # Generate approximate times for sun events based on the season
        # This is a simple approximation and doesn't consider location accurately
        month = time.month
        
        # Adjust sun events based on season (Northern Hemisphere)
        if 3 <= month <= 5:  # Spring
            dawn = "05:30"
            sunrise = "06:00"
            noon = "12:00"
            sunset = "19:00"
            dusk = "19:30"
        elif 6 <= month <= 8:  # Summer
            dawn = "04:30"
            sunrise = "05:00"
            noon = "12:00"
            sunset = "20:00"
            dusk = "20:30"
        elif 9 <= month <= 11:  # Fall
            dawn = "06:00"
            sunrise = "06:30"
            noon = "12:00"
            sunset = "18:00"
            dusk = "18:30"
        else:  # Winter
            dawn = "06:30"
            sunrise = "07:00"
            noon = "12:00"
            sunset = "17:00"
            dusk = "17:30"
            
        return {
            'status': status,
            'light_level': round(light_level, 1),
            'dawn': dawn,
            'sunrise': sunrise,
            'noon': noon,
            'sunset': sunset,
            'dusk': dusk,
            'current_time': time.strftime('%H:%M')
        }
    except Exception as e:
        logging.error(f"Error calculating daylight conditions: {str(e)}")
        # Return default values if calculation fails
        return {
            'status': 'unknown',
            'light_level': 5.0,  # Neutral value
            'dawn': '06:00',
            'sunrise': '07:00',
            'noon': '12:00',
            'sunset': '19:00',
            'dusk': '20:00',
            'current_time': time.strftime('%H:%M')
        }

def get_accident_risk(lat, lon, time=None):
    """
    Estimates accident risk for a location based on time and lighting conditions
    
    Args:
        lat: Latitude
        lon: Longitude
        time: Optional datetime (defaults to now)
    
    Returns:
        Dictionary with risk factors and overall risk score (0-10)
    """
    if time is None:
        time = datetime.now(pytz.UTC)
    else:
        # Ensure time is timezone aware
        if time.tzinfo is None:
            time = time.replace(tzinfo=pytz.UTC)
    
    # Get lighting conditions
    light_info = get_daylight_conditions(lat, lon, time)
    light_level = light_info['light_level']
    
    # Get weather conditions (if available)
    try:
        weather = get_weather([lon, lat])
        if weather and 'condition' in weather:
            weather_condition = weather['condition'].lower()
            visibility_reduced = any(cond in weather_condition for cond in 
                                ['rain', 'snow', 'fog', 'mist', 'drizzle', 'thunderstorm'])
        else:
            weather_condition = "clear"
            visibility_reduced = False
    except Exception:
        # Default to moderate conditions if weather API fails
        weather_condition = "clear"
        visibility_reduced = False
    
    # Base risk factors
    risks = {
        'low_light_risk': 0.0,
        'weather_risk': 0.0,
        'time_of_day_risk': 0.0,
        'road_complexity_risk': 0.0
    }
    
    # Calculate lighting risk (higher in low light conditions)
    if light_level < 3:
        # Night driving (highest risk)
        risks['low_light_risk'] = 3.0
    elif light_level < 6:
        # Twilight conditions (moderate risk)
        risks['low_light_risk'] = 2.0
    else:
        # Daylight (low risk)
        risks['low_light_risk'] = 0.0
    
    # Weather risk
    if weather_condition in ['thunderstorm', 'snow', 'blizzard']:
        risks['weather_risk'] = 3.0
    elif weather_condition in ['rain', 'drizzle', 'fog', 'mist']:
        risks['weather_risk'] = 2.0
    elif weather_condition in ['clouds', 'cloudy']:
        risks['weather_risk'] = 0.5
    
    # Time of day risk (independent of light, more about traffic patterns)
    hour = time.hour
    if 7 <= hour <= 9 or 16 <= hour <= 18:
        # Rush hour (higher risk)
        risks['time_of_day_risk'] = 2.0
    elif 23 <= hour or hour <= 4:
        # Late night (higher risk due to fatigue, potential impaired drivers)
        risks['time_of_day_risk'] = 2.5
    else:
        # Regular daytime
        risks['time_of_day_risk'] = 1.0
    
    # For road complexity, we would ideally use historical accident data or road features
    # Here we use a simplified model based on the geographic location
    # In a real system, this would come from a database of accident hotspots
    
    # For this demo, we'll randomize but seed based on the coordinates for consistency
    seed_value = int((lat * 1000 + lon * 1000) % 100000)
    random.seed(seed_value)
    risks['road_complexity_risk'] = random.uniform(0, 2)
    
    # Calculate overall risk (0-10 scale)
    total_risk = (
        risks['low_light_risk'] * 1.5 +  # Weight lighting heavily
        risks['weather_risk'] * 1.3 +    # Weather is important
        risks['time_of_day_risk'] * 1.0 + # Standard weight for time
        risks['road_complexity_risk'] * 1.2  # Road features matter
    )
    
    # Scale to 0-10
    scaled_risk = min(10, max(0, total_risk * 1.1))
    
    return {
        'risk_score': round(scaled_risk, 1),
        'risk_level': 'high' if scaled_risk > 7 else 'medium' if scaled_risk > 4 else 'low',
        'factors': risks,
        'light_conditions': light_info['status'],
        'light_level': light_info['light_level'],
        'visibility_reduced': visibility_reduced,
        'recommendations': get_safety_recommendations(scaled_risk, risks, light_level < 5, visibility_reduced)
    }

def get_safety_recommendations(risk_score, risk_factors, is_dark, poor_visibility):
    """Generate safety recommendations based on risk factors"""
    recommendations = []
    
    if risk_score > 7:
        recommendations.append("Zachowaj szczególną ostrożność - wysoki poziom ryzyka na trasie.")
    
    if risk_factors['low_light_risk'] > 1.5:
        recommendations.append("Słaba widoczność z powodu zmroku lub nocy - włącz pełne oświetlenie.")
    
    if risk_factors['weather_risk'] > 1.5:
        recommendations.append("Trudne warunki pogodowe - dostosuj prędkość do warunków.")
    
    if is_dark and poor_visibility:
        recommendations.append("Krytycznie niska widoczność - rozważ opóźnienie podróży jeśli to możliwe.")
    
    if risk_factors['time_of_day_risk'] > 1.5:
        if datetime.now().hour < 12:
            recommendations.append("Poranny szczyt - spodziewaj się większego natężenia ruchu.")
        else:
            recommendations.append("Popołudniowy szczyt - spodziewaj się większego natężenia ruchu.")
    
    if risk_factors['road_complexity_risk'] > 1.5:
        recommendations.append("Ten odcinek ma historię zwiększonej liczby wypadków.")
    
    if len(recommendations) == 0:
        recommendations.append("Normalne warunki jazdy - zachowaj standardowe środki ostrożności.")
    
    return recommendations

def simulate_traffic_conditions(start, end):
    """
    Simulates traffic conditions based on time of day, location, lighting conditions,
    and accident risk. This improved version considers more factors for a realistic model.
    
    Args:
        start: Start coordinates [lon, lat]
        end: End coordinates [lon, lat]
    
    Returns:
        Integer traffic level (0-3)
        0 = Free flowing, 1 = Light traffic, 2 = Moderate traffic, 3 = Heavy traffic
    """
    # Get current time for simulation with timezone awareness
    current_time = datetime.now(pytz.UTC)
    current_hour = current_time.hour
    
    # Calculate midpoint of the segment for analysis
    mid_lat = (start[1] + end[1]) / 2
    mid_lon = (start[0] + end[0]) / 2
    
    try:
        # Get lighting conditions for this segment
        light_info = get_daylight_conditions(mid_lat, mid_lon, current_time)
        
        # Get accident risk factors
        risk_info = get_accident_risk(mid_lat, mid_lon, current_time)
        
        # Base probability based on time of day
        if 7 <= current_hour <= 9:  # Morning rush hour
            base_probability = 0.7
        elif 16 <= current_hour <= 19:  # Evening rush hour
            base_probability = 0.8
        elif 10 <= current_hour <= 15:  # Midday
            base_probability = 0.3
        elif 20 <= current_hour <= 23:  # Evening
            base_probability = 0.2
        else:  # Late night/early morning
            base_probability = 0.1
        
        # Adjust for lighting conditions
        if light_info['light_level'] < 3:
            # Darkness tends to reduce overall traffic volume but may increase risk
            base_probability -= 0.1  # Less traffic volume
        
        # Adjust for weather/visibility from risk info
        if risk_info.get('visibility_reduced', False):
            base_probability += 0.15  # Worse traffic with poor visibility
        
        # Adjust for road complexity risk (higher risk often correlates with congestion)
        road_complexity = risk_info.get('factors', {}).get('road_complexity_risk', 0)
        if road_complexity > 1:
            base_probability += 0.1  # Higher risk areas often have more traffic
        
        # Calculate day of week impact (weekends have less traffic)
        day_of_week = current_time.weekday()  # 0=Monday, 6=Sunday
        if day_of_week >= 5:  # Weekend
            base_probability *= 0.7  # 30% reduction for weekends
        
        # Add some randomness (with different seed than risk calculation)
        random.seed(int(time.time() * 1000) % 100000)  # Different seed
        random_factor = random.random() * 0.3 - 0.15  # -0.15 to +0.15
        
        # Calculate final probability (cap between 0 and 1)
        probability = max(0, min(1, base_probability + random_factor))
        
        # Determine traffic level based on probability
        if probability < 0.2:
            return 0  # Free flowing
        elif probability < 0.5:
            return 1  # Light traffic
        elif probability < 0.8:
            return 2  # Moderate traffic
        else:
            return 3  # Heavy traffic
            
    except Exception as e:
        # If anything fails, return a reasonable default
        logging.error(f"Error in traffic simulation: {str(e)}")
        # Default based purely on time of day without other factors
        if 7 <= current_hour <= 9 or 16 <= current_hour <= 19:  # Rush hours
            return 2  # Moderate traffic during rush hour
        else:
            return 1  # Light traffic otherwise

def calculate_distance(point1, point2):
    """Calculate straight-line distance between two points in km"""
    # Earth radius in km
    R = 6371.0
    
    # Convert coordinates to radians
    lon1, lat1 = math.radians(point1[0]), math.radians(point1[1])
    lon2, lat2 = math.radians(point2[0]), math.radians(point2[1])
    
    # Differences in coordinates
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    
    # Haversine formula
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    
    return distance

def get_route_details(coordinates, include_traffic=True):
    """
    Get detailed route information between consecutive points
    
    Args:
        coordinates: List of longitude/latitude pairs
        include_traffic: Whether to include real-time traffic data (default: True)
    
    Returns:
        Dictionary with route segments, total distance, and duration
    """
    route_segments = []
    total_distance = 0
    total_duration = 0
    traffic_conditions = []
    traffic_delay_seconds = 0
    
    # Check if API key is available
    if not config.OPENROUTE_API_KEY:
        logging.warning("OpenRouteService API key not configured. Detailed route information will not be available.")
        return {
            'segments': [],
            'total_distance': 0,
            'total_duration': 0,
            'formatted_duration': "0h 0m",
            'avg_traffic_level': 0,
            'traffic_delay': 0,
            'error': "API key missing"
        }
    
    # Calculate route between each consecutive point
    for i in range(len(coordinates) - 1):
        start = coordinates[i]
        end = coordinates[i + 1]
        
        # Call OpenRouteService Directions API
        headers = {
            'Authorization': config.OPENROUTE_API_KEY,
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        # Parametry dla wyświetlania geometrii trasy
        # OpenRouteService wymaga współrzędnych w formacie [longitude, latitude]
        body = {
            "coordinates": [[start[0], start[1]], [end[0], end[1]]],
            "instructions": True,
            "preference": "recommended",
            "geometry": True
        }
        
        try:
            response = requests.post(
                config.OPENROUTE_DIRECTIONS_URL,
                json=body, 
                headers=headers
            )
            
            # Check for API key errors
            if response.status_code == 401 or response.status_code == 403:
                logging.error("Invalid OpenRouteService API key. Please check your API key configuration.")
                raise Exception("Invalid API key")
                
            response.raise_for_status()
            route_data = response.json()
            
            # Extract route details
            if 'routes' in route_data and len(route_data['routes']) > 0:
                route = route_data['routes'][0]
                geometry = route.get('geometry')
                summary = route.get('summary', {})
                
                # Decode the geometry if it's in encoded format
                geometry_coordinates = []
                
                # OpenRouteService zwraca geometrię jako zakodowany ciąg znaków polyline
                # Zachowamy tę zakodowaną wersję, aby później zdekodować ją w JavaScript
                encoded_geometry = None
                
                if isinstance(geometry, str):
                    # Zapisz oryginalny zakodowany string dla JavaScript
                    encoded_geometry = geometry
                    # Dla kompatybilności stwórz też prostą linię jako rezerwę
                    geometry_coordinates = [[start[0], start[1]], [end[0], end[1]]]
                    logging.debug(f"Segment {i}: Zakodowana geometria polyline, długość: {len(geometry)}")
                elif 'coordinates' in route.get('geometry', {}):
                    geometry_coordinates = route['geometry']['coordinates']
                    logging.debug(f"Segment {i}: Geometria jako współrzędne, punktów: {len(geometry_coordinates)}")
                else:
                    geometry_coordinates = [[start[0], start[1]], [end[0], end[1]]]
                    logging.debug(f"Segment {i}: Brak geometrii, używamy linii prostej")
                
                # Log the geometry format for debugging
                logging.debug(f"Segment {i}: Route geometry format: {type(geometry)}")
                
                # Extract duration and distance
                base_duration = summary.get('duration', 0)
                distance = summary.get('distance', 0) / 1000  # Convert to km
                
                # Simulate traffic conditions
                traffic_level = simulate_traffic_conditions(start, end)
                
                # Calculate simulated delay based on traffic level
                if include_traffic and traffic_level > 0:
                    # Add delay based on traffic level (0-3)
                    delay_factor = [0, 0.15, 0.3, 0.6][traffic_level]
                    traffic_delay = base_duration * delay_factor
                else:
                    traffic_delay = 0
                
                # Store the adjusted duration
                adjusted_duration = base_duration + traffic_delay
                
                # Set the color based on traffic level
                if traffic_level == 0:
                    traffic_color = 'green'  # Free flowing
                elif traffic_level == 1:
                    traffic_color = 'yellow'  # Light traffic
                elif traffic_level == 2:
                    traffic_color = 'orange'  # Moderate traffic
                else:
                    traffic_color = 'red'     # Heavy traffic
                
                # Get weather data for each destination point
                weather_data = None
                if i < len(coordinates) - 2:  # Don't get weather for the return to start
                    weather_data = get_weather(end)
                
                # Extract steps and instructions if available
                instructions = []
                if 'legs' in route and len(route['legs']) > 0:
                    for leg in route['legs']:
                        for step in leg.get('steps', []):
                            instructions.append({
                                'instruction': step.get('instruction', ''),
                                'distance': step.get('distance', 0),
                                'duration': step.get('duration', 0)
                            })
                
                # Dodajemy więcej informacji o trasie
                road_features = []
                
                # Dodajemy informacje o światłach, skrzyżowaniach, etc.
                if 'segments' in route and len(route['segments']) > 0:
                    for segment_info in route['segments']:
                        if 'steps' in segment_info:
                            for step in segment_info['steps']:
                                # Analizujemy instrukcje, aby wykryć światła, zakręty, etc.
                                instruction = step.get('instruction', '').lower()
                                if 'traffic light' in instruction or 'światłach' in instruction:
                                    road_features.append({
                                        'type': 'traffic_light', 
                                        'distance': step.get('distance'),
                                        'description': step.get('instruction')
                                    })
                                elif 'roundabout' in instruction or 'rondo' in instruction:
                                    road_features.append({
                                        'type': 'roundabout',
                                        'distance': step.get('distance'),
                                        'description': step.get('instruction')
                                    })
                                elif 'turn' in instruction or 'skręć' in instruction:
                                    road_features.append({
                                        'type': 'turn',
                                        'distance': step.get('distance'),
                                        'description': step.get('instruction')
                                    })
                
                # Dodajemy informacje o warunkach oświetleniowych i ryzyku wypadków
                mid_point_lat = (start[1] + end[1]) / 2
                mid_point_lon = (start[0] + end[0]) / 2
                
                # Pobieramy informacje o warunkach oświetlenia na trasie
                light_conditions = get_daylight_conditions(mid_point_lat, mid_point_lon)
                
                # Pobieramy analizę ryzyka wypadków
                accident_risk = get_accident_risk(mid_point_lat, mid_point_lon)
                
                segment = {
                    'start_idx': i,
                    'end_idx': i + 1,
                    'distance': distance,
                    'duration': adjusted_duration,
                    'base_duration': base_duration,
                    'traffic_delay': traffic_delay,
                    'traffic_level': traffic_level,
                    'traffic_color': traffic_color,
                    'geometry': geometry_coordinates,
                    'encoded_geometry': encoded_geometry,  # Dodajemy zakodowaną wersję
                    'weather': weather_data,
                    'instructions': instructions,
                    'road_features': road_features,
                    'avg_speed': round((distance * 1000 / base_duration) * 3.6, 1) if base_duration > 0 else 0,  # km/h
                    # Dodajemy nowe informacje o oświetleniu i bezpieczeństwie
                    'lighting_conditions': light_conditions,
                    'accident_risk': accident_risk
                }
                
                total_distance += distance
                total_duration += adjusted_duration
                traffic_delay_seconds += traffic_delay
                traffic_conditions.append({
                    'segment': i,
                    'level': traffic_level,
                    'color': traffic_color,
                    'delay_seconds': traffic_delay
                })
                route_segments.append(segment)
            else:
                logging.error("No routes found in the API response")
                # Fall back to a simple straight line
                segment = {
                    'start_idx': i,
                    'end_idx': i + 1,
                    'distance': calculate_distance(start, end),
                    'duration': 0,
                    'base_duration': 0,
                    'traffic_delay': 0,
                    'traffic_level': 0,
                    'traffic_color': 'gray',
                    'geometry': [[start[0], start[1]], [end[0], end[1]]],
                    'instructions': [],
                    'weather': None
                }
                route_segments.append(segment)
        except Exception as e:
            logging.error(f"Error fetching route details: {str(e)}")
            # Fall back to a simple straight line if route can't be calculated
            segment = {
                'start_idx': i,
                'end_idx': i + 1,
                'distance': calculate_distance(start, end),
                'duration': 0,  # Cannot determine duration
                'base_duration': 0,
                'traffic_delay': 0,
                'traffic_level': 0,
                'traffic_color': 'gray',
                'geometry': [[start[0], start[1]], [end[0], end[1]]],
                'instructions': [],
                'weather': None
            }
            route_segments.append(segment)
    
    # Format total_duration as a string (e.g., "2h 30m")
    hours = int(total_duration / 3600)
    minutes = int((total_duration % 3600) / 60)
    formatted_duration = ''
    if hours > 0:
        formatted_duration += f"{hours}h "
    formatted_duration += f"{minutes}m"
    
    # For compatibility with older code
    # min_duration variable is not used, removing to fix linting issues
    
    # Format traffic delay as a string
    delay_minutes = int(traffic_delay_seconds / 60)
    traffic_delay_text = f"+{delay_minutes}m due to traffic" if delay_minutes > 0 else "No delays"
    
    # Analiza świateł drogowych na trasie
    # Zbieramy geometrię z wszystkich segmentów do analizy
    all_geometry = []
    for segment in route_segments:
        if 'geometry' in segment and segment['geometry']:
            all_geometry.extend(segment['geometry'])
    
    # Jeśli mamy wystarczającą liczbę punktów geometrii, analizujemy światła
    traffic_light_analysis = None
    if len(all_geometry) > 2:
        try:
            # Inicjalizacja regionu dla symulowanych świateł
            min_lon = min(point[0] for point in all_geometry)
            max_lon = max(point[0] for point in all_geometry)
            min_lat = min(point[1] for point in all_geometry)
            max_lat = max(point[1] for point in all_geometry)
            
            # Dodaj bufor
            buffer = 0.01  # w przybliżeniu 1km
            region_bounds = [
                [min_lon - buffer, min_lat - buffer],
                [max_lon + buffer, max_lat + buffer]
            ]
            
            # Inicjalizuj symulowane światła drogowe dla tego regionu
            traffic_light_optimizer.initialize_traffic_light_map(region_bounds)
            
            # Analizuj trasę pod kątem świateł
            traffic_light_analysis = traffic_light_optimizer.analyze_route_for_lights({
                'segments': route_segments,
                'coordinates': all_geometry
            })
            
            logging.info(f"Wykryto {len(traffic_light_analysis.get('traffic_lights', []))} świateł drogowych na trasie")
        except Exception as e:
            logging.error(f"Błąd analizy świateł drogowych: {str(e)}")
    
    return {
        'segments': route_segments,
        'total_distance': round(total_distance, 2),
        'total_duration': formatted_duration,
        'total_duration_seconds': total_duration,
        'base_duration_seconds': total_duration - traffic_delay_seconds,
        'traffic_delay_seconds': traffic_delay_seconds,
        'traffic_delay_text': traffic_delay_text,
        'traffic_conditions': traffic_conditions,
        'has_traffic_data': include_traffic,
        'traffic_light_analysis': traffic_light_analysis,  # Dodajemy analizę świateł
        'timestamp': int(time.time())
    }

def check_for_traffic_updates(route_data, threshold_percent=15):
    """
    Check if traffic conditions have changed significantly since route was created
    
    Args:
        route_data: The original route data
        threshold_percent: Percentage change threshold to trigger update
        
    Returns:
        Dictionary with update status and new route data if needed
    """
    # If no timestamp or over 10 minutes old, always update
    if 'timestamp' not in route_data or time.time() - route_data.get('timestamp', 0) > 600:
        # Make sure we have coordinates to work with
        if 'coordinates' not in route_data:
            return {
                'needs_update': False,
                'reason': 'No coordinates available to check for updates'
            }
            
        new_route = get_route_details(route_data['coordinates'])
        return {
            'needs_update': True,
            'reason': 'Route information is outdated',
            'new_route': new_route
        }
    
    # Check each segment for traffic changes
    if 'route_details' in route_data and 'segments' in route_data['route_details']:
        segments = route_data['route_details']['segments']
        coordinates = [segment['geometry'][0] for segment in segments]
    else:
        # If we don't have detailed segment information, use the original coordinates
        if 'coordinates' not in route_data:
            return {
                'needs_update': False,
                'reason': 'No route details available to check for updates'
            }
        coordinates = route_data['coordinates']
        updated_route = get_route_details(coordinates)
        return {
            'needs_update': True,
            'reason': 'Route information needs to be refreshed',
            'new_route': updated_route
        }
    
    # Get current traffic conditions
    updated_route = get_route_details(coordinates)
    
    # Compare segment durations
    duration_changes = []
    max_change_percent = 0
    changed_segment_idx = -1
    
    for i, (old_segment, new_segment) in enumerate(zip(segments, updated_route['segments'])):
        if 'duration' not in old_segment or 'duration' not in new_segment:
            continue
            
        old_duration = old_segment['duration']
        new_duration = new_segment['duration']
        
        if old_duration == 0:
            continue
            
        change_percent = abs(new_duration - old_duration) / old_duration * 100
        
        duration_changes.append({
            'segment': i,
            'old_duration': old_duration,
            'new_duration': new_duration,
            'change_percent': change_percent,
            'increased': new_duration > old_duration
        })
        
        if change_percent > max_change_percent:
            max_change_percent = change_percent
            changed_segment_idx = i
    
    # Determine if an update is needed
    needs_update = max_change_percent >= threshold_percent
    
    if needs_update and changed_segment_idx >= 0:
        old_segment = segments[changed_segment_idx] 
        new_segment = updated_route['segments'][changed_segment_idx]
        
        # Get the location names for better context
        from_location = f"point {changed_segment_idx + 1}"
        to_location = f"point {changed_segment_idx + 2}"
        
        if changed_segment_idx < len(segments) - 1 and 'weather' in segments[changed_segment_idx + 1] and segments[changed_segment_idx + 1]['weather']:
            to_location = segments[changed_segment_idx + 1]['weather']['location_name']
        
        # Create reason message
        old_minutes = int(old_segment['duration'] / 60)
        new_minutes = int(new_segment['duration'] / 60)
        diff_minutes = new_minutes - old_minutes
        
        if diff_minutes > 0:
            reason = f"Traffic increased on the route to {to_location} (+{diff_minutes} min)"
        else:
            reason = f"Traffic decreased on the route to {to_location} ({diff_minutes} min)"
    else:
        reason = "No significant traffic changes"
    
    return {
        'needs_update': needs_update,
        'reason': reason,
        'max_change_percent': max_change_percent,
        'changed_segment': changed_segment_idx if needs_update else -1,
        'duration_changes': duration_changes,
        'new_route': updated_route if needs_update else None
    }
