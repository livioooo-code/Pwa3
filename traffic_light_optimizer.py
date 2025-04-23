"""
Smart Traffic Light Optimization Algorithm

Ten moduł implementuje zaawansowany algorytm optymalizacji czasu przejazdu
bazując na cyklach i fazach świateł drogowych. Pozwala to na bardziej efektywne
planowanie trasy poprzez uwzględnienie cyklów sygnalizacji świetlnej.
"""

import math
import random
import logging
import time
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

# Typowy czas cyklu sygnalizacji świetlnej (w sekundach) dla różnych typów skrzyżowań
TRAFFIC_LIGHT_CYCLES = {
    'small_intersection': {'min': 45, 'max': 60},
    'medium_intersection': {'min': 60, 'max': 90},
    'large_intersection': {'min': 90, 'max': 120},
    'complex_intersection': {'min': 120, 'max': 180}
}

# Szacowany czas opóźnienia na sygnalizacji (w sekundach)
TRAFFIC_LIGHT_DELAYS = {
    'green': 0,            # Bez opóźnienia na zielonym
    'red_start': 30,       # Średnie opóźnienie gdy trafiamy na początek czerwonego
    'red_middle': 20,      # Średnie opóźnienie gdy trafiamy w środku czerwonego
    'red_end': 5,          # Małe opóźnienie gdy trafiamy pod koniec czerwonego
    'yellow': 5            # Małe opóźnienie na żółtym (należy zmniejszyć prędkość)
}

# Mapa skrzyżowań z sygnalizacją w regionie
# W prawdziwym systemie te dane byłyby pobierane z API lub bazy danych
# Format: [longitude, latitude]: {'type': typ_skrzyżowania, 'cycle_time': czas_cyklu, 'offset': przesunięcie_fazy}
# Offset = 0 oznacza, że cykl zaczyna się od początku zdefiniowanego okresu (np. pełnej godziny)
TRAFFIC_LIGHT_MAP = {}

def initialize_traffic_light_map(region_bounds):
    """
    Inicjalizuje mapę świateł drogowych dla danego regionu.
    W prawdziwym systemie dane byłyby pobierane z API.
    
    Args:
        region_bounds: [[min_lon, min_lat], [max_lon, max_lat]]
    """
    global TRAFFIC_LIGHT_MAP
    
    # Resetuj mapę
    TRAFFIC_LIGHT_MAP = {}
    
    # Używamy deterministycznego ziarna aby generować zawsze te same światła dla danego regionu
    min_lon, min_lat = region_bounds[0]
    max_lon, max_lat = region_bounds[1]
    
    seed_val = int((min_lon + max_lon + min_lat + max_lat) * 1000) % 100000
    random.seed(seed_val)
    
    # Symulacja gęstości świateł zależnie od położenia (wyższe wartości lat/lon = bliżej centrum miasta)
    center_lon = (min_lon + max_lon) / 2
    center_lat = (min_lat + max_lat) / 2
    
    # Oszacuj liczbę świateł na podstawie wielkości obszaru
    area_size = (max_lon - min_lon) * (max_lat - min_lat)
    num_lights = int(area_size * 50000)  # Skalowanie liczby świateł
    num_lights = max(10, min(100, num_lights))  # Limit liczby świateł
    
    # Generuj światła
    for _ in range(num_lights):
        # Bliżej centrum większa gęstość świateł
        distance_factor = random.random()
        lon = min_lon + (max_lon - min_lon) * (0.5 + (random.random() - 0.5) * distance_factor)
        lat = min_lat + (max_lat - min_lat) * (0.5 + (random.random() - 0.5) * distance_factor)
        
        # Określ typ skrzyżowania (bliżej centrum większe skrzyżowania)
        distance_to_center = math.sqrt((lon - center_lon)**2 + (lat - center_lat)**2)
        max_distance = math.sqrt((max_lon - center_lon)**2 + (max_lat - center_lat)**2)
        distance_ratio = distance_to_center / max_distance if max_distance > 0 else 0
        
        # Wybierz typ skrzyżowania
        if distance_ratio < 0.2:
            intersection_type = 'complex_intersection'
        elif distance_ratio < 0.4:
            intersection_type = 'large_intersection'
        elif distance_ratio < 0.7:
            intersection_type = 'medium_intersection'
        else:
            intersection_type = 'small_intersection'
        
        # Wygeneruj czas cyklu dla wybranego typu
        cycle_min = TRAFFIC_LIGHT_CYCLES[intersection_type]['min']
        cycle_max = TRAFFIC_LIGHT_CYCLES[intersection_type]['max']
        cycle_time = random.randint(cycle_min, cycle_max)
        
        # Wygeneruj przesunięcie fazy (offset)
        offset = random.randint(0, cycle_time - 1)
        
        # Zapisz dane skrzyżowania
        TRAFFIC_LIGHT_MAP[(round(lon, 5), round(lat, 5))] = {
            'type': intersection_type,
            'cycle_time': cycle_time,
            'offset': offset,
            'green_time': int(cycle_time * 0.4),  # 40% cyklu to zielone
            'yellow_time': 3,  # Stały czas żółtego
            'coordinates': [lon, lat]
        }
    
    logging.info(f"Zainicjalizowano {len(TRAFFIC_LIGHT_MAP)} świateł drogowych dla regionu")
    return TRAFFIC_LIGHT_MAP

