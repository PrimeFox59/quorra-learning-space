import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, Workspace, Class, Quiz, QuizAttempt, SystemConfig, LandingTeacher, LandingStudent, LandingFAQ
from functools import wraps

superuser_bp = Blueprint('superuser', __name__, url_prefix='/quorra/admin')

def superuser_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'SUPERUSER':
            flash('Akses ditolak. Halaman ini hanya untuk Superuser.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@superuser_bp.route('/dashboard')
@login_required
@superuser_required
def dashboard():
    total_users = User.query.count()
    total_gurus = User.query.filter_by(role='GURU').count()
    total_murids = User.query.filter_by(role='MURID').count()
    pending_users_count = User.query.filter_by(is_approved=False).count()
    total_workspaces = Workspace.query.count()
    total_classes = Class.query.count()
    total_quizzes = Quiz.query.count()
    total_attempts = QuizAttempt.query.count()

    users = User.query.order_by(User.is_approved.asc(), User.id.desc()).all()
    workspaces = Workspace.query.all()

    # Query Landing Page CMS items
    cms_teachers = LandingTeacher.query.order_by(LandingTeacher.id.asc()).all()
    cms_students = LandingStudent.query.order_by(LandingStudent.id.asc()).all()
    cms_faqs = LandingFAQ.query.order_by(LandingFAQ.id.asc()).all()

    # Get Gemini System Configs
    gemini_key_obj = SystemConfig.query.filter_by(key='gemini_api_key').first()
    gemini_model_obj = SystemConfig.query.filter_by(key='gemini_model').first()

    gemini_api_key = gemini_key_obj.value if gemini_key_obj else ''
    gemini_model = gemini_model_obj.value if gemini_model_obj else 'gemini-2.5-flash'

    available_models = [
        'gemini-3.6-flash',
        'gemini-3.5-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.1-flash-lite',
        'gemini-3.1-pro',
        'gemini-3-flash',
        'gemini-2.5-flash',
        'gemini-2.5-flash-lite',
        'gemini-2.5-pro',
        'gemini-2.0-flash',
        'gemini-2.0-flash-lite',
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-1.5-flash-8b'
    ]

    return render_template(
        'superuser/dashboard.html',
        total_users=total_users,
        total_gurus=total_gurus,
        total_murids=total_murids,
        pending_users_count=pending_users_count,
        total_workspaces=total_workspaces,
        total_classes=total_classes,
        total_quizzes=total_quizzes,
        total_attempts=total_attempts,
        users=users,
        workspaces=workspaces,
        cms_teachers=cms_teachers,
        cms_students=cms_students,
        cms_faqs=cms_faqs,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        available_models=available_models
    )

@superuser_bp.route('/user/approve/<int:user_id>', methods=['POST'])
@login_required
@superuser_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f'Akun astronot {user.username} ({user.role}) telah berhasil disetujui / dikonfirmasi!', 'success')
    return redirect(url_for('superuser.dashboard'))

@superuser_bp.route('/ai-config', methods=['POST'])
@login_required
@superuser_required
def update_ai_config():
    api_key = request.form.get('gemini_api_key', '').strip()
    model = request.form.get('gemini_model', 'gemini-2.5-flash').strip()

    key_cfg = SystemConfig.query.filter_by(key='gemini_api_key').first()
    if not key_cfg:
        key_cfg = SystemConfig(key='gemini_api_key', value=api_key)
        db.session.add(key_cfg)
    else:
        key_cfg.value = api_key

    model_cfg = SystemConfig.query.filter_by(key='gemini_model').first()
    if not model_cfg:
        model_cfg = SystemConfig(key='gemini_model', value=model)
        db.session.add(model_cfg)
    else:
        model_cfg.value = model

    db.session.commit()
    flash('Pengaturan AI Gemini berhasil disimpan!', 'success')
    return redirect(url_for('superuser.dashboard'))

@superuser_bp.route('/user/role/<int:user_id>', methods=['POST'])
@login_required
@superuser_required
def update_user_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    if new_role in ['SUPERUSER', 'GURU', 'MURID']:
        user.role = new_role
        db.session.commit()
        flash(f'Role user {user.username} berhasil diubah menjadi {new_role}.', 'success')
    return redirect(url_for('superuser.dashboard'))

@superuser_bp.route('/user/delete/<int:user_id>', methods=['POST'])
@login_required
@superuser_required
def delete_user(user_id):
    if user_id == current_user.id:
        flash('Anda tidak dapat menghapus akun diri sendiri!', 'danger')
        return redirect(url_for('superuser.dashboard'))
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} telah dihapus dari sistem.', 'success')
    return redirect(url_for('superuser.dashboard'))


# --- LANDING PAGE CMS CRUD ENDPOINTS ---

# 1. TEACHERS CMS
@superuser_bp.route('/cms/teacher/add', methods=['POST'])
@login_required
@superuser_required
def add_cms_teacher():
    name = request.form.get('name')
    title = request.form.get('title')
    experience = request.form.get('experience', '1+ Tahun')
    description = request.form.get('description')
    rating = request.form.get('rating', '4.9 / 5.0')
    total_students = request.form.get('total_students', '100+ Siswa')

    photo = request.files.get('photo')
    photo_path = "uploads/landing/teacher_alistair.png" # default fallback

    if photo and photo.filename:
        filename = secure_filename(f"teacher_{int(os.times().system)}_" + photo.filename)
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'landing')
        os.makedirs(upload_dir, exist_ok=True)
        photo.save(os.path.join(upload_dir, filename))
        photo_path = f"uploads/landing/{filename}"

    teacher = LandingTeacher(
        name=name,
        title=title,
        experience=experience,
        description=description,
        rating=rating,
        total_students=total_students,
        photo_path=photo_path
    )
    db.session.add(teacher)
    db.session.commit()
    flash(f'Mentor/Guru {name} berhasil ditambahkan ke Landing Page!', 'success')
    return redirect(url_for('superuser.dashboard'))


