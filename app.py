from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import os
from datetime import datetime, timedelta
from weasyprint import HTML
import io
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import base64

app = Flask(__name__)

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

@app.route('/api/measurement', methods=['POST'])
def add_measurement():
    try:
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

@app.route('/generate_pdf')
def generate_pdf():
    try:
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
        
        min_glucose = min(glucose_values) if glucose_values else 0
        max_glucose = max(glucose_values) if glucose_values else 0
        
        html_content = generate_pdf_html(measurements, min_glucose, max_glucose)
        pdf = HTML(string=html_content).write_pdf()
        
        return send_file(
            io.BytesIO(pdf),
            as_attachment=True,
            download_name=f'glucose_report_{datetime.now().strftime("%Y-%m-%d")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return f"Ошибка генерации PDF: {str(e)}", 500

def generate_pdf_html(measurements, min_glucose, max_glucose):
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                color: #333;
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
                border-bottom: 2px solid #007cba;
                padding-bottom: 20px;
            }}
            .title {{
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
            }}
            .table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }}
            .table th {{
                background-color: #007cba;
                color: white;
                padding: 12px;
                text-align: left;
            }}
            .table td {{
                padding: 10px;
                border-bottom: 1px solid #ddd;
            }}
            .min-value {{ color: green; font-weight: bold; }}
            .max-value {{ color: red; font-weight: bold; }}
            .footer {{
                margin-top: 30px;
                text-align: center;
                font-size: 12px;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="title">ОТЧЕТ ПО УРОВНЮ ГЛЮКОЗЫ</div>
            <div>Период: последние 30 дней | Сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>
        </div>
        
        <table class="table">
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
            
        html_template += f"""
                <tr>
                    <td>{m['date']}</td>
                    <td>{m['time']}</td>
                    <td class="{value_class}">{m['value']}</td>
                    <td>{m['pressure'] or '-'}</td>
                </tr>
        """
    
    html_template += f"""
            </tbody>
        </table>
        
        <div class="footer">
            Всего измерений: {len(measurements)} | 
            Минимум: {min_glucose} mmol/L | 
            Максимум: {max_glucose} mmol/L
        </div>
    </body>
    </html>
    """
    
    return html_template

# Инициализация БД при запуске
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
