from flask import Flask, render_template, send_from_directory, url_for, request, jsonify
import os
import glob
import platform
import time
import threading
import cv2  # Dodano import cv2
import traceback  # Dodano import traceback

app = Flask(__name__, template_folder='template', static_folder='template')

current_dir = os.path.dirname(os.path.abspath(__file__))
CAMERA_FOLDER = os.path.join(current_dir, "kamera")

camera_port = None
global_cap = None # Globalny obiekt kamery
global_capture_end_time = None # Dodano: Przechowuje czas zakończenia przechwytywania

# Globalne zmienne do zarządzania przechwytywaniem w tle
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
            print(f"Ostrzeżenie: Nie udało się przetworzyć numeru dla pliku {photo_path}")
            continue # Pomiń ten plik
    
    next_num = max_num + 1
    return os.path.join(CAMERA_FOLDER, f"photo{next_num}.jpg")

def scan_usb_for_camera():
    """Skanuje porty USB w poszukiwaniu podłączonej kamery."""
    system = platform.system()
    found_cameras = []
    
    if system == "Windows":
        print("Skanowanie kamer (Windows)...")
        for i in range(10):  # Sprawdź pierwsze 10 portów
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                print(f"Znaleziono kamerę na porcie {i} (Windows).")
                found_cameras.append(i)
                cap.release()
            else:
                # Niektóre wersje OpenCV mogą wymagać zwolnienia nawet jeśli isOpened() jest false
                cap.release() 
    elif system == "Linux":
        print("Skanowanie kamer (Linux)...")
        devices = glob.glob('/dev/video*')
        for device_path in devices:
            try:
                port_num = int(device_path.replace('/dev/video', ''))
                cap = cv2.VideoCapture(port_num)
                if cap.isOpened():
                    print(f"Znaleziono kamerę na {device_path} (port {port_num}).")
                    found_cameras.append(port_num)
                    cap.release()
                else:
                    cap.release()
            except ValueError:
                print(f"Nie można przetworzyć {device_path} na numer portu.")
                continue
            except Exception as e_linux_cam:
                print(f"Błąd podczas sprawdzania kamery {device_path}: {e_linux_cam}")
                if 'cap' in locals() and cap: # type: ignore
                    cap.release() # type: ignore
    
    if found_cameras:
        print(f"Lista znalezionych działających kamer: {found_cameras}")
        return found_cameras[0] # Zwróć pierwszy znaleziony działający port
    else:
        print("Nie znaleziono żadnej działającej kamery.")
        return None

def get_latest_photo_details():
    """Zwraca nazwę pliku i czas modyfikacji najnowszego zdjęcia, lub (None, None)."""
    if not os.path.exists(CAMERA_FOLDER):
        return None, None
    
    photo_files = glob.glob(os.path.join(CAMERA_FOLDER, "photo*.jpg"))
    if not photo_files:
        return None, None
        
    latest_photo = max(photo_files, key=os.path.getmtime)
    modification_time = os.path.getmtime(latest_photo)
    return os.path.basename(latest_photo), modification_time

@app.route('/')
def home():
    try:
        image_filename, _ = get_latest_photo_details()
        image_exists = image_filename is not None
        return render_template('index.html', image_exists=image_exists, image_filename=image_filename)
    except Exception as e:
        print(f"Błąd w home: {e}")
        traceback.print_exc()
        return render_template('index.html', image_exists=False, image_filename=None, error_message="Błąd ładowania strony głównej.")

@app.route('/kamera/<path:filename>')
def get_camera_image(filename):
    try:
        return send_from_directory(CAMERA_FOLDER, filename)
    except Exception as e:
        print(f"Błąd przy serwowaniu obrazu {filename}: {e}")
        return "Błąd serwowania obrazu", 404

@app.route('/style.css')
def css():
    return send_from_directory('template', 'style.css')

