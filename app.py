import os
import json
import sqlite3
import requests
from datetime import datetime
from pathlib import Path
from fpdf import FPDF
from flask import Flask, render_template, redirect, url_for, request, flash, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "mediscan.db"
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-please")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "sk-your-openrouter-key")
API_URL = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "username TEXT UNIQUE NOT NULL,"
        "password_hash TEXT NOT NULL,"
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ")"
    )

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS patients ("
        "patient_id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER UNIQUE NOT NULL,"
        "name TEXT NOT NULL,"
        "age INTEGER,"
        "gender TEXT,"
        "weight REAL,"
        "height REAL,"
        "chronic_diseases TEXT,"
        "previous_surgeries TEXT,"
        "allergies TEXT,"
        "current_medications TEXT,"
        "smoking TEXT,"
        "alcohol TEXT,"
        "exercise_frequency TEXT,"
        "sleep_hours REAL,"
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        "FOREIGN KEY(user_id) REFERENCES users(id)"
        ")"
    )

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS disease_history ("
        "history_id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER NOT NULL,"
        "patient_id INTEGER NOT NULL,"
        "symptoms TEXT,"
        "symptom_duration TEXT,"
        "severity TEXT,"
        "diagnosis_text TEXT,"
        "urgency TEXT,"
        "report_filename TEXT,"
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        "FOREIGN KEY(user_id) REFERENCES users(id),"
        "FOREIGN KEY(patient_id) REFERENCES patients(patient_id)"
        ")"
    )

    conn.commit()
    conn.close()


