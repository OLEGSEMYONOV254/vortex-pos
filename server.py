from flask import Flask, render_template, send_from_directory, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
import pytz
from pytz import timezone
import os
import json
import pandas as pd
from pathlib import Path
import shutil
import atexit
from vortex_ai import ask_vortex
import psycopg2.extras
import math  # добавь вверху, если ещё нет
from db import get_db
#from socketio_server import socketio

tz = pytz.timezone("Asia/Almaty")  # или нужная тебе временная зона



# Инициализация приложения
app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'your-secret-key'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Настройка путей
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

PRODUCTS_FILE = DATA_DIR / "products.json"
UPLOAD_FOLDER = DATA_DIR / 'uploads'
UPLOAD_FOLDER.mkdir(exist_ok=True)
app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
# DB_PATH = DATA_DIR / "database.db"

# Хранилище настроек
promo_settings = {
    'volume': 70,
    'currentVideo': 'dQw4w9WgXcQ',
    'playlist': ['dQw4w9WgXcQ'],
    'playlistMode': 'single',
    'defaultAmount': 5000,
    'theme': 'default'
}

# Подключенные клиенты
connected_clients = {}


@app.before_request
def check_db_connection():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        print("✅ Подключение к базе данных успешно!")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        raise

# Функции работы с базой данных
def get_db():
    """Подключение к PostgreSQL на Render"""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),  # Например: "dpg-d1odjg49c44c73fg14h0-a"
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=os.getenv("DB_PORT", "5432"),  # Порт по умолчанию для PostgreSQL
            sslmode="require"
        )
        conn.autocommit = True
        return conn
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        raise



def init_db():
    """Инициализация базы данных PostgreSQL"""
    with get_db() as conn:
        cur = conn.cursor()
        try:
            # Создаем таблицу receipts если её нет
            cur.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    id SERIAL PRIMARY KEY,
                    date TEXT NOT NULL,
                    total REAL NOT NULL,
                    payment_method TEXT NOT NULL,
                    organization TEXT,
                    counterparty_id INTEGER
                )
            """)
            
            # Создаем таблицу sales если её нет
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sales (
                    id SERIAL PRIMARY KEY,
                    receipt_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    total REAL NOT NULL,
                    date TEXT NOT NULL,
                    currency TEXT DEFAULT '₸',
                    FOREIGN KEY(receipt_id) REFERENCES receipts(id)
                )
            """)
            
            # Создаем таблицу counterparties если её нет
            cur.execute("""
                CREATE TABLE IF NOT EXISTS counterparties (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    bin TEXT,
                    type TEXT NOT NULL,
                    address TEXT,
                    phone TEXT,
                    email TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Создаем таблицу inventory если её нет
            cur.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id SERIAL PRIMARY KEY,
                    product_id REAL NOT NULL,
                    name TEXT NOT NULL,
                    name_chinese TEXT,
                    quantity REAL NOT NULL,
                    unit TEXT NOT NULL,
                    last_updated TEXT NOT NULL
                )
            """)
             # Создаем таблицу products
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    price_wholesale REAL DEFAULT 0,
                    price_bulk REAL DEFAULT 0,
                    category TEXT
                )
            """)
            

            conn.commit()
            print("[ИНИЦИАЛИЗАЦИЯ] Таблицы созданы/проверены в PostgreSQL")
            
        except Exception as e:
            print(f"[ОШИБКА] При создании таблиц: {e}")
            conn.rollback()
        finally:
            cur.close()
        # Добавляем недостающие колонки
        # add_organization_column()
        # add_counterparty_column()
        # add_counterparties_table()


#def create_backup():
 #   """Создание резервной копии базы данных"""
  #  if DB_PATH.exists():
   #     timestamp = datetime.now(tz).strftime("%Y%m%d_%H%M%S")
    #    backup_path = DATA_DIR / f"database_backup_{timestamp}.db"
     #   shutil.copy(DB_PATH, backup_path)
      #  print(f"[БЭКАП] Создана резервная копия: {backup_path}")


# Создаем бэкап при старте и при завершении
#create_backup()
#atexit.register(create_backup)


# Функции работы с товарами
def load_products():
    """Загрузка товаров из PostgreSQL с фильтрацией NaN"""
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT * FROM products ORDER BY id DESC")
            rows = cur.fetchall()
            products = []

            for row in rows:
                product = dict(row)
                # Заменяем NaN и None на 0 для числовых полей
                for field in ['price', 'price_wholesale', 'price_bulk']:
                    value = product.get(field)
                    if value is None or (isinstance(value, float) and math.isnan(value)):
                        product[field] = 0.0
                products.append(product)

            return products
    except Exception as e:
        print(f"[ОШИБКА] Не удалось загрузить товары: {e}")
        return []


def save_products(products):
    """Сохранение всех товаров в PostgreSQL (перезаписывает всё)"""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM products")  # очистить таблицу
            for p in products:
                cur.execute("""
                    INSERT INTO products (id, name, price, price_wholesale, price_bulk, category)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    p.get("id"),
                    p.get("name"),
                    p.get("price"),
                    p.get("price_wholesale", 0),
                    p.get("price_bulk", 0),
                    p.get("category", "")
                ))
            conn.commit()
    except Exception as e:
        print(f"[ОШИБКА] Не удалось сохранить товары: {e}")