@app.route('/scan-camera', methods=['GET'])
def scan_camera():
    """Endpoint do ręcznego skanowania portów USB w poszukiwaniu kamer."""
    global camera_port
    print("Rozpoczęto skanowanie kamer przez endpoint /scan-camera...")
    found_port = scan_usb_for_camera() # scan_usb_for_camera zwraca port lub None
    
    if found_port is not None:
        camera_port = found_port # Ustaw globalny port kamery
        return jsonify({'status': 'success', 'message': f'Znaleziono kamerę na porcie {camera_port}.', 'camera_port': camera_port})
    else:
        return jsonify({'status': 'error', 'message': 'Nie znaleziono żadnej działającej kamery.'}), 404

@app.route('/get-latest-image-info', methods=['GET'])
def get_latest_image_info():
    try:
        image_filename, modification_time = get_latest_photo_details()
        is_camera_active_locally = False
        remaining_time_locally = 0

        with global_capture_active_lock:
            if capture_active: # capture_active jest główną flagą intencji przechwytywania
                is_camera_active_locally = True
                if global_capture_end_time is not None:
                    current_time = time.time()
                    if current_time < global_capture_end_time:
                        remaining_time_locally = int(global_capture_end_time - current_time)
                    else:
                        # Czas minął, ale capture_active może jeszcze nie być wyczyszczone
                        # (np. wątek zakończył się naturalnie, a nie przez komendę OFF)
                        remaining_time_locally = 0 
            else:
                is_camera_active_locally = False
                remaining_time_locally = 0
                # Jeśli capture_active jest False, global_capture_end_time też powinien być None
                # global global_capture_end_time # Nie można przypisać w tym zasięgu bez deklaracji globalnej w funkcji
                # To jest obsługiwane w turn_camera_on

        response_data = {
            'camera_active': is_camera_active_locally,
            'remaining_time': remaining_time_locally if is_camera_active_locally else 0
        }

        if image_filename:
            image_url = url_for('get_camera_image', filename=image_filename, _external=False)
            image_url_with_timestamp = f"{image_url}?v={modification_time}"
            response_data.update({
                'status': 'success',
                'image_filename': image_filename,
                'image_url': image_url_with_timestamp,
                'message': 'Najnowszy obraz dostępny.'
            })
        else:
            response_data.update({
                'status': 'info',
                'message': 'Brak zdjęć.'
            })
        return jsonify(response_data)
    except Exception as e:
        print(f"Błąd w get_latest_image_info: {e}")
        traceback.print_exc()
        return jsonify({
            'status': 'error', 
            'message': 'Błąd serwera przy pobieraniu informacji o obrazie.',
            'camera_active': False,
            'remaining_time': 0
            }), 500

def capture_image_from_camera_instance(cap_instance, output_path):
    """Wykonuje zdjęcie z już otwartej instancji kamery."""
    try:
        if not cap_instance or not cap_instance.isOpened():
            print("Błąd: Instancja kamery nie jest otwarta.")
            return False
        ret, frame = cap_instance.read()
        if not ret:
            print("Nie udało się odczytać ramki z kamery.")
            return False
        cv2.imwrite(output_path, frame)
        # print(f"Zdjęcie zapisane do {output_path}") # Można odkomentować dla bardziej szczegółowego logowania
        return True
    except Exception as e:
        print(f"Wyjątek podczas robienia zdjęcia (instancja): {e}")
        traceback.print_exc()
        return False

