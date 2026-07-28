import random
import string
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, Workspace, Class, Quiz, Question, Option, QuizAttempt, ClassEnrollment, User
from functools import wraps

teacher_bp = Blueprint('teacher', __name__, url_prefix='/quorra/teacher')

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['GURU', 'SUPERUSER']:
            flash('Akses khusus Guru/Superuser.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def generate_unique_class_code():
    while True:
        code = 'QUORRA-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        if not Class.query.filter_by(code=code).first():
            return code

@teacher_bp.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    workspaces = Workspace.query.filter_by(owner_id=current_user.id).all()
    all_classes = []
    for ws in workspaces:
        all_classes.extend(ws.classes.all())
    
    total_classes = len(all_classes)
    total_quizzes = sum(c.quizzes.count() for c in all_classes)
    
    # Calculate enrolled students count
    enrolled_student_ids = set()
    for c in all_classes:
        for e in c.enrollments.all():
            enrolled_student_ids.add(e.student_id)

    return render_template(
        'teacher/dashboard.html',
        workspaces=workspaces,
        classes=all_classes,
        total_classes=total_classes,
        total_quizzes=total_quizzes,
        total_students=len(enrolled_student_ids)
    )

@teacher_bp.route('/workspace/create', methods=['POST'])
@login_required
@teacher_required
def create_workspace():
    name = request.form.get('name')
    description = request.form.get('description')
    if name:
        ws = Workspace(name=name, description=description, owner_id=current_user.id)
        db.session.add(ws)
        db.session.commit()
        flash(f'Workspace "{name}" berhasil dibuat!', 'success')
    return redirect(url_for('teacher.dashboard'))

@teacher_bp.route('/workspace/delete/<int:ws_id>', methods=['POST'])
@login_required
@teacher_required
def delete_workspace(ws_id):
    ws = Workspace.query.get_or_404(ws_id)
    if ws.owner_id != current_user.id and current_user.role != 'SUPERUSER':
        flash('Anda tidak memiliki izin menghapus workspace ini.', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    db.session.delete(ws)
    db.session.commit()
    flash('Workspace berhasil dihapus.', 'info')
    return redirect(url_for('teacher.dashboard'))

@teacher_bp.route('/class/create', methods=['POST'])
@login_required
@teacher_required
def create_class():
    workspace_id = request.form.get('workspace_id')
    name = request.form.get('name')
    subject = request.form.get('subject')

    ws = Workspace.query.get_or_404(workspace_id)
    if ws.owner_id != current_user.id and current_user.role != 'SUPERUSER':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('teacher.dashboard'))

    code = generate_unique_class_code()
    new_class = Class(workspace_id=ws.id, name=name, subject=subject, code=code)
    db.session.add(new_class)
    db.session.commit()

    flash(f'Kelas "{name}" berhasil dibuat! Kode Join: {code}', 'success')
    return redirect(url_for('teacher.class_detail', class_id=new_class.id))

@teacher_bp.route('/class/<int:class_id>')
@login_required
@teacher_required
def class_detail(class_id):
    c = Class.query.get_or_404(class_id)
    quizzes = c.quizzes.order_by(Quiz.created_at.desc()).all()
    enrollments = c.enrollments.all()
    return render_template('teacher/class_detail.html', class_obj=c, quizzes=quizzes, enrollments=enrollments)

@teacher_bp.route('/class/delete/<int:class_id>', methods=['POST'])
@login_required
@teacher_required
def delete_class(class_id):
    c = Class.query.get_or_404(class_id)
    db.session.delete(c)
    db.session.commit()
    flash('Kelas berhasil dihapus.', 'info')
    return redirect(url_for('teacher.dashboard'))

@teacher_bp.route('/quiz/create/<int:class_id>', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_quiz(class_id):
    c = Class.query.get_or_404(class_id)
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        quiz_type = request.form.get('quiz_type', 'KUIS') # QUEST, KUIS, UJIAN
        time_limit_minutes = int(request.form.get('time_limit_minutes', 0))
        max_attempts = int(request.form.get('max_attempts', 1))
        exp_reward = int(request.form.get('exp_reward', 50))

        time_limit_seconds = time_limit_minutes * 60

        new_quiz = Quiz(
            class_id=c.id,
            title=title,
            description=description,
            quiz_type=quiz_type,
            time_limit_seconds=time_limit_seconds,
            max_attempts=max_attempts,
            exp_reward=exp_reward
        )
        db.session.add(new_quiz)
        db.session.commit()

        flash(f'{quiz_type} "{title}" berhasil dibuat! Silakan tambahkan soal.', 'success')
        return redirect(url_for('teacher.quiz_builder', quiz_id=new_quiz.id))

    return render_template('teacher/create_quiz.html', class_obj=c)

import json
import uuid
import os
import urllib.request
from flask import current_app
from models import SystemConfig

def save_upload_file(file_obj, subfolder):
    if not file_obj or file_obj.filename == '':
        return None
    allowed_exts = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    ext = file_obj.filename.rsplit('.', 1)[-1].lower() if '.' in file_obj.filename else ''
    if ext not in allowed_exts:
        return None
    
    filename = f"{uuid.uuid4().hex[:12]}_{secure_filename(file_obj.filename)}"
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, filename)
    file_obj.save(filepath)
    return f"uploads/{subfolder}/{filename}"

import urllib.error

def fetch_valid_gemini_models(api_key):
    """Fetch exact valid generateContent models directly from Google Gemini API."""
    if not api_key:
        return []
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode('utf-8')
            res_json = json.loads(res_body)
            models_raw = res_json.get('models', [])
            valid_models = []
            for m in models_raw:
                methods = m.get('supportedGenerationMethods', [])
                if 'generateContent' in methods:
                    name = m.get('name', '').replace('models/', '')
                    valid_models.append(name)
            return valid_models
    except Exception as e:
        print("Notice: Error fetching dynamic Gemini models list:", e)
        return []

def call_gemini_ai(material_text, num_questions, api_key, model_name):
    # Fetch valid models directly from Google API if possible
    api_models = fetch_valid_gemini_models(api_key)
    
    models_to_try = []
    
    if api_models:
        # 1. Exact match
        if model_name in api_models:
            models_to_try.append(model_name)
        # 2. Substring match (e.g. gemini-1.5-flash -> gemini-1.5-flash-latest)
        for m in api_models:
            if (model_name in m or m in model_name) and m not in models_to_try:
                models_to_try.append(m)
        # 3. Add remaining valid models from API key
        for m in api_models:
            if m not in models_to_try:
                models_to_try.append(m)
    else:
        # Fallback static candidates if API model listing fails
        static_candidates = [
            model_name,
            f"{model_name}-latest",
            'gemini-1.5-flash-latest',
            'gemini-1.5-pro-latest',
            'gemini-2.0-flash-exp',
            'gemini-1.5-flash',
            'gemini-1.5-pro',
            'gemini-2.0-flash'
        ]
        for candidate in static_candidates:
            if candidate not in models_to_try:
                models_to_try.append(candidate)

    last_error = ""

    for current_model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={api_key}"
        
        prompt = f"""
Anda adalah pembuat soal kuis profesional. Buatkan tepat {num_questions} soal pilihan ganda (masing-masing 5 opsi: A, B, C, D, E) berdasarkan materi berikut:

MATERI:
{material_text}

SYARAT MUTLAK:
1. Berikan respon HANYA MURNI TEKS JSON ARRAY (tanpa tanda markdown ```json atau penjelasan teks apapun).
2. Setiap objek dalam array harus memiliki format berikut:
[
  {{
    "question_text": "Pertanyaan soal...",
    "points": 10,
    "options": [
      {{"letter": "A", "text": "Pilihan jawaban A", "is_correct": false}},
      {{"letter": "B", "text": "Pilihan jawaban B", "is_correct": true}},
      {{"letter": "C", "text": "Pilihan jawaban C", "is_correct": false}},
      {{"letter": "D", "text": "Pilihan jawaban D", "is_correct": false}},
      {{"letter": "E", "text": "Pilihan jawaban E", "is_correct": false}}
    ]
  }}
]
"""

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        
        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body)
                raw_text = res_json['candidates'][0]['content']['parts'][0]['text']
                
                raw_text = raw_text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                
                questions_data = json.loads(raw_text.strip())
                model_note = f" (menggunakan model {current_model})" if current_model != model_name else f" ({current_model})"
                return True, questions_data, model_note
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode('utf-8')
                err_json = json.loads(err_body)
                msg = err_json.get('error', {}).get('message', str(e))
            except Exception:
                msg = str(e)
            last_error = f"Model {current_model} error [{e.code}]: {msg}"
        except Exception as e:
            last_error = str(e)

    return False, [], last_error


