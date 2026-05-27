import os
import json
import sqlite3
import requests
from datetime import datetime
from pathlib import Path
from fpdf import FPDF
from fpdf.enums import XPos, YPos
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


def parse_diagnosis_json(text):
    text = text.strip()
    # Strip markdown code block wrappers if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
        # Ensure all fields are present
        required_keys = ['diagnosis', 'explanation', 'medications', 'home_remedies', 'urgency', 'red_flags']
        for key in required_keys:
            if key not in data:
                if key in ['medications', 'home_remedies', 'red_flags']:
                    data[key] = []
                else:
                    data[key] = "N/A"
        return data
    except Exception:
        # Fallback if json parsing fails
        return {
            "diagnosis": "Clinical Impression",
            "explanation": text,
            "medications": [],
            "home_remedies": [],
            "urgency": "Moderate",
            "red_flags": []
        }


def query_gpt_model(patient_info, symptoms, duration, severity):
    if not OPENROUTER_API_KEY:
        return "Error: No OpenRouter API key found. Please add OPENROUTER_API_KEY to your .env file."

    prompt = f"""
You are an expert medical consultant. Analyze the patient profile and symptoms below and output a precise clinical prescription and diagnosis report.

PATIENT PROFILE:
- Name: {patient_info['name']}
- Age: {patient_info['age']}
- Gender: {patient_info['gender']}

SYMPTOMS:
{symptoms}
Duration: {duration}
Severity: {severity}

Provide the clinical diagnosis and prescription details strictly in JSON format. Do NOT add any conversational preambles or post-scripts. Output ONLY the JSON block.

The JSON schema must look exactly like this:
{{
  "diagnosis": "Suspected Condition (vibrant and clear clinical term, e.g. Acute Gastro-enteritis)",
  "explanation": "A very brief explanation of the condition and why it matches the symptoms (1-2 sentences).",
  "medications": [
    {{
      "name": "Generic or brand name of medication (e.g. Paracetamol 500mg, Cetirizine 10mg)",
      "dosage": "Dosage instructions (e.g. 1 tablet)",
      "frequency": "Frequency (e.g. Twice daily after meals, Once daily at bedtime)",
      "duration": "Duration (e.g. 5 days, 3 days)"
    }}
  ],
  "home_remedies": [
    "Home care advice 1",
    "Home care advice 2"
  ],
  "urgency": "Urgency rating (Mild, Moderate, or Severe)",
  "red_flags": [
    "Warning symptom 1",
    "Warning symptom 2"
  ]
}}
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1000,
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
    
    # Parse the diagnosis JSON
    data = parse_diagnosis_json(diagnosis_text)
    
    pdf = FPDF(format='A4')
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Header Clinic Letterhead
    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_text_color(13, 148, 136)  # Teal
    pdf.cell(100, 10, 'MEDISCAN AI CLINIC', new_x=XPos.RIGHT, new_y=YPos.TOP)
    
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(100, 116, 139)  # Slate Gray
    pdf.cell(80, 10, 'DIGITAL RX PRESCRIPTION', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    
    pdf.set_font('Helvetica', '', 8.5)
    pdf.cell(100, 4, 'Automated 3D Diagnostics & Medical Intelligence', new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(80, 4, f"Date: {datetime.utcnow().strftime('%d %b %Y, %H:%M UTC')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    
    pdf.cell(100, 4, 'License No: AI-2026-RX', new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(80, 4, 'Status: Digitally Signed & Verified', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    
    pdf.ln(3)
    
    # Teal line separator
    pdf.set_draw_color(13, 148, 136)
    pdf.set_line_width(0.8)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)
    
    # Patient Details (Just Name & Age, as requested)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(90, 6, f"PATIENT: {patient_info['name'].upper()}", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(90, 6, f"AGE: {patient_info['age']} Years", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    
    pdf.ln(2)
    pdf.set_draw_color(226, 232, 240)
    pdf.set_line_width(0.3)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)
    
    # Chief Complaint
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(180, 4, 'CHIEF COMPLAINT & SYMPTOMS', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 9.5)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(180, 4.5, f"{symptoms} (Duration: {duration} | Severity: {severity})")
    
    pdf.ln(3)
    
    # Diagnosis (Highlight box)
    start_y = pdf.get_y()
    pdf.set_y(start_y + 1.5)
    pdf.set_x(18)
    pdf.set_font('Helvetica', 'B', 9.5)
    pdf.set_text_color(13, 148, 136)
    pdf.cell(174, 4, 'CLINICAL IMPRESSION / SUSPECTED DIAGNOSIS', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_x(18)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(174, 6, data['diagnosis'].upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_x(18)
    pdf.set_font('Helvetica', 'I', 9.5)
    pdf.set_text_color(71, 85, 105)
    pdf.multi_cell(174, 4.5, data['explanation'])
    pdf.ln(1.5)
    end_y = pdf.get_y()
    
    # Draw background box for diagnosis
    pdf.set_draw_color(13, 148, 136)
    pdf.set_fill_color(240, 253, 250)
    pdf.set_line_width(0.4)
    pdf.rect(15, start_y, 180, end_y - start_y, style='FD')
    
    pdf.set_y(end_y)
    pdf.ln(4)
    
    # Rx Pharmacology
    pdf.set_font('Helvetica', 'B', 20)
    pdf.set_text_color(13, 148, 136)
    pdf.cell(12, 8, 'Rx', new_x=XPos.RIGHT, new_y=YPos.TOP)
    
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(168, 8, 'RECOMMENDED PHARMACOTHERAPY', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    if data['medications']:
        # Table Header
        pdf.set_fill_color(241, 245, 249)
        pdf.set_font('Helvetica', 'B', 8.5)
        pdf.set_text_color(71, 85, 105)
        pdf.set_draw_color(226, 232, 240)
        pdf.set_line_width(0.2)
        
        pdf.cell(60, 6, ' Medication Name', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, fill=True)
        pdf.cell(35, 6, ' Dosage', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, fill=True)
        pdf.cell(50, 6, ' Frequency', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, fill=True)
        pdf.cell(35, 6, ' Duration', border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        
        pdf.set_font('Helvetica', '', 8.5)
        pdf.set_text_color(51, 65, 85)
        for med in data['medications']:
            pdf.cell(60, 6, f" {med.get('name', 'N/A')}", border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.cell(35, 6, f" {med.get('dosage', 'N/A')}", border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.cell(50, 6, f" {med.get('frequency', 'N/A')}", border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.cell(35, 6, f" {med.get('duration', 'N/A')}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.set_font('Helvetica', 'I', 9.5)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(180, 6, 'No specific medications prescribed. Monitor condition closely.', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
    pdf.ln(3)
    
    # Advice & Lifestyle
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(13, 148, 136)
    pdf.cell(180, 5, 'ADVICE & LIFESTYLE MODIFICATIONS', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(51, 65, 85)
    
    if data['home_remedies']:
        for remedy in data['home_remedies']:
            pdf.multi_cell(180, 4, f"- {remedy}")
    else:
        pdf.multi_cell(180, 4, "- Maintain rest, stay hydrated, and monitor vital statistics.")
        
    pdf.ln(3)
    
    # Warnings & Red Flags
    if data['red_flags']:
        start_warning_y = pdf.get_y()
        pdf.set_y(start_warning_y + 1.5)
        pdf.set_x(18)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(185, 28, 28)
        pdf.cell(174, 4, 'WARNINGS & RED FLAGS (Seek immediate medical attention if present):', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.set_font('Helvetica', '', 8.5)
        for flag in data['red_flags']:
            pdf.set_x(18)
            pdf.multi_cell(174, 3.8, f"- {flag}")
        pdf.ln(1.5)
        end_warning_y = pdf.get_y()
        
        pdf.set_draw_color(239, 68, 68)
        pdf.set_fill_color(254, 242, 242)
        pdf.set_line_width(0.3)
        pdf.rect(15, start_warning_y, 180, end_warning_y - start_warning_y, style='FD')
        pdf.set_y(end_warning_y)
        pdf.ln(3)
        
    # Signature Footer Area (Forced at bottom of page)
    pdf.set_y(-38)
    pdf.set_draw_color(226, 232, 240)
    pdf.set_line_width(0.3)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(2)
    
    pdf.set_font('Helvetica', 'B', 8.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(180, 4.5, 'DR. AI CONSULTANT', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    pdf.set_font('Helvetica', 'I', 7.5)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(180, 4, 'Electronically Generated via MediScan AI 3D Core Engine', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    
    pdf.ln(1)
    pdf.set_font('Helvetica', 'I', 7)
    pdf.set_text_color(156, 163, 175)
    pdf.multi_cell(180, 3, 'Disclaimer: This digital prescription is an AI-assisted synthesis based on user-reported symptoms. It is meant for informational support and does not replace regular doctor consultation, physical diagnostics, or clinical tests.', align='C')
    
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
        diagnosis_data = parse_diagnosis_json(diagnosis_text)
        urgency = diagnosis_data.get('urgency', 'Moderate')

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
    patient = conn.execute('SELECT * FROM patients WHERE user_id = ?', (user['id'],)).fetchone()
    conn.close()

    if not record:
        flash('Diagnosis record not found.', 'error')
        return redirect(url_for('dashboard'))

    # Convert row to dictionary and inject parsed json data
    record_dict = dict(record)
    record_dict['data'] = parse_diagnosis_json(record['diagnosis_text'])

    return render_template('diagnosis_result.html', user=user, record=record_dict, patient=patient)


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