def photo_capture_loop(cap_instance, duration_seconds, interval_seconds):
    global camera_port, capture_active, global_capture_active_lock # global_cap jest teraz cap_instance
    
    start_loop_time = time.time()
    next_capture_time = start_loop_time

    print(f"Rozpoczynanie pętli przechwytywania na {duration_seconds}s, interwał {interval_seconds}s")

    active_in_this_run = True 

    while active_in_this_run and (time.time() < start_loop_time + duration_seconds):
        with global_capture_active_lock: 
            if not capture_active: # Sprawdź globalną flagę pod blokadą
                active_in_this_run = False
                print("Pętla przechwytywania zatrzymana przez flagę capture_active.")
                break # Wyjdź z pętli while
        
        if not active_in_this_run: # Dodatkowe sprawdzenie po wyjściu z bloku with
            break

        current_time = time.time()
        if current_time >= next_capture_time:
            if cap_instance and cap_instance.isOpened():
                photo_path = get_next_photo_filename()
                success = capture_image_from_camera_instance(cap_instance, photo_path) # Użyj nowej funkcji
                if success:
                    print(f"Zrobiono zdjęcie: {photo_path} o {time.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    print(f"Nie udało się zrobić zdjęcia o {time.strftime('%Y-%m-%d %H:%M:%S')}")
                next_capture_time = current_time + interval_seconds
            else:
                print("Kamera nie jest otwarta w pętli przechwytywania. Zatrzymywanie pętli.")
                active_in_this_run = False # Zatrzymaj pętlę, jeśli kamera nie działa
                break
        
        # Efektywne oczekiwanie
        time_to_next_capture = next_capture_time - time.time()
        sleep_duration = max(0, min(0.1, time_to_next_capture if time_to_next_capture > 0 else 0))
        time.sleep(sleep_duration)
    
    print(f"Zakończono pętlę przechwytywania zdjęć. Czas trwania: {duration_seconds}s.")
    # Zwolnienie kamery jest teraz obsługiwane przez TurnCameraON po zakończeniu wątku
    with global_capture_active_lock:
        if capture_active and not active_in_this_run: # Jeśli pętla została przerwana inaczej niż przez czas
             pass # Już obsłużone
        elif capture_active: # Jeśli pętla zakończyła się z powodu czasu, a flaga wciąż aktywna
            # To nie powinno się zdarzyć, jeśli logika TurnCameraON jest poprawna
            print("Ostrzeżenie: Pętla zakończona, ale capture_active wciąż True. Wymuszanie False.")
            # capture_active = False # Zostanie ustawione w TurnCameraON

@app.route('/TurnCameraON', methods=['POST'])
def turn_camera_on():
    global capture_active, capture_thread, camera_port, global_capture_active_lock, global_cap
    global global_capture_end_time # Dodano
    data = request.get_json()
    status_command = data.get('Status')
    duration_str = data.get('Time', '30')

    try:
        duration_seconds = int(duration_str)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Nieprawidłowy format czasu.'}), 400

    try:
        interval_seconds = 3 

        with global_capture_active_lock:
            if status_command == 'ON':
                if capture_active:
                    # Jeśli już aktywna, zaktualizuj czas zakończenia, jeśli nowe żądanie ma dłuższy czas
                    new_end_time = time.time() + duration_seconds
                    if global_capture_end_time is None or new_end_time > global_capture_end_time:
                        global_capture_end_time = new_end_time
                        # Wątek już działa, nie uruchamiamy nowego, tylko aktualizujemy czas końca
                        # Pętla photo_capture_loop musi być świadoma global_capture_end_time lub duration musi być dynamiczne
                        # Dla uproszczenia: jeśli kamera jest już ON, to żądanie może tylko przedłużyć czas działania
                        # obecnej pętli, jeśli pętla jest zaprojektowana do sprawdzania global_capture_end_time.
                        # Obecna pętla działa na podstawie duration_seconds przekazanego przy starcie.
                        # Zatem, jeśli jest już ON, zwracamy informację, że jest aktywna.
                        # Użytkownik musiałby ją wyłączyć i włączyć z nowym czasem.
                        # Lub serwer musiałby zatrzymać i uruchomić nowy wątek.
                        # Na razie: jeśli aktywna, to jest aktywna.
                        return jsonify({'status': 'info', 'message': f'Kamera jest już włączona. Pozostały czas ok. {int(global_capture_end_time - time.time()) if global_capture_end_time else "N/A"}s.'}), 200

                current_cam_port = camera_port
                if not current_cam_port:
                    print("Skanowanie w poszukiwaniu kamery przed włączeniem...")
                    current_cam_port = scan_usb_for_camera()
                
                if current_cam_port is None:
                    print("Nie znaleziono kamery. Nie można włączyć.")
                    return jsonify({'status': 'error', 'message': 'Nie znaleziono kamery.'}), 500
                
                camera_port = current_cam_port

                if global_cap and global_cap.isOpened():
                    global_cap.release()
                    global_cap = None

                global_cap = open_camera_with_settings(camera_port) 
                
                if not global_cap or not global_cap.isOpened():
                    print(f"Nie udało się otworzyć kamery na porcie {camera_port}.")
                    global_cap = None 
                    global_capture_end_time = None # Wyczyść, jeśli nie udało się otworzyć
                    return jsonify({'status': 'error', 'message': f'Nie udało się otworzyć kamery na porcie {camera_port}.'}), 500
                
                capture_active = True
                global_capture_end_time = time.time() + duration_seconds # Ustaw czas zakończenia
                
                if capture_thread and capture_thread.is_alive():
                    print("Ostrzeżenie: Poprzedni wątek kamery wciąż aktywny. Próba jego zakończenia.")
                    # To nie powinno się zdarzyć przy poprawnej logice OFF
                    capture_thread.join(timeout=1) 

                capture_thread = threading.Thread(target=photo_capture_loop, args=(global_cap, duration_seconds, interval_seconds))
                capture_thread.daemon = True 
                capture_thread.start()
                print(f"Kamera włączona. Czas trwania: {duration_seconds}s, interwał: {interval_seconds}s. Koniec o: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(global_capture_end_time))}")
                return jsonify({'status': 'success', 'message': f'Kamera włączona na {duration_seconds}s.'})

            elif status_command == 'OFF':
                if not capture_active and (not global_cap or not global_cap.isOpened()):
                    global_capture_end_time = None # Upewnij się, że jest wyczyszczone
                    return jsonify({'status': 'info', 'message': 'Kamera jest już wyłączona.'}), 200

                capture_active = False 
                global_capture_end_time = None # Wyczyść czas zakończenia
                
                if capture_thread and capture_thread.is_alive():
                    print("Oczekiwanie na zakończenie wątku przechwytywania...")
                    capture_thread.join(timeout=max(5, interval_seconds + 2)) 
                    if capture_thread.is_alive():
                        print("Wątek przechwytywania nie zakończył się w oczekiwanym czasie.")
                
                if global_cap and global_cap.isOpened():
                    print("Zwalnianie zasobów kamery...")
                    global_cap.release()
                    global_cap = None 
                    print("Zasoby kamery zwolnione.")
                else:
                    print("global_cap nie był aktywny lub już zwolniony.")
                
                # capture_active = False # Już ustawione wyżej
                return jsonify({'status': 'success', 'message': 'Kamera wyłączona.'})
            else:
                return jsonify({'status': 'error', 'message': 'Nieznana komenda.'}), 400

    except Exception as e:
        print(f"Wyjątek w TurnCameraON: {e}")
        traceback.print_exc() 

        with global_capture_active_lock: # Dodatkowa ochrona dla zmiennych globalnych
            if global_cap and global_cap.isOpened(): 
                global_cap.release()
                global_cap = None
            capture_active = False 
            global_capture_end_time = None # Wyczyść czas zakończenia przy błędzie
        
        return jsonify({'status': 'error', 'message': f'Wystąpił wewnętrzny błąd serwera: {str(e)}'}), 500

# ... (reszta kodu, open_camera_with_settings, capture_image_from_camera) ...
# Upewnij się, że te funkcje używają cv2.
def open_camera_with_settings(port, width=1280, height=720, fps=30):
    """Otwiera kamerę z określonymi ustawieniami."""
    cap = None
    try:
        if port is None:
            print("Błąd: Port kamery nie może być None.")
            return None
            
        resolved_port = port
        if isinstance(port, str) and port.isdigit():            
            resolved_port = int(port)
        
        print(f"Próba otwarcia kamery na porcie: {resolved_port} (typ: {type(resolved_port)}) z cv2.VideoCapture...")

        if platform.system() == "Windows":
            cap = cv2.VideoCapture(resolved_port, cv2.CAP_DSHOW)
            if not cap or not cap.isOpened():
                print(f"Nie udało się otworzyć kamery na porcie {resolved_port} z CAP_DSHOW. Próba bez flagi...")
                cap = cv2.VideoCapture(resolved_port) # Spróbuj bez CAP_DSHOW
        else:             
            cap = cv2.VideoCapture(resolved_port)
            
        if not cap or not cap.isOpened():
            print(f"Nie udało się otworzyć kamery na porcie {resolved_port}.")
            if cap: cap.release()
            return None
            
        print(f"Kamera na porcie {resolved_port} otwarta. Ustawianie parametrów: {width}x{height} @ {fps}fps")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        
        # Daj kamerze chwilę na ustabilizowanie się po ustawieniu parametrów
        time.sleep(0.5) # Zwiększono czas dla stabilności
        return cap # Zwróć obiekt kamery
    except Exception as e:
        print(f"Wyjątek podczas otwierania kamery lub ustawiania parametrów na porcie {port}: {e}")
        traceback.print_exc()
        if cap:
           cap.release()
        return None

def capture_image_from_camera(port, output_path, width=1280, height=720, fps=30):
    """Wykonuje zdjęcie z kamery i zapisuje je do pliku. Zarządza otwarciem i zamknięciem kamery."""
    cap = None
    try:
        cap = open_camera_with_settings(port, width, height, fps)
        if not cap or not cap.isOpened():
            print(f"Nie udało się otworzyć kamery na porcie {port} do zrobienia zdjęcia.")
            return False
        
        ret, frame = cap.read()
        if not ret:
            print(f"Nie udało się odczytać ramki z kamery na porcie {port}.")
            return False
        
        # Upewnij się, że katalog CAMERA_FOLDER istnieje
        if not os.path.exists(CAMERA_FOLDER):
            os.makedirs(CAMERA_FOLDER)
            print(f"Utworzono katalog na zdjęcia: {CAMERA_FOLDER}")

        cv2.imwrite(output_path, frame)
        print(f"Zdjęcie zapisane do {output_path}")
        return True
    except Exception as e:
        print(f"Wyjątek podczas robienia zdjęcia z kamery {port}: {e}")
        traceback.print_exc()
        return False
    finally:
        if cap and cap.isOpened(): # Upewnij się, że zwalniasz tylko otwartą kamerę
            cap.release()
            print(f"Kamera na porcie {port} zwolniona po zrobieniu zdjęcia.")

if __name__ == '__main__':
    # ... (reszta kodu __main__ bez zmian, ale upewnij się, że używa zaktualizowanego scan_usb_for_camera)
    print("Uruchamianie serwera, inicjalne skanowanie w poszukiwaniu kamery...")
    # camera_port jest już globalny, więc przypisanie tutaj go ustawi
    initial_port = scan_usb_for_camera()
    if initial_port is not None:
        camera_port = initial_port # Ustaw globalny port kamery, jeśli znaleziono przy starcie
        print(f"Znaleziono kamerę przy starcie na porcie: {camera_port}")
    else:
        print("Nie znaleziono kamery przy starcie serwera.")
    
    if not os.path.exists(CAMERA_FOLDER):
        os.makedirs(CAMERA_FOLDER) # Utwórz folder, jeśli nie istnieje
        print(f"Utworzono katalog na zdjęcia: {CAMERA_FOLDER}")

    print(f"Uruchamianie serwera Flask na http://0.0.0.0:8898 ...")
    app.run(debug=True, host='0.0.0.0', port=8898)