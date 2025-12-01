from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import os
from datetime import datetime, timedelta
import io
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import base64

app = Flask(__name__)
app.template_folder = '.'

# УМНАЯ ПРОВЕРКА ПУТИ ДЛЯ БАЗЫ
def get_db_path():
    """Выбираем лучший путь для базы данных"""
    possible_paths = [
        '/tmp/glucose.db',           # Сохраняется 30 дней на Render
        '/var/tmp/glucose.db',       # Альтернативный tmp
        'glucose_persistent.db',     # Файл в приложении
        'glucose.db',                # Стандартный путь
    ]
    
    for path in possible_paths:
        try:
            # Проверяем можно ли писать в директорию
            dir_path = os.path.dirname(path) if os.path.dirname(path) else '.'
            if os.path.exists(dir_path) and os.access(dir_path, os.W_OK):
                print(f"✅ Используем путь для БД: {path}")
                return path
        except:
            continue
    
    # Если ничего не подошло - используем последний вариант
    print(f"⚠️  Используем fallback путь: glucose.db")
    return 'glucose.db'

DB_PATH = get_db_path()

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
# ДОБАВЬ ЭТУ ФУНКЦИЮ в app.py после ensure_db()
@app.route('/admin/setup_test_data')
def setup_test_data():
    """Установка тестовых данных через браузер"""
    try:
        import sqlite3
        from datetime import datetime
        
        print(f"🔄 Установка тестовых данных в {DB_PATH}")
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Проверяем есть ли данные
        c.execute("SELECT COUNT(*) FROM measurements")
        count_before = c.fetchone()[0]
        
        # Удаляем старые если есть
        if count_before > 0:
            c.execute("DELETE FROM measurements")
            print(f"🧹 Удалено {count_before} старых записей")
        
        # Добавляем твои данные
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
        
        # Проверяем
        c.execute("SELECT COUNT(*) FROM measurements")
        count_after = c.fetchone()[0]
        
        # Получаем добавленные данные
        c.execute("""
            SELECT date(created_at) as date, time(created_at) as time, value, note 
            FROM measurements ORDER BY created_at
        """)
        
        added_data = []
        for row in c.fetchall():
            added_data.append({
                'date': row[0],
                'time': row[1], 
                'value': row[2],
                'note': row[3]
            })
        
        conn.close()
        
        print(f"✅ Добавлено {count_after} записей")
        
        # Формируем HTML ответ
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Данные установлены</title>
            <style>
                body {{ font-family: Arial; padding: 20px; }}
                .success {{ color: green; font-weight: bold; }}
                table {{ border-collapse: collapse; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; }}
                th {{ background: #f5f5f5; }}
            </style>
        </head>
        <body>
            <h1 class="success">✅ Тестовые данные установлены!</h1>
            <p>Было записей: {count_before}</p>
            <p>Стало записей: {count_after}</p>
            
            <h2>Добавленные измерения:</h2>
            <table>
                <tr><th>Дата</th><th>Время</th><th>Глюкоза</th><th>Примечание</th></tr>
        """
        
        for data in added_data:
            html += f"""
                <tr>
                    <td>{data['date']}</td>
                    <td>{data['time']}</td>
                    <td>{data['value']} mmol/L</td>
                    <td>{data['note']}</td>
                </tr>
            """
        
        html += f"""
            </table>
            
            <div style="margin-top: 30px;">
                <a href="/print_report" style="background: #007cba; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                    📊 Посмотреть отчет
                </a>
                <a href="/admin/db_info" style="margin-left: 10px; padding: 10px 20px; border: 1px solid #ccc; text-decoration: none; border-radius: 5px;">
                    📋 Информация о БД
                </a>
            </div>
            
            <p style="margin-top: 30px; color: #666; font-size: 12px;">
                Путь к БД: {DB_PATH}<br>
                Время выполнения: {datetime.now().strftime('%H:%M:%S')}
            </p>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        error_html = f"""
        <h1 style="color: red;">❌ Ошибка установки данных</h1>
        <p>{str(e)}</p>
        <p>Путь к БД: {DB_PATH}</p>
        <p>Файл существует: {'Да' if os.path.exists(DB_PATH) else 'Нет'}</p>
        <a href="/">На главную</a>
        """
        return error_html
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

# ОСНОВНАЯ ФУНКЦИЯ - ГЕНЕРАЦИЯ ОТЧЕТА
@app.route('/print_report')
def print_report():
    """Генерация печатного отчета с графиком"""
    try:
        ensure_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Простой и надежный запрос
        c.execute('''
            SELECT 
                value, 
                COALESCE(note, '') as note,
                created_at
            FROM measurements 
            ORDER BY created_at DESC
        ''')
        
        measurements_for_table = []  # Для таблицы (первые 30)
        measurements_for_chart = []  # Для графика (все, отсортированные)
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
                    import re
                    numbers = re.findall(r'\d+', pressure_part)
                    if numbers:
                        pressure = '-'.join(numbers[:2]) if len(numbers) >= 2 else numbers[0]
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
            
            # Для графика
            measurements_for_chart.append({
                'date': date_str,
                'time': time_str,
                'value': value,
                'timestamp': timestamp
            })
            glucose_values.append(value)
        
        conn.close()
        
        # СОРТИРУЕМ для графика: старые → новые
        measurements_for_chart.sort(key=lambda x: x['timestamp'])
        
        # ГЕНЕРАЦИЯ ГРАФИКА
        chart_base64 = ""
        if measurements_for_chart:
            try:
                # Берем данные для графика (не более 20 точек для читаемости)
                chart_data = measurements_for_chart[-20:] if len(measurements_for_chart) > 20 else measurements_for_chart
                
                # Подготовка данных
                dates_for_x = []
                values_for_y = []
                
                for m in chart_data:
                    # Формат: "01.12\n14:30"
                    date_obj = datetime.strptime(m['date'], '%Y-%m-%d')
                    date_str = date_obj.strftime('%d.%m')
                    dates_for_x.append(f"{date_str}\n{m['time']}")
                    values_for_y.append(m['value'])
                
                # Создаем график
                plt.figure(figsize=(14, 6))
                
                # Основная линия
                plt.plot(values_for_y, marker='o', linewidth=2, markersize=6, 
                        color='#2c3e50', markerfacecolor='white', markeredgewidth=2)
                
                # Настройки графика
                plt.title('Динамика уровня глюкозы', fontsize=16, fontweight='bold', pad=20)
                plt.xlabel('Дата и время измерения →', fontsize=12, labelpad=10)
                plt.ylabel('Глюкоза (mmol/L)', fontsize=12, labelpad=10)
                plt.grid(True, alpha=0.3, linestyle='--')
                
                # Подписи на оси X
                if len(dates_for_x) > 0:
                    plt.xticks(range(len(dates_for_x)), dates_for_x, rotation=45, fontsize=10, ha='right')
                
                # Целевая зона (норма глюкозы)
                plt.axhspan(3.9, 5.5, alpha=0.1, color='green')
                
                plt.tight_layout()
                
                # Конвертация в base64
                buf = io.BytesIO()
                plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
                plt.close()
                buf.seek(0)
                chart_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                
                print(f"✅ График создан, точек: {len(values_for_y)}")
                
            except Exception as chart_error:
                print(f"⚠️  Ошибка создания графика: {chart_error}")
                chart_base64 = ""
        
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
        
        # ВОЗВРАЩАЕМ ОТЧЕТ
        return render_template('print_report.html',
                             measurements=measurements_for_table,
                             stats=stats,
                             start_date=start_date,
                             end_date=end_date,
                             chart_base64=chart_base64)
        
    except Exception as e:
        # Упрощенное сообщение об ошибке
        error_msg = str(e)[:200]
        print(f"❌ Ошибка в print_report: {error_msg}")
        
        return f'''
        <div style="padding: 20px; font-family: Arial;">
            <h2>📊 Отчет по глюкозе</h2>
            <p>База данных пуста или произошла ошибка.</p>
            <p><a href="/">Добавить измерения</a></p>
            <p style="color: #666; font-size: 12px;">Техническая информация: {error_msg}</p>
        </div>
        '''

# АПИ ДЛЯ ДОБАВЛЕНИЯ ИЗМЕРЕНИЙ
@app.route('/api/measurement', methods=['POST'])
def add_measurement():
    """Добавление нового измерения"""
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
        
        # Получаем ID новой записи
        new_id = c.lastrowid
        conn.close()
        
        print(f"✅ Измерение добавлено: ID={new_id}, value={value}")
        
        return jsonify({
            'message': 'Данные сохранены!', 
            'success': True,
            'id': new_id
        })
        
    except Exception as e:
        print(f"❌ Ошибка добавления измерения: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

# АПИ ДЛЯ ПОЛУЧЕНИЯ ВСЕХ ИЗМЕРЕНИЙ
@app.route('/api/measurements')
def get_measurements():
    """Получение всех измерений"""
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
        print(f"❌ Ошибка получения измерений: {e}")
        return jsonify({'error': str(e)}), 500

# АПИ ДЛЯ СКАЧИВАНИЯ ОТЧЕТА
@app.route('/generate_report')
def generate_report():
    """Генерация отчета для скачивания"""
    try:
        ensure_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT date(created_at) as date, time(created_at) as time, value, note
            FROM measurements 
            WHERE created_at >= date('now', '-1 month')
            ORDER BY created_at DESC
        ''')
        
        measurements = []
        glucose_values = []
        
        for row in c.fetchall():
            date, time, value, note = row
            pressure = note.split('Давление: ')[1] if note and 'Давление:' in note else ''
            
            measurements.append({
                'date': date,
                'time': time,
                'value': value,
                'pressure': pressure
            })
            glucose_values.append(value)
        
        conn.close()
        
        if not measurements:
            return "Нет данных за последний месяц", 404
        
        html_content = generate_report_html(measurements, glucose_values)
        
        return send_file(
            io.BytesIO(html_content.encode('utf-8')),
            as_attachment=True,
            download_name=f'glucose_report_{datetime.now().strftime("%Y-%m-%d")}.html',
            mimetype='text/html'
        )
        
    except Exception as e:
        return f"Ошибка генерации отчета: {str(e)}", 500

def generate_report_html(measurements, glucose_values):
    """Генерация HTML для скачиваемого отчета"""
    min_glucose = min(glucose_values) if glucose_values else 0
    max_glucose = max(glucose_values) if glucose_values else 0
    avg_glucose = sum(glucose_values) / len(glucose_values) if glucose_values else 0
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Отчет по глюкозе</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .header {{ text-align: center; border-bottom: 2px solid #007cba; padding-bottom: 20px; }}
            .stats {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #007cba; color: white; }}
            .min-value {{ color: green; font-weight: bold; }}
            .max-value {{ color: red; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 Отчет по уровню глюкозы</h1>
            <p>Период: последние 30 дней | Сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        </div>
        
        <div class="stats">
            <h3>📈 Статистика</h3>
            <p><strong>Всего измерений:</strong> {len(measurements)}</p>
            <p><strong>Средний уровень:</strong> {avg_glucose:.1f} mmol/L</p>
            <p><strong>Минимальный уровень:</strong> <span class="min-value">{min_glucose} mmol/L</span></p>
            <p><strong>Максимальный уровень:</strong> <span class="max-value">{max_glucose} mmol/L</span></p>
        </div>
        
        <h3>📋 Детальные измерения</h3>
        <table>
            <thead>
                <tr>
                    <th>Дата</th>
                    <th>Время</th>
                    <th>Глюкоза (mmol/L)</th>
                    <th>Давление</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for m in measurements:
        value_class = ""
        if m['value'] == min_glucose:
            value_class = "min-value"
        elif m['value'] == max_glucose:
            value_class = "max-value"
            
        html += f"""
                <tr>
                    <td>{m['date']}</td>
                    <td>{m['time']}</td>
                    <td class="{value_class}">{m['value']}</td>
                    <td>{m['pressure'] or '-'}</td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
    </body>
    </html>
    """
    
    return html

# ФУНКЦИЯ ДЛЯ ВОССТАНОВЛЕНИЯ БАЗЫ (если что-то сломалось)
@app.route('/admin/fix_database')
def fix_database():
    """Восстановление базы данных если возникли проблемы"""
    try:
        print("🔄 Запуск восстановления базы данных...")
        
        # 1. Делаем резервную копию если файл существует
        backup_path = None
        if os.path.exists(DB_PATH):
            backup_path = f"{DB_PATH}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            import shutil
            shutil.copy2(DB_PATH, backup_path)
            print(f"✅ Создана резервная копия: {backup_path}")
        
        # 2. Пересоздаем базу
        result = init_db()
        
        response = {
            "success": result,
            "message": "База данных восстановлена" if result else "Ошибка восстановления",
            "db_path": DB_PATH,
            "backup_created": backup_path is not None,
            "backup_path": backup_path
        }
        
        print(f"✅ Восстановление завершено: {response}")
        
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ Ошибка восстановления БД: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ИНФОРМАЦИЯ О БАЗЕ
@app.route('/admin/db_info')
def db_info():
    """Информация о базе данных"""
    try:
        ensure_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        info = {
            "db_path": DB_PATH,
            "db_size": os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0,
            "db_exists": os.path.exists(DB_PATH),
            "tables": [],
            "record_count": 0,
            "last_records": []
        }
        
        # Таблицы
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        info["tables"] = [row[0] for row in c.fetchall()]
        
        # Количество записей
        if 'measurements' in info["tables"]:
            c.execute("SELECT COUNT(*) FROM measurements")
            info["record_count"] = c.fetchone()[0]
            
            # Последние 5 записей
            c.execute("SELECT value, note, created_at FROM measurements ORDER BY id DESC LIMIT 5")
            info["last_records"] = c.fetchall()
        
        conn.close()
        
        # Форматируем ответ
        html = f"""
        <h2>Информация о базе данных</h2>
        <p><strong>Путь:</strong> {info['db_path']}</p>
        <p><strong>Размер:</strong> {info['db_size']} байт</p>
        <p><strong>Существует:</strong> {'Да' if info['db_exists'] else 'Нет'}</p>
        <p><strong>Таблицы:</strong> {', '.join(info['tables'])}</p>
        <p><strong>Записей в measurements:</strong> {info['record_count']}</p>
        """
        
        if info['last_records']:
            html += "<h3>Последние записи:</h3><ul>"
            for value, note, created_at in info['last_records']:
                html += f"<li>{value} mmol/L | {note or 'нет заметки'} | {created_at}</li>"
            html += "</ul>"
        
        html += f"""
        <p><a href="/">На главную</a></p>
        <p><a href="/admin/fix_database">Восстановить базу</a> (осторожно!)</p>
        """
        
        return html
        
    except Exception as e:
        return f"Ошибка получения информации: {str(e)}"

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Запуск Glucose Tracker")
    print(f"📁 База данных: {DB_PATH}")
    print(f"📊 Путь существует: {os.path.exists(DB_PATH)}")
    print("=" * 50)
    
    ensure_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