def add_counterparties_table():
    """Добавляем таблицу контрагентов, если её нет"""
    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS counterparties (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    bin TEXT,
                    type TEXT NOT NULL,
                    address TEXT,
                    phone TEXT,
                    email TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
            print("[БАЗА] Создана таблица counterparties")
        except Exception as e:
            print(f"[БАЗА] Ошибка при создании таблицы counterparties: {e}")
        finally:
            cur.close()

def add_counterparty_column():
    """Добавляем колонку counterparty_id в таблицу receipts"""
    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS counterparty_id INTEGER")
            conn.commit()
            print("[БАЗА] Колонка counterparty_id добавлена или уже существует")
        except Exception as e:
            print(f"[БАЗА] Ошибка при добавлении колонки counterparty_id: {e}")
        finally:
            cur.close()  # Колонка уже есть

@app.route("/ai", methods=["GET", "POST"])
def vortex_ai():
    if request.method == "GET":
        return render_template("ai.html")
    elif request.method == "POST":
        data = request.get_json()
        prompt = data.get("prompt", "")
        reply = ask_vortex(prompt)
        return jsonify({"response": reply})

@app.route('/trigger_import')
def trigger_import():
    try:
        from .import_utils import import_data
        if import_data():
            return "Импорт данных выполнен успешно!"
        else:
            return "Произошла ошибка при импорте"
    except Exception as e:
        return f"Ошибка: {str(e)}"

# Маршруты приложения
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/test")
def test():
    return render_template("test.html")

@app.route("/api/receipts")
def get_receipts():
    limit = int(request.args.get("limit", 10))

    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(
                "SELECT id, date, total, payment_method FROM receipts ORDER BY date DESC LIMIT %s",
                (limit,)
            )
            rows = cur.fetchall()
            result = [dict(row) for row in rows]
            return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/settings")
def settings():
    products = load_products()
    return render_template("settings.html", products=products)


@socketio.on('connect')
def handle_connect():
    connected_clients[request.sid] = {
        'connected_at': datetime.now(),
        'type': 'settings' if 'settings' in request.referrer else 'promo'
    }
    print(f'Client connected: {request.sid}')
    emit('settings_update', promo_settings)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in connected_clients:
        del connected_clients[request.sid]
    print(f'Client disconnected: {request.sid}')

@socketio.on('get_settings')
def handle_get_settings():
    emit('settings_update', promo_settings)

@socketio.on('set_volume')
def handle_set_volume(data):
    promo_settings['volume'] = data['volume']
    # Отправляем всем промо-клиентам
    for sid, client in connected_clients.items():
        if client['type'] == 'promo':
            emit('volume_changed', data, room=sid)
    emit('command_result', {'success': True, 'message': 'Volume updated'})

@socketio.on('change_video')
def handle_change_video(data):
    promo_settings['currentVideo'] = data['videoId']
    for sid, client in connected_clients.items():
        if client['type'] == 'promo':
            emit('video_changed', data, room=sid)
    emit('command_result', {'success': True, 'message': 'Video changed'})

@socketio.on('update_playlist')
def handle_update_playlist(data):
    promo_settings['playlist'] = data['playlist']
    for sid, client in connected_clients.items():
        if client['type'] == 'promo':
            emit('playlist_updated', data, room=sid)
    emit('command_result', {'success': True, 'message': 'Playlist updated'})

@socketio.on('show_payment')
def handle_show_payment(data):
    for sid, client in connected_clients.items():
        if client['type'] == 'promo':
            emit('show_payment', data, room=sid)
    emit('command_result', {'success': True, 'message': 'Payment shown'})

@socketio.on('hide_payment')
def handle_hide_payment():
    for sid, client in connected_clients.items():
        if client['type'] == 'promo':
            emit('hide_payment', {}, room=sid)
    emit('command_result', {'success': True, 'message': 'Payment hidden'})

@socketio.on('control_command')
def handle_control_command(data):
    for sid, client in connected_clients.items():
        if client['type'] == 'promo':
            emit('control_command', data, room=sid)
    emit('command_result', {'success': True, 'message': 'Command sent'})

@socketio.on('set_theme')
def handle_set_theme(data):
    promo_settings['theme'] = data['theme']
    for sid, client in connected_clients.items():
        if client['type'] == 'promo':
            emit('theme_changed', data, room=sid)
    emit('command_result', {'success': True, 'message': 'Theme changed'})

@socketio.on('save_settings')
def handle_save_settings(data):
    # Здесь можно сохранить настройки в базу данных
    emit('command_result', {'success': True, 'message': 'Settings saved'})

@socketio.on('reset_settings')
def handle_reset_settings():
    global promo_settings
    promo_settings = {
        'volume': 70,
        'currentVideo': 'dQw4w9WgXcQ',
        'playlist': ['dQw4w9WgXcQ'],
        'playlistMode': 'single',
        'defaultAmount': 5000,
        'theme': 'default'
    }
    for sid, client in connected_clients.items():
        if client['type'] == 'promo':
            emit('settings_update', promo_settings, room=sid)
    emit('command_result', {'success': True, 'message': 'Settings reset'})


@app.route("/check_counterparties")
def check_counterparties():
    try:
        with get_db() as conn:
            # Указываем, что хотим работать со словарями
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM counterparties")
                counterparties = cur.fetchall()
                # Преобразуем каждый ряд в словарь явно
                result = []
                for row in counterparties:
                    result.append(dict(row))
                return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/counterparties")
def get_counterparties_api():
    try:
        with get_db() as conn:
            # Используем DictCursor для работы со словарями
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT id, name FROM counterparties ORDER BY name")
                
                # Преобразуем каждую строку в словарь вручную
                result = []
                for row in cur.fetchall():
                    result.append({
                        'id': row['id'],
                        'name': row['name']
                    })
                
                return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/products")
def products():
    products = load_products()
    products_by_category = {}
    for product in products:
        category = product.get("category", "Без категории")
        if category not in products_by_category:
            products_by_category[category] = []
        products_by_category[category].append(product)
    return render_template("products.html",
                           products_by_category=products_by_category,
                           products=products)


@app.route('/export_old_data')
def export_old_data():
    import sqlite3
    try:
        # Подключение к старой SQLite-базе
        old_db = sqlite3.connect('old_database.db')
        old_cur = old_db.cursor()

        # Получаем данные из SQLite
        old_cur.execute("SELECT date, total, payment_method FROM receipts")
        receipts = old_cur.fetchall()

        old_cur.execute("SELECT receipt_id, name, price, quantity, total, date FROM sales")
        sales = old_cur.fetchall()

        # Подключение к PostgreSQL
        with get_db() as conn:
            cur = conn.cursor()

            # Переносим чеки (без id — PostgreSQL сам создаст)
            receipt_id_mapping = {}  # {old_id: new_id}
            old_cur.execute("SELECT id, date, total, payment_method FROM receipts")
            for old_id, date, total, payment_method in old_cur.fetchall():
                cur.execute("""
                    INSERT INTO receipts (date, total, payment_method, organization)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (date, total, payment_method, None))
                new_id = cur.fetchone()[0]
                receipt_id_mapping[old_id] = new_id  # сохраняем соответствие id

            # Переносим продажи (используем новые receipt_id)
            old_cur.execute("SELECT receipt_id, name, price, quantity, total, date FROM sales")
            for receipt_id, name, price, quantity, total, date in old_cur.fetchall():
                new_receipt_id = receipt_id_mapping.get(receipt_id)
                if new_receipt_id:
                    cur.execute("""
                        INSERT INTO sales 
                        (receipt_id, name, price, quantity, total, date, currency)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        new_receipt_id,
                        name,
                        price,
                        quantity,
                        total,
                        date,
                        '₸'
                    ))

            conn.commit()

        return "✅ Данные успешно перенесены из SQLite в PostgreSQL!"
    
    except Exception as e:
        return f"❌ Ошибка при переносе: {str(e)}"




