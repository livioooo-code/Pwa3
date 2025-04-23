# This file is used by gunicorn for deployment on platforms like Render

from app import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)