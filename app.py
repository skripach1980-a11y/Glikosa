from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import os
from datetime import datetime, timedelta
import io
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import base64
import re

app = Flask(__name__)
app.template_folder = '.'

# БАЗА В /tmp - СОХРАНЯЕТСЯ 30 ДНЕЙ
DB_PATH = '/tmp/glucose.db'
print(f"✅ Используем БД: {DB_PATH}")

def init_db():
    """Создаем базу если её нет"""
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

def ensure_db():
    """Проверяем базу, создаем если нет"""
    try:
        # Если файла нет - создаем
        if not os.path.exists(DB_PATH):
            print(f"🔄 Файл БД не найден, создаем: {DB_PATH}")
            return init_db()
        
        # Если файл есть - проверяем структуру
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Проверяем таблицу
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='measurements'")
        result = c.fetchone()
        
        if not result:
            print("🔄 Таблица measurements не найдена, создаем...")
            conn.close()
            return init_db()
        
        # Проверяем есть ли данные
        c.execute("SELECT COUNT(*) FROM measurements")
        count = c.fetchone()[0]
        
        conn.close()
        print(f"✅ БД проверена: {DB_PATH}, записей: {count}")
        return True
    except Exception as e:
        print(f"❌ Ошибка проверки БД: {e}")
        return init_db()

# Инициализация БД при запуске
ensure_db()

# СТУЧАЛКА для uptimerobot
@app.route('/health')
def health_check():
    try:
        conn = sqlite3.connect(DB_PATH)
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
            "records_count": count
        })
    except:
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "glucose_tracker",
            "db_path": DB_PATH,
            "db_exists": os.path.exists(DB_PATH),
            "records_count": 0
        })

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

# ФУНКЦИЯ ДЛЯ СОЗДАНИЯ ГРАФИКА ДАВЛЕНИЯ
def create_pressure_chart(measurements):
    """Создать график артериального давления"""
    try:
        # Извлекаем данные давления
        systolic_list = []  # Верхнее
        diastolic_list = [] # Нижнее
        dates_list = []
        
        for m in measurements:
            pressure = m.get('pressure', '')
            if pressure and pressure != '-':
                # Ищем числа в строке давления
                numbers = re.findall(r'\d+', str(pressure))
                if len(numbers) >= 2:
                    systolic = int(numbers[0])  # Первое число - верхнее
                    diastolic = int(numbers[1]) # Второе число - нижнее
                    
                    systolic_list.append(systolic)
                    diastolic_list.append(diastolic)
                    
                    # Форматируем дату
                    date_obj = datetime.strptime(m['date'], '%Y-%m-%d')
                    date_str = date_obj.strftime('%d.%m')
                    dates_list.append(f"{date_str}\n{m['time']}")
        
        # Нужно минимум 2 точки для графика
        if len(systolic_list) < 2:
            return None
        
        # Создаем график
        plt.figure(figsize=(14, 6))
        
        # Индексы для оси X
        x_indices = range(len(systolic_list))
        
        # Линия верхнего давления
        plt.plot(x_indices, systolic_list, 'ro-', 
                linewidth=2, markersize=8, label='Верхнее (систолическое)')
        
        # Линия нижнего давления  
        plt.plot(x_indices, diastolic_list, 'bs-',
                linewidth=2, markersize=8, label='Нижнее (диастолическое)')
        
        # Зоны нормального давления
        plt.axhspan(110, 130, alpha=0.1, color='green', label='Норма верхнего')
        plt.axhspan(70, 85, alpha=0.1, color='lightblue', label='Норма нижнего')
        
        # Настройки графика
        plt.title('Динамика артериального давления', fontsize=16, fontweight='bold', pad=20)
        plt.xlabel('Дата и время измерения →', fontsize=12, labelpad=10)
        plt.ylabel('Давление (мм рт. ст.)', fontsize=12, labelpad=10)
        plt.grid(True, alpha=0.3, linestyle='--')
        plt.legend(loc='upper left', fontsize=10)
        
        # Подписи на оси X
        if dates_list:
            plt.xticks(x_indices, dates_list, rotation=45, fontsize=10, ha='right')
        
        plt.tight_layout()
        
        # Конвертируем в байты
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
        plt.close()
        buf.seek(0)
        return buf.getvalue()
        
    except Exception as e:
        print(f"⚠️ Ошибка создания графика давления: {e}")
        return None

