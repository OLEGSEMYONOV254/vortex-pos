import json
import psycopg2

# Подключение к новой базе
conn = psycopg2.connect(
    host="ваш_хост",
    database="ваша_база",
    user="ваш_юзер",
    password="ваш_пароль",
    port="5432"
)
cur = conn.cursor()

# Загрузка данных
with open('backup.json') as f:
    data = json.load(f)

# Импорт чеков
for receipt in data['receipts']:
    cur.execute("""
        INSERT INTO receipts 
        (id, date, total, payment_method, organization, counterparty_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, receipt)

# Импорт продаж
for sale in data['sales']:
    cur.execute("""
        INSERT INTO sales 
        (id, receipt_id, name, price, quantity, total, date, currency)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, sale)

conn.commit()
cur.close()
conn.close()
