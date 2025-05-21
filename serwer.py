from flask import Flask, render_template, send_from_directory, url_for
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8898)