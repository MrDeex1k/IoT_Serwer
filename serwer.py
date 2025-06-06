import os
import cv2
import glob
import time
import platform
import threading
import traceback
from ultralytics import YOLO
from datetime import datetime
from flask import Flask, render_template, send_from_directory, url_for, request, jsonify
from db_connector import get_db_connection, insert_detected_object, create_table_if_not_exists

app = Flask(__name__, template_folder='template', static_folder='template')

# Inicjalizacja połączenia z bazą danych
db_conn = get_db_connection()
if db_conn:
    create_table_if_not_exists(db_conn)
    print("Połączenie z bazą danych PostgreSQL ustanowione pomyślnie.")
else:
    print("OSTRZEŻENIE: Nie można połączyć się z bazą danych PostgreSQL. Detekcje nie będą zapisywane.")

# Tablica do śledzenia obiektów wykrytych w bieżącej sesji kamery
detected_objects_in_session = []
session_objects_lock = threading.Lock()

current_dir = os.path.dirname(os.path.abspath(__file__))
CAMERA_FOLDER = os.path.join(current_dir, "kamera")
MODEL_PATH = os.path.join(current_dir, "yolo12x.pt")

# Załaduj model YOLO
model = YOLO(MODEL_PATH)
print(f"Model YOLO załadowany z: {MODEL_PATH}")

camera_port = None
global_cap = None
global_capture_end_time = None

capture_active = False
capture_thread = None
global_capture_active_lock = threading.Lock()

def get_next_photo_filename():
    """Generuje ścieżkę do następnego pliku zdjęcia w folderze CAMERA_FOLDER."""
    if not os.path.exists(CAMERA_FOLDER):
        os.makedirs(CAMERA_FOLDER)
        print(f"Utworzono katalog na zdjęcia z kamery: {CAMERA_FOLDER}")
    
    existing_photos = glob.glob(os.path.join(CAMERA_FOLDER, "photo*.jpg"))
    if not existing_photos:
        return os.path.join(CAMERA_FOLDER, "photo1.jpg")
    
    max_num = 0
    for photo_path in existing_photos:
        try:
            filename = os.path.basename(photo_path)
            num_str = filename.replace("photo", "").replace(".jpg", "")
            num = int(num_str)
            if num > max_num:
                max_num = num
        except ValueError:
            print(f"Pominięto plik o nieprawidłowej nazwie: {photo_path}")
            pass
    
    next_num = max_num + 1
    return os.path.join(CAMERA_FOLDER, f"photo{next_num}.jpg")

def scan_usb_for_camera():
    """Skanuje porty USB w poszukiwaniu podłączonej kamery."""
    system = platform.system()
    found_cameras = []
    
    if system == "Windows":
        print("Skanowanie kamer (Windows)...")
        for i in range(10):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                print(f"Znaleziono kamerę na porcie {i}")
                found_cameras.append(i)
                cap.release()
            else:
                cap.release()
    elif system == "Linux":
        print("Skanowanie kamer (Linux)...")
        devices = glob.glob('/dev/video*')
        for device_path in devices:
            try:
                port_num = int(device_path.replace('/dev/video', ''))
                cap = cv2.VideoCapture(port_num)
                if cap.isOpened():
                    print(f"Znaleziono kamerę na urządzeniu {device_path} (port {port_num})")
                    found_cameras.append(port_num)
                    cap.release()
                else:
                    cap.release()
            except ValueError:
                print(f"Nie można przetworzyć {device_path} jako portu kamery.")
            except Exception as e:
                print(f"Błąd podczas sprawdzania kamery {device_path}: {e}")
                if 'cap' in locals() and cap.isOpened():
                    cap.release()
    
    if found_cameras:
        print(f"Lista znalezionych działających kamer: {found_cameras}")
        return found_cameras[0]
    else:
        print("Nie znaleziono żadnej działającej kamery.")
        return None

def get_latest_photo_details():
    """Zwraca nazwę pliku i czas modyfikacji najnowszego zdjęcia, oraz pełną ścieżkę lub (None, None, None)."""
    if not os.path.exists(CAMERA_FOLDER):
        return None, None, None
    
    photo_files = glob.glob(os.path.join(CAMERA_FOLDER, "photo*.jpg"))
    if not photo_files:
        return None, None, None
        
    latest_photo_path = max(photo_files, key=os.path.getmtime)
    modification_time = os.path.getmtime(latest_photo_path)
    return os.path.basename(latest_photo_path), modification_time, latest_photo_path

