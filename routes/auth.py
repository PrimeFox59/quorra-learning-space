from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User

auth_bp = Blueprint('auth', __name__, url_prefix='/quorra')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_by_role(current_user)

    if request.method == 'POST':
        login_input = request.form.get('login_input') # username or email
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter((User.username == login_input) | (User.email == login_input)).first()

        if not user or not user.check_password(password):
            flash('Kredensial login tidak ditemukan atau password salah.', 'danger')
            return render_template('auth/login.html')

        if not user.is_approved:
            flash('Akun Anda belum disetujui/dikonfirmasi oleh Superuser. Mohon hubungi Superuser stasiun untuk mendapatkan akses.', 'warning')
            return render_template('auth/login.html')

        login_user(user, remember=remember)
        flash(f'Selamat datang di Stasiun Ruang Angkasa, Commander {user.username}!', 'success')
        return redirect_by_role(user)

    return render_template('auth/login.html')


from models import db, User, log_public_activity

@auth_bp.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'MURID')

    if role not in ['GURU', 'MURID']:
        role = 'MURID'

    if User.query.filter_by(username=username).first():
        flash('Username sudah digunakan astronot lain.', 'warning')
        return redirect(url_for('auth.login'))

    if User.query.filter_by(email=email).first():
        flash('Email sudah terdaftar dalam sistem stasiun.', 'warning')
        return redirect(url_for('auth.login'))

    new_user = User(username=username, email=email, role=role, level=1, exp=0, is_approved=False)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    log_public_activity(
        event_type='REGISTER',
        title='Astronot Baru Bergabung!',
        message=f'{username} ({role}) baru saja mendaftar ke Quorra Space!',
        icon_class='bi-person-plus-fill',
        badge_color='cyan'
    )

    flash('Pendaftaran akun Astronot berhasil! Akun Anda sedang menunggu konfirmasi/persetujuan dari Superuser.', 'success')
    return redirect(url_for('auth.login'))



@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah keluar dari Stasiun Ruang Angkasa.', 'info')
    return redirect(url_for('auth.login'))


def redirect_by_role(user):
    if user.role == 'SUPERUSER':
        return redirect(url_for('superuser.dashboard'))
    elif user.role == 'GURU':
        return redirect(url_for('teacher.dashboard'))
    else:
        return redirect(url_for('student.dashboard'))