@teacher_bp.route('/quiz/builder/<int:quiz_id>', methods=['GET', 'POST'])
@login_required
@teacher_required
def quiz_builder(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)

    if request.method == 'POST':
        question_text = request.form.get('question_text')
        points = int(request.form.get('points', 10))
        correct_option = request.form.get('correct_option') # A, B, C, D, E

        # Handle Question Image Upload
        q_image = save_upload_file(request.files.get('question_image'), 'questions')

        option_a = request.form.get('option_a')
        option_b = request.form.get('option_b')
        option_c = request.form.get('option_c')
        option_d = request.form.get('option_d')
        option_e = request.form.get('option_e')

        opt_a_img = save_upload_file(request.files.get('option_a_image'), 'options')
        opt_b_img = save_upload_file(request.files.get('option_b_image'), 'options')
        opt_c_img = save_upload_file(request.files.get('option_c_image'), 'options')
        opt_d_img = save_upload_file(request.files.get('option_d_image'), 'options')
        opt_e_img = save_upload_file(request.files.get('option_e_image'), 'options')

        if question_text and (option_a or opt_a_img) and (option_b or opt_b_img):
            q = Question(quiz_id=quiz.id, question_text=question_text, points=points, image_path=q_image)
            db.session.add(q)
            db.session.commit()

            opts_data = [
                ('A', option_a, opt_a_img),
                ('B', option_b, opt_b_img),
                ('C', option_c, opt_c_img),
                ('D', option_d, opt_d_img),
                ('E', option_e, opt_e_img),
            ]

            opts_to_add = []
            for letter, txt, img in opts_data:
                if txt or img:
                    opts_to_add.append(
                        Option(
                            question_id=q.id,
                            option_letter=letter,
                            option_text=txt or '',
                            image_path=img,
                            is_correct=(correct_option == letter)
                        )
                    )
            db.session.add_all(opts_to_add)
            db.session.commit()
            flash('Soal berhasil ditambahkan!', 'success')
            return redirect(url_for('teacher.quiz_builder', quiz_id=quiz.id))

    questions = quiz.questions.all()
    
    # Check if Gemini AI is configured
    gemini_key = SystemConfig.query.filter_by(key='gemini_api_key').first()
    gemini_model = SystemConfig.query.filter_by(key='gemini_model').first()
    ai_configured = bool(gemini_key and gemini_key.value)

    return render_template(
        'teacher/quiz_builder.html',
        quiz=quiz,
        questions=questions,
        ai_configured=ai_configured,
        ai_model=gemini_model.value if gemini_model else 'gemini-2.5-flash'
    )