# Nowe funkcje dla analizy obrazu
def process_detection_results(results):
    """Przetwarza wyniki detekcji z modelu YOLO i zwraca statystyki oraz szczegóły."""
    people_count = 0
    dogs_count = 0
    detection_details = []
    current_detections = []

    for result in results:
        boxes = result.boxes
        for box in boxes:
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            
            if cls_id == 0:  # Osoba
                people_count += 1
                detection_details.append(f"Człowiek ({confidence*100:.0f}%)")
                current_detections.append(("Człowiek", confidence*100))
            elif cls_id == 16:  # Pies
                dogs_count += 1
                detection_details.append(f"Pies ({confidence*100:.0f}%)")
                current_detections.append(("Pies", confidence*100))
    
    return people_count, dogs_count, detection_details, current_detections

def update_session_detections(current_detections):
    """Aktualizuje tablicę obiektów wykrytych w sesji na podstawie bieżących detekcji."""
    with session_objects_lock:
        for obj_type, confidence in current_detections:
            # Sprawdź, czy obiekt już istnieje w tablicy
            found = False
            for obj in detected_objects_in_session:
                if obj['obiekt'] == obj_type:
                    found = True
                    # Aktualizuj tylko jeśli nowa pewność jest większa
                    if confidence > obj['procent']:
                        obj['procent'] = confidence
                        obj['czas'] = datetime.now()
                    break
            
            # Jeśli nie znaleziono obiektu w tablicy, dodaj nowy
            if not found:
                detected_objects_in_session.append({
                    'obiekt': obj_type,
                    'procent': confidence,
                    'czas': datetime.now()
                })
                print(f"Dodano nowy obiekt do sesji: {obj_type} ({confidence}%)")

def format_detection_summary(people_count, dogs_count, detection_details):
    """Formatuje podsumowanie detekcji do wyświetlenia."""
    if people_count == 0 and dogs_count == 0:
        return "Nie wykryto ludzi ani psów."
    else:
        summary = []
        if people_count > 0:
            summary.append(f"Ludzie: {people_count}")
        if dogs_count > 0:
            summary.append(f"Psy: {dogs_count}")
        return f"Wykryto: {', '.join(summary)}. Szczegóły: {'; '.join(detection_details)}"

def analyze_image_for_web(image_path):
    """Analizuje obraz za pomocą YOLO i zwraca opis wykrytych obiektów."""
    if not image_path or not os.path.exists(image_path):
        return "Brak obrazu do analizy."

    try:
        results = model.predict(image_path, save=False, classes=[0, 16], verbose=False)
        people_count, dogs_count, detection_details, current_detections = process_detection_results(results)
        
        # Aktualizacja tablicy obiektów wykrytych w sesji
        update_session_detections(current_detections)
        
        return format_detection_summary(people_count, dogs_count, detection_details)

    except Exception as e:
        print(f"Błąd podczas analizy obrazu {image_path}: {e}")
        traceback.print_exc()
        return "Błąd analizy obrazu."

# Funkcje związane z kamerą
def open_camera_with_settings(port, width=1280, height=720, fps=30):
    """Otwiera kamerę z określonymi ustawieniami."""
    cap = None
    try:
        if platform.system() == "Windows":
            cap = cv2.VideoCapture(port, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(port)

        if not cap.isOpened():
            print(f"Nie można otworzyć kamery na porcie {port}.")
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        
        actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"Kamera otwarta na porcie {port}. Ustawienia: {width}x{height} @ {fps} FPS.")
        print(f"Rzeczywiste ustawienia: {actual_width}x{actual_height} @ {actual_fps} FPS.")

        if actual_width == 0 or actual_height == 0:
            print(f"Ostrzeżenie: Kamera na porcie {port} może nie wspierać zmiany rozdzielczości/FPS lub zwróciła nieprawidłowe wartości.")

        return cap
    except Exception as e:
        print(f"Błąd podczas otwierania lub konfigurowania kamery na porcie {port}: {e}")
        traceback.print_exc()
        if cap is not None:
            cap.release()
        return None

def capture_image_from_camera_instance(cap_instance, output_path):
    """Wykonuje zdjęcie z już otwartej instancji kamery."""
    try:
        ret, frame = cap_instance.read()
        if ret:
            cv2.imwrite(output_path, frame)
            print(f"Zdjęcie zapisane jako {output_path}")
            return True
        else:
            print("Nie udało się przechwycić obrazu z otwartej kamery.")
            return False
    except Exception as e:
        print(f"Błąd podczas przechwytywania obrazu z instancji kamery: {e}")
        traceback.print_exc()
        return False

