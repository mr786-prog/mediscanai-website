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
        required_keys = [
            'diagnosis', 'explanation', 'detailed_summary', 'medications', 'alternative_medications',
            'home_remedies', 'habit_changes', 'possible_allergies', 'urgency', 'red_flags',
            'patient_profile', 'symptoms', 'differential_diagnosis', 'next_steps'
        ]
        for key in required_keys:
            if key not in data:
                if key in ['medications', 'alternative_medications', 'home_remedies', 'habit_changes', 'possible_allergies', 'red_flags', 'symptoms', 'differential_diagnosis', 'next_steps']:
                    data[key] = []
                else:
                    data[key] = "N/A"
        return data
    except Exception:
        # Fallback if json parsing fails
        return {
            "diagnosis": "Clinical Impression",
            "explanation": text,
            "detailed_summary": "No detailed summary was returned by the AI model.",
            "medications": [],
            "alternative_medications": [],
            "home_remedies": [],
            "habit_changes": [],
            "possible_allergies": [],
            "urgency": "Moderate",
            "red_flags": [],
            "patient_profile": "N/A",
            "symptoms": [],
            "differential_diagnosis": [],
            "next_steps": []
        }


def query_gpt_model(patient_info, symptoms, duration, severity, consultation_details=None, history_summary="No previous clinical history on record."):
    if not OPENROUTER_API_KEY:
        return "Error: No OpenRouter API key found. Please add OPENROUTER_API_KEY to your .env file."

    consultation_block = ""
    if consultation_details:
        consultation_block = f"\nDETAILED DOCTOR INTERVIEW (Patient's Confirmed Responses):\n{consultation_details}\n\n** IMPORTANT: Only include symptoms that the patient explicitly confirmed during the interview. Do NOT assume or infer symptoms that were not mentioned or were explicitly denied. **\n"

    prompt = f"""
You are an expert clinical diagnostician. Your goal is to analyze the patient profile, medical history, current complaints, and interview responses to produce a comprehensive, accurate medical report.
** CRITICAL ACCURACY RULE: Only include symptoms and findings that the patient explicitly confirmed. If the patient said 'No' to a symptom, do NOT include it in the diagnosis, symptoms list, or differential diagnosis. **
The report must be thorough, precise, and strictly based on confirmed information from the consultation.

PATIENT PROFILE:
- Name: {patient_info['name']}
- Age: {patient_info['age']} years
- Gender: {patient_info['gender']}
- Weight: {patient_info.get('weight', 'N/A')} kg | Height: {patient_info.get('height', 'N/A')} cm | BMI: {patient_info.get('bmi', 0):.1f}
- Chronic Diseases: {patient_info.get('chronic_diseases', 'None')}
- Previous Surgeries: {patient_info.get('previous_surgeries', 'None')}
- Allergies: {patient_info.get('allergies', 'None')}
- Current Medications: {patient_info.get('current_medications', 'None')}
- Lifestyle Habits: Smoking: {patient_info.get('smoking', 'N/A')} | Alcohol: {patient_info.get('alcohol', 'N/A')} | Exercise: {patient_info.get('exercise_frequency', 'N/A')}

PATIENT CLINICAL HISTORY:
{history_summary}

CURRENT CHIEF COMPLAINT & CONFIRMED DETAILS:
- Primary Symptoms: {symptoms}
- Duration: {duration}
- Severity: {severity}
{consultation_block}

Provide an exhaustive, high-fidelity clinical assessment report strictly in JSON format. Do NOT add any conversational preambles or post-scripts. Output ONLY the JSON block.
Ensure all sections are packed with rich clinical insights, thorough details, and factor-by-factor explanations.
All medications MUST reference generic names and popular Indian brand names (e.g. Crocin, Dolo, Azithral, Pantocid) where applicable.
Include at least 2 alternative_medications commonly available in Indian pharmacies.
Include at least 2 practical home_remedies suitable for Indian households.

CRITICAL RULE FOR SYMPTOMS LISTING:
- In the "symptoms" JSON array, you MUST ONLY list symptoms that the patient has explicitly confirmed they are experiencing (either in their baseline symptoms or confirmed in the follow-up answers).
- DO NOT list any symptom that the patient has explicitly denied in the consultation. For example, if the AI doctor asked 'Do you have a cough?' and the patient answered 'No', you are STRICTLY FORBIDDEN from listing 'cough' under the "symptoms" array. Denied symptoms must be completely excluded from the symptoms list.

The JSON schema must look exactly like this:
{{
  "diagnosis": "Suspected Condition (a clear, clinical medical term, e.g. Acute Gastro-enteritis)",
  "explanation": "A clear, concise clinical overview of the suspected condition (1-2 sentences).",
  "detailed_summary": "An exhaustive, highly detailed breakdown of the diagnosis. Explain the pathophysiology (what is happening in the body), likely triggers, natural progression pathway, and a thorough medical explanation of how this condition is usually managed. Be extremely thorough, detailed, and informative.",
  "patient_profile": "An exhaustive analysis (at least 3-4 sentences) explaining how the patient's personal factors (such as age, gender, BMI, chronic diseases, daily habits, and previous clinical history) directly influence or overlap with the current symptoms and diagnosis.",
  "symptoms": [
    "CRITICAL: List ONLY the symptoms the patient explicitly confirmed during the interview. Clinical interpretation and physiological basis.",
    "Only include additional symptoms if directly mentioned or confirmed by patient."
  ],
  "differential_diagnosis": [
    {{
      "diagnosis": "Alternative Suspected Condition A",
      "likelihood": "High, Medium, or Low",
      "explanation": "Extremely detailed explanation of why this condition is considered, what clinical criteria match, and how it is differentiated from the primary diagnosis based on the symptoms."
    }},
    {{
      "diagnosis": "Alternative Suspected Condition B",
      "likelihood": "High, Medium, or Low",
      "explanation": "Extremely detailed explanation of why this condition is considered and how it is differentiated."
    }}
  ],
  "medications": [
    {{
      "name": "Primary medication with Indian brand names (e.g. Paracetamol / Crocin / Dolo 650 500mg)",
      "dosage": "Precise dosage instructions (e.g. 1 tablet, 5ml)",
      "frequency": "Frequency (e.g. Three times daily after meals, every 8 hours)",
      "duration": "Duration (e.g. 5 days, 7 days)"
    }}
  ],
  "alternative_medications": [
    {{
      "name": "Alternative medication commonly available in India (e.g. Ibuprofen / Brufen, Azithromycin / Azithral)",
      "dosage": "Precise dosage instructions",
      "frequency": "Frequency",
      "notes": "When to consider this alternative (e.g. OTC substitute, if primary not tolerated, generic option)"
    }}
  ],
  "home_remedies": [
    "Evidence-based home remedy with clear step-by-step instructions (use Indian household context where relevant, e.g. warm turmeric milk, steam inhalation, ORS hydration)",
    "Another practical home care guideline with physiological benefits"
  ],
  "habit_changes": [
    "Lifestyle change or preventive measure 1 with justification",
    "Lifestyle change or preventive measure 2 with justification"
  ],
  "possible_allergies": [
    "Detailed warning regarding potential allergen triggers, food-drug interactions, or drug-drug overlaps to watch out for"
  ],
  "urgency": "Urgency rating (Mild, Moderate, or Severe)",
  "next_steps": [
    "Clinical tests or lab exams to ask a physician for (e.g., CBC, ultrasound, throat swab)",
    "Recommended type of physician or clinic to consult for diagnostic validation",
    "Specific signs of stabilization or recovery to track at home"
  ],
  "red_flags": [
    "Critical warning sign 1: emergency threshold (e.g., high fever unresponsive to medication)",
    "Critical warning sign 2: emergency threshold (e.g., severe abdominal pain moving to lower right)"
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
        "max_tokens": 2000,
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"Error fetching diagnosis: {exc}"



def build_patient_context(patient):
    return {
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
        'bmi': (patient['weight'] / ((patient['height'] / 100) ** 2)) if patient['height'] else 0,
    }


def build_consultation_summary(session_data):
    answers = session_data.get('answers', [])
    if not answers:
        return "No additional doctor interview details were collected."

    lines = ["Follow-up doctor interview details:"]
    for item in answers:
        lines.append(f"- Q: {item.get('question', 'Follow-up question')}")
        lines.append(f"  A: {item.get('answer', 'No answer provided')}")
    return "\n".join(lines)


MAX_CONSULTATION_QUESTIONS = 10
MIN_CONSULTATION_QUESTIONS = 3


def should_finalize_consultation(answers):
    return len(answers) >= MAX_CONSULTATION_QUESTIONS


def normalize_doctor_result(doctor_result, answer_count):
    """Enforce min 3 / max 10 question rules regardless of model output."""
    result = dict(doctor_result)
    if answer_count < MIN_CONSULTATION_QUESTIONS:
        result['ready_to_diagnose'] = False
        if not result.get('question', '').strip():
            result['question'] = "Could you describe when your symptoms started and whether anything makes them better or worse?"
    elif answer_count >= MAX_CONSULTATION_QUESTIONS:
        result['ready_to_diagnose'] = True
        result['question'] = ''
    return result


def get_patient_history_summary(user_id):
    conn = get_db_connection()
    try:
        records = conn.execute(
            'SELECT symptoms, symptom_duration, severity, diagnosis_text, created_at FROM disease_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
            (user_id,)
        ).fetchall()
        if not records:
            return "No previous clinical history on record."
        
        summary_lines = []
        for r in records:
            try:
                diag_data = parse_diagnosis_json(r['diagnosis_text'])
                condition = diag_data.get('diagnosis', 'Unknown condition')
            except Exception:
                condition = "Unknown condition"
            
            try:
                date_obj = datetime.strptime(r['created_at'], '%Y-%m-%d %H:%M:%S')
                date_str = date_obj.strftime('%d %b %Y')
            except Exception:
                date_str = r['created_at']
                
            summary_lines.append(f"- On {date_str}: Presented with '{r['symptoms']}' ({r['severity']} severity, duration: {r['symptom_duration']}). Suspected Diagnosis: '{condition}'.")
        return "\n".join(summary_lines)
    except Exception as e:
        return f"Error retrieving history: {e}"
    finally:
        conn.close()


def query_doctor_question(patient_info, symptoms, duration, severity, answers, history_summary="No previous clinical history on record."):
    if not OPENROUTER_API_KEY:
        return {"ready_to_diagnose": False, "question": "Please set OPENROUTER_API_KEY to enable the doctor interview."}

    answer_log = "\n".join(f"Q: {item['question']}\nA: {item['answer']}" for item in answers) if answers else "No follow-up answers yet."
    answer_count = len(answers)

    min_questions_instruction = ""
    if answer_count < MIN_CONSULTATION_QUESTIONS:
        remaining = MIN_CONSULTATION_QUESTIONS - answer_count
        min_questions_instruction = (
            f"\n*** MANDATORY MINIMUM NOT MET ***\n"
            f"You have collected {answer_count} answer(s). You MUST ask at least {MIN_CONSULTATION_QUESTIONS} "
            f"distinct follow-up questions before concluding ({remaining} more required).\n"
            f"You MUST set ready_to_diagnose = false and ask another targeted clinical question.\n"
            f"Do NOT conclude under any circumstances until at least {MIN_CONSULTATION_QUESTIONS} questions are answered.\n"
        )
    elif answer_count < MAX_CONSULTATION_QUESTIONS:
        min_questions_instruction = (
            f"\n*** ADAPTIVE INTERVIEW (questions {answer_count + 1} to {MAX_CONSULTATION_QUESTIONS} allowed) ***\n"
            f"You have met the minimum of {MIN_CONSULTATION_QUESTIONS} questions. You MAY set ready_to_diagnose = true "
            f"only if you have sufficient clinical evidence for a confident assessment.\n"
            f"If important details are still missing (onset, triggers, associated symptoms, severity patterns, "
            f"medication history, red flags), continue asking — you may ask up to {MAX_CONSULTATION_QUESTIONS} total.\n"
            f"Prefer asking 1–2 more clarifying questions when uncertain rather than concluding too early.\n"
        )

    prompt = f"""