# ГЛАВНАЯ ФУНКЦИЯ - ОТЧЕТ С ДВУМЯ ГРАФИКАМИ
@app.route('/print_report')
def print_report():
    """Генерация печатного отчета с графиками глюкозы и давления"""
    try:
        ensure_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Получаем все данные
        c.execute('''
            SELECT 
                value, 
                COALESCE(note, '') as note,
                created_at
            FROM measurements 
            ORDER BY created_at DESC
        ''')
        
        measurements_for_table = []  # Для таблицы
        measurements_for_chart = []  # Для графиков
        glucose_values = []
        
        for row in c.fetchall():
            value, note, created_at = row
            
            # Парсим дату и время
            if created_at:
                try:
                    dt = datetime.strptime(created_at[:19], '%Y-%m-%d %H:%M:%S')
                    date_str = dt.strftime('%Y-%m-%d')
                    time_str = dt.strftime('%H:%M')
                    timestamp = dt
                except:
                    date_str = datetime.now().strftime('%Y-%m-%d')
                    time_str = datetime.now().strftime('%H:%M')
                    timestamp = datetime.now()
            else:
                date_str = datetime.now().strftime('%Y-%m-%d')
                time_str = datetime.now().strftime('%H:%M')
                timestamp = datetime.now()
            
            # Извлекаем давление из заметки
            pressure = ''
            if note and 'Давление:' in note:
                try:
                    pressure_part = note.split('Давление:')[1].strip()
                    # Ищем числа в формате 130-140 или 130/140
                    numbers = re.findall(r'\d+', pressure_part)
                    if numbers:
                        if len(numbers) >= 2:
                            pressure = f"{numbers[0]}-{numbers[1]}"
                        else:
                            pressure = numbers[0]
                except:
                    pass
            
            # Для таблицы (первые 30 записей)
            if len(measurements_for_table) < 30:
                measurements_for_table.append({
                    'date': date_str,
                    'time': time_str,
                    'value': value,
                    'pressure': pressure if pressure else '-'
                })
            
            # Для графиков
            measurements_for_chart.append({
                'date': date_str,
                'time': time_str,
                'value': value,
                'pressure': pressure,
                'timestamp': timestamp
            })
            glucose_values.append(value)
        
        conn.close()
        
        # СОРТИРУЕМ для графиков: старые → новые
        measurements_for_chart.sort(key=lambda x: x['timestamp'])
        
        # ГРАФИК ГЛЮКОЗЫ
        glucose_chart_base64 = ""
        if measurements_for_chart:
            try:
                # Берем данные для графика
                chart_data = measurements_for_chart[-20:] if len(measurements_for_chart) > 20 else measurements_for_chart
                
                # Подготовка данных
                dates_for_x = []
                values_for_y = []
                
                for m in chart_data:
                    date_obj = datetime.strptime(m['date'], '%Y-%m-%d')
                    date_str = date_obj.strftime('%d.%m')
                    dates_for_x.append(f"{date_str}\n{m['time']}")
                    values_for_y.append(m['value'])
                
                # Создаем график глюкозы
                plt.figure(figsize=(14, 6))
                
                # Основная линия
                plt.plot(values_for_y, marker='o', linewidth=2, markersize=6, 
                        color='#2c3e50', markerfacecolor='white', markeredgewidth=2)
                
                # Настройки
                plt.title('Динамика уровня глюкозы', fontsize=16, fontweight='bold', pad=20)
                plt.xlabel('Дата и время измерения →', fontsize=12, labelpad=10)
                plt.ylabel('Глюкоза (mmol/L)', fontsize=12, labelpad=10)
                plt.grid(True, alpha=0.3, linestyle='--')
                
                # Подписи на оси X
                if len(dates_for_x) > 0:
                    plt.xticks(range(len(dates_for_x)), dates_for_x, rotation=45, fontsize=10, ha='right')
                
                # Целевая зона
                plt.axhspan(3.9, 5.5, alpha=0.1, color='green')
                
                plt.tight_layout()
                
                # Конвертация
                buf = io.BytesIO()
                plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
                plt.close()
                buf.seek(0)
                glucose_chart_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                
                print(f"✅ График глюкозы создан, точек: {len(values_for_y)}")
                
            except Exception as chart_error:
                print(f"⚠️ Ошибка создания графика глюкозы: {chart_error}")
                glucose_chart_base64 = ""
        
        # ГРАФИК ДАВЛЕНИЯ
        pressure_chart_base64 = ""
        if measurements_for_chart:
            pressure_chart = create_pressure_chart(measurements_for_chart)
            if pressure_chart:
                pressure_chart_base64 = base64.b64encode(pressure_chart).decode('utf-8')
                print(f"✅ График давления создан")
        
        # СТАТИСТИКА
        if glucose_values:
            stats = {
                'total': len(glucose_values),
                'avg_glucose': sum(glucose_values) / len(glucose_values),
                'min_glucose': min(glucose_values),
                'max_glucose': max(glucose_values),
            }
            
            # Даты периода
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
        
        # ВОЗВРАЩАЕМ ОТЧЕТ С ДВУМЯ ГРАФИКАМИ
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