@superuser_bp.route('/cms/teacher/edit/<int:id>', methods=['POST'])
@login_required
@superuser_required
def edit_cms_teacher(id):
    t = LandingTeacher.query.get_or_404(id)
    t.name = request.form.get('name', t.name)
    t.title = request.form.get('title', t.title)
    t.experience = request.form.get('experience', t.experience)
    t.description = request.form.get('description', t.description)
    t.rating = request.form.get('rating', t.rating)
    t.total_students = request.form.get('total_students', t.total_students)

    photo = request.files.get('photo')
    if photo and photo.filename:
        filename = secure_filename(f"teacher_{t.id}_" + photo.filename)
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'landing')
        os.makedirs(upload_dir, exist_ok=True)
        photo.save(os.path.join(upload_dir, filename))
        t.photo_path = f"uploads/landing/{filename}"

    db.session.commit()
    flash(f'Data Mentor {t.name} berhasil diperbarui!', 'success')
    return redirect(url_for('superuser.dashboard'))


@superuser_bp.route('/cms/teacher/delete/<int:id>', methods=['POST'])
@login_required
@superuser_required
def delete_cms_teacher(id):
    t = LandingTeacher.query.get_or_404(id)
    name = t.name
    db.session.delete(t)
    db.session.commit()
    flash(f'Mentor {name} telah dihapus dari Landing Page.', 'success')
    return redirect(url_for('superuser.dashboard'))


# 2. STUDENTS TESTIMONIAL CMS
@superuser_bp.route('/cms/student/add', methods=['POST'])
@login_required
@superuser_required
def add_cms_student():
    name = request.form.get('name')
    achievement = request.form.get('achievement')
    level_title = request.form.get('level_title', 'Level 1 Cadet')
    testimonial = request.form.get('testimonial')
    class_name = request.form.get('class_name', 'Kelas Space')
    exp_points = request.form.get('exp_points', '500 EXP')

    photo = request.files.get('photo')
    photo_path = "uploads/landing/student_arya.png" # default fallback

    if photo and photo.filename:
        filename = secure_filename(f"student_{int(os.times().system)}_" + photo.filename)
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'landing')
        os.makedirs(upload_dir, exist_ok=True)
        photo.save(os.path.join(upload_dir, filename))
        photo_path = f"uploads/landing/{filename}"

    student = LandingStudent(
        name=name,
        achievement=achievement,
        level_title=level_title,
        testimonial=testimonial,
        class_name=class_name,
        exp_points=exp_points,
        photo_path=photo_path
    )
    db.session.add(student)
    db.session.commit()
    flash(f'Testimoni Siswa {name} berhasil ditambahkan ke Landing Page!', 'success')
    return redirect(url_for('superuser.dashboard'))


@superuser_bp.route('/cms/student/edit/<int:id>', methods=['POST'])
@login_required
@superuser_required
def edit_cms_student(id):
    s = LandingStudent.query.get_or_404(id)
    s.name = request.form.get('name', s.name)
    s.achievement = request.form.get('achievement', s.achievement)
    s.level_title = request.form.get('level_title', s.level_title)
    s.testimonial = request.form.get('testimonial', s.testimonial)
    s.class_name = request.form.get('class_name', s.class_name)
    s.exp_points = request.form.get('exp_points', s.exp_points)

    photo = request.files.get('photo')
    if photo and photo.filename:
        filename = secure_filename(f"student_{s.id}_" + photo.filename)
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'landing')
        os.makedirs(upload_dir, exist_ok=True)
        photo.save(os.path.join(upload_dir, filename))
        s.photo_path = f"uploads/landing/{filename}"

    db.session.commit()
    flash(f'Testimoni Siswa {s.name} berhasil diperbarui!', 'success')
    return redirect(url_for('superuser.dashboard'))


@superuser_bp.route('/cms/student/delete/<int:id>', methods=['POST'])
@login_required
@superuser_required
def delete_cms_student(id):
    s = LandingStudent.query.get_or_404(id)
    name = s.name
    db.session.delete(s)
    db.session.commit()
    flash(f'Testimoni Siswa {name} telah dihapus.', 'success')
    return redirect(url_for('superuser.dashboard'))


# 3. FAQ CMS
@superuser_bp.route('/cms/faq/add', methods=['POST'])
@login_required
@superuser_required
def add_cms_faq():
    question = request.form.get('question')
    answer = request.form.get('answer')
    faq = LandingFAQ(question=question, answer=answer)
    db.session.add(faq)
    db.session.commit()
    flash('Item FAQ baru berhasil ditambahkan!', 'success')
    return redirect(url_for('superuser.dashboard'))


@superuser_bp.route('/cms/faq/edit/<int:id>', methods=['POST'])
@login_required
@superuser_required
def edit_cms_faq(id):
    f = LandingFAQ.query.get_or_404(id)
    f.question = request.form.get('question', f.question)
    f.answer = request.form.get('answer', f.answer)
    db.session.commit()
    flash('Item FAQ berhasil diperbarui!', 'success')
    return redirect(url_for('superuser.dashboard'))


@superuser_bp.route('/cms/faq/delete/<int:id>', methods=['POST'])
@login_required
@superuser_required
def delete_cms_faq(id):
    f = LandingFAQ.query.get_or_404(id)
    db.session.delete(f)
    db.session.commit()
    flash('Item FAQ telah dihapus.', 'success')
    return redirect(url_for('superuser.dashboard'))