@teacher_bp.route('/quiz/<int:quiz_id>/generate-ai', methods=['POST'])
@login_required
@teacher_required
def generate_ai_questions(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)

    material_text = request.form.get('material_text', '').strip()
    num_questions = int(request.form.get('num_questions', 3))
    points_per_q = int(request.form.get('points_per_q', 10))

    if not material_text:
        flash('Mohon masukkan teks materi pembelajaran.', 'warning')
        return redirect(url_for('teacher.quiz_builder', quiz_id=quiz.id))

    gemini_key_obj = SystemConfig.query.filter_by(key='gemini_api_key').first()
    gemini_model_obj = SystemConfig.query.filter_by(key='gemini_model').first()

    if not gemini_key_obj or not gemini_key_obj.value:
        flash('Superuser belum mengeset Gemini API Key di Command Center!', 'danger')
        return redirect(url_for('teacher.quiz_builder', quiz_id=quiz.id))

    model_name = gemini_model_obj.value if gemini_model_obj and gemini_model_obj.value else 'gemini-2.5-flash'

    generation_mode = request.form.get('generation_mode', 'ADD') # ADD or REPLACE

    success, questions_data, model_note = call_gemini_ai(material_text, num_questions, gemini_key_obj.value, model_name)

    if not success:
        flash(f'Gagal melakukan generate soal dengan AI: {model_note}', 'danger')
        return redirect(url_for('teacher.quiz_builder', quiz_id=quiz.id))

    # If mode is REPLACE, delete existing questions first
    if generation_mode == 'REPLACE':
        Question.query.filter_by(quiz_id=quiz.id).delete()
        db.session.commit()

    added_count = 0
    for q_item in questions_data:
        q_text = q_item.get('question_text')
        if not q_text:
            continue
        
        q_points = q_item.get('points', points_per_q)
        q_obj = Question(quiz_id=quiz.id, question_text=q_text, points=q_points)
        db.session.add(q_obj)
        db.session.commit()

        opts_list = q_item.get('options', [])
        for opt in opts_list:
            letter = opt.get('letter', 'A')
            text = opt.get('text', '')
            is_corr = opt.get('is_correct', False)

            o_obj = Option(
                question_id=q_obj.id,
                option_letter=letter,
                option_text=text,
                is_correct=is_corr
            )
            db.session.add(o_obj)
        
        added_count += 1
    
    db.session.commit()

    mode_text = "menggantikan seluruh soal lama" if generation_mode == 'REPLACE' else "menambahkan ke daftar soal"
    flash(f'Berhasil generate {added_count} soal baru ({mode_text}) menggunakan AI{model_note}!', 'success')
    return redirect(url_for('teacher.quiz_builder', quiz_id=quiz.id))


