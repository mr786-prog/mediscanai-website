# MediScan AI Website

A Flask-based MediScan AI web application with user authentication, patient profile management, GPT-powered medical diagnosis, and PDF medical report generation.

## Setup

1. Create a virtual environment and activate it.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env` and update `OPENROUTER_API_KEY` with your API key.
4. Run the app:
   ```bash
   python app.py
   ```
5. Open `http://127.0.0.1:5000` in your browser.

## Features

- Register and login with username/password
- Create and update patient profile
- Submit symptoms for AI-powered diagnosis
- Generate professional PDF medical reports using FPDF
- View diagnosis history and download reports
- Responsive 3D animation style frontend
