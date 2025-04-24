import os
from flask import Flask, send_from_directory, render_template_string

app = Flask(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
# Zaktualizowano ścieżki, aby wskazywały na folder 'images'
IMAGES_FOLDER = os.path.join(current_dir, "images")
video_path = os.path.join(IMAGES_FOLDER, "video.mp4")

@app.route('/')
def index():
    """Renderuje stronę HTML z odtwarzaczem wideo."""
    html_content = """
    <!doctype html>
    <title>Video Stream</title>
    <style>
      .video-container {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh; /* Opcjonalnie: wyśrodkowanie w pionie na całej wysokości widoku */
        flex-direction: column; /* Aby tytuł był nad wideo */
      }
    </style>
    <body>
      <div class="video-container">
        <h1>Video Stream</h1>
        <video width="800" height="450" controls autoplay loop muted>
          <source src="/images/video.mp4" type="video/mp4">
          Your browser does not support the video tag.
        </video>
      </div>
    </body>
    """
    return render_template_string(html_content)

@app.route('/images/<filename>')
def serve_image(filename):
    """Serwuje pliki z folderu 'images'."""
    return send_from_directory(IMAGES_FOLDER, filename)

if __name__ == '__main__':
    app.run(host='localhost', port=8899)
