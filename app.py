from flask import Flask, render_template, request, jsonify, send_file
import os
from datetime import datetime, timedelta
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
import tempfile

app = Flask(__name__)
app.template_folder = '.'

# === ТВОИ НАСТРОЙКИ TELEGRAM ===
BOT_TOKEN = "8202623703:AAHReI5nLyAzDB6a0y3Dus9nUYJrQmuhT9I"
CHAT_ID = "2108365479"
# ===============================

# Используем SQLite в постоянной папке
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'glucose.db')

# ============ ИНИЦИАЛИЗАЦИЯ БАЗЫ ============
def init_db():
    """Создает таблицы. Добавлена таблица логов бэкапа."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Таблица измерений
    c.execute('''
        CREATE TABLE IF NOT EXISTS measurements
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         value REAL NOT NULL,
         note TEXT,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON measurements(created_at)')
    
    # Таблица истории бэкапов (для проверки даты)
    c.execute('''
        CREATE TABLE IF NOT EXISTS backup_logs
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         status TEXT)
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ База данных готова: {DB_PATH}")

def get_db_connection():
    """Подключение к БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ============ ЛОГИКА УМНОГО БЭКАПА ============
def perform_full_backup():
    """Выполняет бэкап и записывает дату в backup_logs"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as count FROM measurements")
        count = c.fetchone()[0]
        
        if count == 0:
            conn.close()
            return

        # 1. Собираем данные
        c.execute('SELECT * FROM measurements ORDER BY created_at DESC')
        data = []
        for row in c.fetchall():
            data.append({
                'id': row[0],
                'value': row[1],
                'note': row[2],
                'created_at': row[3]
            })
        
        # 2. Отправляем в Telegram
        timestamp = datetime.now().strftime('%Y-%m-%d')
        filename_json = f"backup_7days_{timestamp}.json"
        
        message = f"📅 *Еженедельный бэкап*\\\\n📊 Всего записей: {count}\\\\n⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        })
        
        files = {'document': (filename_json, json.dumps(data, ensure_ascii=False, indent=2, default=str).encode('utf-8'), 'application/json')}
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument", files=files, data={
            'chat_id': CHAT_ID, 'caption': f'💾 Auto Backup {timestamp}'
        })
        
        # 3. ЗАПИСЫВАЕМ ФАКТ БЭКАПА В БАЗУ
        c.execute("INSERT INTO backup_logs (executed_at, status) VALUES (?, ?)", 
                 (datetime.now(), 'success'))
        conn.commit()
        conn.close()
        
        print(f"✅ Еженедельный бэкап выполнен успешно!")
        
    except Exception as e:
        print(f"⚠️ Ошибка выполнения бэкапа: {e}")

def check_and_run_backup():
    """Проверяет дату последнего бэкапа в БД"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Берем дату последнего успешного бэкапа
        c.execute("SELECT executed_at FROM backup_logs ORDER BY executed_at DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        
        run_needed = False
        
        if not row:
            print("🕒 Бэкапов еще не было. Запускаю первый...")
            run_needed = True
        else:
            last_date_str = row[0]
            # Преобразуем строку времени (SQLite хранит как строку) в объект
            try:
                last_date = datetime.strptime(last_date_str, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                # Если формат без микросекунд
                last_date = datetime.strptime(last_date_str, '%Y-%m-%d %H:%M:%S')
                
            days_diff = (datetime.now() - last_date).days
            
            if days_diff >= 7:
                print(f"🕒 Прошло {days_diff} дней с последнего бэкапа. Запускаю...")
                run_needed = True
            else:
                print(f"⏳ Последний бэкап был {days_diff} дн. назад. Ждем...")
        
        if run_needed:
            perform_full_backup()
            
    except Exception as e:
        print(f"⚠️ Ошибка проверки планировщика: {e}")

def start_smart_scheduler():
    """Запускает цикл проверки раз в час"""
    def run():
        # Первая проверка сразу при старте (через 10 сек, чтобы Flask успел запуститься)
        time.sleep(10)
        check_and_run_backup()
        
        while True:
            # Проверяем каждый час (3600 сек)
            # Это надежнее, чем спать 7 дней, так как скрипт может перезагрузиться
            time.sleep(3600)
            check_and_run_backup()
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print("✅ Планировщик бэкапов запущен (проверка базы каждый час)")

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
        
        # Информация о последнем бэкапе для статуса
        c.execute("SELECT executed_at FROM backup_logs ORDER BY executed_at DESC LIMIT 1")
        last_backup = c.fetchone()
        last_backup_str = last_backup[0] if last_backup else "Never"
        
        conn.close()
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "records_count": count,
            "last_backup": last_backup_str
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})

