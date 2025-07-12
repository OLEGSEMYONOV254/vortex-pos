import json
import psycopg2
import os
from urllib.request import urlretrieve

def download_backup():
    backup_url = "https://raw.githubusercontent.com/OLEGSEMYONOV254/vortex-pos/main/data/backup.json"
    os.makedirs('data', exist_ok=True)
    local_path = 'data/backup.json'
    urlretrieve(backup_url, local_path)
    return local_path

def import_data():
    try:
        # Скачиваем файл
        backup_file = download_backup()
        
        # Подключение к PostgreSQL
        conn = psycopg2.connect(
            host="dpg-d1odjg49c44c73fg14h0-a",
            database="vortex_db_nyxr",
            user="vortex_db_nyxr_user",
            password="Wcq7XNNi5sWZN0HOC1IsvSIfnVH51vIr",
            port="5432"
        )
        cur = conn.cursor()

        # Чтение данных
        with open(backup_file) as f:
            data = json.load(f)

        # Импорт данных
        print("Импорт контрагентов...")
        for row in data.get('counterparties', []):
            cur.execute("""
                INSERT INTO counterparties (id, name, bin, type, address, phone, email, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, row)

        print("Импорт чеков...")
        for row in data.get('receipts', []):
            cur.execute("""
                INSERT INTO receipts (id, date, total, payment_method, organization, counterparty_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, row)

        print("Импорт продаж...")
        for row in data.get('sales', []):
            cur.execute("""
                INSERT INTO sales (id, receipt_id, name, price, quantity, total, date, currency)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, row)

        conn.commit()
        print("Импорт успешно завершен!")
        return True

    except Exception as e:
        print(f"Ошибка импорта: {str(e)}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()
        if os.path.exists(backup_file):
            os.remove(backup_file)  # Удаляем временный файл

if __name__ == "__main__":
    import_data()
