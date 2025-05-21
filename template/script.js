let imageRefreshInterval = null;
let autoRefreshActive = false;

// Funkcja do pobierania i wyświetlania najnowszego obrazu
function fetchLatestImage() {
    fetch('/get-latest-image-info')
        .then(response => response.json())
        .then(data => {
            const imgElement = document.getElementById('camera-image');
            const statusInfo = document.getElementById('status-info');
            const noImageDiv = document.querySelector('.no-image');
            const toggleButton = document.getElementById('toggle-camera-button');
            const detectionInfoElement = document.getElementById('detection-info-text'); // Dodano

            // Aktualizacja stanu przycisku i informacji o statusie na podstawie danych z serwera
            if (data.camera_active) {
                if (!autoRefreshActive) { // Jeśli serwer mówi, że kamera jest ON, a UI myśli, że OFF
                    // Uruchom odświeżanie UI bez wysyłania komendy ON do serwera
                    const durationFromServer = data.remaining_time > 0 ? data.remaining_time : 30; // Użyj pozostałego czasu lub domyślnego
                    startAutoRefresh(durationFromServer, false); 
                }
                toggleButton.textContent = 'Wyłącz kamerę (Auto)';
                statusInfo.textContent = `Kamera aktywna. Pozostało ok. ${data.remaining_time}s.`;
                statusInfo.style.color = 'lime';
            } else {
                if (autoRefreshActive) { // Jeśli serwer mówi, że kamera jest OFF, a UI myśli, że ON
                    stopAutoRefresh(false); // Zatrzymaj odświeżanie UI bez wysyłania komendy OFF
                }
                toggleButton.textContent = 'Włącz kamerę (Auto)';
                // statusInfo.textContent = 'Kamera wyłączona.'; // Zostawiamy to dla obsługi obrazu poniżej
                // statusInfo.style.color = 'orange';
            }

            if (data.status === 'success' && data.image_url) {
                if (imgElement) {
                    imgElement.src = data.image_url + '?t=' + new Date().getTime(); // Dodaj timestamp, aby uniknąć cache'owania
                    imgElement.style.display = 'block';
                }
                if (noImageDiv) noImageDiv.style.display = 'none';
                // Komunikat o obrazie, jeśli nie ma innego statusu kamery
                if (!data.camera_active) {
                    statusInfo.textContent = 'Wyświetlono ostatnie zdjęcie. Kamera wyłączona.';
                    statusInfo.style.color = 'orange';
                }
            } else if (data.status === 'info' && data.message === 'Brak zdjęć.') {
                if (imgElement) imgElement.style.display = 'none';
                if (noImageDiv) {
                    noImageDiv.style.display = 'flex';
                    noImageDiv.textContent = 'TUTAJ BĘDZIE WIZJA Z KAMERY (Brak zdjęć)';
                }
                if (!data.camera_active) { // Tylko jeśli kamera nie jest aktywna
                    statusInfo.textContent = 'Brak zdjęć. Kamera wyłączona.';
                    statusInfo.style.color = 'grey';
                }
            } else { // Inne błędy lub statusy, np. success_no_analysis
                if (imgElement) imgElement.style.display = 'none';
                if (noImageDiv) {
                    noImageDiv.style.display = 'flex';
                    noImageDiv.textContent = data.message || 'Problem z załadowaniem obrazu.';
                }
                if (!data.camera_active) {
                     statusInfo.textContent = data.message || 'Problem z kamerą lub obrazem.';
                     statusInfo.style.color = 'red';
                }
            }

            // Aktualizacja informacji o detekcji
            if (detectionInfoElement) {
                if (data.detection_info) {
                    detectionInfoElement.textContent = data.detection_info;
                } else {
                    detectionInfoElement.textContent = 'Oczekiwanie na analizę obrazu...';
                }
            }

        })
        .catch(error => {
            document.getElementById('status-info').textContent = 'Błąd komunikacji z serwerem przy pobieraniu obrazu.';
            document.getElementById('status-info').style.color = 'red';
            console.error('Błąd fetchLatestImage:', error);
            // Przy błędzie komunikacji, lepiej zresetować stan UI kamery do "wyłączonej"
            if (autoRefreshActive) stopAutoRefresh(false);
            document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
        });
}

// Funkcja do ręcznego odświeżenia (przycisk)
function manualRefreshImage() {
    // Zamiast /capture-image, teraz będziemy prosić o najnowszy dostępny obraz
    // Serwer w tle powinien robić zdjęcia, jeśli tryb auto jest włączony
    // Jeśli chcemy wymusić zrobienie zdjęcia TERAZ, potrzebny byłby inny endpoint
    // Na razie zakładamy, że ten przycisk po prostu pobiera najnowsze zdjęcie
    fetchLatestImage(); 
}

