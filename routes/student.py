from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, User, Class, ClassEnrollment, Quiz, Question, Option, QuizAttempt, StudentAnswer, Badge, UserBadge
from datetime import datetime

student_bp = Blueprint('student', __name__, url_prefix='/quorra/student')


@student_bp.route('/dashboard')
@login_required
def dashboard():
    enrollments = ClassEnrollment.query.filter_by(student_id=current_user.id).all()
    classes = [e.class_obj for e in enrollments]

    # Collect available quizzes/quests across joined classes
    active_quizzes = []
    for c in classes:
        for q in c.quizzes.all():
            attempts_count = QuizAttempt.query.filter_by(quiz_id=q.id, student_id=current_user.id).count()
            can_attempt = (q.max_attempts == 0) or (attempts_count < q.max_attempts)
            active_quizzes.append({
                'quiz': q,
                'class_name': c.name,
                'attempts_count': attempts_count,
                'can_attempt': can_attempt
            })

    # Badges info
    all_badges = Badge.query.all()
    user_badge_ids = [ub.badge_id for ub in current_user.badges.all()]

    return render_template(
        'student/dashboard.html',
        classes=classes,
        active_quizzes=active_quizzes,
        all_badges=all_badges,
        user_badge_ids=user_badge_ids
    )

@student_bp.route('/join', methods=['GET', 'POST'])
@login_required
def join_class():
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        class_obj = Class.query.filter_by(code=code).first()

        if not class_obj:
            flash('Kode kelas tidak ditemukan. Mohon periksa kembali kode dari Guru Anda.', 'danger')
            return redirect(url_for('student.join_class'))

        existing = ClassEnrollment.query.filter_by(class_id=class_obj.id, student_id=current_user.id).first()
        if existing:
            flash(f'Anda sudah terdaftar di kelas "{class_obj.name}".', 'info')
            return redirect(url_for('student.class_view', class_id=class_obj.id))

        new_enrollment = ClassEnrollment(class_id=class_obj.id, student_id=current_user.id)
        db.session.add(new_enrollment)
        db.session.commit()

        # Check badge for joining classes
        check_and_unlock_badges(current_user)

        flash(f'Berhasil bergabung dengan kelas "{class_obj.name}"! Selamat belajar astronot!', 'success')
        return redirect(url_for('student.class_view', class_id=class_obj.id))

    return render_template('student/join_class.html')

@student_bp.route('/class/<int:class_id>')
@login_required
def class_view(class_id):
    c = Class.query.get_or_404(class_id)
    enrollment = ClassEnrollment.query.filter_by(class_id=c.id, student_id=current_user.id).first()
    
    if not enrollment and current_user.role != 'SUPERUSER':
        flash('Anda belum terdaftar di kelas ini.', 'warning')
        return redirect(url_for('student.dashboard'))

    quizzes = c.quizzes.order_by(Quiz.created_at.desc()).all()
    quiz_data = []
    for q in quizzes:
        user_attempts = QuizAttempt.query.filter_by(quiz_id=q.id, student_id=current_user.id).order_by(QuizAttempt.score.desc()).all()
        attempts_count = len(user_attempts)
        best_score = user_attempts[0].score if user_attempts else None
        can_attempt = (q.max_attempts == 0) or (attempts_count < q.max_attempts)
        
        quiz_data.append({
            'quiz': q,
            'attempts_count': attempts_count,
            'best_score': best_score,
            'can_attempt': can_attempt
        })

    return render_template('student/class_view.html', class_obj=c, quiz_data=quiz_data)

@student_bp.route('/quiz/take/<int:quiz_id>')
@login_required
def take_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check attempt limit
    attempts_count = QuizAttempt.query.filter_by(quiz_id=quiz.id, student_id=current_user.id).count()
    if quiz.max_attempts > 0 and attempts_count >= quiz.max_attempts:
        flash(f'Anda telah mencapai batas maksimal percobaan ({quiz.max_attempts}x) untuk kuis ini.', 'warning')
        return redirect(url_for('student.class_view', class_id=quiz.class_id))

    questions = quiz.questions.all()
    if not questions:
        flash('Kuis ini belum memiliki soal.', 'warning')
        return redirect(url_for('student.class_view', class_id=quiz.class_id))

    return render_template('student/take_quiz.html', quiz=quiz, questions=questions, attempt_number=attempts_count + 1)

@student_bp.route('/quiz/submit/<int:quiz_id>', methods=['POST'])
@login_required
def submit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    questions = quiz.questions.all()
    
    total_questions = len(questions)
    correct_count = 0
    total_points = sum(q.points for q in questions)
    earned_points = 0
    time_taken = int(request.form.get('time_taken_seconds', 0))

    attempts_count = QuizAttempt.query.filter_by(quiz_id=quiz.id, student_id=current_user.id).count() + 1

    # Pre-calculate score & answers
    answers_to_create = []
    for q in questions:
        selected_option_id = request.form.get(f'question_{q.id}')
        opt_id = int(selected_option_id) if selected_option_id else None
        is_corr = False
        if opt_id:
            opt = Option.query.get(opt_id)
            if opt and opt.is_correct:
                is_corr = True
                correct_count += 1
                earned_points += q.points
        answers_to_create.append((q.id, opt_id, is_corr))

    score = int((earned_points / total_points) * 100) if total_points > 0 else 0

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        student_id=current_user.id,
        score=score,
        total_questions=total_questions,
        correct_answers=correct_count,
        time_taken_seconds=time_taken,
        attempt_number=attempts_count
    )
    db.session.add(attempt)
    db.session.flush() # Mendapatkan attempt.id

    # Simpan jawaban detail per soal
    for q_id, opt_id, is_corr in answers_to_create:
        st_ans = StudentAnswer(
            attempt_id=attempt.id,
            question_id=q_id,
            selected_option_id=opt_id,
            is_correct=is_corr
        )
        db.session.add(st_ans)

    # Award EXP
    exp_gained = quiz.exp_reward if score >= 60 else int(quiz.exp_reward * (score / 100))
    current_user.add_exp(exp_gained)

    db.session.commit()

    # Check Badges
    new_badges = check_and_unlock_badges(current_user, score=score, time_taken=time_taken)

    flash_msg = f'Misi Selesai! Skor Anda: {score}/100. (+{exp_gained} EXP)'
    if new_badges:
        flash_msg += f' Selamat! Anda membuka Badge baru: {", ".join(new_badges)}!'

    flash(flash_msg, 'success')
    return redirect(url_for('student.performance'))

