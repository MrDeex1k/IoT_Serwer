import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

def load_db_credentials(env_file_path):
    """Ładuje dane uwierzytelniające do bazy danych z pliku .env"""
    load_dotenv(env_file_path)
    
    return {
        'host': os.getenv('DB_HOST'),
        'port': os.getenv('DB_PORT'),
        'dbname': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }

def get_db_connection(credentials=None):
    """Tworzy połączenie z bazą danych PostgreSQL"""
    if credentials is None:
        # Domyślna ścieżka do pliku credentials.env
        current_dir = os.path.dirname(os.path.abspath(__file__))
        env_file_path = os.path.join(current_dir, "credentials.env")
        credentials = load_db_credentials(env_file_path)
    
    try:
        conn = psycopg2.connect(
            host=credentials['host'],
            port=credentials['port'],
            dbname=credentials['dbname'],
            user=credentials['user'],
            password=credentials['password']
        )
        return conn
    except Exception as e:
        print(f"Błąd podczas łączenia z bazą danych: {e}")
        return None

def create_table_if_not_exists(conn):
    """Tworzy tabelę WYKRYTE_OBIEKTY, jeśli nie istnieje"""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS WYKRYTE_OBIEKTY
    (
        ID SERIAL PRIMARY KEY,
        OBIEKT VARCHAR(255),
        PROCENT NUMERIC(5, 2),
        CZAS TIMESTAMP
    );
    """
    
    try:
        cursor = conn.cursor()
        cursor.execute(create_table_query)
        conn.commit()
        cursor.close()
        print("Tabela WYKRYTE_OBIEKTY została utworzona lub już istnieje")
        return True
    except Exception as e:
        print(f"Błąd podczas tworzenia tabeli: {e}")
        conn.rollback()
        return False

def insert_detected_object(obiekt, procent, czas=None, conn=None):
    """
    Wstawia dane wykrytego obiektu do tabeli WYKRYTE_OBIEKTY
    
    Parametry:
    - obiekt: nazwa wykrytego obiektu (str)
    - procent: procent pewności detekcji (float)
    - czas: czas detekcji (datetime), domyślnie aktualny czas
    - conn: aktywne połączenie z bazą danych, jeśli None, tworzy nowe
    
    Zwraca:
    - True, jeśli operacja się powiodła, False w przeciwnym przypadku
    """
    should_close_conn = False
    
    if conn is None:
        conn = get_db_connection()
        if conn is None:
            return False
        should_close_conn = True
    
    if czas is None:
        czas = datetime.now()
    
    try:
        cursor = conn.cursor()
        
        # Upewniamy się, że tabela istnieje
        create_table_if_not_exists(conn)
        
        insert_query = """
        INSERT INTO WYKRYTE_OBIEKTY (OBIEKT, PROCENT, CZAS)
        VALUES (%s, %s, %s);
        """
        
        cursor.execute(insert_query, (obiekt, procent, czas))
        conn.commit()
        cursor.close()
        print(f"Wykryty obiekt '{obiekt}' ({procent}%) został dodany do bazy danych")
        return True
    except Exception as e:
        print(f"Błąd podczas wstawiania danych: {e}")
        conn.rollback()
        return False
    finally:
        if should_close_conn and conn is not None:
            conn.close()

if __name__ == "__main__":
    # Test połączenia i wstawiania danych
    conn = get_db_connection()
    if conn:
        create_table_if_not_exists(conn)
        # Wstawiamy dane tylko raz na sesję
        insert_detected_object("Człowiek", 95.5, conn=conn)
        insert_detected_object("Pies", 87.2, conn=conn)
        conn.close()
        print("Test zakończony pomyślnie")
    else:
        print("Nie można nawiązać połączenia z bazą danych")