from flask import Flask, render_template, send_from_directory, url_for, request, jsonify
import os
import cv2
import glob
import platform

app = Flask(__name__, template_folder='template', static_folder='template')

current_dir = os.path.dirname(os.path.abspath(__file__))
IMAGES_FOLDER = os.path.join(current_dir, "images")

def scan_usb_for_camera():
    """
    Skanuje porty USB w poszukiwaniu podłączonej kamery.
    Zwraca: String z identyfikatorem portu kamery lub None, jeśli nie znaleziono kamery.
    """
    system = platform.system()
    found_cameras = []
    
    if system == "Windows":
        # Na Windowsie kamery są zazwyczaj dostępne jako index 0, 1, 2...
        for i in range(10):  # Sprawdź pierwsze 10 indeksów
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)  # Używamy DirectShow na Windows
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        # Pobierz informacje o kamerze
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        print(f"Znaleziono kamerę na porcie: {i}, rozdzielczość: {width}x{height}")
                        found_cameras.append(str(i))
                    cap.release()
            except Exception as e:
                print(f"Błąd przy próbie dostępu do portu {i}: {e}")
    
    elif system == "Linux":
        # Na Linuxie kamery są dostępne jako /dev/videoX
        devices = glob.glob('/dev/video*')
        for device in devices:
            try:
                cap = cv2.VideoCapture(device)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        # Pobierz informacje o kamerze
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        print(f"Znaleziono kamerę na porcie: {device}, rozdzielczość: {width}x{height}")
                        found_cameras.append(device)
                    cap.release()
            except Exception as e:
                print(f"Błąd przy próbie dostępu do urządzenia {device}: {e}")
    
    if found_cameras:
        return found_cameras[0]  # Zwraca pierwszy znaleziony port kamery
    else:
        print("Nie znaleziono żadnej kamery na portach USB.")
        return None

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

@app.route('/scan-camera', methods=['GET'])
def scan_camera():
    """Endpoint do ręcznego skanowania portów USB w poszukiwaniu kamer."""
    global camera_port
    camera_port = scan_usb_for_camera()
    
    if camera_port:
        return jsonify({
            "status": "success",
            "message": f"Znaleziono kamerę na porcie: {camera_port}",
            "port": camera_port
        })
    else:
        return jsonify({
            "status": "error",
            "message": "Nie znaleziono żadnej kamery"
        }), 404

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
        
        # Sprawdź czy kamera jest dostępna
        global camera_port
        if not camera_port and status == 1:
            print("Próba włączenia kamery, ale nie wykryto żadnego urządzenia")
            camera_port = scan_usb_for_camera()  # Spróbuj ponownie znaleźć kamerę
            if not camera_port:
                return jsonify({"error": "Nie znaleziono kamery"}), 404
        
        # Tutaj możesz dodać kod do obsługi kamery na podstawie parametrów status i time
        if status == 1:
            print(f"Włączono kamerę na porcie {camera_port} na {time} sekund")
        else:
            print("Wyłączono kamerę")
        
        return "", 200  # OK
        
    except Exception as e:
        print(f"Błąd podczas przetwarzania żądania TurnCameraON: {e}")
        return "", 500  # Internal Server Error

# Zmienna globalna do przechowywania informacji o porcie kamery
camera_port = None

if __name__ == '__main__':
    # Skanuj porty USB w poszukiwaniu kamery przy starcie serwera
    camera_port = scan_usb_for_camera()
    if camera_port:
        print(f"Serwer będzie używał kamery na porcie: {camera_port}")
    else:
        print("Nie znaleziono żadnej kamery. Serwer uruchomiony bez dostępu do kamery.")
    
    app.run(debug=True, host='0.0.0.0', port=8898)