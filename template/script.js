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

            // Aktualizacja stanu przycisku i informacji o statusie na podstawie danych z serwera
            if (data.camera_active) {
                if (!autoRefreshActive) { // Jeśli serwer mówi, że kamera jest ON, a klient myśli, że OFF
                    const estimatedDuration = data.remaining_time > 0 ? data.remaining_time : parseInt(document.getElementById('capture-time').value, 10) || 30;
                    startAutoRefresh(estimatedDuration, false); // false - nie wysyłaj komendy ON, bo serwer już jest ON
                }
                toggleButton.textContent = 'Wyłącz kamerę (Auto)';
                statusInfo.textContent = `Kamera aktywna. Pozostało ok. ${data.remaining_time}s.`;
                statusInfo.style.color = 'lime';
            } else {
                if (autoRefreshActive) { // Jeśli serwer mówi, że kamera jest OFF, a klient myśli, że ON
                    stopAutoRefresh(false); // false - nie wysyłaj komendy OFF, bo serwer już jest OFF
                }
                toggleButton.textContent = 'Włącz kamerę (Auto)';
                // statusInfo.textContent = 'Kamera wyłączona.'; // Zostawiamy to dla obsługi obrazu poniżej
                // statusInfo.style.color = 'orange';
            }

            if (data.status === 'success' && data.image_url) {
                if (imgElement) {
                    imgElement.src = data.image_url + '?' + new Date().getTime(); // Unikaj cache
                    imgElement.alt = "Obraz z kamery: " + data.image_filename;
                    imgElement.style.display = 'block';
                    if (noImageDiv) noImageDiv.style.display = 'none';
                } else {
                    window.location.reload(); 
                }
                // Komunikat o obrazie, jeśli nie ma innego statusu kamery
                if (!data.camera_active) {
                    statusInfo.textContent = data.message;
                    statusInfo.style.color = 'white';
                }
            } else if (data.status === 'info' && data.message === 'Brak zdjęć.') {
                if (imgElement) imgElement.style.display = 'none';
                if (noImageDiv) {
                    noImageDiv.style.display = 'flex';
                    noImageDiv.textContent = "TUTAJ BĘDZIE WIZJA Z KAMERY (brak zdjęć)";
                }
                 if (!data.camera_active) { // Pokaż tylko jeśli kamera nie jest aktywna
                    statusInfo.textContent = data.message;
                    statusInfo.style.color = 'orange';
                } else if (imgElement && imgElement.style.display === 'none' && data.camera_active) {
                    // Kamera aktywna, ale brak obrazu - może być problem z pierwszym zdjęciem
                    if (noImageDiv) noImageDiv.textContent = "Kamera aktywna, oczekiwanie na pierwsze zdjęcie...";
                    statusInfo.textContent = "Kamera aktywna, oczekiwanie na pierwsze zdjęcie...";
                    statusInfo.style.color = 'lime';
                }
            } else { // Błąd lub brak obrazu z innego powodu
                if (imgElement) imgElement.style.display = 'none';
                if (noImageDiv) {
                    noImageDiv.style.display = 'flex';
                    noImageDiv.textContent = "Problem z wyświetleniem obrazu.";
                }
                if (!data.camera_active) {
                    statusInfo.textContent = 'Błąd: ' + (data.message || 'Nie udało się pobrać obrazu.');
                    statusInfo.style.color = 'red';
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
                document.getElementById('status-info').textContent = data.message + ` Pozostało ok. ${durationSeconds}s.`;
                document.getElementById('status-info').style.color = 'lime';
                document.getElementById('toggle-camera-button').textContent = 'Wyłącz kamerę (Auto)';
                
                fetchLatestImage(); // Pobierz obraz od razu
                if (imageRefreshInterval) clearInterval(imageRefreshInterval); // Wyczyść stary interwał, jeśli istnieje
                imageRefreshInterval = setInterval(fetchLatestImage, 3000);

                // Główny timeout do zatrzymania odświeżania i wysłania komendy OFF
                // Ten timeout powinien być zarządzany centralnie lub resetowany, jeśli użytkownik ponownie włączy kamerę
                // Na razie, jeśli startAutoRefresh jest wywołane ponownie, stary timeout będzie nadal aktywny.
                // To wymaga bardziej zaawansowanego zarządzania stanem.
                // Prostsze podejście: serwer sam zarządza czasem aktywności kamery.
                // Klient tylko odpytuje o stan.

            } else {
                document.getElementById('status-info').textContent = 'Błąd: ' + data.message;
                document.getElementById('status-info').style.color = 'red';
                autoRefreshActive = false; // Nie udało się włączyć
                document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
            }
        })
        .catch(error => {
            document.getElementById('status-info').textContent = 'Błąd komunikacji z serwerem (TurnCameraON).';
            document.getElementById('status-info').style.color = 'red';
            console.error('Błąd TurnCameraON ON:', error);
            autoRefreshActive = false;
            document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
        });
    } else {
        // Jeśli nie wysyłamy komendy (bo serwer już jest ON), tylko uruchamiamy odświeżanie UI
        fetchLatestImage(); // Pobierz obraz od razu
        if (imageRefreshInterval) clearInterval(imageRefreshInterval);
        imageRefreshInterval = setInterval(fetchLatestImage, 3000);
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
            document.getElementById('status-info').textContent = data.message;
            document.getElementById('status-info').style.color = data.status === 'success' ? 'orange' : 'red';
            if(data.status === 'success') {
                document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
            }
            fetchLatestImage(); // Odśwież stan po komendzie OFF
        })
        .catch(error => {
            document.getElementById('status-info').textContent = 'Błąd przy wysyłaniu komendy OFF.';
            document.getElementById('status-info').style.color = 'red';
            console.error('Błąd TurnCameraON OFF:', error);
            // Nawet jeśli błąd, zaktualizuj UI
             document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
        });
    } else {
        // Jeśli zatrzymane automatycznie (np. przez fetchLatestImage po informacji od serwera)
        console.log("Automatyczne odświeżanie zatrzymane (nie przez użytkownika).");
        document.getElementById('toggle-camera-button').textContent = 'Włącz kamerę (Auto)';
        // fetchLatestImage(); // Odśwież stan
    }
}

function toggleCamera() {
    const timeInput = document.getElementById('capture-time');
    const duration = parseInt(timeInput.value, 10);

    if (autoRefreshActive) {
        stopAutoRefresh(true); 
    } else {
        if (isNaN(duration) || duration <= 0) {
            alert("Proszę podać prawidłowy czas trwania (w sekundach).");
            return;
        }
        startAutoRefresh(duration, true);
    }
}

// Ładuj najnowszy obraz przy starcie strony
document.addEventListener('DOMContentLoaded', function() {
    fetchLatestImage();
});
