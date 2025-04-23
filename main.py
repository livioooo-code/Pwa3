import os
import csv
import io
import json
import time
import logging
from datetime import datetime

from flask import render_template, request, jsonify, flash, redirect, url_for, session, make_response, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user

from app import app
from extensions import db
from forms import LoginForm, RegistrationForm
from models import Courier, Route, Location, CourierRouteAssignment
import config
from route_optimizer import optimize_route, geocode_address, get_route_details, check_for_traffic_updates

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Initialize database connection status
db_connected = True

@app.route('/')
def index():
    """Display the main page with the navigation form"""
    saved_routes = []
    
    if db_connected:
        try:
            # Get saved routes from the database
            saved_routes = Route.query.order_by(Route.created_at.desc()).all()
        except Exception as e:
            logging.error(f"Error loading saved routes: {str(e)}")
    
    return render_template('index.html', api_key=config.OPENROUTE_API_KEY, saved_routes=saved_routes)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    form = LoginForm()
    if form.validate_on_submit():
        courier = Courier.query.filter_by(username=form.username.data).first()
        if courier and courier.check_password(form.password.data):
            login_user(courier, remember=form.remember.data)
            next_page = request.args.get('next')
            flash(f'Witaj, {courier.username}! Zostałeś zalogowany.', 'success')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Niepoprawna nazwa użytkownika lub hasło', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    form = RegistrationForm()
    if form.validate_on_submit():
        courier = Courier(
            username=form.username.data,
            email=form.email.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            phone=form.phone.data
        )
        courier.set_password(form.password.data)
        
        db.session.add(courier)
        db.session.commit()
        
        flash(f'Konto zostało pomyślnie utworzone! Możesz się teraz zalogować.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    logout_user()
    flash('Zostałeś wylogowany.', 'info')
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    """Display user profile and routes"""
    # Fetch user's assigned routes
    assigned_routes = CourierRouteAssignment.query.filter_by(courier_id=current_user.id).all()
    return render_template('profile.html', courier=current_user, assignments=assigned_routes)

@app.route('/optimize', methods=['POST'])
def optimize():
    """Process the form data and optimize the route"""
    try:
        import time
        
        # Get locations from the form
        locations = []
        location_details = []
        use_current_location = request.form.get('use_current_location') == 'on'
        current_location_coords = None
        
        if use_current_location:
            # Pobierz współrzędne bieżącej lokalizacji z danych formularza
            current_lat = request.form.get('current_lat', '')
            current_lon = request.form.get('current_lon', '')
            
            if current_lat and current_lon:
                # Dodaj aktualną lokalizację jako pierwszy punkt
                current_location_coords = [float(current_lon), float(current_lat)]
                locations.append("Aktualna lokalizacja")
                location_details.append({
                    'city': 'Aktualna lokalizacja',
                    'street': '',
                    'number': '',
                    'category': 'current_location',
                    'time_window_start': '',
                    'time_window_end': '',
                    'estimated_duration': '5'
                })
        
        # Pobierz pozostałe lokalizacje z formularza
        for i in range(int(request.form.get('location_count', 0))):
            city = request.form.get(f'city_{i}', '')
            street = request.form.get(f'street_{i}', '')
            number = request.form.get(f'number_{i}', '')
            category = request.form.get(f'category_{i}', 'home')
            time_window_start = request.form.get(f'time_window_start_{i}', '')
            time_window_end = request.form.get(f'time_window_end_{i}', '')
            estimated_duration = request.form.get(f'estimated_duration_{i}', '10')
            
            if city and street and number:
                address = f"{street} {number}, {city}"
                locations.append(address)
                location_details.append({
                    'city': city,
                    'street': street,
                    'number': number,
                    'category': category,
                    'time_window_start': time_window_start,
                    'time_window_end': time_window_end,
                    'estimated_duration': estimated_duration
                })
            elif city and street:
                address = f"{street}, {city}"
                locations.append(address)
                location_details.append({
                    'city': city,
                    'street': street,
                    'number': '',
                    'category': category,
                    'time_window_start': time_window_start,
                    'time_window_end': time_window_end,
                    'estimated_duration': estimated_duration
                })
        
        # Sprawdź, czy mamy wystarczająco dużo adresów do optymalizacji
        min_locations = 2
        if use_current_location:
            min_locations = 1  # Jeśli używamy aktualnej lokalizacji, wystarczy jeden dodatkowy adres
            
        if len(locations) < min_locations:
            flash("Proszę wprowadzić co najmniej dwie lokalizacje do optymalizacji trasy.", "danger")
            return redirect(url_for('index'))

        # Geocode addresses to coordinates
        coords = []
        formatted_addresses = []
        for idx, address in enumerate(locations):
            # Jeśli to aktualna lokalizacja, użyj przekazanych współrzędnych
            if idx == 0 and use_current_location and current_location_coords:
                coords.append(current_location_coords)
                formatted_addresses.append("Aktualna lokalizacja")
                # Dodaj współrzędne do location_details
                location_details[idx]['longitude'] = current_location_coords[0]
                location_details[idx]['latitude'] = current_location_coords[1]
                location_details[idx]['formatted_address'] = "Aktualna lokalizacja"
            else:
                geocode_result = geocode_address(address)
                if geocode_result and 'coordinates' in geocode_result:
                    coords.append(geocode_result['coordinates'])
                    formatted_addresses.append(geocode_result['formatted_address'])
                    # Add coordinates to location details
                    location_details[idx]['longitude'] = geocode_result['coordinates'][0]
                    location_details[idx]['latitude'] = geocode_result['coordinates'][1]
                    location_details[idx]['formatted_address'] = geocode_result['formatted_address']
                else:
                    flash(f"Nie udało się odnaleźć adresu: {address}", "danger")
                    return redirect(url_for('index'))

        # Optimize route
        optimized_route, total_time, total_distance = optimize_route(coords)
        
        if not optimized_route:
            flash("Could not optimize route. Please try different locations.", "danger")
            return redirect(url_for('index'))

        # Get route details with real-time traffic information
        include_traffic = request.form.get('include_traffic', 'true').lower() == 'true'
        route_details = get_route_details(optimized_route, include_traffic=include_traffic)
        
        # Sprawdź, czy mamy geometrię tras
        for i, segment in enumerate(route_details.get('segments', [])):
            if 'geometry' in segment:
                num_points = len(segment['geometry'])
                logging.debug(f"Segment {i} ma {num_points} punktów geometrycznych")
        
        # Store in session for display
        session['optimized_route'] = {
            'coordinates': optimized_route,
            'addresses': [formatted_addresses[i] for i in range(len(formatted_addresses))],
            'total_time': route_details['total_duration'],
            'total_distance': route_details['total_distance'],
            'total_duration_seconds': route_details['total_duration_seconds'],
            'route_details': route_details,
            'location_details': location_details,
            'traffic_delay_text': route_details.get('traffic_delay_text', ''),
            'has_traffic_data': route_details.get('has_traffic_data', False),
            'traffic_conditions': route_details.get('traffic_conditions', []),
            'last_traffic_update': int(time.time()),
            # Dodatkowo wyciągamy segmenty trasy na górny poziom dla łatwiejszego dostępu w JavaScript
            'segments': route_details.get('segments', [])
        }
        
        flash("Route optimized successfully!", "success")
        return redirect(url_for('index'))
    
    except Exception as e:
        logging.error(f"Error in optimization: {str(e)}")
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/get_route')
def get_route():
    """Return the optimized route data for AJAX requests"""
    import time
    
    route_data = session.get('optimized_route', {})
    
    # Check if we need to update for traffic changes
    if route_data and 'coordinates' in route_data:
        # Check if route is older than 2 minutes or check_traffic parameter is provided
        current_time = int(time.time())
        last_update = route_data.get('last_traffic_update', 0)
        force_check = request.args.get('check_traffic', 'false').lower() == 'true'
        
        if force_check or (current_time - last_update > 120):  # 2 minutes
            logging.debug("Checking for traffic updates...")
            traffic_update = check_for_traffic_updates(route_data)
            
            if traffic_update.get('needs_update', False):
                logging.debug(f"Traffic update needed: {traffic_update['reason']}")
                
                # Update the route with new traffic data
                new_route = traffic_update.get('new_route')
                if new_route:
                    # Update duration and traffic information
                    route_data['total_time'] = new_route['total_duration']
                    route_data['total_duration_seconds'] = new_route['total_duration_seconds']
                    route_data['traffic_delay_text'] = new_route.get('traffic_delay_text', '')
                    route_data['traffic_conditions'] = new_route.get('traffic_conditions', [])
                    route_data['route_details'] = new_route
                    route_data['last_traffic_update'] = current_time
                    route_data['has_traffic_update'] = True
                    route_data['traffic_update_reason'] = traffic_update['reason']
                    
                    # Store the updated route back in the session
                    session['optimized_route'] = route_data
            else:
                # Still update the last check timestamp
                route_data['last_traffic_update'] = current_time
                session['optimized_route'] = route_data
    
    return jsonify(route_data)

@app.route('/.well-known/<path:filename>')
def well_known(filename):
    """Serve .well-known files for PWA and TWA support"""
    return send_from_directory(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.well-known'), filename)

@app.route('/get_navigation')
def get_navigation():
    """Return navigation route from current location to first stop"""
    try:
        from_location = request.args.get('from', '')
        to_location = request.args.get('to', '')
        
        if not from_location or not to_location:
            return jsonify({'error': 'Missing from or to parameters'}), 400
        
        # Parse coordinates
        from_coords = [float(x) for x in from_location.split(',')]
        to_coords = [float(x) for x in to_location.split(',')]
        
        # Convert to [lon, lat] format for the API
        from_coords_api = [from_coords[1], from_coords[0]]
        to_coords_api = [to_coords[1], to_coords[0]]
        
        # Get navigation route details from OpenRouteService
        route_details = get_route_details([from_coords_api, to_coords_api])
        
        if route_details and len(route_details) > 0:
            return jsonify({'route': route_details[0]})
        else:
            return jsonify({'error': 'Could not find navigation route'}), 404
    
    except Exception as e:
        logging.error(f"Error in navigation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/save_route', methods=['POST'])
@login_required
def save_route():
    """Save route to database"""
    if not db_connected:
        flash("Route saving is currently unavailable due to database issues.", "danger")
        return redirect(url_for('index'))
        
    try:
        route_name = request.form.get('route_name', '')
        route_data_json = request.form.get('route_data', '')
        
        if not route_data_json:
            flash("No route data available to save.", "warning")
            return redirect(url_for('index'))
            
        route_data = json.loads(route_data_json)
        
        if not route_data or 'coordinates' not in route_data:
            flash("Invalid route data.", "warning")
            return redirect(url_for('index'))
            
        # Create new route
        new_route = Route(
            name=route_name,
            total_distance=route_data.get('total_distance', 0),
            total_time=route_data.get('total_time', '0m'),
            coordinates_json=json.dumps(route_data.get('coordinates', []))
        )
        
        db.session.add(new_route)
        db.session.flush()  # Get the ID for the new route
        
        # Add locations
        for i, coords in enumerate(route_data.get('coordinates', [])):
            # Skip the last point if it's the same as the first (return to start)
            if i == len(route_data.get('coordinates', [])) - 1 and i > 0:
                if coords[0] == route_data['coordinates'][0][0] and coords[1] == route_data['coordinates'][0][1]:
                    continue
            
            # Get location details if available
            location_detail = None
            if route_data.get('location_details') and i < len(route_data.get('location_details')):
                location_detail = route_data['location_details'][i]
            
            # Get address if available
            formatted_address = ''
            if route_data.get('addresses') and i < len(route_data.get('addresses')):
                formatted_address = route_data['addresses'][i]
            
            # Create location entry
            city = location_detail.get('city', '') if location_detail else ''
            street = location_detail.get('street', '') if location_detail else ''
            number = location_detail.get('number', '') if location_detail else ''
            category = location_detail.get('category', 'home') if location_detail else 'home'
            
            # Parse time windows if present
            time_window_start = None
            time_window_end = None
            estimated_duration = 10
            
            if location_detail:
                if location_detail.get('time_window_start'):
                    try:
                        time_window_start = datetime.strptime(location_detail.get('time_window_start'), '%H:%M').time()
                    except:
                        pass
                        
                if location_detail.get('time_window_end'):
                    try:
                        time_window_end = datetime.strptime(location_detail.get('time_window_end'), '%H:%M').time()
                    except:
                        pass
                        
                if location_detail.get('estimated_duration'):
                    try:
                        estimated_duration = int(location_detail.get('estimated_duration'))
                    except:
                        pass
            
            # Create location
            location = Location(
                route_id=new_route.id,
                city=city,
                street=street,
                number=number,
                position=i,
                formatted_address=formatted_address,
                longitude=coords[0],
                latitude=coords[1],
                category=category,
                time_window_start=time_window_start,
                time_window_end=time_window_end,
                estimated_duration=estimated_duration
            )
            
            db.session.add(location)
        
        # Assign the route to the current user if logged in
        if current_user.is_authenticated:
            assignment = CourierRouteAssignment(
                courier_id=current_user.id,
                route_id=new_route.id,
                status='assigned'
            )
            db.session.add(assignment)
        
        db.session.commit()
        flash("Route saved successfully!", "success")
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error saving route: {str(e)}")
        flash(f"An error occurred while saving the route: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/load_route/<int:route_id>')
def load_route(route_id):
    """Load a route from the database"""
    try:
        route = Route.query.get(route_id)
        
        if not route:
            flash("Route not found.", "danger")
            return redirect(url_for('index'))
            
        # Get location details
        locations = Location.query.filter_by(route_id=route.id).order_by(Location.position).all()
        
        location_details = []
        formatted_addresses = []
        
        for loc in locations:
            location_details.append({
                'city': loc.city,
                'street': loc.street,
                'number': loc.number,
                'formatted_address': loc.formatted_address,
                'longitude': loc.longitude,
                'latitude': loc.latitude,
                'category': loc.category,
                'time_window_start': loc.time_window_start.strftime('%H:%M') if loc.time_window_start else '',
                'time_window_end': loc.time_window_end.strftime('%H:%M') if loc.time_window_end else '',
                'estimated_duration': loc.estimated_duration
            })
            formatted_addresses.append(loc.formatted_address)
            
        # Get the latest route details with current traffic conditions
        route_details = get_route_details(route.coordinates)
        
        # Store in session
        session['optimized_route'] = {
            'coordinates': route.coordinates,
            'addresses': formatted_addresses,
            'total_time': route_details['total_duration'],
            'total_distance': route_details['total_distance'],
            'total_duration_seconds': route_details['total_duration_seconds'],
            'route_details': route_details,
            'location_details': location_details,
            'traffic_delay_text': route_details.get('traffic_delay_text', ''),
            'has_traffic_data': route_details.get('has_traffic_data', False),
            'traffic_conditions': route_details.get('traffic_conditions', []),
            'last_traffic_update': int(time.time()),
            'segments': route_details.get('segments', []),
            'loaded_route_id': route.id,
            'loaded_route_name': route.name
        }
        
        flash(f"Route '{route.name}' loaded successfully!", "success")
        return redirect(url_for('index'))
        
    except Exception as e:
        logging.error(f"Error loading route: {str(e)}")
        flash(f"An error occurred while loading the route: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/delete_route/<int:route_id>', methods=['POST'])
@login_required
def delete_route(route_id):
    """Delete a route from the database"""
    try:
        route = Route.query.get(route_id)
        
        if not route:
            flash("Route not found.", "danger")
            return redirect(url_for('index'))
        
        # Check if the user is assigned to this route
        assignment = CourierRouteAssignment.query.filter_by(courier_id=current_user.id, route_id=route.id).first()
        if not assignment:
            flash("You don't have permission to delete this route.", "danger")
            return redirect(url_for('index'))
            
        # Delete route (cascade will delete locations and assignments)
        db.session.delete(route)
        db.session.commit()
        
        flash("Route deleted successfully!", "success")
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting route: {str(e)}")
        flash(f"An error occurred while deleting the route: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/export_route', methods=['POST'])
def export_route():
    """Export route data in various formats"""
    try:
        route_data_json = request.form.get('route_data', '')
        export_format = request.form.get('format', 'csv')
        
        if not route_data_json:
            flash("No route data available to export.", "warning")
            return redirect(url_for('index'))
            
        route_data = json.loads(route_data_json)
        
        if export_format == 'csv':
            # Create CSV file
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(['Position', 'Address', 'Latitude', 'Longitude', 'Category', 'Time Window'])
            
            # Write data
            for i, address in enumerate(route_data.get('addresses', [])):
                coords = route_data.get('coordinates', [])[i]
                location_detail = None
                if route_data.get('location_details') and i < len(route_data.get('location_details')):
                    location_detail = route_data['location_details'][i]
                
                category = location_detail.get('category', 'home') if location_detail else 'home'
                time_window = ''
                if location_detail and location_detail.get('time_window_start') and location_detail.get('time_window_end'):
                    time_window = f"{location_detail.get('time_window_start')} - {location_detail.get('time_window_end')}"
                
                writer.writerow([i+1, address, coords[1], coords[0], category, time_window])
            
            # Create response
            response = make_response(output.getvalue())
            response.headers["Content-Disposition"] = "attachment; filename=route_export.csv"
            response.headers["Content-type"] = "text/csv"
            return response
            
        elif export_format == 'json':
            # Create JSON response
            response = make_response(json.dumps(route_data, indent=2))
            response.headers["Content-Disposition"] = "attachment; filename=route_export.json"
            response.headers["Content-type"] = "application/json"
            return response
            
        else:
            flash("Unsupported export format.", "warning")
            return redirect(url_for('index'))
            
    except Exception as e:
        logging.error(f"Error exporting route: {str(e)}")
        flash(f"An error occurred while exporting the route: {str(e)}", "danger")
        return redirect(url_for('index'))