@app.route("/add_product", methods=["POST"])
def add_product():
    try:
        product_data = {
            "id": int(datetime.now(tz).timestamp()),
            "name": request.form.get("name"),
            "price": float(request.form.get("price")),
            "price_wholesale": float(request.form.get("price_wholesale", 0)),
            "price_bulk": float(request.form.get("price_bulk", 0)),
            "category": request.form.get("category", "")
        }

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO products (id, name, price, price_wholesale, price_bulk, category)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                product_data["id"],
                product_data["name"],
                product_data["price"],
                product_data["price_wholesale"],
                product_data["price_bulk"],
                product_data["category"]
            ))
            conn.commit()

        return redirect(url_for("products"))
    except Exception as e:
        return f"Ошибка: {str(e)}", 400



@app.route("/update_product", methods=["POST"])
def update_product():
    try:
        product_id = int(request.form.get("id"))
        name = request.form.get("name")
        price = float(request.form.get("price"))
        price_wholesale = float(request.form.get("price_wholesale", 0))
        price_bulk = float(request.form.get("price_bulk", 0))
        category = request.form.get("category", "")

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE products
                SET name = %s,
                    price = %s,
                    price_wholesale = %s,
                    price_bulk = %s,
                    category = %s
                WHERE id = %s
            """, (
                name, price, price_wholesale, price_bulk, category, product_id
            ))
            conn.commit()

        return redirect(url_for("products"))
    except Exception as e:
        return f"Ошибка: {str(e)}", 400



@app.route("/delete_product", methods=["POST"])
def delete_product():
    try:
        product_id = int(request.form.get("id"))

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
            conn.commit()

        return redirect(url_for("products"))
    except Exception as e:
        return f"Ошибка: {str(e)}", 400



@app.route("/upload_excel", methods=["POST"])
def upload_excel():
    if 'excel_file' not in request.files:
        return "Файл не загружен", 400

    file = request.files['excel_file']
    if not file.filename.lower().endswith(('.xls', '.xlsx')):
        return "Неверный формат файла", 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)

    try:
        df = pd.read_excel(filepath)

        with get_db() as conn:
            cur = conn.cursor()
            for _, row in df.iterrows():
                cur.execute("""
                    INSERT INTO products (name, price, price_wholesale, price_bulk, category)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    str(row.get("name", "")).strip(),
                    float(row.get("price", 0)),
                    float(row.get("price_wholesale", 0)),
                    float(row.get("price_bulk", 0)),
                    str(row.get("category", "")).strip()
                ))
            conn.commit()

        return redirect(url_for("products"))
    except Exception as e:
        return f"Ошибка при импорте: {str(e)}", 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)



