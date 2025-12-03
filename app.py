from flask import Flask, render_template, request, jsonify, send_file
import os
from datetime import datetime
import io
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import base64
import re
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.template_folder = '.'

# Ваша строка подключения PostgreSQL
DATABASE_URL = "postgresql://glikosa_user:o88hNjd91vCsLFcpbp9ZeAWSPo5syzfI@dpg-d4o9onidbo4c73et3b40-a/glikosa_bd"

# Подключение к PostgreSQL
def get_db_connection():
    """Получить подключение к базе данных"""
    try:
        # Используем вашу строку подключения
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor
        )
        return conn, 'postgres'
    except Exception as e:
        print(f"⚠️ Ошибка подключения к PostgreSQL: {e}")
        print("🔄 Пробуем SQLite как запасной вариант...")
        
        try:
            import sqlite3
            conn = sqlite3.connect('glucose.db')
            return conn, 'sqlite'
        except:
            raise Exception(f"Не удалось подключиться ни к одной БД: {e}")

def init_db():
    """Инициализация базы данных"""
    try:
        conn, db_type = get_db_connection()
        cur = conn.cursor()
        
        if db_type == 'postgres':
            # Создаем таблицу для PostgreSQL
            cur.execute('''
                CREATE TABLE IF NOT EXISTS measurements (
                    id SERIAL PRIMARY KEY,
                    value DECIMAL NOT NULL,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("✅ Таблица measurements создана/проверена в PostgreSQL")
        else:
            # Для SQLite
            cur.execute('''
                CREATE TABLE IF NOT EXISTS measurements
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 value REAL NOT NULL,
                 note TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
            ''')
            print("✅ Таблица measurements создана/проверена в SQLite")
        
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        return False

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

# API для работы с данными
@app.route('/api/measurement', methods=['POST'])
def add_measurement():
    try:
        data = request.get_json()
        
        if not data or 'value' not in data:
            return jsonify({'error': 'Нет данных', 'success': False}), 400
            
        value = float(data['value'])
        note = data.get('note', '')
        
        conn, db_type = get_db_connection()
        cur = conn.cursor()
        
        if db_type == 'postgres':
            cur.execute(
                'INSERT INTO measurements (value, note) VALUES (%s, %s) RETURNING id',
                (value, note)
            )
            inserted_id = cur.fetchone()['id']
        else:
            cur.execute(
                'INSERT INTO measurements (value, note) VALUES (?, ?)',
                (value, note)
            )
            inserted_id = cur.lastrowid
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'message': '✅ Данные сохранены в PostgreSQL!',
            'success': True,
            'id': inserted_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/measurements')
def get_measurements():
    try:
        conn, db_type = get_db_connection()
        cur = conn.cursor()
        
        if db_type == 'postgres':
            cur.execute('''
                SELECT id, value, note, 
                       to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at 
                FROM measurements 
                ORDER BY created_at DESC
            ''')
            rows = cur.fetchall()
            measurements = []
            for row in rows:
                measurements.append({
                    'id': row['id'],
                    'value': float(row['value']),
                    'note': row['note'] or '',
                    'created_at': row['created_at'],
                    'date': row['created_at'][:10],
                    'time': row['created_at'][11:16]
                })
        else:
            cur.execute('''
                SELECT id, value, note, 
                       datetime(created_at) as created_at 
                FROM measurements 
                ORDER BY created_at DESC
            ''')
            rows = cur.fetchall()
            measurements = []
            for row in rows:
                measurements.append({
                    'id': row[0],
                    'value': float(row[1]),
                    'note': row[2] or '',
                    'created_at': row[3],
                    'date': row[3][:10],
                    'time': row[3][11:16]
                })
        
        cur.close()
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
        conn, db_type = get_db_connection()
        cur = conn.cursor()
        
        if db_type == 'postgres':
            cur.execute('''
                SELECT 
                    value, 
                    COALESCE(note, '') as note,
                    to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at
                FROM measurements 
                ORDER BY created_at DESC
            ''')
            rows = cur.fetchall()
        else:
            cur.execute('''
                SELECT 
                    value, 
                    COALESCE(note, '') as note,
                    created_at
                FROM measurements 
                ORDER BY created_at DESC
            ''')
            rows = cur.fetchall()
        
        measurements_for_table = []
        measurements_for_chart = []
        glucose_values = []
        
        for row in rows:
            if db_type == 'postgres':
                value = float(row['value'])
                note = row['note']
                created_at = row['created_at']
            else:
                value = float(row[0])
                note = row[1]
                created_at = row[2]
            
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
        
        cur.close()
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

# Тестовые данные для PostgreSQL
@app.route('/admin/setup_test_data')
def setup_test_data():
    """Добавить тестовые данные"""
    try:
        conn, db_type = get_db_connection()
        cur = conn.cursor()
        
        # Очищаем старые данные
        cur.execute("DELETE FROM measurements")
        
        # Тестовые данные
        test_data = [
            (6.4, 'Давление: 130-140', '2024-11-29 10:00:00'),
            (6.9, 'Давление: 130-140', '2024-11-30 10:00:00'),
            (6.8, 'Давление: 130-140', '2024-12-01 10:00:00'),
        ]
        
        if db_type == 'postgres':
            for data in test_data:
                cur.execute(
                    "INSERT INTO measurements (value, note, created_at) VALUES (%s, %s, %s)",
                    data
                )
        else:
            cur.executemany(
                "INSERT INTO measurements (value, note, created_at) VALUES (?, ?, ?)", 
                test_data
            )
        
        conn.commit()
        cur.close()
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
            <h1 class="success">✅ Данные добавлены в PostgreSQL!</h1>
            
            <h3>Добавленные измерения:</h3>
            <div class="data-item">📅 <strong>29 ноября 10:00</strong> - Глюкоза: 6.4 mmol/L, Давление: 130-140</div>
            <div class="data-item">📅 <strong>30 ноября 10:00</strong> - Глюкоза: 6.9 mmol/L, Давление: 130-140</div>
            <div class="data-item">📅 <strong>1 декабря 10:00</strong> - Глюкоза: 6.8 mmol/L, Давление: 130-140</div>
            
            <div style="margin-top: 30px;">
                <a href="/print_report" class="button">📊 Посмотреть отчет с графиками</a>
                <a href="/" class="button" style="background: #95a5a6;">➕ Добавить новые измерения</a>
            </div>
            
            <p style="margin-top: 20px; color: #27ae60; font-weight: bold;">
                ✅ Теперь данные сохраняются в PostgreSQL и не будут удаляться!
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

@app.route('/health')
def health_check():
    try:
        conn, db_type = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as count FROM measurements")
        result = cur.fetchone()
        
        count = result['count'] if db_type == 'postgres' else result[0]
        
        cur.close()
        conn.close()
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": "PostgreSQL",
            "database_url": "postgresql://glikosa_user:*****@dpg-d4o9onidbo4c73et3b40-a/glikosa_bd",
            "records_count": count
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        })

@app.route('/admin/db_status')
def db_status():
    """Проверка статуса базы данных"""
    try:
        conn, db_type = get_db_connection()
        cur = conn.cursor()
        
        # Проверяем таблицу
        if db_type == 'postgres':
            cur.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM measurements) as total_records,
                    (SELECT MAX(created_at) FROM measurements) as last_record,
                    (SELECT MIN(created_at) FROM measurements) as first_record,
                    version() as postgres_version
            """)
            result = cur.fetchone()
            
            status = {
                "database_type": "PostgreSQL",
                "connected": True,
                "total_records": result['total_records'],
                "last_record": str(result['last_record']) if result['last_record'] else "Нет данных",
                "first_record": str(result['first_record']) if result['first_record'] else "Нет данных",
                "postgres_version": result['postgres_version'],
                "connection_string": DATABASE_URL.replace('o88hNjd91vCsLFcpbp9ZeAWSPo5syzfI', '*****')
            }
        else:
            cur.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM measurements) as total_records,
                    (SELECT MAX(created_at) FROM measurements) as last_record,
                    (SELECT MIN(created_at) FROM measurements) as first_record
            """)
            result = cur.fetchone()
            
            status = {
                "database_type": "SQLite",
                "connected": True,
                "total_records": result[0],
                "last_record": result[1] if result[1] else "Нет данных",
                "first_record": result[2] if result[2] else "Нет данных"
            }
        
        cur.close()
        conn.close()
        
        return jsonify(status)
        
    except Exception as e:
        return jsonify({
            "database_type": "Ошибка",
            "connected": False,
            "error": str(e)
        })

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 GLIKOSA Tracker запущен!")
    print(f"📊 База данных: PostgreSQL")
    print(f"🔗 Подключение: {DATABASE_URL.replace('o88hNjd91vCsLFcpbp9ZeAWSPo5syzfI', '*****')}")
    print("=" * 60)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