You are a senior physician conducting an adaptive clinical consultation.
Ask exactly one concise, empathetic follow-up question at a time.

STRICT QUESTION COUNT RULES:
- MINIMUM: You MUST ask at least {MIN_CONSULTATION_QUESTIONS} distinct follow-up questions before you may conclude.
- MAXIMUM: You may ask up to {MAX_CONSULTATION_QUESTIONS} follow-up questions in total.
- Between questions {MIN_CONSULTATION_QUESTIONS} and {MAX_CONSULTATION_QUESTIONS}: Continue asking if clinically useful information is still missing. Only set ready_to_diagnose=true when you have enough evidence AND at least {MIN_CONSULTATION_QUESTIONS} answers collected.
- At exactly {MAX_CONSULTATION_QUESTIONS} answers: You MUST set ready_to_diagnose=true and question="".
{min_questions_instruction}
Patient profile:
- Name: {patient_info['name']}
- Age: {patient_info['age']} years
- Gender: {patient_info['gender']}
- Weight: {patient_info.get('weight', 'N/A')} kg | Height: {patient_info.get('height', 'N/A')} cm | BMI: {patient_info.get('bmi', 0):.1f}
- Chronic diseases: {patient_info.get('chronic_diseases', 'None')}
- Allergies: {patient_info.get('allergies', 'None')}
- Current medications: {patient_info.get('current_medications', 'None')}