def capture_image_from_camera(port, output_path, width=1280, height=720, fps=30):
    """Wykonuje zdjęcie z kamery i zapisuje je do pliku. Zarządza otwarciem i zamknięciem kamery."""
    cap = None
    try:
        cap = open_camera_with_settings(port, width, height, fps)
        if cap is None:
            return False 

        ret, frame = cap.read()
        if ret:
            cv2.imwrite(output_path, frame)
            print(f"Zdjęcie zapisane jako {output_path}")
            return True
        else:
            print(f"Nie udało się przechwycić obrazu z kamery na porcie {port}.")
            return False
    except Exception as e:
        print(f"Błąd podczas przechwytywania obrazu z kamery {port}: {e}")
        traceback.print_exc()
        return False
    finally:
        if cap is not None:
            cap.release()
            print(f"Kamera na porcie {port} została zwolniona.")

# Funkcje dla zarządzania sesją i bazą danych
def save_session_objects_to_db():
    """Zapisuje wszystkie wykryte obiekty z bieżącej sesji do bazy danych."""
    with session_objects_lock:
        if detected_objects_in_session:
            print("Zapisywanie wykrytych obiektów do bazy danych:")
            for obj in detected_objects_in_session:
                if db_conn:
                    insert_detected_object(obj['obiekt'], obj['procent'], obj['czas'], db_conn)
                    print(f"- {obj['obiekt']}: {obj['procent']}% (czas: {obj['czas']})")
                else:
                    print(f"- {obj['obiekt']}: {obj['procent']}% (czas: {obj['czas']}) - BRAK POŁĄCZENIA Z BAZĄ")
            return True
        else:
            print("Nie wykryto żadnych obiektów w tej sesji")
            return False

def reset_session_objects():
    """Resetuje listę wykrytych obiektów w sesji."""
    with session_objects_lock:
        global detected_objects_in_session
        detected_objects_in_session = []
        print("Zresetowano listę wykrytych obiektów na początku nowej sesji")

def get_camera_status():
    """Zwraca aktualny status kamery i pozostały czas."""
    with global_capture_active_lock:
        camera_active_status = capture_active
        remaining_time_status = 0
        if global_capture_end_time and camera_active_status:
            remaining_time_status = max(0, int(global_capture_end_time - time.time()))
    return camera_active_status, remaining_time_status

