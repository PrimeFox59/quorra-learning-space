import random
import string
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, Workspace, Class, Quiz, Question, Option, QuizAttempt, StudentAnswer, ClassEnrollment, User, log_public_activity

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

        log_public_activity(
            event_type='CREATE_WORKSPACE',
            title='Workspace Baru!',
            message=f'Guru {current_user.username} mendirikan workspace baru: "{name}"',
            icon_class='bi-folder-plus',
            badge_color='purple'
        )

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

    log_public_activity(
        event_type='CREATE_CLASS',
        title='Kelas Pembelajaran Baru!',
        message=f'Guru {current_user.username} membuka kelas baru: "{name}" (Kode: {code})',
        icon_class='bi-door-open-fill',
        badge_color='emerald'
    )

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

@teacher_bp.route('/class/edit/<int:class_id>', methods=['POST'])
@login_required
@teacher_required
def edit_class(class_id):
    c = Class.query.get_or_404(class_id)
    if c.workspace.owner_id != current_user.id and current_user.role != 'SUPERUSER':
        flash('Anda tidak memiliki izin mengedit kelas ini.', 'danger')
        return redirect(url_for('teacher.dashboard'))

    name = request.form.get('name', '').strip()
    subject = request.form.get('subject', '').strip()

    if name:
        c.name = name
    if subject:
        c.subject = subject

    db.session.commit()
    flash(f'Kelas "{c.name}" berhasil diperbarui!', 'success')
    return redirect(request.referrer or url_for('teacher.dashboard'))


@teacher_bp.route('/class/delete/<int:class_id>', methods=['POST'])
@login_required
@teacher_required
def delete_class(class_id):
    c = Class.query.get_or_404(class_id)
    if c.workspace.owner_id != current_user.id and current_user.role != 'SUPERUSER':
        flash('Anda tidak memiliki izin menghapus kelas ini.', 'danger')
        return redirect(url_for('teacher.dashboard'))

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

