import json
import psycopg2
from pathlib import Path

DB_CONFIG = {
    "host": "dpg-d1odjg49c44c73fg14h0-a",
    "database": "vortex_db_nyxr",
    "user": "vortex_db_nyxr_user",
    "password": "Wcq7XNNi5sWZN0HOC1IsvSIfnVH51vIr",
    "port": "5432"
}

def import_data():
    try:
        with open('data/backup.json') as f:
            data = json.load(f)
        
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Импорт контрагентов
        print("Импортируем контрагентов...")
        for row in data['counterparties']:
            cur.execute("""
                INSERT INTO counterparties (id, name, bin, type, address, phone, email, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, row)
        
        # Импорт чеков
        print("Импортируем чеки...")
        for row in data['receipts']:
            cur.execute("""
                INSERT INTO receipts (id, date, total, payment_method, organization, counterparty_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, row)
        
        # Импорт продаж
        print("Импортируем продажи...")
        for row in data['sales']:
            cur.execute("""
                INSERT INTO sales (id, receipt_id, name, price, quantity, total, date, currency)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, row)
        
        conn.commit()
        print("Импорт успешно завершен!")
        
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    import_data()