def query_gpt_model(patient_info, symptoms, duration, severity):
    if not OPENROUTER_API_KEY:
        return "Error: No OpenRouter API key found. Please add OPENROUTER_API_KEY to your .env file."

    prompt = f"""
You are a professional medical consultant. Analyze the patient profile and symptoms below, then provide a professional diagnostic report.

PATIENT PROFILE:
- Name: {patient_info['name']}
- Age: {patient_info['age']}
- Gender: {patient_info['gender']}
- Weight: {patient_info['weight']} kg
- Height: {patient_info['height']} cm
- Chronic diseases: {patient_info['chronic_diseases']}
- Surgeries: {patient_info['previous_surgeries']}
- Allergies: {patient_info['allergies']}
- Current medications: {patient_info['current_medications']}
- Smoking: {patient_info['smoking']}
- Alcohol: {patient_info['alcohol']}
- Exercise frequency: {patient_info['exercise_frequency']}
- Sleep hours per night: {patient_info['sleep_hours']}

SYMPTOMS:
{symptoms}
Duration: {duration}
Severity: {severity}

Please provide:
1. A preliminary diagnosis list of 3 possible conditions with likelihood.
2. A concise explanation for each condition.
3. Medication recommendations and dosing guidance.
4. Safe home remedies.
5. Red flags for immediate medical attention.
6. A clear urgency level.
7. Professional next-step recommendations.

Use a professional clinical tone. Do not claim to replace a licensed doctor.

The output shuld be like in the format
first give the top 3 disease which the pateint is affected by
Disease 1: Name of the disease in that frmat
then give the home remedies the person the do 
then give the medicines (that are avaliable in india) that he / she can take
the at last give the urgency level of the disease and the red flags that the person should look for and if he / she should go to the doctor immediately or not

"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "max_tokens": 1200,
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"Error fetching diagnosis: {exc}"


def create_medical_report(user, patient_info, symptoms, duration, severity, diagnosis_text):
    report_name = f"report_{user['username']}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    report_path = REPORTS_DIR / report_name
    pdf = FPDF(format='A4')
    pdf.add_page()
    
    # Set margins: 10mm left/right, 10mm top/bottom
    pdf.set_left_margin(10)
    pdf.set_right_margin(10)
    pdf.set_top_margin(10)
    pdf.set_auto_page_break(auto=True, margin=10)

    # Calculate usable width (A4 = 210mm, minus 20mm margins)
    content_width = 190

    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(content_width, 10, 'MediScan AI Medical Report', ln=True, align='C')
    pdf.ln(3)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_x(10)
    pdf.cell(content_width, 7, f"Report generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ln=True)
    pdf.set_x(10)
    pdf.cell(content_width, 7, f"Patient: {patient_info['name']}", ln=True)
    pdf.set_x(10)
    pdf.cell(content_width, 7, f"Username: {user['username']}", ln=True)
    pdf.ln(4)

    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_x(10)
    pdf.cell(content_width, 7, 'Patient Summary', ln=True)
    pdf.set_font('Helvetica', '', 9)
    pdf.set_x(10)
    pdf.multi_cell(content_width, 5, f"Age: {patient_info['age']} | Gender: {patient_info['gender']} | BMI: {patient_info['bmi']:.1f}")
    pdf.set_x(10)
    pdf.multi_cell(content_width, 5, f"Chronic diseases: {patient_info['chronic_diseases']}")
    pdf.set_x(10)
    pdf.multi_cell(content_width, 5, f"Previous surgeries: {patient_info['previous_surgeries']}")
    pdf.set_x(10)
    pdf.multi_cell(content_width, 5, f"Allergies: {patient_info['allergies']}")
    pdf.set_x(10)
    pdf.multi_cell(content_width, 5, f"Current medications: {patient_info['current_medications']}")
    pdf.ln(3)

    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_x(10)
    pdf.cell(content_width, 7, 'Presenting Complaint', ln=True)
    pdf.set_font('Helvetica', '', 9)
    pdf.set_x(10)
    pdf.multi_cell(content_width, 5, f"Symptoms: {symptoms}")
    pdf.set_x(10)
    pdf.multi_cell(content_width, 5, f"Duration: {duration}")
    pdf.set_x(10)
    pdf.multi_cell(content_width, 5, f"Severity: {severity}")
    pdf.ln(3)

    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_x(10)
    pdf.cell(content_width, 7, 'Diagnostic Findings', ln=True)
    pdf.set_font('Helvetica', '', 9)
    pdf.set_x(10)
    pdf.multi_cell(content_width, 5, diagnosis_text)

    pdf.output(str(report_path))
    return report_name


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user


def startup():
    initialize_database()


@app.route('/')
def home():
    user = get_current_user()
    return render_template('index.html', user=user)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()

        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('register'))

        if password != password_confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))

        conn = get_db_connection()
        existing = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            conn.close()
            flash('Username is already taken.', 'error')
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
        conn.commit()
        conn.close()

        flash('Account created successfully. Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))

        flash('Invalid username or password.', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))


@app.route('/dashboard')
def dashboard():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    patient = conn.execute('SELECT * FROM patients WHERE user_id = ?', (user['id'],)).fetchone()
    history = conn.execute('SELECT * FROM disease_history WHERE user_id = ? ORDER BY created_at DESC', (user['id'],)).fetchall()
    conn.close()

    return render_template('dashboard.html', user=user, patient=patient, history=history)


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    patient = conn.execute('SELECT * FROM patients WHERE user_id = ?', (user['id'],)).fetchone()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        age = request.form.get('age', '').strip()
        gender = request.form.get('gender', '').strip()
        weight = request.form.get('weight', '').strip()
        height = request.form.get('height', '').strip()
        chronic_diseases = request.form.get('chronic_diseases', '').strip()
        previous_surgeries = request.form.get('previous_surgeries', '').strip()
        allergies = request.form.get('allergies', '').strip()
        current_medications = request.form.get('current_medications', '').strip()
        smoking = request.form.get('smoking', '').strip()
        alcohol = request.form.get('alcohol', '').strip()
        exercise_frequency = request.form.get('exercise_frequency', '').strip()
        sleep_hours = request.form.get('sleep_hours', '').strip()

        if not name or not age or not gender:
            flash('Name, age, and gender are required.', 'error')
            return redirect(url_for('profile'))

        if patient:
            conn.execute(
                'UPDATE patients SET name = ?, age = ?, gender = ?, weight = ?, height = ?, chronic_diseases = ?, previous_surgeries = ?, allergies = ?, current_medications = ?, smoking = ?, alcohol = ?, exercise_frequency = ?, sleep_hours = ? WHERE user_id = ?',
                (name, age, gender, weight or None, height or None, chronic_diseases, previous_surgeries, allergies, current_medications, smoking, alcohol, exercise_frequency, sleep_hours or None, user['id'])
            )
        else:
            conn.execute(
                'INSERT INTO patients (user_id, name, age, gender, weight, height, chronic_diseases, previous_surgeries, allergies, current_medications, smoking, alcohol, exercise_frequency, sleep_hours) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (user['id'], name, age, gender, weight or None, height or None, chronic_diseases, previous_surgeries, allergies, current_medications, smoking, alcohol, exercise_frequency, sleep_hours or None)
            )

        conn.commit()
        conn.close()
        flash('Profile details saved successfully.', 'success')
        return redirect(url_for('dashboard'))

    conn.close()
    return render_template('profile.html', user=user, patient=patient)


@app.route('/new-diagnosis', methods=['GET', 'POST'])
def new_diagnosis():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    patient = conn.execute('SELECT * FROM patients WHERE user_id = ?', (user['id'],)).fetchone()
    conn.close()

    if not patient:
        flash('Please complete your profile before using diagnosis.', 'error')
        return redirect(url_for('profile'))

    if request.method == 'POST':
        symptoms = request.form.get('symptoms', '').strip()
        duration = request.form.get('duration', '').strip()
        severity = request.form.get('severity', '').strip()

        if not symptoms or not duration or not severity:
            flash('Please fill in all diagnosis fields.', 'error')
            return redirect(url_for('new_diagnosis'))

        patient_info = {
            'name': patient['name'],
            'age': patient['age'],
            'gender': patient['gender'],
            'weight': patient['weight'],
            'height': patient['height'],
            'chronic_diseases': patient['chronic_diseases'],
            'previous_surgeries': patient['previous_surgeries'],
            'allergies': patient['allergies'],
            'current_medications': patient['current_medications'],
            'smoking': patient['smoking'],
            'alcohol': patient['alcohol'],
            'exercise_frequency': patient['exercise_frequency'],
            'sleep_hours': patient['sleep_hours'],
            'bmi': (patient['weight'] / ((patient['height'] / 100) ** 2)) if patient['height'] else 0,
        }

        diagnosis_text = query_gpt_model(patient_info, symptoms, duration, severity)
        urgency = 'Moderate'
        for marker in ['Urgency:', 'URGENCY:', 'urgency:']:
            if marker in diagnosis_text:
                try:
                    urgency = diagnosis_text.split(marker, 1)[1].split('\n', 1)[0].strip()
                    break
                except Exception:
                    pass

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO disease_history (user_id, patient_id, symptoms, symptom_duration, severity, diagnosis_text, urgency) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (user['id'], patient['patient_id'], symptoms, duration, severity, diagnosis_text, urgency)
        )
        history_id = cursor.lastrowid
        conn.commit()

        report_filename = create_medical_report(user, patient_info, symptoms, duration, severity, diagnosis_text)
        conn.execute('UPDATE disease_history SET report_filename = ? WHERE history_id = ?', (report_filename, history_id))
        conn.commit()
        conn.close()

        flash('Diagnosis completed and medical report generated.', 'success')
        return redirect(url_for('diagnosis_result', history_id=history_id))

    return render_template('new_diagnosis.html', user=user, patient=patient)


@app.route('/diagnosis/<int:history_id>')
def diagnosis_result(history_id):
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    record = conn.execute('SELECT * FROM disease_history WHERE history_id = ? AND user_id = ?', (history_id, user['id'])).fetchone()
    conn.close()

    if not record:
        flash('Diagnosis record not found.', 'error')
        return redirect(url_for('dashboard'))

    return render_template('diagnosis_result.html', user=user, record=record)


@app.route('/history')
def history():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    records = conn.execute('SELECT * FROM disease_history WHERE user_id = ? ORDER BY created_at DESC', (user['id'],)).fetchall()
    conn.close()
    return render_template('history.html', user=user, records=records)


@app.route('/download-report/<filename>')
def download_report(filename):
    return send_from_directory(REPORTS_DIR, filename, as_attachment=True)


if __name__ == '__main__':
    initialize_database()
    app.run(debug=True)