@teacher_bp.route('/quiz/edit/<int:quiz_id>', methods=['POST'])
@login_required
@teacher_required
def edit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    title = request.form.get('title')
    description = request.form.get('description')
    quiz_type = request.form.get('quiz_type', 'KUIS')
    time_limit_minutes = int(request.form.get('time_limit_minutes', 0))
    max_attempts = int(request.form.get('max_attempts', 1))
    exp_reward = int(request.form.get('exp_reward', 50))

    if title:
        quiz.title = title
        quiz.description = description
        quiz.quiz_type = quiz_type
        quiz.time_limit_seconds = time_limit_minutes * 60
        quiz.max_attempts = max_attempts
        quiz.exp_reward = exp_reward
        db.session.commit()
        flash(f'Kuis/Quest "{title}" berhasil diperbarui!', 'success')
    else:
        flash('Judul kuis tidak boleh kosong.', 'danger')

    redirect_to = request.form.get('redirect_to', 'class_detail')
    if redirect_to == 'quiz_builder':
        return redirect(url_for('teacher.quiz_builder', quiz_id=quiz.id))
    return redirect(url_for('teacher.class_detail', class_id=quiz.class_id))

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

    # Student Timeline Analytics (per-siswa berdasarkan timeline pengerjaan)
    # Palette warna menarik untuk setiap siswa
    color_palette = [
        '#38bdf8', '#a855f7', '#f43f5e', '#10b981', '#f59e0b',
        '#ec4899', '#6366f1', '#14b8a6', '#84cc16', '#eab308'
    ]

    # Map siswa ke list attempt
    student_map = {}
    for a in attempts:
        s_id = a.student_id
        if s_id not in student_map:
            uname = a.student.username
            # Buat inisial (misal: "Ahmad Rizky" -> "AR", "Fahmi" -> "F")
            parts = uname.strip().split()
            if len(parts) >= 2:
                initials = (parts[0][0] + parts[1][0]).upper()
            elif len(parts) == 1 and len(parts[0]) >= 2:
                initials = parts[0][:2].upper()
            else:
                initials = uname[:2].upper()

            student_map[s_id] = {
                'student_id': s_id,
                'name': uname,
                'initials': initials,
                'attempts': []
            }
        
        student_map[s_id]['attempts'].append({
            'score': a.score,
            'quiz_title': a.quiz.title,
            'attempt_number': a.attempt_number,
            'date': a.completed_at.strftime('%d %b %H:%M')
        })

    student_timeline_analytics = []
    color_idx = 0
    for s_id, s_data in student_map.items():
        s_data['color'] = color_palette[color_idx % len(color_palette)]
        color_idx += 1
        student_timeline_analytics.append(s_data)

    return render_template(
        'teacher/analytics.html',
        class_obj=c,
        quizzes=quizzes,
        attempts=attempts,
        enrollments=enrollments,
        avg_score=avg_score,
        max_score=max_score,
        passed_count=passed_count,
        quiz_analytics=quiz_analytics,
        student_timeline_analytics=student_timeline_analytics
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

@teacher_bp.route('/attempt/detail/<int:attempt_id>')
@login_required
@teacher_required
def view_attempt_detail(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    quiz = attempt.quiz
    questions = quiz.questions.all()
    
    # Ambil jawaban tersimpan murid
    saved_answers = {ans.question_id: ans for ans in attempt.answers.all()}
    
    detailed_results = []
    for q in questions:
        ans = saved_answers.get(q.id)
        selected_option = ans.selected_option if ans else None
        correct_option = next((opt for opt in q.options.all() if opt.is_correct), None)
        
        # Jika pengerjaan kuis dilakukan sebelum fitur StudentAnswer (skor sempurna/100%), perhitungkan sebagai kunci jawaban
        if not ans and attempt.score == 100:
            selected_option = correct_option
            is_corr = True
            is_ans = True
        else:
            is_corr = ans.is_correct if ans else False
            is_ans = selected_option is not None

        detailed_results.append({
            'question': q,
            'selected_option': selected_option,
            'correct_option': correct_option,
            'is_correct': is_corr,
            'is_answered': is_ans
        })

    return render_template(
        'teacher/attempt_detail.html',
        attempt=attempt,
        quiz=quiz,
        student=attempt.student,
        detailed_results=detailed_results
    )



def calculate_student_analytics(student, class_id):
    c = Class.query.get_or_404(class_id)
    quizzes = c.quizzes.all()
    quiz_ids = [q.id for q in quizzes]

    attempts = QuizAttempt.query.filter(
        QuizAttempt.quiz_id.in_(quiz_ids),
        QuizAttempt.student_id == student.id
    ).order_by(QuizAttempt.completed_at.asc()).all() if quiz_ids else []

    total_attempts = len(attempts)
    if not total_attempts:
        return {
            'has_data': False,
            'total_attempts': 0,
            'avg_score': 0,
            'radar_scores': [0, 0, 0, 0, 0],
            'strengths': [],
            'weaknesses': [],
            'recommendations': [],
            'quiz_breakdown': []
        }

    scores = [a.score for a in attempts]
    avg_score = round(sum(scores) / total_attempts, 1)

    # 1. Pemahaman Konsep (Berdasarkan persentase total jawaban benar)
    total_q = sum(a.total_questions for a in attempts)
    total_corr = sum(a.correct_answers for a in attempts)
    concept_score = round((total_corr / total_q) * 100) if total_q > 0 else avg_score

    # 2. Kecepatan (Rata-rata detik per soal vs standar 60 detik)
    total_time = sum(a.time_taken_seconds for a in attempts)
    avg_sec_per_q = (total_time / total_q) if total_q > 0 else 60
    if avg_sec_per_q <= 20:
        speed_score = 95
    elif avg_sec_per_q <= 40:
        speed_score = 80
    elif avg_sec_per_q <= 60:
        speed_score = 65
    else:
        speed_score = 45

    # 3. Ketelitian (Perbandingan skor pertama vs skor rata-rata)
    first_attempts = {}
    for a in attempts:
        if a.quiz_id not in first_attempts:
            first_attempts[a.quiz_id] = a.score
    first_avg = sum(first_attempts.values()) / len(first_attempts) if first_attempts else avg_score
    precision_score = round(min(100, max(30, first_avg * 0.7 + concept_score * 0.3)))

    # 4. Konsistensi (Deviasi skor antar percobaan)
    if len(scores) > 1:
        variance = sum((x - avg_score) ** 2 for x in scores) / len(scores)
        std_dev = variance ** 0.5
        consistency_score = round(min(100, max(30, 100 - (std_dev * 1.5))))
    else:
        consistency_score = 85

    # 5. Ketahanan Ujian (Performa pada quiz tipe UJIAN)
    ujian_attempts = [a for a in attempts if a.quiz.quiz_type == 'UJIAN']
    if ujian_attempts:
        stamina_score = round(sum(a.score for a in ujian_attempts) / len(ujian_attempts))
    else:
        stamina_score = round(avg_score * 0.9)

    radar_scores = [
        int(concept_score),
        int(precision_score),
        int(speed_score),
        int(consistency_score),
        int(stamina_score)
    ]

    # Analisis Kualitatif & Rekomendasi Diagnostik
    strengths = []
    weaknesses = []
    recommendations = []

    if concept_score >= 80:
        strengths.append("Daya Tangkap Tinggi: Sangat menguasai materi inti & konsep dasar.")
    elif concept_score >= 60:
        strengths.append("Cukup Memahami Materi: Memiliki dasar pengetahuan yang memadai.")

    if speed_score >= 80:
        strengths.append("Respon Cepat: Mampu mengambil keputusan & menyelesaikan soal secara efisien.")
    
    if consistency_score >= 80:
        strengths.append("Konsisten: Menunjukkan stabilitas performa tinggi dari waktu ke waktu.")

    if precision_score >= 85:
        strengths.append("Ketelitian Tinggi: Cenderung jarang melakukan kesalahan akibat terburu-buru.")

    if not strengths:
        strengths.append("Motivasi Belajar: Terus berusaha menyelesaikan misi evaluasi.")

    # Kelemahan
    if concept_score < 65:
        weaknesses.append("Penguasaan Konsep Belum Optimal: Perlu pendalaman materi & remedial.")

    if precision_score < 70:
        weaknesses.append("Kurang Teliti pada Percobaan Awal: Sering salah di percobaan pertama.")

    if speed_score < 55:
        weaknesses.append("Manajemen Waktu Lambat: Membutuhkan waktu lebih lama per nomor soal.")

    if consistency_score < 60:
        weaknesses.append("Performa Fluktuatif: Hasil evaluasi belum stabil di setiap materi.")

    if not weaknesses:
        weaknesses.append("Tidak ada kelemahan signifikan. Pertahankan ritme belajar saat ini!")

    # Rekomendasi
    if concept_score < 70:
        recommendations.append("Berikan rangkuman materi singkat / flashcard sebelum mencoba kuis ulang.")
    if precision_score < 70:
        recommendations.append("Himbau murid untuk membaca ulang setiap pilihan jawaban sebelum submit.")
    if speed_score < 60:
        recommendations.append("Latih dengan kuis batas waktu bertahap untuk meningkatkan kelincahan berpikir.")
    if consistency_score >= 80 and concept_score >= 80:
        recommendations.append("Siap untuk materi tingkat lanjut (Advanced Quest / Soal Pengayaan).")
    elif not recommendations:
        recommendations.append("Lanjutkan ke modul pembelajaran berikutnya untuk meningkatkan level.")

    # Analisis Kontekstual Soal & Jawaban Murid
    attempt_ids = [a.id for a in attempts]
    student_answers = StudentAnswer.query.filter(StudentAnswer.attempt_id.in_(attempt_ids)).all() if attempt_ids else []

    quiz_context_map = {}
    correct_questions = []
    incorrect_questions = []

    for sa in student_answers:
        q = sa.question
        q_text_short = (q.question_text[:70] + "...") if len(q.question_text) > 70 else q.question_text
        q_quiz_title = q.quiz.title

        if q_quiz_title not in quiz_context_map:
            quiz_context_map[q_quiz_title] = {'correct': 0, 'total': 0, 'questions': []}

        quiz_context_map[q_quiz_title]['total'] += 1
        if sa.is_correct:
            quiz_context_map[q_quiz_title]['correct'] += 1
            correct_questions.append({
                'quiz': q_quiz_title,
                'question': q_text_short,
                'user_choice': sa.selected_option.option_text if sa.selected_option else 'Tidak diisi'
            })
        else:
            incorrect_option_text = sa.selected_option.option_text if sa.selected_option else 'Tidak diisi'
            correct_opt = next((opt for opt in q.options.all() if opt.is_correct), None)
            correct_option_text = correct_opt.option_text if correct_opt else '-'

            incorrect_questions.append({
                'quiz': q_quiz_title,
                'question': q_text_short,
                'user_choice': incorrect_option_text,
                'correct_choice': correct_option_text
            })

    # Analisis kontekstual per materi kuis
    context_insights = []
    for quiz_t, data_q in quiz_context_map.items():
        acc = round((data_q['correct'] / data_q['total']) * 100) if data_q['total'] > 0 else 0
        if acc >= 80:
            status = "Sangat Dikuasai"
            badge_class = "text-emerald-400 border-emerald-500/40 bg-emerald-950/60"
        elif acc >= 60:
            status = "Cukup Dikuasai"
            badge_class = "text-sky-400 border-sky-500/40 bg-sky-950/60"
        else:
            status = "Perlu Remedial"
            badge_class = "text-rose-400 border-rose-500/40 bg-rose-950/60"

        context_insights.append({
            'quiz_title': quiz_t,
            'accuracy': acc,
            'total_answered': data_q['total'],
            'correct_count': data_q['correct'],
            'status': status,
            'badge_class': badge_class
        })

    # Tambahkan temuan konteks spesifik ke strengths & weaknesses
    if incorrect_questions:
        unique_failed_quizzes = list(set([iq['quiz'] for iq in incorrect_questions]))
        weaknesses.append(f"Materi Spesifik yang Perlu Dievaluasi: Terdeteksi kesalahan pada topik ({', '.join(unique_failed_quizzes)}).")
        recommendations.append(f"Fokuskan remedial pada soal-soal di materi '{incorrect_questions[0]['quiz']}', khususnya pertanyaan mengenai '{incorrect_questions[0]['question']}'.")
    else:
        strengths.append("Sempurna dalam Konteks Soal: Berhasil menjawab seluruh pertanyaan dengan tepat tanpa kesalahan.")

    # Analisis Psikologis & Pemetaan MBTI Karakter Pembelajaran
    # 1. E (Extraversion) vs I (Introversion): Berdasarkan aktivitas perulangan kuis & partisipasi kelas
    # 2. S (Sensing) vs N (Intuition): Berdasarkan ketelitian detail soal spesifik & pemahaman konseptual
    # 3. T (Thinking) vs F (Feeling): Berdasarkan respon rasionalitas efisiensi waktu vs ketabahan coba lagi
    # 4. J (Judging) vs P (Perceiving): Berdasarkan kepatuhan batas waktu & struktur pengerjaan

    # Analisis Psikologis & Pemetaan MBTI Karakter Pembelajaran
    # Prioritaskan MBTI resmi dari Tes MBTI Siswa jika ada
    mbti_source_is_test = False
    if student.mbti_type:
        mbti_type = student.mbti_type
        mbti_source_is_test = True
    else:
        mbti_dim_1 = 'I' if total_attempts <= 2 else 'E'
        mbti_dim_2 = 'S' if precision_score >= 75 else 'N'
        mbti_dim_3 = 'T' if speed_score >= 70 else 'F'
        mbti_dim_4 = 'J' if consistency_score >= 70 else 'P'
        mbti_type = f"{mbti_dim_1}{mbti_dim_2}{mbti_dim_3}{mbti_dim_4}"

    mbti_dict = {
        'ISTJ': {'title': 'The Inspector / Pengamat Tekun', 'trait': 'Metodis, sangat teliti pada detail, menyukai struktur materi yang sistematis.', 'icon': 'bi-shield-check'},
        'ISFJ': {'title': 'The Protector / Penjaga Setia', 'trait': 'Sabar, penuh ketekunan, belajar dengan tenang dan memperhatikan aturan.', 'icon': 'bi-heart-pulse'},
        'INFJ': {'title': 'The Advocate / Pemikir Visi', 'trait': 'Reflektif, berorientasi pada pemahaman makna mendalam daripada sekadar nilai.', 'icon': 'bi-eye-fill'},
        'INTJ': {'title': 'The Architect / Perancang Strategis', 'trait': 'Analitis, mandiri, selalu mencari pola dan cara efisien menyelesaikan misi.', 'icon': 'bi-diagram-3-fill'},
        'ISTP': {'title': 'The Craftsman / Eksen Strategis', 'trait': 'Praktikal, tenang di bawah tekanan waktu, pemecah masalah yang taktis.', 'icon': 'bi-tools'},
        'ISFP': {'title': 'The Artist / Penjelajah Fleksibel', 'trait': 'Adaptif, menyukai pengalaman belajar visual & fleksibel tanpa keterpaksaan.', 'icon': 'bi-palette-fill'},
        'INFP': {'title': 'The Mediator / Pembelajar Idealis', 'trait': 'Kreatif, belajar berdasarkan antusiasme materi yang disukainya.', 'icon': 'bi-stars'},
        'INTP': {'title': 'The Thinker / Logikawan Kuantum', 'trait': 'Penuh rasa ingin tahu, rasa analisis teoritis tinggi, fleksibel dalam berpikir.', 'icon': 'bi-cpu-fill'},
        'ESTP': {'title': 'The Dynamo / Eksekutor Cepat', 'trait': 'Lincah, berani mengambil risiko, merespon kuis dengan kecepatan tinggi.', 'icon': 'bi-lightning-charge-fill'},
        'ESFP': {'title': 'The Performer / Motivator Aktif', 'trait': 'Antusias, bersemangat saat mendapat tantangan EXP & penghargaan kompetitif.', 'icon': 'bi-trophy-fill'},
        'ENFP': {'title': 'The Campaigner / Inovator Antusias', 'trait': 'Kreatif, cepat menangkap ide baru dan menyukai simulasi interaktif.', 'icon': 'bi-magic'},
        'ENTP': {'title': 'The Debater / Eksplorer Kritis', 'trait': 'Suka tantangan soal kompleks, berani mencoba berbagai kemungkinan opsi.', 'icon': 'bi-lightbulb-fill'},
        'ESTJ': {'title': 'The Executive / Pengelola Disiplin', 'trait': 'Organisatoris, teratur, menargetkan skor maksimal dengan strategi jelas.', 'icon': 'bi-award-fill'},
        'ESFJ': {'title': 'The Provider / Kolaborator Handal', 'trait': 'Kooperatif, bersemangat belajar bersama rekan kelas di leaderboard.', 'icon': 'bi-people-fill'},
        'ENFJ': {'title': 'The Protagonist / Pemimpin Inspiratif', 'trait': 'Karismatis, konsisten, terdorong membantu & menjadi panutan kelas.', 'icon': 'bi-compass-fill'},
        'ENTJ': {'title': 'The Commander / Komandan Strategis', 'trait': 'Berjiwa pemimpin, kompetitif, fokus pada pencapaian target tertinggi.', 'icon': 'bi-flag-fill'}
    }

    mbti_profile = mbti_dict.get(mbti_type, mbti_dict['INTJ'])

    # Profil Psikologis Pembelajaran (Psychological Learning Dimensions)
    psy_resilience = min(100, max(40, int((stamina_score * 0.5) + (total_attempts * 10)))) # Ketahanan Mental
    psy_risk_tolerance = min(100, max(30, int((speed_score * 0.6) + (100 - precision_score) * 0.4))) # Toleransi Risiko
    psy_focus_depth = min(100, max(40, int((concept_score * 0.6) + (precision_score * 0.4)))) # Kedalaman Fokus

    psychological_profile = {
        'mbti_type': mbti_type,
        'mbti_title': mbti_profile['title'],
        'mbti_trait': mbti_profile['trait'],
        'mbti_icon': mbti_profile['icon'],
        'psy_resilience': psy_resilience,
        'psy_risk_tolerance': psy_risk_tolerance,
        'psy_focus_depth': psy_focus_depth,
        'mbti_source_is_test': mbti_source_is_test,
        'mbti_tested_at': student.mbti_tested_at.strftime('%d %b %Y %H:%M') if student.mbti_tested_at else None
    }

    # Breakdown per kuis
    quiz_breakdown = []
    for q in quizzes:
        q_atts = [a for a in attempts if a.quiz_id == q.id]
        if q_atts:
            best = max(a.score for a in q_atts)
            last = q_atts[-1].score
            cnt = len(q_atts)
        else:
            best = None
            last = None
            cnt = 0

        quiz_breakdown.append({
            'quiz_title': q.title,
            'quiz_type': q.quiz_type,
            'attempt_count': cnt,
            'best_score': best,
            'latest_score': last
        })

    return {
        'has_data': True,
        'total_attempts': total_attempts,
        'avg_score': avg_score,
        'radar_scores': radar_scores, # [Pemahaman, Ketelitian, Kecepatan, Konsistensi, Ketahanan]
        'strengths': strengths,
        'weaknesses': weaknesses,
        'recommendations': recommendations,
        'context_insights': context_insights,
        'correct_questions': correct_questions,
        'incorrect_questions': incorrect_questions,
        'psychological_profile': psychological_profile,
        'quiz_breakdown': quiz_breakdown
    }


import uuid
import json
from models import db, Workspace, Class, Quiz, Question, Option, QuizAttempt, StudentAnswer, ClassEnrollment, User, SystemConfig, StudentReport, log_public_activity

@teacher_bp.route('/student/analysis/<int:class_id>/<int:student_id>')
@login_required
@teacher_required
def student_analysis_detail(class_id, student_id):
    c = Class.query.get_or_404(class_id)
    student = User.query.get_or_404(student_id)
    
    analytics_data = calculate_student_analytics(student, class_id)

    # Cek apakah sudah ada rapor yang pernah digenerate untuk siswa & kelas ini
    existing_report = StudentReport.query.filter_by(class_id=c.id, student_id=student.id).order_by(StudentReport.created_at.desc()).first()

    return render_template(
        'teacher/student_analysis.html',
        class_obj=c,
        student=student,
        data=analytics_data,
        report=existing_report
    )


@teacher_bp.route('/student/generate-report/<int:class_id>/<int:student_id>', methods=['POST'])
@login_required
@teacher_required
def generate_student_report(class_id, student_id):
    c = Class.query.get_or_404(class_id)
    student = User.query.get_or_404(student_id)
    
    analytics_data = calculate_student_analytics(student, class_id)
    if not analytics_data.get('has_data'):
        flash('Siswa belum memiliki data pengerjaan kuis untuk dibuatkan Rapor.', 'warning')
        return redirect(url_for('teacher.student_analysis_detail', class_id=class_id, student_id=student_id))

    # AI Prompt Synthesis
    psy = analytics_data['psychological_profile']
    mbti_str = f"{psy['mbti_type']} ({psy['mbti_title']}) - {psy['mbti_trait']}"
    radar = analytics_data['radar_scores'] # [Pemahaman, Ketelitian, Kecepatan, Konsistensi, Ketahanan]
    strengths_str = " | ".join(analytics_data['strengths'])
    weaknesses_str = " | ".join(analytics_data['weaknesses'])
    recs_str = " | ".join(analytics_data['recommendations'])

    prompt = f"""
Bertindaklah sebagai Pakar Psikologi Pendidikan dan Konsultan Pembelajaran Sains/Teknologi Senior.
Susun Rapor Akademik & Karakter Pembelajaran Resmi untuk Wali Murid berdasarkan data performa siswa berikut:

--- DATA SISWA ---
Nama Siswa: {student.username} (Level {student.level} - {student.rank_title})
Kelas: {c.name} ({c.subject})
Rata-rata Nilai Evaluasi: {analytics_data['avg_score']} / 100 (Total Percobaan: {analytics_data['total_attempts']})

--- METRIK GRAFIK RADAR KEMAMPUAN (0-100) ---
1. Pemahaman Konsep: {radar[0]}
2. Ketelitian Detail: {radar[1]}
3. Kecepatan Respon: {radar[2]}
4. Konsistensi Performa: {radar[3]}
5. Ketahanan Ujian: {radar[4]}

--- PROFIL PSIKOLOGIS & MBTI ---
Tipe Karakter MBTI: {mbti_str}
Indikator Psikologi: Ketahanan Mental ({psy['psy_resilience']}%), Kedalaman Fokus ({psy['psy_focus_depth']}%), Toleransi Risiko ({psy['psy_risk_tolerance']}%)

--- POTENSI & KELEMAHAN ---
Kekuatan & Potensi Utama: {strengths_str}
Kelemahan & Area Remedial: {weaknesses_str}
Rekomendasi Strategi Belajar: {recs_str}

--- INSTRUKSI OUTPUT ---
Hasilkan respons JSON valid tanpa markdown formatting tambahan dengan struktur persis seperti berikut:
{{
  "narrative_summary": "Tuliskan 2-3 paragraf narasi ringkasan performa akademik dan perkembangan karakter siswa secara profesional, hangat, serta memberikan motivasi positif untuk orang tua/wali murid.",
  "strengths_detail": "Penjelasan mendalam mengenai keunggulan, minat, dan potensi bakat unik siswa.",
  "weaknesses_detail": "Analisis konstruktif tentang area yang membutuhkan pendampingan, remedial, atau latihan ekstra di rumah.",
  "mbti_analysis": "Uraian komprehensif bagaimana tipe karakter MBTI siswa mempengaruhi gaya belajarnya serta panduan cara membimbing siswa dengan tipe kepribadian ini.",
  "recommendation": "Langkah-langkah konkret & rekomendasi praktis untuk orang tua/wali murid serta guru."
}}
"""

    # Panggil Gemini API
    ai_generated = False
    narrative_summary = ""
    strengths_detail = ""
    weaknesses_detail = ""
    mbti_analysis = ""
    recommendation = ""

    api_key_cfg = SystemConfig.query.filter_by(key='gemini_api_key').first()
    model_cfg = SystemConfig.query.filter_by(key='gemini_model').first()
    api_key = api_key_cfg.value.strip() if api_key_cfg and api_key_cfg.value else ""
    model_name = model_cfg.value.strip() if model_cfg and model_cfg.value else "gemini-2.5-flash"

    if api_key:
        import urllib.request, json
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        data_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data_bytes, headers={'Content-Type': 'application/json'})
        
        try:
            with urllib.request.urlopen(req, timeout=35) as res:
                res_json = json.loads(res.read().decode('utf-8'))
                raw_text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                
                parsed_res = json.loads(raw_text.strip())
                narrative_summary = parsed_res.get('narrative_summary', '')
                strengths_detail = parsed_res.get('strengths_detail', '')
                weaknesses_detail = parsed_res.get('weaknesses_detail', '')
                mbti_analysis = parsed_res.get('mbti_analysis', '')
                recommendation = parsed_res.get('recommendation', '')
                ai_generated = True
        except Exception as err:
            print("Notice: AI Report generation fallback triggered:", err)

    if not ai_generated:
        # Fallback Algorithmic Synthesis
        narrative_summary = (
            f"Siswa {student.username} menunjukkan progres belajar yang sangat positif di kelas {c.name}. "
            f"Dengan perolehan rata-rata nilai {analytics_data['avg_score']}/100 dari total {analytics_data['total_attempts']} kali evaluasi, "
            f"siswa memperlihatkan profil kepribadian {psy['mbti_type']} ({psy['mbti_title']}) yang {psy['mbti_trait'].lower()} "
            f"Kecepatan dan ketelitian belajar siswa berada pada tingkat yang memuaskan dan berpotensi untuk ditingkatkan lebih jauh."
        )
        strengths_detail = "\n".join([f"• {s}" for s in analytics_data['strengths']])
        weaknesses_detail = "\n".join([f"• {w}" for w in analytics_data['weaknesses']])
        mbti_analysis = (
            f"Sebagai seorang {psy['mbti_title']} ({psy['mbti_type']}), siswa memiliki karakteristik belajar unik. "
            f"Anak cenderung merespons tugas pembelajaran dengan ketahanan mental sebesar {psy['psy_resilience']}% "
            f"dan kedalaman fokus {psy['psy_focus_depth']}%. Pendampingan berulang secara terstruktur sangat direkomendasikan."
        )
        recommendation = "\n".join([f"• {r}" for r in analytics_data['recommendations']])

    # Simpan Rapor ke DB
    report_token = str(uuid.uuid4())
    report = StudentReport(
        report_token=report_token,
        student_id=student.id,
        class_id=c.id,
        created_by_id=current_user.id,
        ai_narrative_summary=narrative_summary,
        ai_strengths_detail=strengths_detail,
        ai_weaknesses_detail=weaknesses_detail,
        ai_mbti_analysis=mbti_analysis,
        ai_recommendation=recommendation,
        metrics_json=json.dumps(analytics_data)
    )
    db.session.add(report)
    db.session.commit()

    flash('Rapor Diagnostik AI & Potensi Siswa berhasil digenerate!', 'success')
    return redirect(url_for('teacher.view_report_detail', report_token=report_token))


@teacher_bp.route('/student/report/<string:report_token>')
def view_report_detail(report_token):
    report = StudentReport.query.filter_by(report_token=report_token).first_or_404()
    metrics_data = json.loads(report.metrics_json) if report.metrics_json else calculate_student_analytics(report.student, report.class_id)
    
    return render_template(
        'teacher/report_view.html',
        report=report,
        student=report.student,
        class_obj=report.class_obj,
        data=metrics_data,
        is_public=not current_user.is_authenticated or current_user.role not in ['GURU', 'SUPERUSER']
    )