# ============ API ============
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
        c.execute('INSERT INTO measurements (value, note) VALUES (?, ?)', (value, note))
        conn.commit()
        inserted_id = c.lastrowid
        conn.close()
        
        # Telegram уведомление (просто инфо, не бэкап)
        try:
            message = f"📝 *Новая запись*\\\\n📊 {value} mmol/L"
            if note: message += f"\\\\n📝 {note}"
            message += f"\\\\n⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            
            def send_notify():
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                    'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'
                }, timeout=5)
            threading.Thread(target=send_notify, daemon=True).start()
        except:
            pass
        
        return jsonify({
            'message': '✅ Сохранено!',
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
        c.execute('SELECT id, value, note, datetime(created_at) as created_at FROM measurements ORDER BY created_at DESC')
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

# ============ ГРАФИКИ ============
def create_pressure_chart(measurements):
    try:
        systolic_list = []
        diastolic_list = []
        dates_list = []
        
        for m in measurements:
            pressure = m.get('pressure', '')
            if pressure and pressure != '-':
                numbers = re.findall(r'\\d+', str(pressure))
                if len(numbers) >= 2:
                    systolic_list.append(int(numbers[0]))
                    diastolic_list.append(int(numbers[1]))
                    date_obj = datetime.strptime(m['date'], '%Y-%m-%d')
                    date_str = date_obj.strftime('%d.%m')
                    dates_list.append(f"{date_str}\\n{m['time']}")
        
        if len(systolic_list) < 2:
            return None
        
        plt.figure(figsize=(14, 6))
        x_indices = range(len(systolic_list))
        
        plt.plot(x_indices, systolic_list, 'ro-', linewidth=2, markersize=8, label='Верхнее')
        plt.plot(x_indices, diastolic_list, 'bs-', linewidth=2, markersize=8, label='Нижнее')
        
        plt.axhspan(110, 130, alpha=0.1, color='green')
        plt.axhspan(70, 85, alpha=0.1, color='lightblue')
        
        plt.title('Динамика артериального давления', fontsize=16, fontweight='bold')
        plt.xlabel('Дата и время', fontsize=12)
        plt.ylabel('Давление (мм рт. ст.)', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        if dates_list:
            plt.xticks(x_indices, dates_list, rotation=45, ha='right')
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
        plt.close()
        buf.seek(0)
        return buf.getvalue()
    except:
        return None

@app.route('/print_report')
def print_report():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT value, COALESCE(note, "") as note, datetime(created_at) as created_at FROM measurements ORDER BY created_at DESC')
        measurements = []
        glucose_values = []
        
        for row in c.fetchall():
            value = float(row['value'])
            note = row['note']
            created_at = row['created_at']
            
            dt = datetime.strptime(created_at[:19], '%Y-%m-%d %H:%M:%S')
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M')
            
            pressure = ''
            if note and 'Давление:' in note:
                pressure_part = note.split('Давление:')[1].strip()
                numbers = re.findall(r'\\d+', pressure_part)
                if len(numbers) >= 2:
                    pressure = f"{numbers[0]}-{numbers[1]}"
            
            if len(measurements) < 30:
                measurements.append({
                    'date': date_str,
                    'time': time_str,
                    'value': value,
                    'pressure': pressure or '-'
                })
            
            glucose_values.append(value)
        
        conn.close()
        
        # График глюкозы
        glucose_chart_base64 = ""
        if measurements:
            chart_data = measurements[-20:] if len(measurements) > 20 else measurements
            dates_for_x = [f"{m['date'][-5:]}\\n{m['time']}" for m in chart_data]
            values_for_y = [m['value'] for m in chart_data]
            
            plt.figure(figsize=(14, 6))
            plt.plot(values_for_y, marker='o', linewidth=2, markersize=6, color='#2c3e50')
            plt.title('Динамика уровня глюкозы')
            plt.xlabel('Дата и время')
            plt.ylabel('Глюкоза (mmol/L)')
            plt.grid(True, alpha=0.3)
            plt.xticks(range(len(dates_for_x)), dates_for_x, rotation=45, ha='right')
            plt.axhspan(3.9, 5.5, alpha=0.1, color='green')
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
            plt.close()
            glucose_chart_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        # Статистика
        stats = {
            'total': len(glucose_values),
            'avg_glucose': round(sum(glucose_values) / len(glucose_values), 1) if glucose_values else 0,
            'min_glucose': min(glucose_values) if glucose_values else 0,
            'max_glucose': max(glucose_values) if glucose_values else 0,
        }
        
        return render_template('print_report.html',
                             measurements=measurements,
                             stats=stats,
                             glucose_chart_base64=glucose_chart_base64)
    except Exception as e:
        return f'<div style="padding: 40px;"><h1>Ошибка отчета</h1><p>{e}</p><a href="/">Главная</a></div>'

# ============ АДМИН: БЭКАПЫ ============
@app.route('/admin/simple_backup')
def simple_backup():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as count FROM measurements")
        count = c.fetchone()['count']
        
        # Дата последнего бэкапа
        c.execute("SELECT executed_at FROM backup_logs ORDER BY executed_at DESC LIMIT 1")
        last_backup = c.fetchone()
        last_backup_str = last_backup[0][:16] if last_backup else "Никогда"
        
        conn.close()
        
        return f'''
        <!DOCTYPE html>
        <html><head><title>💾 Бэкапы</title>
        <style>
        body {{font-family:Arial;padding:20px;background:#f8f9fa;}}
        .container {{max-width:600px;margin:0 auto;}}
        .card {{background:white;padding:25px;border-radius:12px;margin:20px 0;box-shadow:0 4px 6px rgba(0,0,0,0.1);}}
        .btn {{display:inline-block;padding:15px 25px;margin:10px;border-radius:8px;text-decoration:none;font-size:16px;font-weight:bold;}}
        .btn:hover {{transform:translateY(-2px);}}
        .btn-telegram {{background:#0088cc;color:white;}}
        .btn-restore {{background:#2ecc71;color:white;}}
        .btn-download {{background:#3498db;color:white;}}
        .btn-home {{background:#95a5a6;color:white;}}
        h1 {{color:#2c3e50;text-align:center;}}
        .stats {{background:#e8f4fd;padding:15px;border-radius:8px;text-align:center;}}
        </style></head>
        <body>
        <div class="container">
            <h1>💾 Бэкапы данных</h1>
            <div class="stats">
                <h2>📊 Записей: <strong>{count}</strong></h2>
                <p>✅ Авто-бэкап каждые <strong>7 дней</strong></p>
                <p>🕒 Последний: <strong>{last_backup_str}</strong></p>
            </div>
            <div class="card">
                <h3>🚀 Быстрые действия</h3>
                <a href="/admin/backup_to_telegram" class="btn btn-telegram">🤖 Бэкап в TG сейчас</a>
                <a href="/admin/upload_backup" class="btn btn-restore">📱 Загрузить с телефона</a>
                <a href="/admin/backup_list" class="btn btn-restore">📋 Бэкапы Telegram</a>
                <a href="/admin/merge_backups" class="btn" style="background:#9b59b6;color:white;">🔗 Объединить бэкапы</a>
                <a href="/admin/clean_old" class="btn" style="background:#e74c3c;color:white;">🗑️ Оставить 1000 новых</a>

            </div>
            <div class="card">
                <h3>📥 Скачать</h3>
                <a href="/admin/backup" class="btn btn-download">📄 База (.db)</a>
                <a href="/api/measurements" class="btn btn-download">📋 JSON</a>
            </div>
            <div style="text-align:center;">
                <a href="/" class="btn btn-home">🏠 Главная</a>
                <a href="/print_report" class="btn btn-download">📊 Отчет</a>
            </div>
        </div></body></html>
        '''
    except:
        return "Ошибка"

@app.route('/admin/backup_list')
def backup_list():
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?limit=50"
        response = requests.get(url, timeout=15)
        if not response.json().get('ok'):
            return '<h1>❌ Telegram недоступен</h1><a href="/admin/simple_backup">← Назад</a>'
        
        backups = []
        updates = response.json()['result']
        for update in reversed(updates):
            if 'message' in update and 'document' in update['message']:
                doc = update['message']['document']
                if doc['file_name'].endswith('.json'):
                    date_match = re.search(r'(\\d{4}-\\d{2}-\\d{2}|\\d{8}_\\d{6})', doc['file_name'])
                    date_str = date_match.group(1) if date_match else 'неизвестно'
                    backups.append({
                        'file_id': doc['file_id'],
                        'filename': doc['file_name'],
                        'date_str': date_str,
                        'caption': update['message'].get('caption', '')[:100]
                    })
        
        if not backups:
            return '''
            <div style="text-align:center;padding:40px;">
                <h1 style="color:#f39c12;">📭 Бэкапы не найдены</h1>
                <p>Сделайте сначала бэкап!</p>
                <a href="/admin/simple_backup" style="background:#3498db;color:white;padding:15px 30px;text-decoration:none;border-radius:8px;">🔙 Бэкапы</a>
            </div>
            '''
        
        html = '''
        <!DOCTYPE html><html><head><title>📋 Выбор бэкапа</title>
        <style>body{font-family:Arial;padding:20px;background:#f8f9fa;}
        .container{max-width:700px;margin:0 auto;}
        .card{background:white;padding:25px;border-radius:12px;margin:20px 0;box-shadow:0 4px 6px rgba(0,0,0,0.1);}
        h1{color:#2c3e50;text-align:center;}
        .backup-item{background:#f8f9fa;padding:20px;border-radius:8px;margin:15px 0;border-left:5px solid #3498db;cursor:pointer;transition:all 0.3s;}
        .backup-item:hover{background:#e8f4fd;transform:translateX(5px);}
        .filename{font-weight:bold;font-size:18px;color:#2c3e50;}
        .date{color:#7f8c8d;font-size:14px;}
        .caption{color:#34495e;margin-top:8px;}
        .btn{background:#2ecc71;color:white;padding:12px 25px;border:none;border-radius:6px;cursor:pointer;font-size:16px;text-decoration:none;display:inline-block;margin:5px;}
        .btn:hover{background:#27ae60;}
        .stats{background:#e8f4fd;padding:15px;border-radius:8px;text-align:center;margin-bottom:20px;}
        </style></head><body>
        <div class="container">
        <h1>📋 Выберите бэкап</h1>
        <div class="stats"><h3>Найдено: <strong>{}</strong></h3><p>🆕 Новые сверху</p></div>
        <div class="card">
        '''
        html = html.format(len(backups))
        
        for backup in backups[:20]:
            html += f'''
            <div class="backup-item">
                <div class="filename">{backup['filename']}</div>
                <div class="date">📅 {backup['date_str']}</div>
                <div class="caption">{backup['caption']}</div>
                <a href="/admin/restore_backup/{backup['file_id']}" class="btn">🔄 Восстановить</a>
            </div>
            '''
        
        html += '''
        </div><div class="card" style="text-align:center;">
            <p><strong>⚠️ Заменит все данные!</strong></p>
            <a href="/admin/simple_backup" class="btn">🔙 Бэкапы</a>
            <a href="/" class="btn" style="background:#95a5a6;">🏠 Главная</a>
        </div></div></body></html>
        '''
        return html
        
    except Exception as e:
        return f'<h1>❌ Ошибка</h1><pre>{e}</pre><a href="/admin/simple_backup">← Назад</a>'

@app.route('/admin/restore_backup/<file_id>')
def restore_specific_backup(file_id):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        response = requests.get(url, timeout=10)
        file_info = response.json()
        
        if not file_info['ok']:
            return '<h1>❌ Файл не найден</h1><a href="/admin/backup_list">← Выбрать другой</a>'
        
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info['result']['file_path']}"
        response = requests.get(file_url, timeout=15)
        data = json.loads(response.text)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM measurements")
        
        restored_count = 0
        for item in data:
            try:
                c.execute("INSERT INTO measurements (value, note, created_at) VALUES (?, ?, ?)",
                         (float(item['value']), item.get('note', ''), item.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))))
                restored_count += 1
            except:
                continue
        
        conn.commit()
        conn.close()
        
        filename = file_info['result']['file_path'].split('/')[-1]
        return f'''
        <!DOCTYPE html><html><head><title>✅ Восстановлено!</title></head>
        <body style="font-family:Arial;padding:40px;text-align:center;background:#f8f9fa;">
        <div style="background:white;padding:40px;border-radius:12px;max-width:500px;margin:0 auto;box-shadow:0 8px 20px rgba(0,0,0,0.1);">
            <h1 style="color:#27ae60;font-size:32px;">✅ Готово!</h1>
            <p style="font-size:22px;margin:20px 0;"><strong>{restored_count}</strong> записей</p>
            <p style="color:#7f8c8d;font-size:16px;">Из: <strong>{filename}</strong></p>
            <div style="margin:30px 0;">
                <a href="/print_report" style="background:#2ecc71;color:white;padding:18px 35px;text-decoration:none;border-radius:10px;font-size:18px;margin:10px;display:inline-block;">📊 Отчет</a>
                <a href="/" style="background:#3498db;color:white;padding:18px 35px;text-decoration:none;border-radius:10px;font-size:18px;margin:10px;display:inline-block;">➕ Добавить</a>
            </div>
            <a href="/admin/backup_list" style="background:#95a5a6;color:white;padding:12px 25px;text-decoration:none;border-radius:8px;font-size:16px;">🔄 Другой бэкап</a>
        </div></body></html>
        '''
    except Exception as e:
        return f'<h1>❌ Ошибка</h1><pre>{e}</pre><a href="/admin/backup_list">← Назад</a>'

