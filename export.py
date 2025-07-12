import sqlite3
import json
from pathlib import Path

# Пути к файлам
SQLITE_DB = Path("data/database.db")  # Старая база SQLite
BACKUP_FILE = Path("data/backup.json")  # Файл для резервной копии

def export_data():
    try:
        # Подключение к SQLite
        conn = sqlite3.connect(str(SQLITE_DB))
        cursor = conn.cursor()
        
        # Получаем список всех таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print("Найдены таблицы:", tables)

        # Экспортируем только нужные таблицы
        data = {}
        for table in ['receipts', 'sales', 'counterparties']:
            if table in tables:
                cursor.execute(f"SELECT * FROM {table}")
                data[table] = cursor.fetchall()
                print(f"Экспортировано {len(data[table])} записей из {table}")

        # Сохраняем в JSON
        with open(BACKUP_FILE, 'w') as f:
            json.dump(data, f)
            
        print(f"Данные сохранены в {BACKUP_FILE}")
        return True
        
    except Exception as e:
        print(f"Ошибка при экспорте: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    export_data()
