import sqlite3

# Подключение к базе
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Создание таблицы sales
cursor.execute('''
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price REAL,
    quantity REAL,
    total REAL,
    date TEXT,
    currency TEXT
)
''')

# Создание таблицы products (если нужно)
cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price REAL
)
''')

conn.commit()
conn.close()

print("Таблицы успешно созданы.")