@app.route('/admin/backup_to_telegram')
def backup_to_telegram():
    """Ручной запуск бэкапа"""
    try:
        perform_full_backup() # Используем общую функцию
        return '''
        <div style="text-align:center;padding:40px;">
            <h1 style="color:#27ae60;">✅ Бэкап отправлен!</h1>
            <p>Проверьте Telegram. Дата сохранена.</p>
            <a href="/admin/simple_backup" style="background:#3498db;color:white;padding:15px 30px;text-decoration:none;border-radius:8px;">🔄 Еще раз</a>
        </div>
        '''
    except Exception as e:
        return f'<h1>❌ Ошибка</h1><pre>{e}</pre>'

# ============ ЗАГРУЗКА БЭКАПА С ТЕЛЕФОНА ============
@app.route('/admin/upload_backup', methods=['GET', 'POST'])
def upload_backup():
    """📱 Загрузка файла с телефона"""
    if request.method == 'GET':
        return f'''
        <!DOCTYPE html>
        <html><head><title>📤 Загрузить бэкап</title>
        <style>body{{font-family:Arial;padding:30px;background:#f8f9fa;text-align:center;}}
        .card{{background:white;padding:30px;border-radius:15px;max-width:500px;margin:20px auto;box-shadow:0 8px 25px rgba(0,0,0,0.1);}}
        input[type=file]{{padding:20px;border:3px dashed #3498db;border-radius:10px;width:90%;margin:20px 0;}}
        .btn{{background:#2ecc71;color:white;padding:15px 30px;border:none;border-radius:10px;font-size:18px;cursor:pointer;margin:10px;display:inline-block;text-decoration:none;}}
        </style></head><body>
        <div class="card">
            <h1>📤 Загрузить с телефона</h1>
            <form method="post" enctype="multipart/form-data">
                <input type="file" name="backup_file" accept=".db,.json" required>
                <br><button type="submit" class="btn">🚀 Загрузить</button>
                <a href="/admin/simple_backup" class="btn" style="background:#95a5a6;">🔙 Бэкапы</a>
            </form>
            <div style="margin-top:30px;color:#7f8c8d;">
                <p>📄 .db = замена базы | 📋 .json = данные</p>
            </div>
        </div></body></html>'''
    
    if 'backup_file' not in request.files:
        return '❌ Нет файла', 400
    file = request.files['backup_file']
    if not file.filename:
        return '❌ Выберите файл', 400
    
    try:
        filename = file.filename.lower()
        if filename.endswith('.db'):
            file.save(DB_PATH)
            # При загрузке DB нужно проверить, есть ли там таблица логов
            init_db() 
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM measurements")
            count = c.fetchone()[0]
            conn.close()
            return f'<div style="text-align:center;padding:50px;"><h1 style="color:#27ae60;">✅ БАЗА ЗАГРУЖЕНА!</h1><p>📊 Записей: <strong>{count}</strong></p><a href="/print_report" class="btn">📊 Отчет</a><a href="/" class="btn" style="background:#3498db;">➕ Добавить</a></div>'
        elif filename.endswith('.json'):
            data = json.load(file)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM measurements")
            for item in data:
                c.execute("INSERT INTO measurements (value, note, created_at) VALUES (?, ?, ?)",
                         (item['value'], item.get('note', ''), item.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))))
            conn.commit()
            conn.close()
            return f'<div style="text-align:center;padding:50px;"><h1 style="color:#27ae60;">✅ ДАННЫЕ ВОССТАНОВЛЕНЫ!</h1><p>📊 Загружено: <strong>{len(data)}</strong></p><a href="/print_report" class="btn">📊 Отчет</a></div>'
    except Exception as e:
        return f'❌ Ошибка: {e}<br><a href="/admin/upload_backup">← Назад</a>'

