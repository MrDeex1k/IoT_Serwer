import cv2
from flask import Flask, Response, render_template_string, request, jsonify
import threading
import time
import atexit
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

control_app = Flask("control_app")
stream_app = Flask("stream_app")

camera = None
camera_active = False
camera_timer = None
camera_lock = threading.Lock()

DEFAULT_STREAM_DURATION = 300
MIN_STREAM_DURATION = 60
MAX_STREAM_DURATION = 300

def initialize_camera():
    """Inicjalizuje obiekt kamery w sposób bezpieczny wątkowo."""
    global camera
    with camera_lock:
        if camera is None:
            logging.info("Inicjalizowanie kamery...")
            camera = cv2.VideoCapture(0)
            if not camera.isOpened():
                logging.error("Błąd: Nie można otworzyć kamery.")
                camera = None
                return False
            logging.info("Kamera zainicjalizowana.")
        elif not camera.isOpened():
            logging.info("Próba ponownego otwarcia kamery...")
            camera.open(0)
            if not camera.isOpened():
                logging.error("Błąd: Nie można ponownie otworzyć kamery.")
                camera = None
                return False
            logging.info("Kamera ponownie otwarta.")
        return True

def release_camera_resource():
    """Zwalnia zasób kamery w sposób bezpieczny wątkowo."""
    global camera, camera_active, camera_timer
    with camera_lock:
        logging.info("Zwalnianie kamery...")
        if camera_timer is not None:
            camera_timer.cancel()
            camera_timer = None
            logging.info("Anulowano aktywny timer kamery.")
        if camera is not None and camera.isOpened():
            camera.release()
            logging.info("Zasób kamery zwolniony.")
        camera_active = False
        logging.info("Kamera oznaczona jako nieaktywna.")

atexit.register(release_camera_resource)

def turn_off_camera_after_delay():
    """Funkcja wywoływana przez timer do wyłączenia kamery."""
    global camera_active, camera_timer
    with camera_lock:
        logging.info("Czas minął. Wyłączanie kamery.")
        camera_active = False
        camera_timer = None

def generate_frames():
    """Generator klatek wideo do strumieniowania (działa w stream_app)."""
    global camera_active, camera
    last_frame_time = time.time()
    while True:
        with camera_lock:
            is_active = camera_active
            cam_instance = camera

        if not is_active or cam_instance is None or not cam_instance.isOpened():
            time.sleep(0.1)
            continue

        try:
            with camera_lock:
                 if not cam_instance or not cam_instance.isOpened():
                     logging.warning("generate_frames: Kamera została zamknięta przed odczytem.")
                     continue

            success, frame = cam_instance.read()

            if not success:
                logging.error("Błąd: Nie można odczytać klatki z kamery.")
                with camera_lock:
                    camera_active = False
                time.sleep(0.5)
                continue
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    logging.warning("Błąd: Nie można zakodować klatki.")
                    continue

                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                last_frame_time = time.time()

        except Exception as e:
            logging.error(f"Wyjątek w generate_frames: {e}")
            with camera_lock:
                camera_active = False
            time.sleep(1)

@stream_app.route('/')
def index():
    """Renderuje stronę HTML z odtwarzaczem strumienia wideo."""
    html_content = """
    <!doctype html>
    <title>Live Camera Stream</title>
    <style>
      body { font-family: sans-serif; }
      .video-container {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 90vh; /* Zmniejszono, aby zrobić miejsce na status */
        flex-direction: column;
      }
      img {
          max-width: 90%;
          max-height: 80vh; /* Ograniczenie wysokości */
          height: auto;
          border: 1px solid #ccc;
      }
      #status { font-weight: bold; margin-top: 10px; }
    </style>
    <body>
      <div class="video-container">
        <h1>Live Camera Stream (Port 8899)</h1>
        <img id="stream" src="/video_feed" alt="Video Stream">
        <p>Camera Status: <span id="status">Inactive</span></p>
      </div>
      <script>
          // Prosty sposób na sprawdzenie, czy strumień jest aktywny
          // (nie jest to status w czasie rzeczywistym, tylko czy obraz się ładuje)
          const img = document.getElementById('stream');
          const statusEl = document.getElementById('status');

          img.onload = () => 
          {
              statusEl.textContent = 'Active';
              statusEl.style.color = 'green';
          };
          img.onerror = () => 
          {
              statusEl.textContent = 'Inactive / Error';
              statusEl.style.color = 'red';
              // Można dodać logikę ponownego ładowania lub informowania użytkownika
              // img.src = "/video_feed?" + new Date().getTime(); // Próba odświeżenia
          };

          fetch('/video_feed').then(response => 
          {
             if (response.ok && response.headers.get('content-type')?.includes('multipart/x-mixed-replace')) 
             {} 
             else 
             {
                  img.onerror(); // Traktuj jako błąd/nieaktywny
             }
          }).catch(() => {
              img.onerror();
          });

          console.log("Use control server on port 8898 (/TurnCameraON) to manage the stream.");

      </script>
    </body>
    """
    return render_template_string(html_content)

