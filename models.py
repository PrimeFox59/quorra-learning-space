from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='MURID') # SUPERUSER, GURU, MURID
    is_approved = db.Column(db.Boolean, default=False, nullable=False)
    level = db.Column(db.Integer, default=1)
    exp = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    workspaces = db.relationship('Workspace', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    enrollments = db.relationship('ClassEnrollment', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    quiz_attempts = db.relationship('QuizAttempt', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    badges = db.relationship('UserBadge', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def add_exp(self, points):
        self.exp += points
        new_level = (self.exp // 100) + 1
        self.level = new_level

    @property
    def rank_title(self):
        if self.level <= 2:
            return "Stellar Cadet"
        elif self.level <= 4:
            return "Cosmic Explorer"
        elif self.level <= 7:
            return "Astral Pilot"
        elif self.level <= 10:
            return "Fleet Commander"
        else:
            return "Galactic Admiral"

    @property
    def exp_next_level(self):
        return self.level * 100

    @property
    def exp_progress_percent(self):
        current_level_exp = self.exp % 100
        return min(100, int((current_level_exp / 100) * 100))


class Workspace(db.Model):
    __tablename__ = 'workspaces'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    classes = db.relationship('Class', backref='workspace', lazy='dynamic', cascade='all, delete-orphan')


class Class(db.Model):
    __tablename__ = 'classes'
    
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey('workspaces.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(10), unique=True, nullable=False)
    subject = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    enrollments = db.relationship('ClassEnrollment', backref='class_obj', lazy='dynamic', cascade='all, delete-orphan')
    quizzes = db.relationship('Quiz', backref='class_obj', lazy='dynamic', cascade='all, delete-orphan')


class ClassEnrollment(db.Model):
    __tablename__ = 'class_enrollments'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)


class Quiz(db.Model):
    __tablename__ = 'quizzes'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    quiz_type = db.Column(db.String(20), default='KUIS') # QUEST, KUIS, UJIAN
    time_limit_seconds = db.Column(db.Integer, default=0) # 0 = no limit
    max_attempts = db.Column(db.Integer, default=1) # 0 = unlimited
    exp_reward = db.Column(db.Integer, default=50)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship('Question', backref='quiz', lazy='dynamic', cascade='all, delete-orphan')
    attempts = db.relationship('QuizAttempt', backref='quiz', lazy='dynamic', cascade='all, delete-orphan')


class Question(db.Model):
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    points = db.Column(db.Integer, default=10)
    
    options = db.relationship('Option', backref='question', lazy='dynamic', cascade='all, delete-orphan')


class Option(db.Model):
    __tablename__ = 'options'
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    option_letter = db.Column(db.String(2), nullable=False) # A, B, C, D, E
    option_text = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(255), nullable=True)
    is_correct = db.Column(db.Boolean, default=False)


class SystemConfig(db.Model):
    __tablename__ = 'system_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)



class QuizAttempt(db.Model):
    __tablename__ = 'quiz_attempts'
    
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False) # Total points percentage e.g. 85
    total_questions = db.Column(db.Integer, nullable=False)
    correct_answers = db.Column(db.Integer, nullable=False)
    time_taken_seconds = db.Column(db.Integer, default=0)
    attempt_number = db.Column(db.Integer, default=1)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)


class Badge(db.Model):
    __tablename__ = 'badges'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon_slug = db.Column(db.String(50), nullable=False) # e.g. 'rocket', 'brain', 'crown', 'zap', 'shield'
    exp_required = db.Column(db.Integer, default=0)
    condition_type = db.Column(db.String(50), default='SCORE') # SCORE, EXP, QUIZ_COUNT


class UserBadge(db.Model):
    __tablename__ = 'user_badges'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badges.id'), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)

    badge = db.relationship('Badge')


# --- LANDING PAGE CMS MODELS ---
class LandingTeacher(db.Model):
    __tablename__ = 'landing_teachers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    experience = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    rating = db.Column(db.String(20), default="4.95 / 5.0")
    total_students = db.Column(db.String(50), default="350+ Siswa")
    photo_path = db.Column(db.String(255), nullable=True)


class LandingStudent(db.Model):
    __tablename__ = 'landing_students'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    achievement = db.Column(db.String(150), nullable=False)
    level_title = db.Column(db.String(100), nullable=False)
    testimonial = db.Column(db.Text, nullable=False)
    class_name = db.Column(db.String(50), nullable=False)
    exp_points = db.Column(db.String(50), default="1,000 EXP")
    photo_path = db.Column(db.String(255), nullable=True)


class LandingFAQ(db.Model):
    __tablename__ = 'landing_faqs'

    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