@student_bp.route('/performance')
@login_required
def performance():
    attempts = QuizAttempt.query.filter_by(student_id=current_user.id).order_by(QuizAttempt.completed_at.asc()).all()
    
    chart_data = []
    for a in attempts:
        chart_data.append({
            'id': a.id,
            'date': a.completed_at.strftime('%d %b %Y %H:%M'),
            'quiz_title': a.quiz.title,
            'quiz_type': a.quiz.quiz_type,
            'class_name': a.quiz.class_obj.name,
            'attempt_number': a.attempt_number,
            'score': a.score,
            'correct_answers': a.correct_answers,
            'total_questions': a.total_questions,
            'time_taken': a.time_taken_seconds
        })

    scores = [a.score for a in attempts]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    max_score = max(scores) if scores else 0
    passed_count = sum(1 for s in scores if s >= 60)

    # Legacy variables maintained for backwards compatibility
    chart_labels = [a.completed_at.strftime('%d %b %H:%M') for a in attempts]
    chart_scores = [a.score for a in attempts]
    chart_quizzes = [a.quiz.title for a in attempts]

    return render_template(
        'student/performance.html',
        attempts=attempts,
        chart_data=chart_data,
        avg_score=avg_score,
        max_score=max_score,
        passed_count=passed_count,
        chart_labels=chart_labels,
        chart_scores=chart_scores,
        chart_quizzes=chart_quizzes
    )

@student_bp.route('/leaderboard/<int:class_id>')
@login_required
def leaderboard(class_id):
    c = Class.query.get_or_404(class_id)
    enrollments = c.enrollments.all()
    student_ids = [e.student_id for e in enrollments]

    students = User.query.filter(User.id.in_(student_ids)).all() if student_ids else []
    
    # Build student stats for this class leaderboard
    leaderboard_data = []
    for s in students:
        attempts = QuizAttempt.query.join(Quiz).filter(Quiz.class_id == c.id, QuizAttempt.student_id == s.id).all()
        avg_score = round(sum(a.score for a in attempts) / len(attempts), 1) if attempts else 0
        total_quizzes_passed = sum(1 for a in attempts if a.score >= 60)

        leaderboard_data.append({
            'student': s,
            'exp': s.exp,
            'level': s.level,
            'rank_title': s.rank_title,
            'avg_score': avg_score,
            'passed_count': total_quizzes_passed
        })

    # Sort leaderboard by EXP (descending), then Avg Score
    leaderboard_data.sort(key=lambda x: (x['exp'], x['avg_score']), reverse=True)

    return render_template('student/leaderboard.html', class_obj=c, leaderboard_data=leaderboard_data)


def check_and_unlock_badges(user, score=None, time_taken=None):
    unlocked_names = []
    user_badge_ids = [ub.badge_id for ub in user.badges.all()]
    all_badges = Badge.query.all()

    total_attempts = QuizAttempt.query.filter_by(student_id=user.id).count()
    class_count = ClassEnrollment.query.filter_by(student_id=user.id).count()

    for b in all_badges:
        if b.id in user_badge_ids:
            continue

        unlocked = False
        if b.condition_type == 'QUIZ_COUNT' and total_attempts >= 1:
            unlocked = True
        elif b.condition_type == 'SCORE' and score is not None and score >= 100:
            unlocked = True
        elif b.condition_type == 'SPEED' and time_taken is not None and time_taken < 60:
            unlocked = True
        elif b.condition_type == 'EXP' and user.exp >= b.exp_required:
            unlocked = True
        elif b.condition_type == 'CLASS_COUNT' and class_count >= 2:
            unlocked = True

        if unlocked:
            ub = UserBadge(user_id=user.id, badge_id=b.id)
            db.session.add(ub)
            unlocked_names.append(b.name)

    if unlocked_names:
        db.session.commit()

    return unlocked_names


@student_bp.route('/analytics')
@login_required
def analytics():
    from routes.teacher import calculate_student_analytics
    enrollment = ClassEnrollment.query.filter_by(student_id=current_user.id).first()
    if not enrollment:
        flash('Anda belum terdaftar di kelas manapun.', 'info')
        return redirect(url_for('student.dashboard'))

    analytics_data = calculate_student_analytics(current_user, enrollment.class_id)
    return render_template(
        'student/my_analytics.html',
        student=current_user,
        class_obj=enrollment.class_obj,
        data=analytics_data
    )