Patient's Previous Clinical History (use this to check for patterns, recurring conditions, or relevant context):
{history_summary}

Baseline symptoms:
- Symptoms: {symptoms}
- Duration: {duration}
- Severity: {severity}

Collected answers so far: {answer_count} / {MAX_CONSULTATION_QUESTIONS} (minimum before concluding: {MIN_CONSULTATION_QUESTIONS})
{answer_log}

Return ONLY valid JSON with:
{{
  "ready_to_diagnose": false,
  "question": "one concise follow-up question or empty string if ready",
  "confidence": "Low/Medium/High"
}}
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 300,
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        parsed = json.loads(text)
        return normalize_doctor_result(parsed, len(answers))
    except Exception:
        return normalize_doctor_result({
            "ready_to_diagnose": False,
            "question": "Can you tell me whether the pain is constant, worsening, or comes and goes?",
            "confidence": "Medium",
        }, len(answers))



def finalize_diagnosis(user, patient, session_data):
    patient_info = build_patient_context(patient)
    symptoms = session_data['symptoms']
    duration = session_data['duration']
    severity = session_data['severity']
    consultation_details = build_consultation_summary(session_data)

    # Retrieve patient clinical history summary
    history_summary = get_patient_history_summary(user['id'])

    diagnosis_text = query_gpt_model(patient_info, symptoms, duration, severity, consultation_details=consultation_details, history_summary=history_summary)
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

    return history_id