# ФУНКЦИЯ ДЛЯ ДОБАВЛЕНИЯ ТЕСТОВЫХ ДАННЫХ
@app.route('/admin/setup_test_data')
def setup_test_data():
    """Добавить архивные данные за ноябрь-декабрь"""
    try:
        import sqlite3
        
        print(f"🔄 Добавление тестовых данных в {DB_PATH}")
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Очищаем старые данные
        c.execute("DELETE FROM measurements")
        
        # Твои архивные данные (3 точки)
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
        
        print("✅ Тестовые данные добавлены")
        
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
            <h1 class="success">✅ Архивные данные добавлены!</h1>
            
            <h3>Добавленные измерения:</h3>
            <div class="data-item">📅 <strong>29 ноября 10:00</strong> - Глюкоза: 6.4 mmol/L, Давление: 130-140</div>
            <div class="data-item">📅 <strong>30 ноября 10:00</strong> - Глюкоза: 6.9 mmol/L, Давление: 130-140</div>
            <div class="data-item">📅 <strong>1 декабря 10:00</strong> - Глюкоза: 6.8 mmol/L, Давление: 130-140</div>
            
            <div style="margin-top: 30px;">
                <a href="/print_report" class="button">📊 Посмотреть отчет с графиками</a>
                <a href="/" class="button" style="background: #95a5a6;">➕ Добавить новые измерения</a>
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

# ОСТАЛЬНЫЕ ФУНКЦИИ (без изменений)
@app.route('/api/measurement', methods=['POST'])
def add_measurement():
    try:
        ensure_db()
        data = request.get_json()
        
        if not data or 'value' not in data:
            return jsonify({'error': 'Нет данных', 'success': False}), 400
            
        value = float(data['value'])
        note = data.get('note', '')
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO measurements (value, note) VALUES (?, ?)', 
                 (value, note))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Данные сохранены!', 'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/measurements')
def get_measurements():
    try:
        ensure_db()
        conn = sqlite3.connect(DB_PATH)
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
                'id': row[0],
                'value': row[1],
                'note': row[2] or '',
                'created_at': row[3],
                'date': row[3][:10],
                'time': row[3][11:16]
            })
        
        conn.close()
        return jsonify(measurements)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Glucose Tracker запущен")
    print(f"📁 База данных: {DB_PATH}")
    print(f"📊 Путь существует: {os.path.exists(DB_PATH)}")
    print("=" * 50)
    
    ensure_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