function startAutoRefresh(durationSeconds, sendCommandToServer = true) {
    if (autoRefreshActive && sendCommandToServer) { // Jeśli już aktywne i to jest nowe żądanie od użytkownika
        console.log("Automatyczne odświeżanie jest już aktywne. Zatrzymuję poprzednie.");
        // Nie ma potrzeby wysyłać OFF, bo zaraz wyślemy ON
        // stopAutoRefresh(true); // To by wysłało OFF
        clearInterval(imageRefreshInterval); // Tylko wyczyść interwał
    }
    
    autoRefreshActive = true;
    // document.getElementById('status-info').textContent = `Automatyczne odświeżanie aktywne przez ${durationSeconds}s.`;
    // document.getElementById('status-info').style.color = 'lime';
    // document.getElementById('toggle-camera-button').textContent = 'Wyłącz kamerę (Auto)';

    if (sendCommandToServer) {
        fetch('/TurnCameraON', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ Status: 'ON', Time: durationSeconds.toString() })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log("Serwer potwierdził włączenie kamery.");
                fetchLatestImage(); // Pobierz obraz od razu po potwierdzeniu
                if (imageRefreshInterval) clearInterval(imageRefreshInterval); // Wyczyść stary interwał na wszelki wypadek
                imageRefreshInterval = setInterval(fetchLatestImage, 3000); // Ustaw nowy interwał
            } else {
                console.error("Serwer zwrócił błąd przy włączaniu kamery:", data.message);
                document.getElementById('status-info').textContent = `Błąd serwera: ${data.message}`;
                document.getElementById('status-info').style.color = 'red';
                autoRefreshActive = false; // Resetuj stan, bo nie udało się włączyć
                document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
            }
        })
        .catch(error => {
            console.error('Błąd przy wysyłaniu komendy TurnCameraON:', error);
            document.getElementById('status-info').textContent = 'Błąd komunikacji przy włączaniu kamery.';
            document.getElementById('status-info').style.color = 'red';
            autoRefreshActive = false; // Resetuj stan
            document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
        });
    } else {
        // Jeśli nie wysyłamy komendy (bo serwer już jest ON lub odświeżamy UI), tylko uruchamiamy odświeżanie UI
        fetchLatestImage(); // Pobierz obraz i status
        if (imageRefreshInterval) clearInterval(imageRefreshInterval);
        imageRefreshInterval = setInterval(fetchLatestImage, 3000); // Ustaw interwał odświeżania UI
        // Status i przycisk powinny być już ustawione przez fetchLatestImage
    }
}

function stopAutoRefresh(userInitiated = true) {
    if (imageRefreshInterval) {
        clearInterval(imageRefreshInterval);
        imageRefreshInterval = null;
    }
    autoRefreshActive = false;
    // document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';

    if (userInitiated) {
        fetch('/TurnCameraON', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ Status: 'OFF' })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log("Serwer potwierdził wyłączenie kamery.");
                // Po potwierdzeniu wyłączenia, zaktualizuj UI
                fetchLatestImage(); // To powinno pokazać ostatnie zdjęcie i status "wyłączona"
            } else {
                console.error("Serwer zwrócił błąd przy wyłączaniu kamery:", data.message);
                document.getElementById('status-info').textContent = `Błąd serwera: ${data.message}`;
                document.getElementById('status-info').style.color = 'red';
                // Nie resetujemy autoRefreshActive, bo już jest false
            }
             // Niezależnie od odpowiedzi serwera, przycisk powinien być "Włącz"
            document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
        })
        .catch(error => {
            console.error('Błąd przy wysyłaniu komendy TurnCameraON (OFF):', error);
            document.getElementById('status-info').textContent = 'Błąd komunikacji przy wyłączaniu kamery.';
            document.getElementById('status-info').style.color = 'red';
            document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
        });
    } else {
        // Jeśli zatrzymane automatycznie (np. przez fetchLatestImage po informacji od serwera)
        console.log("Automatyczne odświeżanie zatrzymane (nie przez użytkownika).");
        document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
        // fetchLatestImage(); // Odśwież stan, jeśli to konieczne (zwykle fetchLatestImage to zainicjował)
    }
}

function toggleCamera() {
    const timeInput = document.getElementById('capture-time');
    const duration = parseInt(timeInput.value, 10);

    if (autoRefreshActive) {
        stopAutoRefresh(true); 
    } else {
        if (isNaN(duration) || duration <= 0) {
            alert("Proszę podać prawidłowy czas trwania (większy od 0).");
            return;
        }
        startAutoRefresh(duration, true);
    }
}

// Ładuj najnowszy obraz przy starcie strony
document.addEventListener('DOMContentLoaded', function() {
    fetchLatestImage();
});