@app.route('/admin/merge_backups', methods=['GET', 'POST'])
def merge_backups():
    """🔗 ОБЪЕДИНЕНИЕ МНОЖЕСТВЕННЫХ БЭКАПОВ"""
    if request.method == 'GET':
        return f'''
        <!DOCTYPE html>
        <html><head><title>🔗 Объединить бэкапы</title>
        <style>body{{font-family:Arial;padding:30px;background:#f8f9fa;}}
        .card{{background:white;padding:30px;border-radius:15px;max-width:500px;margin:20px auto;box-shadow:0 8px 25px rgba(0,0,0,0.1);}}
        input[type=file]{{padding:20px;border:3px dashed #3498db;border-radius:10px;width:90%;margin:20px 0;}}
        .btn{{background:#9b59b6;color:white;padding:15px 30px;border:none;border-radius:10px;font-size:18px;cursor:pointer;margin:10px;display:inline-block;text-decoration:none;}}
        </style></head><body>
        <div class="card">
            <h1>🔗 Объединить бэкапы</h1>
            <p>📱 Выберите несколько .json файлов:</p>
            <form method="post" enctype="multipart/form-data">
                <input type="file" name="backup_files" accept=".json" multiple required>
                <br><button type="submit" class="btn">🔗 ОБЪЕДИНИТЬ</button>
                <a href="/admin/simple_backup" class="btn" style="background:#95a5a6;">🔙 Бэкапы</a>
            </form>
            <div style="margin-top:30px;color:#7f8c8d;">
                <p>📊 Уникальные записи | Дубликаты удаляются | Сортировка по дате</p>
            </div>
        </div></body></html>'''
    
    if 'backup_files' not in request.files:
        return '❌ Выберите файлы', 400
    
    files = request.files.getlist('backup_files')
    all_data = []
    
    # Собираем ВСЕ данные из файлов
    for file in files:
        if file.filename.endswith('.json'):
            data = json.load(file)
            all_data.extend(data)
    
    if not all_data:
        return '❌ Нет данных в файлах', 400
    
    # УДАЛЯЕМ ДУБЛИКАТЫ (по value + created_at)
    unique_data = []
    seen = set()
    for item in all_data:
        key = f"{item['value']:.1f}_{item.get('created_at', '')}"
        if key not in seen:
            seen.add(key)
            unique_data.append(item)
    
    # Сортируем по дате
    unique_data.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    # Сохраняем в базу
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM measurements")
    
    for item in unique_data:
        c.execute("INSERT INTO measurements (value, note, created_at) VALUES (?, ?, ?)",
                 (item['value'], item.get('note', ''), item.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))))
    
    conn.commit()
    conn.close()
    
    return f'''
    <div style="text-align:center;padding:50px;">
        <h1 style="color:#9b59b6;font-size:36px;">✅ БЭКАПЫ ОБЪЕДИНЕНЫ!</h1>
        <p style="font-size:24px;">
            📊 Загружено: <strong>{len(unique_data)}</strong> уникальных записей<br>
            🗑️  Удалено дублей: <strong>{len(all_data) - len(unique_data)}</strong>
        </p>
        <a href="/print_report" class="btn">📊 Отчет</a>
        <a href="/" class="btn" style="background:#3498db;">➕ Добавить</a>
    </div>'''