def detect_traffic_lights_on_route(route_geometry, radius_meters=30):
    """
    Wykrywa sygnalizacje świetlne na trasie.
    
    Args:
        route_geometry: Punkty geometrii trasy jako tablica [lon, lat]
        radius_meters: Promień wyszukiwania świateł w metrach
    
    Returns:
        Lista znalezionych świateł z ich pozycją na trasie i informacjami
    """
    if not TRAFFIC_LIGHT_MAP:
        # Określ granice regionu na podstawie geometrii trasy
        lons = [p[0] for p in route_geometry]
        lats = [p[1] for p in route_geometry]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        
        # Powiększ granice o bufor
        buffer = 0.01  # Około 1km bufor
        initialize_traffic_light_map([
            [min_lon - buffer, min_lat - buffer],
            [max_lon + buffer, max_lat + buffer]
        ])
    
    # Konwersja promienia z metrów na stopnie (przybliżenie)
    # 1 stopień ≈ 111 km na równiku, więc 1m ≈ 0.000009 stopnia
    radius_deg = radius_meters * 0.000009
    
    # Znajdź wszystkie światła w pobliżu punktów trasy
    found_lights = []
    
    # Obliczamy odległość wzdłuż trasy dla każdego punktu
    route_distance = 0.0
    prev_point = None
    route_distances = [0.0]  # Odległość dla pierwszego punktu (używamy float)
    
    for point in route_geometry[1:]:
        if prev_point:
            # Oblicz odległość między punktami (prosta formuła Pitagorasa, przybliżenie)
            segment_dist = math.sqrt((point[0] - prev_point[0])**2 + (point[1] - prev_point[1])**2)
            route_distance += segment_dist
        route_distances.append(float(route_distance))  # Jawne konwertowanie do float
        prev_point = point
    
    # Teraz dla każdego punktu trasy sprawdź pobliskie światła
    checked_lights = set()  # Unikamy duplikatów
    
    for i, point in enumerate(route_geometry):
        for light_coords, light_info in TRAFFIC_LIGHT_MAP.items():
            light_lon, light_lat = light_coords
            
            # Szybkie sprawdzenie odległości (przybliżenie)
            if (abs(point[0] - light_lon) <= radius_deg and 
                abs(point[1] - light_lat) <= radius_deg and
                light_coords not in checked_lights):
                
                # Dokładny pomiar odległości
                distance = math.sqrt((point[0] - light_lon)**2 + (point[1] - light_lat)**2)
                if distance <= radius_deg:
                    found_lights.append({
                        'coordinates': [light_lon, light_lat],
                        'distance_along_route': route_distances[i],
                        'route_point_index': i,
                        'cycle_time': light_info['cycle_time'],
                        'type': light_info['type'],
                        'offset': light_info['offset'],
                        'green_time': light_info['green_time'],
                        'yellow_time': light_info['yellow_time']
                    })
                    checked_lights.add(light_coords)
    
    # Sortuj światła według odległości wzdłuż trasy
    found_lights.sort(key=lambda x: x['distance_along_route'])
    
    logging.debug(f"Wykryto {len(found_lights)} świateł drogowych na trasie")
    return found_lights

