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

def init_db():
    try:
        conn = sqlite3.connect('glucose.db')
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS measurements
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             value REAL NOT NULL,
             note TEXT,
             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
        ''')
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")

def ensure_db():
    try:
        conn = sqlite3.connect('glucose.db')
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='measurements'")
        result = c.fetchone()
        conn.close()
        
        if not result:
            print("🔄 Таблица не найдена, создаем...")
            init_db()
        return True
    except:
        init_db()
        return True

# Инициализация БД при запуске
ensure_db()

# СТУЧАЛКА для uptimerobot
@app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "glucose_tracker"
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

@app.route('/print_report')
def print_report():
    try:
        ensure_db()
        conn = sqlite3.connect('glucose.db')
        c = conn.cursor()
        
        # Получаем данные за последние 30 дней
        c.execute('''
            SELECT date(created_at) as date, time(created_at) as time, value, note
            FROM measurements 
            WHERE created_at >= date('now', '-30 days')
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
        
        # Рассчитываем статистику
        if glucose_values:
            stats = {
                'total': len(measurements),
                'avg_glucose': sum(glucose_values) / len(glucose_values),
                'min_glucose': min(glucose_values),
                'max_glucose': max(glucose_values),
            }
            
            # Определяем период отчета
            if measurements:
                start_date = measurements[-1]['date']  # Самая старая дата
                end_date = measurements[0]['date']     # Самая новая дата
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
                             measurements=measurements,
                             stats=stats,
                             start_date=start_date,
                             end_date=end_date)
        
    except Exception as e:
        return f"Ошибка генерации отчета: {str(e)}", 500

@app.route('/api/measurement', methods=['POST'])
def add_measurement():
    try:
        ensure_db()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Пустые данные', 'success': False}), 400
            
        value = float(data['value'])
        note = data.get('note', '')
        
        conn = sqlite3.connect('glucose.db')
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
        conn = sqlite3.connect('glucose.db')
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

@app.route('/generate_report')
def generate_report():
    try:
        ensure_db()
        conn = sqlite3.connect('glucose.db')
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
    min_glucose = min(glucose_values) if glucose_values else 0
    max_glucose = max(glucose_values) if glucose_values else 0
    avg_glucose = sum(glucose_values) / len(glucose_values) if glucose_values else 0
    
    chart_image = create_chart_image(measurements)
    chart_base64 = base64.b64encode(chart_image).decode('utf-8') if chart_image else ''
    
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
            .chart {{ text-align: center; margin: 30px 0; }}
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
    """
    
    if chart_base64:
        html += f"""
        <div class="chart">
            <h3>📉 Динамика уровня глюкозы</h3>
            <img src="data:image/png;base64,{chart_base64}" alt="График глюкозы" style="max-width: 100%;">
        </div>
        """
    
    html += """
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

def create_chart_image(measurements):
    try:
        if not measurements:
            return None
            
        recent_measurements = measurements[:20]
        dates = [f"{m['date']}\n{m['time']}" for m in recent_measurements]
        glucose_values = [m['value'] for m in recent_measurements]
        
        plt.figure(figsize=(12, 6))
        plt.plot(glucose_values, marker='o', linewidth=2, markersize=4, color='#2c3e50')
        
        if glucose_values:
            min_val = min(glucose_values)
            max_val = max(glucose_values)
            min_idx = glucose_values.index(min_val)
            max_idx = glucose_values.index(max_val)
            
            plt.plot(min_idx, min_val, 'go', markersize=8, label='Min')
            plt.plot(max_idx, max_val, 'ro', markersize=8, label='Max')
        
        plt.title('Динамика уровня глюкозы', fontsize=16, fontweight='bold')
        plt.xlabel('Измерения')
        plt.ylabel('Глюкоза (mmol/L)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(range(len(dates)), dates, rotation=45)
        plt.tight_layout()
        
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        
        img_buffer.seek(0)
        return img_buffer.getvalue()
        
    except Exception as e:
        print(f"❌ Ошибка создания графика: {str(e)}")
        return None

if __name__ == '__main__':
    ensure_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
