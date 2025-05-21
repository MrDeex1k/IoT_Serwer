from flask import Flask, render_template, send_from_directory, url_for, request, jsonify
import os

app = Flask(__name__, template_folder='template', static_folder='template')

current_dir = os.path.dirname(os.path.abspath(__file__))
IMAGES_FOLDER = os.path.join(current_dir, "images")

@app.route('/')
def home():
    try:
        test_image_path = os.path.join(IMAGES_FOLDER, "test.jpg")
        if os.path.exists(test_image_path):
            return render_template('index.html', image_exists=True)
        else:
            return render_template('index.html', image_exists=False)
    except Exception as e:
        print(f"Błąd: {e}")
        return render_template('index.html', image_exists=False)

@app.route('/images/<path:filename>')
def get_image(filename):
    try:
        return send_from_directory(IMAGES_FOLDER, filename)
    except Exception as e:
        print(f"Nie udało się załadować obrazu: {e}")
        return "Nie udało się załadować obrazu", 404

@app.route('/style.css')
def css():
    return send_from_directory('template', 'style.css')

@app.route('/TurnCameraON', methods=['POST'])
def turn_camera_on():
    try:
        data = request.get_json()
        
        if not data or not isinstance(data, dict):
            print("Nie udało się odczytać JSON-a lub format danych jest niepoprawny")
            return "", 400  # Bad Request
            
        print(f"Pomyślnie odebrano JSON: {data}")
        
        # Sprawdzanie czy wymagane pola istnieją
        if 'Status' not in data or 'Time' not in data:
            print("Brak wymaganych pól Status i/lub Time w JSON-ie")
            return "", 400  # Bad Request
            
        status = data['Status']
        time = data['Time']
        
        # Walidacja wartości Status
        if status not in [0, 1]:
            print(f"Nieprawidłowa wartość Status: {status}, musi być 0 lub 1")
            return "", 400  # Bad Request
            
        # Walidacja wartości Time
        if not isinstance(time, (int, float)) or time < 30 or time > 300:
            print(f"Nieprawidłowa wartość Time: {time}, musi być liczbą z zakresu 30-300")
            return "", 400  # Bad Request
        
        print(f"Odczytano poprawne parametry - Status: {status}, Time: {time}")
        return "", 200  # OK
        
    except Exception as e:
        print(f"Błąd podczas przetwarzania żądania TurnCameraON: {e}")
        return "", 500  # Internal Server Error

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8898)