def estimate_traffic_light_delay(light_info, arrival_time):
    """
    Szacuje opóźnienie na światłach w zależności od czasu przybycia.
    
    Args:
        light_info: Informacje o sygnalizacji
        arrival_time: Przewidywany czas przybycia (datetime)
    
    Returns:
        Szacowane opóźnienie w sekundach i status sygnalizacji
    """
    # Uwzględnij strefę czasową
    if arrival_time.tzinfo is None:
        arrival_time = arrival_time.replace(tzinfo=pytz.UTC)
    
    # Oblicz czas w bieżącym cyklu
    seconds_since_epoch = arrival_time.timestamp()
    cycle_time = light_info['cycle_time']
    offset = light_info['offset']
    
    # Pozycja w cyklu (0 to start cyklu)
    cycle_position = (int(seconds_since_epoch) + offset) % cycle_time
    
    # Określ fazę świateł
    green_time = light_info['green_time']
    yellow_time = light_info['yellow_time']
    red_time = cycle_time - green_time - yellow_time
    
    # Sprawdź w której fazie jesteśmy
    if cycle_position < green_time:
        # Zielone światło
        status = 'green'
        delay = 0
    elif cycle_position < green_time + yellow_time:
        # Żółte światło
        status = 'yellow'
        delay = TRAFFIC_LIGHT_DELAYS['yellow']
    else:
        # Czerwone światło
        status = 'red'
        red_position = cycle_position - green_time - yellow_time
        red_fraction = red_position / red_time
        
        if red_fraction < 0.25:
            # Początek czerwonego
            delay = TRAFFIC_LIGHT_DELAYS['red_start']
        elif red_fraction < 0.75:
            # Środek czerwonego
            delay = TRAFFIC_LIGHT_DELAYS['red_middle']
        else:
            # Koniec czerwonego
            delay = TRAFFIC_LIGHT_DELAYS['red_end']
    
    return delay, status

def optimize_arrival_time(light_info, current_time, current_speed, distance_to_light):
    """
    Optymalizuje czas przybycia do świateł, sugerując dostosowanie prędkości.
    
    Args:
        light_info: Informacje o sygnalizacji
        current_time: Aktualny czas (datetime)
        current_speed: Aktualna prędkość w m/s
        distance_to_light: Odległość do świateł w metrach
    
    Returns:
        Słownik z informacjami optymalizacyjnymi (sugerowana prędkość, oszczędność czasu)
    """
    if current_speed <= 0:
        return {"success": False, "message": "Brak danych o prędkości"}
    
    # Oblicz bazowy czas przybycia
    base_arrival_time = current_time + timedelta(seconds=distance_to_light/current_speed)
    
    # Sprawdź opóźnienie przy bazowym czasie przybycia
    base_delay, base_status = estimate_traffic_light_delay(light_info, base_arrival_time)
    
    # Jeśli już trafiamy na zielone, nie ma potrzeby optymalizacji
    if base_status == 'green':
        return {
            "success": True,
            "optimized": False,
            "message": "Aktualna prędkość jest optymalna, trafisz na zielone światło",
            "suggested_speed": current_speed,
            "time_saved": 0,
            "current_status": base_status,
            "arrival_time": base_arrival_time
        }
    
    # Ustawienia optymalizacji
    cycle_time = light_info['cycle_time']
    green_time = light_info['green_time']
    yellow_time = light_info['yellow_time']
    offset = light_info['offset']
    
    # Przedział prędkości do rozważenia (80% - 120% aktualnej prędkości)
    min_speed = max(current_speed * 0.8, 5)  # Minimum 5 m/s (18 km/h)
    max_speed = min(current_speed * 1.2, 30)  # Maximum 30 m/s (108 km/h)
    
    # Sprawdź różne prędkości
    best_speed = current_speed
    best_delay = base_delay
    best_status = base_status
    best_arrival = base_arrival_time
    
    # Testuj różne prędkości z krokiem 0.5 m/s
    for test_speed in [min_speed + 0.5*i for i in range(int((max_speed-min_speed)/0.5)+1)]:
        test_arrival_time = current_time + timedelta(seconds=distance_to_light/test_speed)
        test_delay, test_status = estimate_traffic_light_delay(light_info, test_arrival_time)
        
        # Jeśli znaleźliśmy lepszą prędkość (mniejsze opóźnienie)
        if test_delay < best_delay:
            best_delay = test_delay
            best_speed = test_speed
            best_status = test_status
            best_arrival = test_arrival_time
        
        # Jeśli znaleźliśmy zielone światło, możemy zakończyć
        if test_status == 'green':
            break
    
    # Oblicz oszczędność czasu
    time_saved = base_delay - best_delay
    
    # Konwertuj prędkość na km/h dla lepszej czytelności
    best_speed_kmh = best_speed * 3.6
    current_speed_kmh = current_speed * 3.6
    
    if best_speed == current_speed:
        message = "Nie można zoptymalizować czasu przybycia, utrzymaj obecną prędkość"
        optimized = False
    else:
        # Czy trzeba przyspieszyć czy zwolnić?
        if best_speed > current_speed:
            action = "przyspiesz"
        else:
            action = "zwolnij"
            
        message = f"{action} do {best_speed_kmh:.1f} km/h aby trafić na lepszą fazę świateł"
        optimized = True
    
    return {
        "success": True,
        "optimized": optimized,
        "message": message,
        "suggested_speed": best_speed,
        "suggested_speed_kmh": best_speed_kmh,
        "current_speed_kmh": current_speed_kmh,
        "time_saved": time_saved,
        "current_status": best_status,
        "arrival_time": best_arrival
    }

