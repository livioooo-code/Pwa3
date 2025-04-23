# Courier Navigation System

System nawigacji dla kurierów oparty na OpenRouteService API.

## Funkcje

- Automatyczna optymalizacja tras dostaw
- Interaktywna wizualizacja tras na mapie
- Uwzględnianie ruchu drogowego w czasie rzeczywistym
- Szczegółowe sekwencje przystanków z adresami
- Zapisywanie i ładowanie tras z bazy danych
- Progresywna aplikacja webowa (PWA) z funkcjami offline
- Automatyczne wykrywanie lokalizacji kuriera
- Śledzenie w czasie rzeczywistym
- Kategoryzacja przystanków
- Integracja z danymi pogodowymi
- Uwierzytelnianie użytkowników

## Technologie

- Python (Flask)
- JavaScript
- PostgreSQL
- OpenRouteService API
- OpenWeatherMap API
- Leaflet.js (mapy)
- Bootstrap (interfejs)

## Instalacja

1. Sklonuj repozytorium
2. Zainstaluj zależności: `pip install -r requirements.txt`
3. Skonfiguruj zmienne środowiskowe (patrz sekcja konfiguracji)
4. Uruchom aplikację: `python wsgi.py`

## Konfiguracja

Aplikacja wymaga następujących zmiennych środowiskowych:

- `DATABASE_URL`: URL do bazy danych PostgreSQL
- `OPENROUTE_API_KEY`: Klucz API dla OpenRouteService
- `WEATHER_API_KEY`: Klucz API dla OpenWeatherMap (opcjonalnie)
- `SESSION_SECRET`: Tajny klucz dla sesji Flask

## Wdrożenie

Aplikacja jest gotowa do wdrożenia na platformie Render lub innej platformie obsługującej aplikacje Python/Flask.

## Licencja

MIT