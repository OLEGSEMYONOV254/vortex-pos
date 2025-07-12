import json
import psycopg2
from pathlib import Path

# Настройки PostgreSQL (замените на ваши)
DB_CONFIG = {
    "host": "dpg-d1odjg49c44c73fg14h0-a",
    "database": "vortex_db_nyxr",
    "user": "vortex_db_nyxr_user",
    "password": "Wcq7XNNi5sWZN0HOC1IsvSIfnVH51vIr",
    "port": "5432"
}

BACKUP_FILE = Path("data/backup.json")

def import_data():
    try:
        # Читаем резервную копию
        with open(BACKUP_FILE) as f:
            data = json.load(f)
        
        # Подключение к PostgreSQL
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Импорт данных
        for table, records in data.items():
            if not records:
                continue
                
            print(f"Импортируем {len(records)} записей в {table}...")
            
            # Получаем названия столбцов
            cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")
            columns = [row[0] for row in cursor.fetchall()]
            cols_str = ', '.join(columns)
            vals_str = ', '.join(['%s'] * len(columns))
            
            # Вставляем данные
            for record in records:
                cursor.execute(
                    f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str})",
                    record
                )
            
        conn.commit()
        print("Импорт успешно завершен!")
        return True
        
    except Exception as e:
        print(f"Ошибка при импорте: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    import_data()