@app.route("/promo")
def promo():
    return render_template("promo.html")


@app.route("/1Cweb")
def Cwebs():
    """1С-подобный интерфейс"""
    return render_template("1Cweb.html")


@app.route("/api/1c/add_product", methods=["POST"])
def add_1c_product():
    """Добавление товара через 1С интерфейс"""
    try:
        new_product = request.json
        products = load_products()

        # Генерируем ID как максимальный существующий + 1
        new_id = max(p['id'] for p in products) + 1 if products else 1
        new_product['id'] = new_id

        products.append(new_product)
        save_products(products)

        return jsonify({"status": "success", "id": new_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/1c/update_product", methods=["POST"])
def update_1c_product():
    """Обновление товара через 1С интерфейс"""
    try:
        updated_product = request.json
        products = load_products()

        for i, p in enumerate(products):
            if p['id'] == updated_product['id']:
                products[i] = updated_product
                break

        save_products(products)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/1c/delete_product", methods=["POST"])
def delete_1c_product():
    """Удаление товара через 1С интерфейс"""
    try:
        product_id = request.json.get('id')
        products = load_products()
        products = [p for p in products if p['id'] != product_id]
        save_products(products)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400




@app.route("/kassa")
def kassa():
    products = load_products()
    return render_template("kassa.html", products=products)



from datetime import datetime

from datetime import datetime

@app.route("/stats")
def stats():
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Получаем параметры из запроса
    date_from = request.args.get('date_from', today)
    date_to = request.args.get('date_to', today)
    organization = request.args.get('organization', '')
    counterparty_id = request.args.get('counterparty_id', '')  # Новый параметр

    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        query = """
            SELECT 
                r.id, 
                r.date, 
                r.total, 
                r.payment_method, 
                r.organization,
                c.name as counterparty_name,
                c.id as counterparty_id,  -- Adding counterparty ID
                COUNT(s.id) as items_count
            FROM receipts r
            LEFT JOIN sales s ON r.id = s.receipt_id
            LEFT JOIN counterparties c ON r.counterparty_id = c.id
            WHERE r.date >= %s AND r.date <= %s
        """
        
        params = [date_from, date_to + " 23:59:59"] if date_from == date_to else [date_from, date_to]
        
        if organization:
            query += " AND r.organization = %s"
            params.append(organization)
            
        if counterparty_id:  # Добавляем фильтр по контрагенту
            query += " AND r.counterparty_id = %s"
            params.append(counterparty_id)
        
        query += """
            GROUP BY 
                r.id, r.date, r.total, r.payment_method, 
                r.organization, c.name, c.id
            ORDER BY r.date DESC
        """
        
        # Получаем списки для фильтров
        cur.execute("SELECT DISTINCT organization FROM receipts ORDER BY organization")
        organizations = [org['organization'] for org in cur.fetchall()]
        
        cur.execute("SELECT id, name FROM counterparties ORDER BY name")
        counterparties = cur.fetchall()  # Список всех контрагентов
        
        cur.execute(query, params)
        receipts = cur.fetchall()

    return render_template(
        "stats.html", 
        receipts=receipts, 
        date_from=date_from, 
        date_to=date_to,
        organization=organization,
        organizations=organizations,
        counterparty_id=counterparty_id,  # Передаем выбранный контрагент
        counterparties=counterparties     # Передаем список контрагентов
    )


@app.route("/api/1c/export_excel")
def export_1c_excel():
    """Экспорт товаров в Excel для 1С интерфейса"""
    try:
        products = load_products()
        df = pd.DataFrame(products)

        # Создаем временный файл
        temp_path = DATA_DIR / "temp_export.xlsx"
        df.to_excel(temp_path, index=False)

        # Отправляем файл
        return send_from_directory(
            directory=DATA_DIR,
            path="temp_export.xlsx",
            as_attachment=True,
            download_name="products_export.xlsx"
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if temp_path.exists():
            temp_path.unlink()


@app.route("/api/1c/sync_database")
def sync_1c_database():
    """Синхронизация товаров с основной базой"""
    try:
        products = load_products()

        with get_db() as db:
            # Здесь можно добавить логику синхронизации
            # Например, обновление остатков или цен

            db.commit()

        return jsonify({"status": "success", "synced_items": len(products)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/report")
def report():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT r.id, r.date, r.total, r.payment_method, 
                   COUNT(s.id) as items_count
            FROM receipts r
            LEFT JOIN sales s ON r.id = s.receipt_id
            GROUP BY r.id
            ORDER BY r.date DESC
        """)
        receipts = cur.fetchall()
    return render_template("report.html", receipts=receipts)


@app.route('/api/1c/products')
def get_1c_products():
    """API для 1С интерфейса с пагинацией"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    products = load_products()

    # Пагинация
    start = (page - 1) * per_page
    end = start + per_page
    paginated_products = products[start:end]

    return jsonify({
        'products': paginated_products,
        'total': len(products),
        'page': page,
        'per_page': per_page
    })

@app.route("/get_products")
def get_products():
    products = load_products()
    return jsonify(products)




@app.route("/process_sale", methods=["POST"])
def process_sale():
    try:
        data = request.json
        cart = data.get("cart", [])
        payment_method = data.get("payment_method", "cash")
        organization = data.get("organization", "")
        counterparty_id = data.get("counterparty_id", None)

        # Суммируем общую стоимость
        total = sum(float(item.get("total", 0)) for item in cart)

        # Получаем дату и время в нужной зоне
        date = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        with get_db() as db:
            cursor = db.cursor()

            # Чек
            cursor.execute(
                """INSERT INTO receipts (date, total, payment_method, organization, counterparty_id)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (date, total, payment_method, organization, counterparty_id)
            )
            receipt_id = cursor.fetchone()[0]

            # Продажи
            for item in cart:
                cursor.execute("""
                    INSERT INTO sales 
                    (receipt_id, name, price, quantity, total, date, currency) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    receipt_id,
                    item.get("name"),
                    float(item.get("price", 0)),
                    float(item.get("quantity", 1)),
                    float(item.get("total", 0)),
                    date,
                    "₸"
                ))
                print(f"[DEBUG] Добавлен товар: {item.get('name')} x {item.get('quantity')}")

            # Отправляем информацию клиенту
            socketio.emit('receipt_processed', {'receipt_id': receipt_id})
            socketio.emit('show_total', {
                'total': total,
                'payment_method': payment_method,
                'receipt_id': receipt_id
            })

        print(f"[✅] Чек №{receipt_id} успешно добавлен.")
        print(f"[🛒] Товаров в чеке: {len(cart)}")

        return jsonify({"status": "success", "receipt_id": receipt_id})
    
    except Exception as e:
        print(f"[❌] Ошибка при обработке продажи: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route("/receipt_details/<int:receipt_id>")
def receipt_details(receipt_id):
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cur.execute("""
            SELECT r.*, c.name as counterparty_name, c.bin as counterparty_bin
            FROM receipts r
            LEFT JOIN counterparties c ON r.counterparty_id = c.id
            WHERE r.id = %s
        """, (receipt_id,))
        receipt = cur.fetchone()

        cur.execute(
            "SELECT name, price, quantity, total FROM sales WHERE receipt_id = %s",
            (receipt_id,)
        )

        items = cur.fetchall()
        print(f"[DEBUG] Чек ID: {receipt_id}")
        print(f"[DEBUG] Найдено товаров: {len(items)}")


    return render_template("receipt_details.html", receipt=receipt, items=items)


@app.route('/send_to_screen', methods=["POST"])
def send_to_screen():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        socketio.emit("show_total", {
            "total": data.get("total", "0"),
            "payment_method": data.get("payment_method", "cash"),
            "items": data.get("items", [])
        })
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/clear_screen', methods=["POST"])
def clear_screen():
    socketio.emit("clear_screen")
    return jsonify({"status": "success"})


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# --- Добавляем колонку organization, если её нет ---
def add_organization_column():
    """Добавляем колонку organization в таблицу receipts"""
    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS organization TEXT")
            conn.commit()
            print("[БАЗА] Колонка organization добавлена или уже существует")
        except Exception as e:
            print(f"[БАЗА] Ошибка при добавлении колонки organization: {e}")
        finally:
            cur.close()  # Колонка уже есть

# add_organization_column()


# ================ ИНВЕНТАРИЗАЦИЯ ================
@app.route("/inventory")
def show_inventory():
    """Страница учета товаров"""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, name, name_chinese, quantity, unit, 
                       to_char(last_updated, 'YYYY-MM-DD HH24:MI') as last_updated 
                FROM inventory
                ORDER BY last_updated DESC
            """)
            items = cur.fetchall()
            return render_template("inventory.html", items=items)
    except Exception as e:
        print(f"Ошибка при работе с базой: {str(e)}")
        return render_template("inventory.html", items=[])


@app.route("/inventory/add", methods=["POST"])
@app.route("/inventory/add", methods=["POST"])
def add_inventory():
    """Добавление товара"""
    try:
        name = request.form["name"]
        name_chinese = request.form.get("name_chinese", "")
        quantity = float(request.form["quantity"])
        unit = request.form["unit"]

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO inventory 
                (product_id, name, name_chinese, quantity, unit, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s)""",
                (int(datetime.now(tz).timestamp()), name, name_chinese, quantity, unit,
                 datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()

        return redirect(url_for("show_inventory"))
    except Exception as e:
        return f"Ошибка: {str(e)}", 400


# ================ КОНЕЦ ИНВЕНТАРИЗАЦИИ ================

# ================ ФУНКЦИИ РЕДАКТИРОВАНИЯ ================
@app.route("/inventory/edit/<int:item_id>")
def edit_inventory_item(item_id):
    """Страница редактирования товара"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM inventory WHERE id = %s",
            (item_id,)
        )
        item = cur.fetchone()
    return render_template("edit_inventory.html", item=item)


@app.route("/inventory/update/<int:item_id>", methods=["POST"])
def update_inventory_item(item_id):
    """Обновление товара"""
    try:
        name = request.form["name"]
        name_chinese = request.form.get("name_chinese", "")  # Получаем китайское название
        quantity = float(request.form["quantity"])
        unit = request.form["unit"]

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """UPDATE inventory SET
                name = %s,
                name_chinese = %s,
                quantity = %s,
                unit = %s,
                last_updated = %s
                WHERE id = %s""",
                (name, name_chinese, quantity, unit,
                 datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
                 item_id)
            )
            conn.commit()

        return redirect(url_for("show_inventory"))
    except Exception as e:
        return f"Ошибка: {str(e)}", 400


@app.route("/inventory/delete/<int:item_id>", methods=["POST"])
def delete_inventory_item(item_id):
    """Удаление товара"""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM inventory WHERE id = %s", (item_id,))
            conn.commit()
        return redirect(url_for("show_inventory"))
    except Exception as e:
        return f"Ошибка: {str(e)}", 400


# ================ КОНЕЦ ФУНКЦИЙ РЕДАКТИРОВАНИЯ ================

# ================ API для работы с контрагентами ================
@app.route("/api/counterparties", methods=["GET"])
def get_counterparties():
    """Получение списка контрагентов"""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, name, bin, type, address, phone, email,
                       to_char(created_at, 'YYYY-MM-DD HH24:MI') as created_at,
                       to_char(updated_at, 'YYYY-MM-DD HH24:MI') as updated_at
                FROM counterparties
                ORDER BY name
            """)
            counterparties = cur.fetchall()
            return jsonify([dict(row) for row in counterparties])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/counterparties", methods=["POST"])
def add_counterparty():
    """Добавление нового контрагента"""
    try:
        data = request.json
        required_fields = ["name", "type"]
        for field in required_fields:
            if field not in data:
                return jsonify({"status": "error", "message": f"Missing required field: {field}"}), 400

        tz = pytz.timezone('Asia/Almaty')
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO counterparties 
                (name, bin, type, address, phone, email, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data["name"],
                data.get("bin"),
                data["type"],
                data.get("address"),
                data.get("phone"),
                data.get("email"),
                now,
                now
            ))

            counterparty_id = cursor.fetchone()[0]  # ✅ правильно получаем ID
            db.commit()

        return jsonify({"status": "success", "id": counterparty_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route("/api/counterparties/<int:counterparty_id>", methods=["PUT"])
def update_counterparty(counterparty_id):
    """Обновление данных контрагента"""
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        updates = []
        params = []
        fields = ["name", "bin", "type", "address", "phone", "email"]

        for field in fields:
            if field in data:
                updates.append(f"{field} = %s")
                params.append(data[field])

        if not updates:
            return jsonify({"status": "error", "message": "No fields to update"}), 400

        params.append(datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"))  # updated_at
        params.append(counterparty_id)

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE counterparties SET {', '.join(updates)}, updated_at = %s WHERE id = %s",
                params
            )
            conn.commit()

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/counterparties/<int:counterparty_id>", methods=["DELETE"])
def delete_counterparty(counterparty_id):
    """Удаление контрагента"""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM counterparties WHERE id = %s", (counterparty_id,))
            conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/counterparties")
def counterparties_page():
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("""
                    SELECT id, name, bin, type, 
                           COALESCE(address, '') as address,
                           COALESCE(phone, '') as phone,
                           COALESCE(email, '') as email,
                           to_char(created_at, 'YYYY-MM-DD HH24:MI') as created_at
                    FROM counterparties
                    ORDER BY name
                """)
                counterparties = cur.fetchall()
        
        return render_template("counterparties.html", 
                            counterparties=counterparties)
    
    except Exception as e:
        return f"Ошибка при загрузке контрагентов: {str(e)}", 500

@app.route("/import_products_json")
def import_products_json():
    try:
        file_path = DATA_DIR / "products.json"

        # Читаем JSON
        with open(file_path, "r", encoding="utf-8") as f:
            products = json.load(f)

        success_count = 0
        error_count = 0

        with get_db() as conn:
            cur = conn.cursor()

            for product in products:
                try:
                    # Проверка на обязательные поля
                    if not product.get("name") or product.get("price") is None:
                        print(f"[⚠️] Пропущено: нет имени или цены: {product}")
                        error_count += 1
                        continue

                    # Вставка
                    cur.execute("""
                        INSERT INTO products (id, name, price, price_wholesale, price_bulk, category)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, (
                        int(product.get("id", datetime.now(tz).timestamp())),
                        str(product.get("name")),
                        float(product.get("price", 0)),
                        float(product.get("price_wholesale", 0)),
                        float(product.get("price_bulk", 0)),
                        str(product.get("category", ""))
                    ))

                    success_count += 1

                except Exception as item_error:
                    print(f"[❌] Ошибка при добавлении: {product.get('name')} — {item_error}")
                    error_count += 1

            conn.commit()

        return f"✅ Успешно добавлено: {success_count} товаров. Ошибок: {error_count}"
    except Exception as e:
        return f"[ОШИБКА] Не удалось импортировать: {str(e)}", 500




# ================ КОНЕЦ API для контрагентов ================

if __name__ == '__main__':
    try:
        init_db()
        print("[СЕРВЕР] Сервер запущен на http://localhost:8080")
        print(f"[СЕРВЕР] Папка с данными: {DATA_DIR}")
        socketio.run(app, host='0.0.0.0', port=8080, debug=True)
    except Exception as e:
        print(f"[ОШИБКА] При запуске сервера: {e}")