@stream_app.route('/video_feed')
def video_feed():
    """Endpoint strumieniowania wideo."""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@control_app.route('/TurnCameraON', methods=['POST'])
def turn_camera_on_off():
    """Endpoint do włączania/wyłączania kamery na określony czas."""
    global camera_active, camera_timer

    if not request.is_json:
        logging.warning("Otrzymano żądanie /TurnCameraON bez typu JSON.")
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    status = data.get('status')
    duration_in = data.get('time')
    duration = DEFAULT_STREAM_DURATION

    if status not in [0, 1]:
        logging.warning(f"Nieprawidłowa wartość statusu: {status}")
        return jsonify({"error": "Invalid status value. Must be 0 or 1."}), 400

    if status == 1:
        if isinstance(duration_in, int) and MIN_STREAM_DURATION <= duration_in <= MAX_STREAM_DURATION:
            duration = duration_in
            logging.info(f"Otrzymano prawidłowy czas trwania: {duration}s.")
        else:
            logging.warning(f"Nieprawidłowy lub brakujący czas trwania ({duration_in}). Używanie domyślnego: {DEFAULT_STREAM_DURATION}s.")

        logging.info(f"Żądanie włączenia kamery na {duration} sekund.")
        with camera_lock:
            if camera_timer is not None:
                camera_timer.cancel()
                camera_timer = None
                logging.info("Anulowano poprzedni timer.")

            if not initialize_camera():
                 logging.error("Nie udało się zainicjalizować kamery na żądanie.")
                 return jsonify({"error": "Failed to initialize camera."}), 500

            camera_active = True
            camera_timer = threading.Timer(duration, turn_off_camera_after_delay)
            camera_timer.start()
            logging.info(f"Kamera włączona. Timer ustawiony na {duration}s.")
        return jsonify({"message": f"Camera turned ON for {duration} seconds."}), 200

    else: # status == 0
        logging.info("Żądanie wyłączenia kamery.")
        with camera_lock:
            if camera_timer is not None:
                camera_timer.cancel()
                camera_timer = None
                logging.info("Anulowano timer przy żądaniu wyłączenia.")
                
            camera_active = False
            logging.info("Kamera oznaczona jako nieaktywna.")
        return jsonify({"message": "Camera turned OFF."}), 200

def run_control_server():
    logging.info("Serwer kontrolny startuje na http://0.0.0.0:8898")
    # Używamy 'werkzeug' jako serwera deweloperskiego, ale dla produkcji rozważ Gunicorn/uWSGI
    control_app.run(host='0.0.0.0', port=8898, debug=False, threaded=True, use_reloader=False)

def run_stream_server():
    logging.info("Serwer strumieniowania startuje na http://0.0.0.0:8899")
    stream_app.run(host='0.0.0.0', port=8899, debug=False, threaded=True, use_reloader=False)

if __name__ == '__main__':
    logging.info("Uruchamianie serwerów w oddzielnych wątkach...")

    control_thread = threading.Thread(target=run_control_server, daemon=True)
    stream_thread = threading.Thread(target=run_stream_server, daemon=True)

    control_thread.start()
    stream_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Otrzymano sygnał przerwania. Zamykanie serwerów...")

    logging.info("Serwery zatrzymane.")