def _pdf_section_title(pdf, title, subtitle=None):
    pdf.ln(1.5)
    pdf.set_font('Helvetica', 'B', 9.5)
    pdf.set_text_color(13, 148, 136)
    pdf.cell(180, 4.5, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if subtitle:
        pdf.set_font('Helvetica', 'I', 7.5)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(180, 3.5, subtitle, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(0.5)


def _pdf_body_text(pdf, text, line_height=4):
    pdf.set_font('Helvetica', '', 8.5)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(180, line_height, text)


def _pdf_bullet_list(pdf, items, fallback):
    pdf.set_font('Helvetica', '', 8.5)
    pdf.set_text_color(51, 65, 85)
    if items:
        for item in items:
            pdf.multi_cell(180, 3.8, f"  -  {item}")
    else:
        pdf.multi_cell(180, 3.8, f"  -  {fallback}")


def _pdf_med_table(pdf, col_widths, headers, rows):
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_text_color(71, 85, 105)
    pdf.set_draw_color(226, 232, 240)
    pdf.set_line_width(0.2)
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 5.5, f" {header}", border=1, fill=True,
                 new_x=XPos.RIGHT if i < len(headers) - 1 else XPos.LMARGIN,
                 new_y=YPos.TOP if i < len(headers) - 1 else YPos.NEXT)
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(51, 65, 85)
    for row in rows:
        for i, cell in enumerate(row):
            pdf.cell(col_widths[i], 5.5, f" {(cell or 'N/A')[:42]}", border=1,
                     new_x=XPos.RIGHT if i < len(row) - 1 else XPos.LMARGIN,
                     new_y=YPos.TOP if i < len(row) - 1 else YPos.NEXT)


def create_medical_report(user, patient_info, symptoms, duration, severity, diagnosis_text):
    report_name = f"report_{user['username']}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    report_path = REPORTS_DIR / report_name
    data = parse_diagnosis_json(diagnosis_text)

    pdf = FPDF(format='A4')
    pdf.add_page()
    pdf.set_margins(12, 12, 12)
    pdf.set_auto_page_break(auto=True, margin=14)

    # Compact header
    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_text_color(13, 148, 136)
    pdf.cell(110, 7, 'MEDISCAN AI CLINIC', new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(68, 7, 'DIGITAL RX PRESCRIPTION', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    pdf.set_font('Helvetica', '', 7.5)
    pdf.cell(110, 3.5, 'Automated Diagnostics & Medical Intelligence', new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(68, 3.5, datetime.utcnow().strftime('%d %b %Y, %H:%M UTC'), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    pdf.set_draw_color(13, 148, 136)
    pdf.set_line_width(0.6)
    pdf.line(12, pdf.get_y() + 1, 198, pdf.get_y() + 1)
    pdf.ln(3)

    # Patient row
    pdf.set_font('Helvetica', 'B', 9.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(95, 5, f"Patient: {patient_info['name'].upper()}", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(83, 5, f"Age: {patient_info['age']} yrs  |  Urgency: {data.get('urgency', 'Moderate')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    pdf.ln(1)

    # Chief complaint
    _pdf_section_title(pdf, 'CHIEF COMPLAINT')
    _pdf_body_text(pdf, f"{symptoms}\nDuration: {duration}  |  Severity: {severity}")

    # Confirmed symptoms
    if data.get('symptoms'):
        _pdf_section_title(pdf, 'CONFIRMED SYMPTOMS (from consultation)')
        _pdf_bullet_list(pdf, data['symptoms'], '')

    # Diagnosis highlight box
    start_y = pdf.get_y() + 1
    pdf.set_x(14)
    pdf.set_font('Helvetica', 'B', 8.5)
    pdf.set_text_color(13, 148, 136)
    pdf.cell(182, 4, 'CLINICAL IMPRESSION / SUSPECTED DIAGNOSIS', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(14)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(15, 23, 42)
    pdf.multi_cell(182, 5, data['diagnosis'].upper())
    pdf.set_x(14)
    pdf.set_font('Helvetica', 'I', 8.5)
    pdf.set_text_color(71, 85, 105)
    pdf.multi_cell(182, 4, data['explanation'])
    end_y = pdf.get_y() + 1
    pdf.set_draw_color(13, 148, 136)
    pdf.set_fill_color(240, 253, 250)
    pdf.set_line_width(0.3)
    pdf.rect(12, start_y, 186, end_y - start_y, style='FD')
    pdf.set_y(end_y)
    pdf.ln(1)

    # Clinical summary (condensed)
    _pdf_section_title(pdf, 'DETAILED CLINICAL SUMMARY')
    summary = data.get('detailed_summary', 'No detailed summary was returned.')
    if len(summary) > 600:
        summary = summary[:597] + '...'
    _pdf_body_text(pdf, summary, line_height=3.8)

    # Primary medications
    _pdf_section_title(pdf, 'Rx  PRIMARY RECOMMENDED MEDICATIONS', 'Commonly available in India - consult a physician before use')
    if data['medications']:
        _pdf_med_table(
            pdf, [62, 30, 48, 30],
            ['Medication', 'Dosage', 'Frequency', 'Duration'],
            [[m.get('name'), m.get('dosage'), m.get('frequency'), m.get('duration')] for m in data['medications']]
        )
    else:
        _pdf_body_text(pdf, 'No specific medications prescribed. Monitor condition closely.')

    # Alternative medications (India)
    _pdf_section_title(pdf, 'ALTERNATIVE MEDICATIONS (Available in India)', 'OTC substitutes or alternatives if primary is unavailable or not tolerated')
    alt_meds = data.get('alternative_medications', [])
    if alt_meds:
        _pdf_med_table(
            pdf, [58, 28, 42, 52],
            ['Medication', 'Dosage', 'Frequency', 'Notes'],
            [[m.get('name'), m.get('dosage'), m.get('frequency'), m.get('notes', m.get('duration', ''))] for m in alt_meds]
        )
    else:
        _pdf_body_text(pdf, 'No alternative medications suggested. Discuss substitutes with your local pharmacist or physician.')

    # Home remedies — dedicated section
    _pdf_section_title(pdf, 'HOME REMEDIES & SUPPORTIVE CARE', 'Safe at-home measures alongside medical treatment')
    start_remedy_y = pdf.get_y()
    pdf.set_x(14)
    _pdf_bullet_list(pdf, data.get('home_remedies', []), 'Maintain rest, stay hydrated, and monitor symptoms closely.')
    end_remedy_y = pdf.get_y() + 1
    pdf.set_draw_color(226, 232, 240)
    pdf.set_fill_color(248, 250, 252)
    pdf.set_line_width(0.2)
    pdf.rect(12, start_remedy_y, 186, end_remedy_y - start_remedy_y, style='D')
    pdf.set_y(end_remedy_y)
    pdf.ln(0.5)

    # Lifestyle & allergies side by side feel — stacked compact
    _pdf_section_title(pdf, 'LIFESTYLE & PREVENTIVE ADVICE')
    _pdf_bullet_list(pdf, data.get('habit_changes', []), 'Avoid triggers, maintain hydration, and follow regular sleep and meal routines.')

    _pdf_section_title(pdf, 'ALLERGIES & DRUG INTERACTIONS')
    _pdf_bullet_list(pdf, data.get('possible_allergies', []), 'Review current medications and known allergies before taking any new medicine.')

    # Next steps
    if data.get('next_steps'):
        _pdf_section_title(pdf, 'RECOMMENDED NEXT STEPS')
        _pdf_bullet_list(pdf, data['next_steps'], '')

    # Red flags
    if data.get('red_flags'):
        start_warning_y = pdf.get_y() + 1
        pdf.set_x(14)
        pdf.set_font('Helvetica', 'B', 8.5)
        pdf.set_text_color(185, 28, 28)
        pdf.cell(182, 4, 'WARNINGS & RED FLAGS - Seek immediate medical attention if present:', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('Helvetica', '', 8)
        for flag in data['red_flags']:
            pdf.set_x(14)
            pdf.multi_cell(182, 3.6, f"  -  {flag}")
        end_warning_y = pdf.get_y() + 1
        pdf.set_draw_color(239, 68, 68)
        pdf.set_fill_color(254, 242, 242)
        pdf.set_line_width(0.25)
        pdf.rect(12, start_warning_y, 186, end_warning_y - start_warning_y, style='FD')
        pdf.set_y(end_warning_y)

    # Footer — flows naturally, no forced blank space
    pdf.ln(4)
    pdf.set_draw_color(226, 232, 240)
    pdf.set_line_width(0.3)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(2)
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(186, 4, 'DR. AI CONSULTANT', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    pdf.set_font('Helvetica', 'I', 7)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(186, 3.5, 'Electronically Generated via MediScan AI', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    pdf.ln(1)
    pdf.set_font('Helvetica', 'I', 6.5)
    pdf.set_text_color(156, 163, 175)
    pdf.multi_cell(186, 3, 'Disclaimer: This AI-assisted report is based on user-reported symptoms for informational support only. It does not replace in-person doctor consultation, physical examination, or clinical tests.', align='C')

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

        session['consultation'] = {
            'symptoms': symptoms,
            'duration': duration,
            'severity': severity,
            'answers': [],
            'last_question': '',
        }

        return redirect(url_for('doctor_consultation'))

    return render_template('new_diagnosis.html', user=user, patient=patient)


@app.route('/doctor-consultation', methods=['GET', 'POST'])
def doctor_consultation():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    conn = get_db_connection()
    patient = conn.execute('SELECT * FROM patients WHERE user_id = ?', (user['id'],)).fetchone()
    # Fetch past clinical diagnoses to show in sidebar and send to GPT
    past_history = conn.execute(
        'SELECT symptoms, severity, created_at, diagnosis_text FROM disease_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
        (user['id'],)
    ).fetchall()
    conn.close()

    if not patient:
        flash('Please complete your profile before using diagnosis.', 'error')
        return redirect(url_for('profile'))

    session_data = session.get('consultation')
    if not session_data:
        flash('Start a new diagnosis to begin the doctor interview.', 'error')
        return redirect(url_for('new_diagnosis'))

    # Format past history records for both rendering and passing to GPT
    past_diagnoses = []
    for r in past_history:
        diag_data = parse_diagnosis_json(r['diagnosis_text'])
        try:
            date_obj = datetime.strptime(r['created_at'], '%Y-%m-%d %H:%M:%S')
            date_str = date_obj.strftime('%d %b %Y')
        except Exception:
            date_str = r['created_at']
        past_diagnoses.append({
            'date': date_str,
            'symptoms': r['symptoms'],
            'severity': r['severity'],
            'diagnosis': diag_data.get('diagnosis', 'Unknown condition')
        })

    if past_diagnoses:
        history_summary = "\n".join(f"- On {item['date']}: Presented with '{item['symptoms']}' ({item['severity']} severity). Suspected Diagnosis: '{item['diagnosis']}'." for item in past_diagnoses)
    else:
        history_summary = "No previous clinical history on record."

    if request.method == 'POST':
        answer = request.form.get('answer', '').strip()
        if not answer:
            flash('Please answer the doctor question.', 'error')
            return redirect(url_for('doctor_consultation'))

        session_data['answers'].append({
            'question': session_data.get('last_question', 'Follow-up question'),
            'answer': answer,
        })
        session['consultation'] = session_data

        # Only finalize if we have asked at least MIN_CONSULTATION_QUESTIONS and hit max
        if should_finalize_consultation(session_data['answers']):
            history_id = finalize_diagnosis(user, patient, session_data)
            session.pop('consultation', None)
            flash('AI consultation completed after gathering comprehensive clinical details.', 'success')
            return redirect(url_for('diagnosis_result', history_id=history_id))

        patient_info = build_patient_context(patient)
        doctor_result = query_doctor_question(patient_info, session_data['symptoms'], session_data['duration'], session_data['severity'], session_data['answers'], history_summary=history_summary)

        # Check if doctor is ready to diagnose, but only after MIN_CONSULTATION_QUESTIONS
        if doctor_result.get('ready_to_diagnose') and len(session_data['answers']) >= MIN_CONSULTATION_QUESTIONS:
            history_id = finalize_diagnosis(user, patient, session_data)
            session.pop('consultation', None)
            flash('AI consultation completed and your detailed report is ready.', 'success')
            return redirect(url_for('diagnosis_result', history_id=history_id))

        session_data['last_question'] = doctor_result.get('question', '')
        session['consultation'] = session_data

    if should_finalize_consultation(session_data['answers']):
        history_id = finalize_diagnosis(user, patient, session_data)
        session.pop('consultation', None)
        flash('AI consultation completed after gathering comprehensive clinical details.', 'success')
        return redirect(url_for('diagnosis_result', history_id=history_id))

    patient_info = build_patient_context(patient)
    doctor_result = query_doctor_question(patient_info, session_data['symptoms'], session_data['duration'], session_data['severity'], session_data['answers'], history_summary=history_summary)

    # Check if doctor is ready to diagnose, but only after MIN_CONSULTATION_QUESTIONS
    if doctor_result.get('ready_to_diagnose') and len(session_data['answers']) >= MIN_CONSULTATION_QUESTIONS:
        history_id = finalize_diagnosis(user, patient, session_data)
        session.pop('consultation', None)
        flash('AI consultation completed and your detailed report is ready.', 'success')
        return redirect(url_for('diagnosis_result', history_id=history_id))

    session_data['last_question'] = doctor_result.get('question', '')
    session['consultation'] = session_data

    # Build chat history for chat UI
    chat_history = []
    # Initial AI question
    if session_data['answers']:
        for idx, qa in enumerate(session_data['answers']):
            if qa['question']:
                chat_history.append({'role': 'ai', 'text': qa['question']})
            chat_history.append({'role': 'user', 'text': qa['answer']})
        # Add the current AI question if not ready to diagnose
        if session_data['last_question']:
            chat_history.append({'role': 'ai', 'text': session_data['last_question']})
    else:
        if session_data['last_question']:
            chat_history.append({'role': 'ai', 'text': session_data['last_question']})

    return render_template('doctor_consultation.html', user=user, patient=patient, chat_history=chat_history, answer_count=len(session_data['answers']), past_diagnoses=past_diagnoses)


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