def analyze_route_for_lights(route_data, average_speed_ms=11):
    """
    Analizuje całą trasę pod kątem sygnalizacji świetlnej i tworzy optymalny plan.
    
    Args:
        route_data: Dane trasy z geometrią, segmentami, etc.
        average_speed_ms: Średnia prędkość w m/s (domyślnie ~40 km/h)
    
    Returns:
        Słownik z analizą i zaleceniami dla sygnalizacji na trasie
    """
    result = {
        "traffic_lights": [],
        "total_original_delay": 0,
        "total_optimized_delay": 0,
        "total_time_saved": 0,
        "recommendations": []
    }
    
    # Sprawdź czy mamy dostęp do geometrii trasy
    if not route_data or 'segments' not in route_data:
        return {"success": False, "message": "Brak danych trasy"}
    
    # Złącz geometrię ze wszystkich segmentów
    all_geometry = []
    for segment in route_data['segments']:
        if 'geometry' in segment:
            all_geometry.extend(segment['geometry'])
    
    # Jeśli używamy zakodowanej geometrii, zdekoduj ją
    # Ta część wymagałaby biblioteki do dekodowania polyline
    
    # Wykryj światła na trasie
    lights = detect_traffic_lights_on_route(all_geometry)
    
    if not lights:
        return {
            "success": True,
            "message": "Nie wykryto sygnalizacji świetlnej na trasie",
            "traffic_lights": []
        }
    
    # Oblicz całkowitą długość trasy w metrach
    total_distance = 0
    for i in range(len(all_geometry) - 1):
        p1 = all_geometry[i]
        p2 = all_geometry[i + 1]
        # Przybliżenie odległości
        segment_dist = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2) * 111000  # 1 stopień ≈ 111 km
        total_distance += segment_dist
    
    # Początkowy czas
    start_time = datetime.now(pytz.UTC)
    current_time = start_time
    
    # Analizuj każde światło na trasie
    for i, light in enumerate(lights):
        # Oblicz dystans od początku trasy
        light_distance = light['distance_along_route'] * 111000  # Konwersja na metry
        
        # Oszacuj czas przybycia do światła
        time_to_light = light_distance / average_speed_ms
        arrival_time = start_time + timedelta(seconds=time_to_light)
        
        # Sprawdź opóźnienie bez optymalizacji
        original_delay, status = estimate_traffic_light_delay(light, arrival_time)
        
        # Optymalizuj prędkość
        optimization = optimize_arrival_time(
            light, current_time, average_speed_ms, 
            light_distance - (i > 0 and lights[i-1]['distance_along_route'] * 111000 or 0)
        )
        
        # Zaktualizuj czas dla następnych świateł
        if optimization['optimized']:
            current_time = optimization['arrival_time']
            optimized_delay = 0  # Zakładamy, że optymalizacja pozwala uniknąć opóźnienia
        else:
            current_time = arrival_time + timedelta(seconds=original_delay)
            optimized_delay = original_delay
        
        # Dodaj dane światła do wyników
        light_result = {
            "position": i + 1,
            "distance": light_distance,
            "coordinates": light['coordinates'],
            "cycle_time": light['cycle_time'],
            "type": light['type'],
            "estimated_arrival": arrival_time.strftime("%H:%M:%S"),
            "original_delay": original_delay,
            "optimized_delay": optimized_delay,
            "light_status": status,
            "optimization": optimization
        }
        
        result["traffic_lights"].append(light_result)
        result["total_original_delay"] += original_delay
        result["total_optimized_delay"] += optimized_delay
        
        # Dodaj rekomendację jeśli optymalizacja jest możliwa
        if optimization['optimized'] and optimization['time_saved'] > 5:
            recommendation = f"Światło {i+1}: {optimization['message']} (oszczędność: {int(optimization['time_saved'])}s)"
            result["recommendations"].append(recommendation)
    
    # Oblicz całkowitą oszczędność czasu
    result["total_time_saved"] = result["total_original_delay"] - result["total_optimized_delay"]
    
    # Podsumowanie
    if result["total_time_saved"] > 0:
        result["summary"] = f"Optymalizacja świateł może zaoszczędzić {int(result['total_time_saved'])} sekund"
    else:
        result["summary"] = "Brak możliwości optymalizacji świateł na tej trasie"
    
    # Dodaj ostateczne zalecenie
    if result["recommendations"]:
        result["final_recommendation"] = "Dostosuj prędkość w podanych miejscach, aby zminimalizować czas oczekiwania na światłach"
    else:
        result["final_recommendation"] = "Utrzymuj stałą prędkość na całej trasie"
    
    return result

