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

app = Flask(__name__)
app.template_folder = '.'

# Используем SQLite в постоянной папке
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'glucose.db')
print(f"✅ Используем БД: {DB_PATH}")

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
    # Включаем поддержку словарей
    conn.row_factory = sqlite3.Row
    return conn

# Инициализация при старте
init_db()

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
            "python_version": os.sys.version
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
            </style>
        </head>
        <body>
            <h1 class="success">✅ Тестовые данные добавлены!</h1>
            
            <h3>Добавленные измерения:</h3>
            <div class="data-item">📅 <strong>29 ноября 10:00</strong> - Глюкоза: 6.4 mmol/L, Давление: 130-140</div>
            <div class="data-item">📅 <strong>30 ноября 10:00</strong> - Глюкоза: 6.9 mmol/L, Давление: 130-140</div>
            <div class="data-item">📅 <strong>1 декабря 10:00</strong> - Глюкоза: 6.8 mmol/L, Давление: 130-140</div>
            
            <div style="margin-top: 30px;">
                <a href="/print_report" class="button">📊 Посмотреть отчет с графиками</a>
                <a href="/" class="button" style="background: #95a5a6;">➕ Добавить новые измерения</a>
            </div>
            
            <p style="margin-top: 20px; color: #27ae60; font-weight: bold;">
                ✅ Данные сохраняются в SQLite (файл: glucose.db)
            </p>
        </body>
        </html>
        '''
        
    except Exception as e:
        return f'''
        <h1 style="color: #e74c3c;">❌ Ошибка</h1>
        <p>{str(e)}</p>
        <a href="/">На главную</a>
        '''

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
            "first_record": result['first_record'] if result['first_record'] else "Нет данных"
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

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 GLIKOSA Tracker запущен!")
    print(f"📊 База данных: SQLite")
    print(f"📁 Файл базы: {DB_PATH}")
    print("=" * 60)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