@teacher_bp.route('/question/edit/<int:question_id>', methods=['POST'])
@login_required
@teacher_required
def edit_question(question_id):
    q = Question.query.get_or_404(question_id)
    quiz_id = q.quiz_id

    question_text = request.form.get('question_text')
    points = int(request.form.get('points', 10))
    correct_option = request.form.get('correct_option')

    # Optional image update
    q_image = save_upload_file(request.files.get('question_image'), 'questions')
    if q_image:
        q.image_path = q_image

    q.question_text = question_text
    q.points = points

    # Options A-E
    opts_map = {opt.option_letter: opt for opt in q.options.all()}

    for letter in ['A', 'B', 'C', 'D', 'E']:
        txt = request.form.get(f'option_{letter.lower()}')
        img = save_upload_file(request.files.get(f'option_{letter.lower()}_image'), 'options')
        
        if letter in opts_map:
            opt = opts_map[letter]
            if txt:
                opt.option_text = txt
            if img:
                opt.image_path = img
            opt.is_correct = (correct_option == letter)
        elif txt or img:
            new_opt = Option(
                question_id=q.id,
                option_letter=letter,
                option_text=txt or '',
                image_path=img,
                is_correct=(correct_option == letter)
            )
            db.session.add(new_opt)

    db.session.commit()
    flash('Soal berhasil diperbarui!', 'success')
    return redirect(url_for('teacher.quiz_builder', quiz_id=quiz_id))


@teacher_bp.route('/question/delete/<int:question_id>', methods=['POST'])
@login_required
@teacher_required
def delete_question(question_id):
    q = Question.query.get_or_404(question_id)
    quiz_id = q.quiz_id
    db.session.delete(q)
    db.session.commit()
    flash('Soal berhasil dihapus.', 'info')
    return redirect(url_for('teacher.quiz_builder', quiz_id=quiz_id))

@teacher_bp.route('/quiz/delete/<int:quiz_id>', methods=['POST'])
@login_required
@teacher_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    class_id = quiz.class_id
    db.session.delete(quiz)
    db.session.commit()
    flash('Quiz/Quest berhasil dihapus.', 'info')
    return redirect(url_for('teacher.class_detail', class_id=class_id))

@teacher_bp.route('/analytics/class/<int:class_id>')
@login_required
@teacher_required
def class_analytics(class_id):
    c = Class.query.get_or_404(class_id)
    quizzes = c.quizzes.all()
    quiz_ids = [q.id for q in quizzes]
    
    attempts = QuizAttempt.query.filter(QuizAttempt.quiz_id.in_(quiz_ids)).order_by(QuizAttempt.completed_at.asc()).all() if quiz_ids else []
    enrollments = c.enrollments.all()

    # Calculate average class score
    scores = [a.score for a in attempts]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    max_score = max(scores) if scores else 0
    passed_count = sum(1 for s in scores if s >= 60)

    # Per-quiz analytics
    quiz_analytics = []
    for q in quizzes:
        q_attempts = [a for a in attempts if a.quiz_id == q.id]
        q_avg = round(sum(a.score for a in q_attempts) / len(q_attempts), 1) if q_attempts else 0
        quiz_analytics.append({
            'quiz_title': q.title,
            'quiz_type': q.quiz_type,
            'attempt_count': len(q_attempts),
            'avg_score': q_avg
        })

    return render_template(
        'teacher/analytics.html',
        class_obj=c,
        quizzes=quizzes,
        attempts=attempts,
        enrollments=enrollments,
        avg_score=avg_score,
        max_score=max_score,
        passed_count=passed_count,
        quiz_analytics=quiz_analytics
    )

@teacher_bp.route('/attempt/delete/<int:attempt_id>', methods=['POST'])
@login_required
@teacher_required
def delete_attempt(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    class_id = attempt.quiz.class_id
    db.session.delete(attempt)
    db.session.commit()
    flash('Nilai percobaan siswa berhasil dihapus / di-reset.', 'success')
    return redirect(url_for('teacher.class_analytics', class_id=class_id))
