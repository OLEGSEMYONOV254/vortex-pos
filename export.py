import sqlite3
import json

# Подключение к старой базе
old_db = sqlite3.connect('old_database.db')
old_cur = old_db.cursor()

# Экспорт чеков
old_cur.execute("SELECT * FROM receipts")
receipts = old_cur.fetchall()

# Экспорт продаж
old_cur.execute("SELECT * FROM sales")
sales = old_cur.fetchall()

# Сохраняем в JSON
with open('backup.json', 'w') as f:
    json.dump({'receipts': receipts, 'sales': sales}, f)

old_db.close()