def photo_capture_loop(cap_instance, duration_seconds, interval_seconds):
    global camera_port, capture_active, global_capture_active_lock, global_capture_end_time
    
    start_loop_time = time.time()
    next_capture_time = start_loop_time

    print(f"Rozpoczynanie pętli przechwytywania na {duration_seconds}s, interwał {interval_seconds}s")

    active_in_this_run = True 

    while active_in_this_run and (time.time() < start_loop_time + duration_seconds):
        with global_capture_active_lock: 
            if not capture_active:
                active_in_this_run = False
                print("Pętla przechwytywania zatrzymana przez flagę capture_active.")
                break
        
        if not active_in_this_run: 
            break

        current_time = time.time()
        if current_time >= next_capture_time:
            if cap_instance and cap_instance.isOpened():
                photo_path = get_next_photo_filename()
                success = capture_image_from_camera_instance(cap_instance, photo_path)
                if success:
                    print(f"Zrobiono zdjęcie: {photo_path} o {time.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    print(f"Nie udało się zrobić zdjęcia o {time.strftime('%Y-%m-%d %H:%M:%S')}")
                next_capture_time = current_time + interval_seconds
            else:
                print("Kamera nie jest otwarta w pętli przechwytywania. Zatrzymywanie pętli.")
                active_in_this_run = False 
                break
        
        # Efektywne oczekiwanie
        time_to_next_capture = next_capture_time - time.time()
        sleep_duration = max(0, min(0.1, time_to_next_capture if time_to_next_capture > 0 else 0))
        time.sleep(sleep_duration)
    
    print(f"Zakończono pętlę przechwytywania zdjęć. Czas trwania: {duration_seconds}s.")
    with global_capture_active_lock:
        if capture_active and not active_in_this_run:
             pass
        elif capture_active:
            print("Pętla zakończona automatycznie (upłynął czas). Ustawiam capture_active na False.")
            # Zapisanie wszystkich wykrytych obiektów do bazy danych przy automatycznym zakończeniu
            save_session_objects_to_db()
            capture_active = False
            global_capture_end_time = time.time()
            # Tutaj nie zwalniamy kamery, to zrobi inny kod, gdy wykryje zmianę capture_active

# Trasy Flask
@app.route('/')
def home():
    try:
        image_filename, _, image_path = get_latest_photo_details()
        image_exists = image_filename is not None
        detection_info = None
        if image_exists and image_path:
            detection_info = analyze_image_for_web(image_path)
            
        camera_active_status, remaining_time_status = get_camera_status()

        return render_template('index.html', 
                               image_exists=image_exists, 
                               image_filename=image_filename,
                               detection_info=detection_info,
                               camera_active=camera_active_status,
                               remaining_time=remaining_time_status)
    except Exception as e:
        print(f"Błąd w home: {e}")
        traceback.print_exc()
        return render_template('index.html', 
                               image_exists=False, 
                               image_filename=None,
                               detection_info="Błąd ładowania informacji.",
                               camera_active=False,
                               remaining_time=0)

@app.route('/kamera/<path:filename>')
def get_camera_image(filename):
    try:
        return send_from_directory(CAMERA_FOLDER, filename, as_attachment=False)
    except Exception as e:
        print(f"Błąd przy serwowaniu obrazu {filename}: {e}")
        traceback.print_exc()
        return "Błąd serwowania obrazu", 404

@app.route('/style.css')
def css():
    return send_from_directory('template', 'style.css')

@app.route('/scan-camera', methods=['GET'])
def scan_camera():
    """Endpoint do ręcznego skanowania portów USB w poszukiwaniu kamer."""
    global camera_port
    print("Rozpoczęto skanowanie kamer przez endpoint /scan-camera...")
    found_port = scan_usb_for_camera()
    
    if found_port is not None:
        camera_port = found_port
        return jsonify({'status': 'success', 'message': f'Znaleziono i ustawiono kamerę na porcie {camera_port}.', 'camera_port': camera_port})
    else:
        camera_port = None
        return jsonify({'status': 'error', 'message': 'Nie znaleziono żadnej działającej kamery.'}), 404 

@app.route('/get-latest-image-info', methods=['GET'])
def get_latest_image_info():
    image_filename, _, image_path = get_latest_photo_details()
    detection_info = "Analiza nie przeprowadzona."

    if image_filename and image_path:
        image_url = url_for('get_camera_image', filename=image_filename, _external=True)
        detection_info = analyze_image_for_web(image_path)
        status_message = 'success'
    elif image_filename:
        image_url = url_for('get_camera_image', filename=image_filename, _external=True)
        detection_info = "Brak ścieżki do analizy obrazu."
        status_message = 'success_no_analysis'
    else:
        image_url = None
        detection_info = "Brak zdjęć."
        status_message = 'info'

    camera_active_status, remaining_time_status = get_camera_status()

    return jsonify({
        'status': status_message, 
        'image_url': image_url, 
        'image_filename': image_filename,
        'detection_info': detection_info,
        'camera_active': camera_active_status,
        'remaining_time': remaining_time_status,
        'message': "Brak zdjęć." if status_message == 'info' else ""
    })

@app.route('/TurnCameraON', methods=['POST'])
def turn_camera_on():
    global camera_port, global_cap, capture_active, capture_thread, global_capture_end_time, global_capture_active_lock
    data = request.get_json()
    status = data.get('Status')
    
    with global_capture_active_lock:
        if status == 'ON':
            if not camera_port:
                print("Port kamery nieustawiony. Próba skanowania...")
                found_port = scan_usb_for_camera()
                if found_port is not None:
                    camera_port = found_port
                    print(f"Automatycznie znaleziono i ustawiono kamerę na porcie {camera_port}.")
                else:
                    print("Nie udało się automatycznie znaleźć kamery. Nie można włączyć.")
                    return jsonify({'status': 'error', 'message': 'Nie można włączyć kamery, port nieznany i nie udało się go znaleźć.'}), 500

            if capture_active:
                print("Próba włączenia kamery, gdy jest już aktywna. Najpierw wyłącz.")
                return jsonify({'status': 'info', 'message': 'Kamera jest już włączona.'})

            try:
                duration = int(data.get('Time', '30')) 
                interval = 3
                
                # Resetowanie tablicy wykrytych obiektów na początku nowej sesji
                reset_session_objects()
                
                if global_cap is None: 
                    global_cap = open_camera_with_settings(camera_port)
                    if global_cap is None:
                        print(f"Nie udało się otworzyć kamery na porcie {camera_port} przy próbie włączenia.")
                        return jsonify({'status': 'error', 'message': f'Nie udało się otworzyć kamery na porcie {camera_port}.'}), 500
                
                capture_active = True
                global_capture_end_time = time.time() + duration
                
                capture_thread = threading.Thread(target=photo_capture_loop, args=(global_cap, duration, interval))
                capture_thread.daemon = True
                capture_thread.start()
                
                print(f"Kamera włączona na {duration}s. Przechwytywanie w tle rozpoczęte.")
                return jsonify({'status': 'success', 'message': f'Kamera włączona na {duration} sekund.'})
            except ValueError:
                return jsonify({'status': 'error', 'message': 'Nieprawidłowy format czasu.'}), 400
            except Exception as e:
                print(f"Błąd przy włączaniu kamery: {e}")
                traceback.print_exc()
                capture_active = False
                if global_cap:
                    global_cap.release()
                    global_cap = None
                return jsonify({'status': 'error', 'message': f'Wewnętrzny błąd serwera przy włączaniu kamery: {str(e)}'}), 500

        elif status == 'OFF':
            if not capture_active:
                print("Próba wyłączenia kamery, gdy nie jest aktywna.")
                return jsonify({'status': 'info', 'message': 'Kamera jest już wyłączona.'})

            capture_active = False
            global_capture_end_time = time.time()

            # Sprawdzamy, czy mamy już zapisane dane w bazie (mogło to nastąpić przy automatycznym zakończeniu)
            auto_ended = False
            if capture_thread and not capture_thread.is_alive():
                print("Wykryto, że wątek kamery już się zakończył (prawdopodobnie upłynął czas).")
                auto_ended = True
            
            # Zapisanie wszystkich wykrytych obiektów do bazy danych, tylko jeśli nie zakończyło się automatycznie
            if not auto_ended:
                save_session_objects_to_db()
            else:
                print("Pomijam zapis do bazy danych, gdyż sesja zakończyła się automatycznie (dane już zapisane)")

            if global_cap is not None:
                print("Zwalnianie kamery po komendzie OFF...")
                global_cap.release()
                global_cap = None
            
            if capture_thread and capture_thread.is_alive():
                print("Oczekiwanie na zakończenie wątku przechwytywania...")
                capture_thread.join(timeout=5.0)
                if capture_thread.is_alive():
                    print("Wątek przechwytywania nie zakończył się w oczekiwanym czasie.")
                else:
                    print("Wątek przechwytywania zakończony.")
            capture_thread = None 
            
            # Wyświetlenie podsumowania wykrytych obiektów w zakończonej sesji
            print_detection_summary()

            print("Kamera wyłączona.")
            return jsonify({'status': 'success', 'message': 'Kamera wyłączona.'})
        else:
            return jsonify({'status': 'error', 'message': 'Nieprawidłowy status. Użyj "ON" lub "OFF".'}), 400

def print_detection_summary():
    """Wyświetla podsumowanie wykrytych obiektów w sesji."""
    with session_objects_lock:
        if detected_objects_in_session:
            print("Podsumowanie wykrytych obiektów w sesji:")
            for obj in detected_objects_in_session:
                print(f"- {obj['obiekt']}: {obj['procent']}% (czas: {obj['czas']})")
        else:
            print("Nie wykryto żadnych obiektów w tej sesji")

if __name__ == '__main__':
    print("Uruchamianie serwera, inicjalne skanowanie w poszukiwaniu kamery...")
    initial_port = scan_usb_for_camera()
    if initial_port is not None:
        camera_port = initial_port 
        print(f"Znaleziono kamerę przy starcie na porcie: {camera_port}")
    else:
        camera_port = None
        print("Nie znaleziono kamery przy starcie serwera.")
    
    if not os.path.exists(CAMERA_FOLDER):
        os.makedirs(CAMERA_FOLDER)

    print(f"Uruchamianie serwera Flask na http://0.0.0.0:8898 ...")
    try:
        app.run(debug=True, host='0.0.0.0', port=8898)
    finally:
        # Zamknij połączenie z bazą danych przy zamykaniu serwera
        if db_conn:
            db_conn.close()
            print("Połączenie z bazą danych zostało zamknięte.")