def get_light_timing_for_route(route_geometry):
    """
    Pobiera informacje o cyklach sygnalizacji dla trasy.
    Funkcja uproszczona do użycia w głównym algorytmie optymalizacji trasy.
    
    Args:
        route_geometry: Lista punktów geometrii trasy [lon, lat]
    
    Returns:
        Lista sygnalizacji na trasie z podstawowymi informacjami
    """
    try:
        # Wykryj światła na trasie
        lights = detect_traffic_lights_on_route(route_geometry)
        
        # Uproszczona odpowiedź dla API
        simplified_lights = []
        for light in lights:
            simplified_lights.append({
                'coordinates': light['coordinates'],
                'distance': light['distance_along_route'] * 111000,  # Konwersja na metry
                'cycle_time': light['cycle_time'],
                'green_time': light['green_time'],
                'type': light['type']
            })
        
        return simplified_lights
    except Exception as e:
        logging.error(f"Błąd w analizie świateł drogowych: {str(e)}")
        return []

# Test funkcji, jeśli moduł jest uruchamiany bezpośrednio
if __name__ == "__main__":
    # Przykładowe dane trasy (można zastąpić rzeczywistymi danymi z API)
    test_route = [
        [16.9252, 52.4064],  # Poznań, Polska
        [16.9262, 52.4074],
        [16.9272, 52.4084],
        [16.9282, 52.4094],
        [16.9292, 52.4104]
    ]
    
    # Testuj funkcję wykrywania świateł
    lights = detect_traffic_lights_on_route(test_route)
    print(f"Wykryto {len(lights)} świateł na trasie testowej")
    
    if lights:
        # Testuj funkcję optymalizacji
        test_light = lights[0]
        optimization = optimize_arrival_time(
            test_light,
            datetime.now(pytz.UTC),
            11.0,  # ~40 km/h
            500.0  # 500 metrów do światła
        )
        
        print("Wynik optymalizacji:")
        for key, value in optimization.items():
            print(f"{key}: {value}")