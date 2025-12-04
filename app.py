from flask import Flask, render_template, request, jsonify, send_file
import os
from datetime import datetime
import io
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import base64
import re
import sqlite3
import requests
import json
import threading
import time

app = Flask(__name__)
app.template_folder = '.'

# === ТВОИ НАСТРОЙКИ TELEGRAM ===
BOT_TOKEN = "8202623703:AAHReI5nLyAzDB6a0y3Dus9nUYJrQmuhT9I"
CHAT_ID = "2108365479"
# ===============================

# Используем SQLite в постоянной папке
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'glucose.db')

# ============ АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ ИЗ TELEGRAM ============
def auto_restore_from_telegram():
    """Автоматически восстановить базу из Telegram при старте"""
    try:
        print("🔄 Проверяю базу данных...")
        
        # Если база уже есть и не пустая - пропускаем
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            try:
                c.execute("SELECT COUNT(*) FROM measurements")
                count = c.fetchone()[0]
                conn.close()
                if count > 0:
                    print(f"✅ База уже есть, записей: {count}")
                    return False
            except:
                conn.close()
        
        print("🔍 Ищу бэкап в Telegram...")
        
        # Получаем последние сообщения
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?limit=10"
        response = requests.get(url, timeout=10)
        
        if not response.json().get('ok'):
            print("⚠️ Не могу подключиться к Telegram")
            return False
        
        # Ищем JSON бэкап
        json_file_id = None
        for update in reversed(response.json()['result']):
            if 'message' in update and 'document' in update['message']:
                doc = update['message']['document']
                if doc['file_name'].endswith('.json'):
                    json_file_id = doc['file_id']
                    print(f"📦 Найден бэкап: {doc['file_name']}")
                    break
        
        if not json_file_id:
            print("⚠️ Бэкап не найден")
            return False
        
        # Получаем файл
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={json_file_id}"
        response = requests.get(url)
        file_info = response.json()
        
        if not file_info['ok']:
            print("⚠️ Не могу получить файл")
            return False
        
        # Скачиваем и восстанавливаем
        print("⬇️ Скачиваю бэкап...")
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info['result']['file_path']}"
        response = requests.get(file_url)
        data = json.loads(response.text)
        
        print(f"📊 Восстанавливаю {len(data)} записей...")
        
        # Создаём базу
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS measurements
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             value REAL NOT NULL,
             note TEXT,
             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
        ''')
        
        # Очищаем и вставляем
        c.execute("DELETE FROM measurements")
        
        for item in data:
            c.execute(
                "INSERT INTO measurements (value, note, created_at) VALUES (?, ?, ?)",
                (item['value'], item['note'], item.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            )
        
        conn.commit()
        conn.close()
        
        print(f"✅ Восстановлено {len(data)} записей!")
        
        # Отправляем уведомление
        try:
            message = f"🔄 *Автовосстановление базы*\n\n"
            message += f"📊 Записей восстановлено: {len(data)}\n"
            if data:
                first_date = data[0].get('created_at', '')[:10]
                last_date = data[-1].get('created_at', '')[:10]
                if first_date and last_date:
                    message += f"📅 Период: {first_date} — {last_date}\n"
            message += f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }
            requests.post(url, json=payload, timeout=5)
        except:
            pass
        
        return True
        
    except Exception as e:
        print(f"⚠️ Ошибка автовосстановления: {e}")
        return False

# ============ РУЧНАЯ ЗАГРУЗКА БЭКАПА ============
@app.route('/admin/upload_backup', methods=['GET', 'POST'])
def upload_backup():
    """Загрузить бэкап вручную"""
    if request.method == 'GET':
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>📤 Загрузить бэкап</title>
            <style>
                body { font-family: Arial; padding: 20px; text-align: center; }
                .card { background: #f8f9fa; padding: 25px; border-radius: 10px; margin: 20px auto; max-width: 600px; }
                .btn { 
                    background: #3498db; 
                    color: white; 
                    padding: 12px 24px; 
                    border: none; 
                    border-radius: 6px; 
                    cursor: pointer; 
                    margin: 10px;
                    text-decoration: none;
                    display: inline-block;
                }
                .btn-success { background: #2ecc71; }
                .btn-danger { background: #e74c3c; }
                input[type="file"] { 
                    padding: 15px; 
                    margin: 20px 0; 
                    border: 2px dashed #3498db; 
                    border-radius: 5px; 
                    width: 90%;
                }
            </style>
        </head>
        <body>
            <h1>📤 Загрузка бэкапа</h1>
            
            <div class="card">
                <h3>📱 Из Telegram:</h3>
                <ol>
                    <li>Открой Telegram</li>
                    <li>Найди файл от бота (glucose_backup_*.db или .json)</li>
                    <li>Скачай файл</li>
                    <li>Загрузи здесь:</li>
                </ol>
                
                <form method="post" enctype="multipart/form-data">
                    <input type="file" name="backup_file" accept=".db,.json" required>
                    <br>
                    <button type="submit" class="btn btn-success">📤 Загрузить</button>
                    <a href="/" class="btn">🏠 На главную</a>
                </form>
            </div>
            
            <div class="card" style="background: #fff3cd;">
                <h3>⚠️ Внимание!</h3>
                <p><strong>.db файл</strong> - полностью заменит текущую базу</p>
                <p><strong>.json файл</strong> - добавит данные к существующим</p>
                <a href="/admin/setup_test_data" class="btn btn-danger">🗑️ Начать с чистой базы</a>
            </div>
        </body>
        </html>
        '''
    
    # Обработка загрузки
    if 'backup_file' not in request.files:
        return '❌ Нет файла', 400
    
    file = request.files['backup_file']
    if file.filename == '':
        return '❌ Файл не выбран', 400
    
    try:
        filename = file.filename.lower()
        
        # .db файл - полная замена базы
        if filename.endswith('.db'):
            file.save(DB_PATH)
            
            # Проверяем
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM measurements")
            count = c.fetchone()[0]
            conn.close()
            
            return f'''
            <div style="text-align: center; padding: 40px;">
                <h1 style="color: #27ae60;">✅ База восстановлена!</h1>
                <p style="font-size: 18px;">Записей: <strong>{count}</strong></p>
                <div style="margin: 30px;">
                    <a href="/print_report" class="btn btn-success">📊 Отчет</a>
                    <a href="/" class="btn">➕ Добавить данные</a>
                </div>
            </div>
            '''
        
        # .json файл - восстановление данных
        elif filename.endswith('.json'):
            data = json.load(file)
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # Очищаем и вставляем
            c.execute("DELETE FROM measurements")
            
            for item in data:
                c.execute(
                    "INSERT INTO measurements (value, note, created_at) VALUES (?, ?, ?)",
                    (item['value'], item['note'], item.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                )
            
            conn.commit()
            conn.close()
            
            return f'''
            <div style="text-align: center; padding: 40px;">
                <h1 style="color: #27ae60;">✅ Данные восстановлены!</h1>
                <p style="font-size: 18px;">Добавлено: <strong>{len(data)}</strong> записей</p>
                <div style="margin: 30px;">
                    <a href="/print_report" class="btn btn-success">📊 Отчет</a>
                    <a href="/" class="btn">➕ Добавить данные</a>
                </div>
            </div>
            '''
        
        else:
            return '''
            <h1 style="color: #e74c3c;">❌ Неверный формат</h1>
            <p>Только .db или .json</p>
            <p><a href="/admin/upload_backup">← Назад</a></p>
            '''
            
    except Exception as e:
        return f'''
        <h1 style="color: #e74c3c;">❌ Ошибка</h1>
        <pre>{str(e)}</pre>
        <p><a href="/admin/upload_backup">← Попробовать снова</a></p>
        '''

# ============ ИНИЦИАЛИЗАЦИЯ БАЗЫ ============
def init_db():
    """Инициализация базы данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS measurements
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             value REAL NOT NULL,
             note TEXT,
             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
        ''')
        
        # Создаем индекс для быстрого поиска по дате
        c.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON measurements(created_at)')
        
        conn.commit()
        
        # Проверяем что таблица создана
        c.execute("SELECT COUNT(*) FROM measurements")
        count = c.fetchone()[0]
        
        conn.close()
        print(f"✅ База создана/проверена: {DB_PATH}, записей: {count}")
        return True
    except Exception as e:
        print(f"❌ Ошибка создания БД: {e}")
        return False

def get_db_connection():
    """Получить подключение к SQLite"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ============ ЗАПУСК И АВТОВОССТАНОВЛЕНИЕ ============
print("=" * 60)
print("🚀 GLIKOSA Tracker запускается...")
print("=" * 60)

# Пытаемся восстановить из Telegram
if auto_restore_from_telegram():
    print("✅ Данные восстановлены из Telegram")
else:
    print("📝 Используем существующую/новую базу")

# Инициализируем базу
init_db()

# ============ ОСНОВНЫЕ МАРШРУТЫ ============
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/glucose')
def glucose():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/analytics')
def analytics():
    return render_template('dashboard.html')

@app.route('/health')
def health_check():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM measurements")
        count = c.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "glucose_tracker",
            "db_path": DB_PATH,
            "db_exists": os.path.exists(DB_PATH),
            "records_count": count,
            "python_version": os.sys.version,
            "telegram_bot": "configured",
            "auto_restore": "enabled"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })

# API для работы с данными
@app.route('/api/measurement', methods=['POST'])
def add_measurement():
    try:
        data = request.get_json()
        
        if not data or 'value' not in data:
            return jsonify({'error': 'Нет данных', 'success': False}), 400
            
        value = float(data['value'])
        note = data.get('note', '')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            'INSERT INTO measurements (value, note) VALUES (?, ?)',
            (value, note)
        )
        conn.commit()
        
        inserted_id = c.lastrowid
        
        c.close()
        conn.close()
        
        # Отправляем уведомление в Telegram о новой записи
        try:
            message = f"📝 *Новая запись глюкозы*\n\n"
            message += f"📊 Значение: *{value} mmol/L*\n"
            if note:
                message += f"📝 Примечание: {note}\n"
            message += f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }
            requests.post(url, json=payload, timeout=5)
        except:
            pass  # Игнорируем ошибки Telegram
        
        return jsonify({
            'message': '✅ Данные сохранены!',
            'success': True,
            'id': inserted_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/measurements')
def get_measurements():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute('''
            SELECT id, value, note, 
                   datetime(created_at) as created_at 
            FROM measurements 
            ORDER BY created_at DESC
        ''')
        
        measurements = []
        for row in c.fetchall():
            measurements.append({
                'id': row['id'],
                'value': row['value'],
                'note': row['note'] or '',
                'created_at': row['created_at'],
                'date': row['created_at'][:10],
                'time': row['created_at'][11:16]
            })
        
        conn.close()
        return jsonify(measurements)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Функция для создания графиков
def create_pressure_chart(measurements):
    """Создать график артериального давления"""
    try:
        systolic_list = []
        diastolic_list = []
        dates_list = []
        
        for m in measurements:
            pressure = m.get('pressure', '')
            if pressure and pressure != '-':
                numbers = re.findall(r'\d+', str(pressure))
                if len(numbers) >= 2:
                    systolic_list.append(int(numbers[0]))
                    diastolic_list.append(int(numbers[1]))
                    
                    date_obj = datetime.strptime(m['date'], '%Y-%m-%d')
                    date_str = date_obj.strftime('%d.%m')
                    dates_list.append(f"{date_str}\n{m['time']}")
        
        if len(systolic_list) < 2:
            return None
        
        plt.figure(figsize=(14, 6))
        x_indices = range(len(systolic_list))
        
        plt.plot(x_indices, systolic_list, 'ro-', 
                linewidth=2, markersize=8, label='Верхнее (систолическое)')
        plt.plot(x_indices, diastolic_list, 'bs-',
                linewidth=2, markersize=8, label='Нижнее (диастолическое)')
        
        plt.axhspan(110, 130, alpha=0.1, color='green', label='Норма верхнего')
        plt.axhspan(70, 85, alpha=0.1, color='lightblue', label='Норма нижнего')
        
        plt.title('Динамика артериального давления', fontsize=16, fontweight='bold', pad=20)
        plt.xlabel('Дата и время измерения →', fontsize=12, labelpad=10)
        plt.ylabel('Давление (мм рт. ст.)', fontsize=12, labelpad=10)
        plt.grid(True, alpha=0.3, linestyle='--')
        plt.legend(loc='upper left', fontsize=10)
        
        if dates_list:
            plt.xticks(x_indices, dates_list, rotation=45, fontsize=10, ha='right')
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
        plt.close()
        buf.seek(0)
        return buf.getvalue()
        
    except Exception as e:
        print(f"⚠️ Ошибка создания графика давления: {e}")
        return None

@app.route('/print_report')
def print_report():
    """Генерация печатного отчета"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute('''
            SELECT 
                value, 
                COALESCE(note, '') as note,
                datetime(created_at) as created_at
            FROM measurements 
            ORDER BY created_at DESC
        ''')
        
        measurements_for_table = []
        measurements_for_chart = []
        glucose_values = []
        
        for row in c.fetchall():
            value = float(row['value'])
            note = row['note']
            created_at = row['created_at']
            
            # Парсим дату
            try:
                dt = datetime.strptime(created_at[:19], '%Y-%m-%d %H:%M:%S')
                date_str = dt.strftime('%Y-%m-%d')
                time_str = dt.strftime('%H:%M')
                timestamp = dt
            except:
                date_str = datetime.now().strftime('%Y-%m-%d')
                time_str = datetime.now().strftime('%H:%M')
                timestamp = datetime.now()
            
            # Извлекаем давление
            pressure = ''
            if note and 'Давление:' in note:
                try:
                    pressure_part = note.split('Давление:')[1].strip()
                    numbers = re.findall(r'\d+', pressure_part)
                    if numbers:
                        if len(numbers) >= 2:
                            pressure = f"{numbers[0]}-{numbers[1]}"
                        else:
                            pressure = numbers[0]
                except:
                    pass
            
            if len(measurements_for_table) < 30:
                measurements_for_table.append({
                    'date': date_str,
                    'time': time_str,
                    'value': value,
                    'pressure': pressure if pressure else '-'
                })
            
            measurements_for_chart.append({
                'date': date_str,
                'time': time_str,
                'value': value,
                'pressure': pressure,
                'timestamp': timestamp
            })
            glucose_values.append(value)
        
        conn.close()
        
        # Сортировка для графиков
        measurements_for_chart.sort(key=lambda x: x['timestamp'])
        
        # График глюкозы
        glucose_chart_base64 = ""
        if measurements_for_chart:
            try:
                chart_data = measurements_for_chart[-20:] if len(measurements_for_chart) > 20 else measurements_for_chart
                
                dates_for_x = []
                values_for_y = []
                
                for m in chart_data:
                    date_obj = datetime.strptime(m['date'], '%Y-%m-%d')
                    date_str = date_obj.strftime('%d.%m')
                    dates_for_x.append(f"{date_str}\n{m['time']}")
                    values_for_y.append(m['value'])
                
                plt.figure(figsize=(14, 6))
                plt.plot(values_for_y, marker='o', linewidth=2, markersize=6, 
                        color='#2c3e50', markerfacecolor='white', markeredgewidth=2)
                
                plt.title('Динамика уровня глюкозы', fontsize=16, fontweight='bold', pad=20)
                plt.xlabel('Дата и время измерения →', fontsize=12, labelpad=10)
                plt.ylabel('Глюкоза (mmol/L)', fontsize=12, labelpad=10)
                plt.grid(True, alpha=0.3, linestyle='--')
                
                if len(dates_for_x) > 0:
                    plt.xticks(range(len(dates_for_x)), dates_for_x, rotation=45, fontsize=10, ha='right')
                
                plt.axhspan(3.9, 5.5, alpha=0.1, color='green')
                plt.tight_layout()
                
                buf = io.BytesIO()
                plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
                plt.close()
                buf.seek(0)
                glucose_chart_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                
            except Exception as chart_error:
                print(f"⚠️ Ошибка создания графика глюкозы: {chart_error}")
                glucose_chart_base64 = ""
        
        # График давления
        pressure_chart_base64 = ""
        if measurements_for_chart:
            pressure_chart = create_pressure_chart(measurements_for_chart)
            if pressure_chart:
                pressure_chart_base64 = base64.b64encode(pressure_chart).decode('utf-8')
        
        # Статистика
        if glucose_values:
            stats = {
                'total': len(glucose_values),
                'avg_glucose': round(sum(glucose_values) / len(glucose_values), 1),
                'min_glucose': min(glucose_values),
                'max_glucose': max(glucose_values),
            }
            
            if measurements_for_chart:
                start_date = measurements_for_chart[0]['date']
                end_date = measurements_for_chart[-1]['date']
            else:
                start_date = end_date = datetime.now().strftime('%Y-%m-%d')
        else:
            stats = {
                'total': 0,
                'avg_glucose': 0,
                'min_glucose': 0,
                'max_glucose': 0,
            }
            start_date = end_date = datetime.now().strftime('%Y-%m-%d')
        
        return render_template('print_report.html',
                             measurements=measurements_for_table,
                             stats=stats,
                             start_date=start_date,
                             end_date=end_date,
                             glucose_chart_base64=glucose_chart_base64,
                             pressure_chart_base64=pressure_chart_base64)
        
    except Exception as e:
        error_msg = str(e)[:200]
        print(f"❌ Ошибка в print_report: {error_msg}")
        
        return f'''
        <div style="padding: 20px; font-family: Arial;">
            <h2>📊 Отчет по глюкозе</h2>
            <p>Ошибка генерации отчета: {error_msg}</p>
            <p><a href="/">Вернуться на главную</a></p>
        </div>
        '''

# Тестовые данные
@app.route('/admin/setup_test_data')
def setup_test_data():
    """Добавить тестовые данные"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Очищаем старые данные
        c.execute("DELETE FROM measurements")
        
        # Тестовые данные
        test_data = [
            (6.4, 'Давление: 130-140', '2024-11-29 10:00:00'),
            (6.9, 'Давление: 130-140', '2024-11-30 10:00:00'),
            (6.8, 'Давление: 130-140', '2024-12-01 10:00:00'),
        ]
        
        c.executemany(
            "INSERT INTO measurements (value, note, created_at) VALUES (?, ?, ?)", 
            test_data
        )
        
        conn.commit()
        conn.close()
        
        # Отправляем уведомление
        try:
            message = "✅ *Тестовые данные добавлены!*\n\n"
            message += "📅 29.11.2024: 6.4 mmol/L\n"
            message += "📅 30.11.2024: 6.9 mmol/L\n"
            message += "📅 01.12.2024: 6.8 mmol/L\n\n"
            message += f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }
            requests.post(url, json=payload, timeout=5)
        except:
            pass
        
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Данные добавлены</title>
            <style>
                body { font-family: Arial; padding: 30px; }
                .success { color: #2ecc71; font-size: 24px; }
                .data-item { margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px; }
                .button { display: inline-block; background: #3498db; color: white; padding: 12px 24px; 
                         text-decoration: none; border-radius: 5px; margin: 10px 5px; }
                .telegram { background: #0088cc; }
            </style>
        </head>
        <body>
            <h1 class="success">✅ Тестовые данные добавлены!</h1>
            <p>📱 Уведомление отправлено в Telegram</p>
            
            <h3>Добавленные измерения:</h3>
            <div class="data-item">📅 <strong>29 ноября 10:00</strong> - Глюкоза: 6.4 mmol/L, Давление: 130-140</div>
            <div class="data-item">📅 <strong>30 ноября 10:00</strong> - Глюкоза: 6.9 mmol/L, Давление: 130-140</div>
            <div class="data-item">📅 <strong>1 декабря 10:00</strong> - Глюкоза: 6.8 mmol/L, Давление: 130-140</div>
            
            <div style="margin-top: 30px;">
                <a href="/print_report" class="button">📊 Отчет с графиками</a>
                <a href="/admin/backup_to_telegram" class="button telegram">🤖 Отправить бэкап в Telegram</a>
                <a href="/" class="button" style="background: #95a5a6;">➕ Добавить данные</a>
            </div>
        </body>
        </html>
        '''
        
    except Exception as e:
        return f'''
        <h1 style="color: #e74c3c;">❌ Ошибка</h1>
        <p>{str(e)}</p>
        <a href="/">На главную</a>
        '''

# Telegram функции
@app.route('/admin/backup_to_telegram')
def backup_to_telegram():
    """Отправить бэкап данных в Telegram"""
    try:
        # === ПОДГОТОВКА ДАННЫХ ===
        conn = get_db_connection()
        c = conn.cursor()
        
        # Получаем статистику
        c.execute("SELECT COUNT(*) as count FROM measurements")
        count = c.fetchone()['count']
        
        c.execute("""
            SELECT MIN(datetime(created_at)) as first_date,
                   MAX(datetime(created_at)) as last_date,
                   ROUND(AVG(value), 1) as avg_value,
                   MIN(value) as min_value,
                   MAX(value) as max_value
            FROM measurements
        """)
        stats = c.fetchone()
        
        # Получаем последние 5 записей
        c.execute('''
            SELECT value, note, datetime(created_at) as created_at 
            FROM measurements 
            ORDER BY created_at DESC
            LIMIT 5
        ''')
        recent_data = c.fetchall()
        
        conn.close()
        
        # === 1. ОТПРАВКА СТАТИСТИКИ ===
        message = f"""
📊 *Бэкап данных глюкозы*

📅 *Период:* {stats['first_date'][:10] if stats['first_date'] else 'Нет данных'} — {stats['last_date'][:10] if stats['last_date'] else 'Нет данных'}
📈 *Всего записей:* {count}

📉 *Статистика:*
• Среднее: {stats['avg_value'] or 0} mmol/L
• Минимум: {stats['min_value'] or 0} mmol/L
• Максимум: {stats['max_value'] or 0} mmol/L

📋 *Последние записи:*
"""
        
        for row in recent_data:
            created_at = row['created_at']
            date_str = created_at[:10]
            time_str = created_at[11:16]
            note = f" ({row['note']})" if row['note'] else ""
            message += f"• {date_str} {time_str}: {row['value']} mmol/L{note}\n"
        
        message += f"\n🔄 *Автоматический бэкап*\n⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        # Отправляем сообщение
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': True
        }
        
        response = requests.post(url, json=payload)
        
        if response.status_code != 200:
            return f"❌ Ошибка отправки сообщения: {response.text}<br><a href='/'>На главную</a>"
        
        # === 2. ОТПРАВКА ФАЙЛА БАЗЫ ===
        if count > 0 and os.path.exists(DB_PATH):
            # Отправляем .db файл
            with open(DB_PATH, 'rb') as db_file:
                files = {'document': db_file}
                data = {'chat_id': CHAT_ID}
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
                
                response = requests.post(url, files=files, data=data, timeout=30)
                
                if response.status_code != 200:
                    return f"❌ Ошибка отправки файла: {response.text}<br><a href='/'>На главную</a>"
        
        # === 3. ОТПРАВКА JSON ДАННЫХ ===
        if count > 0:
            # Экспортируем все данные в JSON
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('SELECT * FROM measurements')
            data = []
            for row in c.fetchall():
                data.append(dict(row))
            conn.close()
            
            # Сохраняем временный JSON файл
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            json.dump(data, temp_file, ensure_ascii=False, indent=2, default=str)
            temp_file.close()
            
            # Отправляем JSON файл
            with open(temp_file.name, 'rb') as f:
                files = {'document': f}
                data = {'chat_id': CHAT_ID}
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
                response = requests.post(url, files=files, data=data, timeout=30)
            
            # Удаляем временный файл
            os.unlink(temp_file.name)
            
            if response.status_code != 200:
                return f"❌ Ошибка отправки JSON: {response.text}<br><a href='/'>На главную</a>"
        
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>✅ Бэкап отправлен</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 40px; text-align: center; }
                .success { color: #27ae60; font-size: 24px; margin: 20px 0; }
                .button { 
                    display: inline-block; 
                    background: #3498db; 
                    color: white; 
                    padding: 15px 30px; 
                    text-decoration: none; 
                    border-radius: 8px; 
                    margin: 10px; 
                    font-size: 16px;
                }
                .telegram { background: #0088cc; }
            </style>
        </head>
        <body>
            <h1 class="success">✅ Бэкап отправлен в Telegram!</h1>
            <p>📱 Проверь свой Telegram аккаунт</p>
            
            <div style="margin-top: 30px;">
                <a href="/admin/backup_to_telegram" class="button telegram">🔄 Отправить ещё раз</a>
                <a href="/admin/backup" class="button">📥 Скачать вручную</a>
                <a href="/" class="button">🏠 На главную</a>
            </div>
            
            <p style="margin-top: 30px; color: #7f8c8d;">
                ⏰ Следующий автоматический бэкап будет в 21:00
            </p>
        </body>
        </html>
        '''
        
    except Exception as e:
        import traceback
        return f'''
        <h1 style="color: #e74c3c;">❌ Ошибка отправки в Telegram</h1>
        <pre>{str(e)}</pre>
        <h3>🔧 Проверь:</h3>
        <ol>
            <li>Бот запущен (@BotFather → /mybots)?</li>
            <li>Ты написал боту в ЛС "Привет"?</li>
            <li>Chat ID правильный? (2108365479)</li>
        </ol>
        <a href="/">На главную</a>
        '''

@app.route('/admin/test_telegram')
def test_telegram():
    """Тестовая отправка сообщения"""
    try:
        message = "✅ *Глюкоза Трекер работает!*\n\n"
        message += "🤖 Бот настроен корректно\n"
        message += "📊 Все функции доступны\n"
        message += f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            return '''
            <h1 style="color: #27ae60;">✅ Тест успешен!</h1>
            <p>Сообщение отправлено в Telegram.</p>
            <p>Проверь свой Telegram аккаунт.</p>
            <p><a href="/admin/backup_to_telegram">📊 Отправить полный бэкап</a></p>
            '''
        else:
            return f'''
            <h1 style="color: #e74c3c;">❌ Ошибка</h1>
            <pre>{response.text}</pre>
            <p>Проверь настройки бота.</p>
            '''
            
    except Exception as e:
        return f'''
        <h1>❌ Ошибка</h1>
        <pre>{str(e)}</pre>
        '''

# Админ функции
@app.route('/admin/db_status')
def db_status():
    """Проверка статуса базы данных"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Проверяем таблицу
        c.execute("""
            SELECT 
                (SELECT COUNT(*) FROM measurements) as total_records,
                (SELECT MAX(created_at) FROM measurements) as last_record,
                (SELECT MIN(created_at) FROM measurements) as first_record
        """)
        result = c.fetchone()
        
        status = {
            "database_type": "SQLite",
            "connected": True,
            "db_file": DB_PATH,
            "file_size": os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0,
            "total_records": result['total_records'],
            "last_record": result['last_record'] if result['last_record'] else "Нет данных",
            "first_record": result['first_record'] if result['first_record'] else "Нет данных",
            "telegram_bot": "настроен",
            "auto_restore": "включено"
        }
        
        conn.close()
        
        return jsonify(status)
        
    except Exception as e:
        return jsonify({
            "database_type": "SQLite (ошибка)",
            "connected": False,
            "error": str(e)
        })

@app.route('/admin/backup')
def backup_database():
    """Скачать резервную копию базы"""
    if not os.path.exists(DB_PATH):
        return "База данных не найдена", 404
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        DB_PATH,
        as_attachment=True,
        download_name=f'glucose_backup_{timestamp}.db'
    )

@app.route('/admin/simple_backup')
def simple_backup():
    """Простой интерфейс для бэкапов"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as count FROM measurements")
        count = c.fetchone()['count']
        conn.close()
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head><title>Бэкап данных</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>📊 Бэкап данных глюкозы</h1>
            <p>Всего записей: <strong>{count}</strong></p>
            
            <div style="margin: 20px 0;">
                <a href="/admin/backup_to_telegram" style="
                    display: inline-block;
                    background: #0088cc;
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-size: 18px;
                    margin: 10px;
                ">
                    🤖 Отправить в Telegram
                </a>
            </div>
            
            <div style="margin: 20px 0;">
                <a href="/admin/backup" style="
                    display: inline-block;
                    background: #3498db;
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-size: 18px;
                    margin: 10px;
                ">
                    📥 Скачать базу (.db)
                </a>
            </div>
            
            <div style="margin: 20px 0;">
                <a href="/api/measurements" style="
                    display: inline-block;
                    background: #2ecc71;
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-size: 18px;
                    margin: 10px;
                ">
                    📄 Скачать JSON
                </a>
            </div>
            
            <h3>📋 Рекомендация:</h3>
            <p>1. <strong>Каждый день</strong> заходи на эту страницу</p>
            <p>2. Нажимай "🤖 Отправить в Telegram"</p>
            <p>3. Данные сохранятся в твоем Telegram</p>
            
            <p style="color: #e74c3c; font-weight: bold; margin-top: 20px;">
                ⚠️ На бесплатном Render данные могут удалиться в любой момент!
                Делай бэкапы регулярно!
            </p>
        </body>
        </html>
        '''
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# Автоматический бэкап
def auto_backup_daily():
    """Ежедневный автоматический бэкап в 21:00"""
    while True:
        try:
            now = datetime.now()
            
            # Проверяем время каждый час
            if now.hour == 21 and now.minute == 0:
                print(f"⏰ {now.strftime('%H:%M')} - Отправляю ежедневный бэкап...")
                
                try:
                    # Отправляем бэкап
                    requests.get("https://glikosa.onrender.com/admin/backup_to_telegram", timeout=30)
                    print("✅ Ежедневный бэкап отправлен")
                except Exception as e:
                    print(f"⚠️ Ошибка авто-бэкапа: {e}")
                
                # Ждем 61 минуту чтобы не отправить дважды
                time.sleep(3660)
            else:
                # Проверяем каждую минуту
                time.sleep(60)
                
        except Exception as e:
            print(f"⚠️ Ошибка в авто-бэкапе: {e}")
            time.sleep(300)

# Запуск приложения
if __name__ == '__main__':
    # Запускаем авто-бэкап
    backup_thread = threading.Thread(target=auto_backup_daily, daemon=True)
    backup_thread.start()
    
    print("=" * 60)
    print("🚀 GLIKOSA Tracker запущен!")
    print(f"📊 База данных: SQLite ({DB_PATH})")
    print(f"🤖 Telegram бот: настроен")
    print(f"🔄 Автовосстановление: включено")
    print(f"⏰ Авто-бэкап: 21:00 ежедневно")
    print("=" * 60)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