@app.route('/admin/clean_old')
def clean_old_records():
    """🗑️ ОСТАВИТЬ ТОЛЬКО ПОСЛЕДНИЕ 1000 записей"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Удаляем всё КРОМЕ последних 1000
    c.execute("""
        DELETE FROM measurements 
        WHERE id NOT IN (
            SELECT id FROM measurements 
            ORDER BY created_at DESC 
            LIMIT 1000
        )
    """)
    
    deleted = c.rowcount
    c.execute("SELECT COUNT(*) FROM measurements")
    remains = c.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    return f'''
    <div style="text-align:center;padding:50px;">
        <h1 style="color:#e74c3c;">🗑️ ОЧИСТКА ЗАВЕРШЕНА</h1>
        <p style="font-size:24px;">
            ✅ Осталось записей: <strong>{remains}</strong><br>
            🗑️  Удалено старых: <strong>{deleted}</strong>
        </p>
        <a href="/print_report" class="btn" style="background:#2ecc71;">📊 Проверить отчет</a>
        <a href="/admin/simple_backup" class="btn">🔙 Бэкапы</a>
    </div>'''

@app.route('/admin/backup')
def backup_database():
    if not os.path.exists(DB_PATH):
        return "База не найдена", 404
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(DB_PATH, as_attachment=True, download_name=f'glucose_backup_{timestamp}.db')

# ============ ЗАПУСК ============
if __name__ == '__main__':
    init_db() # Создаст backup_logs, если нет
    start_smart_scheduler() # Запустит проверку
    
    print("=" * 60)
    print("🚀 GLIKOSA Tracker")
    print("✅ База: не обнуляется")
    print("✅ Бэкап: раз в 7 дней (устойчив к перезагрузкам)")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)

