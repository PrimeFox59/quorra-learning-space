from flask import Flask, redirect, url_for, render_template
from flask_login import LoginManager, current_user
from config import Config
from models import db, User, LandingTeacher, LandingStudent, LandingFAQ
from database import init_db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Silakan login terlebih dahulu untuk mengakses stasiun ruang angkasa.'
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.superuser import superuser_bp
    from routes.teacher import teacher_bp
    from routes.student import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(superuser_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(student_bp)

    @app.route('/')
    def root_redirect():
        return redirect('/quorra/')

    @app.route('/quorra')
    @app.route('/quorra/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == 'SUPERUSER':
                return redirect(url_for('superuser.dashboard'))
            elif current_user.role == 'GURU':
                return redirect(url_for('teacher.dashboard'))
            else:
                return redirect(url_for('student.dashboard'))
        teachers = LandingTeacher.query.all()
        students = LandingStudent.query.all()
        faqs = LandingFAQ.query.all()
        return render_template('landing.html', teachers=teachers, students=students, faqs=faqs)

    # Initialize Database & Seed Default Accounts
    init_db(app)

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
