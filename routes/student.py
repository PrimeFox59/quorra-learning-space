from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, User, Class, ClassEnrollment, Quiz, Question, Option, QuizAttempt, StudentAnswer, Badge, UserBadge, log_public_activity
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

        log_public_activity(
            event_type='JOIN_CLASS',
            title='Astronot Masuk Kelas!',
            message=f'{current_user.username} telah bergabung ke kelas "{class_obj.name}"!',
            icon_class='bi-rocket-takeoff-fill',
            badge_color='cyan'
        )

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

    # Log activity submit quiz (Hanya jika meraih skor sempurna 100)
    if score == 100:
        log_public_activity(
            event_type='SUBMIT_QUIZ',
            title='Nilai Sempurna! 🎯',
            message=f'{current_user.username} meraih skor sempurna 100/100 pada "{quiz.title}"!',
            icon_class='bi-award-fill',
            badge_color='amber'
        )

    # Check if student reached Rank #1 in class leaderboard
    c = quiz.class_obj
    class_enrollments = c.enrollments.all()
    c_student_ids = [e.student_id for e in class_enrollments]
    c_students = User.query.filter(User.id.in_(c_student_ids)).all() if c_student_ids else []
    
    leaderboard_data = []
    for s in c_students:
        s_attempts = QuizAttempt.query.join(Quiz).filter(Quiz.class_id == c.id, QuizAttempt.student_id == s.id).all()
        s_avg = round(sum(a.score for a in s_attempts) / len(s_attempts), 1) if s_attempts else 0
        leaderboard_data.append({'student_id': s.id, 'exp': s.exp, 'avg_score': s_avg})

    leaderboard_data.sort(key=lambda x: (x['exp'], x['avg_score']), reverse=True)
    if leaderboard_data and leaderboard_data[0]['student_id'] == current_user.id:
        log_public_activity(
            event_type='RANK_1',
            title='Peringkat 1 Baru! 🏆',
            message=f'Selamat! {current_user.username} menduduki Peringkat 1 di kelas "{c.name}"!',
            icon_class='bi-trophy-fill',
            badge_color='gold'
        )

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


# --- FITUR TES MBTI KEPRIBADIAN DIRI ---
from models import StudentMBTIResult

MBTI_QUESTIONS = [
    # E vs I
    {"id": 1, "dimension": "EI", "text": "Saat berada di lingkungan baru atau acara sosial, kamu cenderung...", "options": [{"val": "E", "text": "Mudah memulai obrolan & mendapat energi dari berinteraksi dengan orang baru."}, {"val": "I", "text": "Lebih tenang mengamati & merasa energi lebih cepat terkuras jika terlalu ramai."}]},
    {"id": 2, "dimension": "EI", "text": "Saat menyelesaikan tugas / proyek sulit, kamu lebih suka...", "options": [{"val": "E", "text": "Mendiskusikan ide bersama tim / kelompok belajar."}, {"val": "I", "text": "Fokus memikirkannya secara mandiri dalam suasana tenang."}]},
    {"id": 3, "dimension": "EI", "text": "Setelah seharian beraktivitas padat, cara terbaik bagimu untuk refresh adalah...", "options": [{"val": "E", "text": "Nongkrong atau mengobrol dengan teman-teman."}, {"val": "I", "text": "Menikmati waktu sendiri (membaca, main game, atau istirahat)."}]},
    
    # S vs N
    {"id": 4, "dimension": "SN", "text": "Saat mempelajari topik materi pelajaran baru, kamu lebih tertarik pada...", "options": [{"val": "S", "text": "Fakta riil, contoh konkret, dan langkah praktikal yang jelas."}, {"val": "N", "text": "Konsep teori mendalam, potensi masa depan, dan gambaran besar."}]},
    {"id": 5, "dimension": "SN", "text": "Ketika membaca petunjuk atau soal kuis, kamu cenderung...", "options": [{"val": "S", "text": "Memperhatikan setiap kata & detail instruksi secara cermat."}, {"val": "N", "text": "Menangkap inti ide utama dengan cepat tanpa terlalu terpaku pada detail kata."}]},
    {"id": 6, "dimension": "SN", "text": "Orang lain sering mengenali kamu sebagai seorang yang...", "options": [{"val": "S", "text": "Praktis, realistis, dan mengutamakan bukti nyata."}, {"val": "N", "text": "Imajinatif, inovatif, dan kaya akan gagasan baru."}]},
    
    # T vs F
    {"id": 7, "dimension": "TF", "text": "Saat mengambil keputusan penting, kamu paling mengutamakan...", "options": [{"val": "T", "text": "Logika objektif, kriteria ilmiah, dan analisis sebab-akibat."}, {"val": "F", "text": "Nilai-nilai kemanusiaan, empati, dan dampaknya bagi perasaan orang lain."}]},
    {"id": 8, "dimension": "TF", "text": "Jika teman kelompokmu melakukan kesalahan dalam tugas...", "options": [{"val": "T", "text": "Langsung mengoreksi bagian yang salah secara lugas demi hasil terbaik."}, {"val": "F", "text": "Menyampaikan koreksi secara halus dan hati-hati agar tidak menyinggung."}]},
    {"id": 9, "dimension": "TF", "text": "Kamu merasa paling dihargai ketika dipuji atas...", "options": [{"val": "T", "text": "Kecerdasan, efisiensi kerja, dan kemampuan pemecahan masalahmu."}, {"val": "F", "text": "Kebaikan hati, kepedulian, dan dedikasi hubunganmu."}]},

    # J vs P
    {"id": 10, "dimension": "JP", "text": "Gaya kamu dalam mengatur jadwal kegiatan sehari-hari adalah...", "options": [{"val": "J", "text": "Terstruktur, membuat to-do list, dan suka menyelesaikan tugas jauh hari."}, {"val": "P", "text": "Spontan, fleksibel, dan terbiasa bekerja produktif menjelang tenggat waktu."}]},
    {"id": 11, "dimension": "JP", "text": "Ketika rencana yang sudah disusun mendadak berubah, reaksi kamu...", "options": [{"val": "J", "text": "Agak terganggu dan berusaha secepatnya mengembalikan kepastian rencana."}, {"val": "P", "text": "Tenang dan mudah beradaptasi dengan situasi atau opsi baru."}]},
    {"id": 12, "dimension": "JP", "text": "Ruang belajar / kamar pribadi kamu biasanya dalam kondisi...", "options": [{"val": "J", "text": "Rapi, terorganisir, dan barang diletakkan sesuai tempatnya."}, {"val": "P", "text": "Fleksibel / sedikit acak, namun kamu tetap tahu di mana letak barangmu."}]}
]


@student_bp.route('/mbti-test')
@login_required
def mbti_test():
    latest_result = StudentMBTIResult.query.filter_by(student_id=current_user.id).order_by(StudentMBTIResult.created_at.desc()).first()
    return render_template('student/mbti_test.html', questions=MBTI_QUESTIONS, latest_result=latest_result)


@student_bp.route('/mbti-test/submit', methods=['POST'])
@login_required
def submit_mbti_test():
    scores = {'E': 0, 'I': 0, 'S': 0, 'N': 0, 'T': 0, 'F': 0, 'J': 0, 'P': 0}
    
    for q in MBTI_QUESTIONS:
        ans = request.form.get(f'q_{q["id"]}')
        if ans in scores:
            scores[ans] += 1

    # Tentukan tipe MBTI (Dominan)
    type_e_i = 'E' if scores['E'] >= scores['I'] else 'I'
    type_s_n = 'S' if scores['S'] >= scores['N'] else 'N'
    type_t_f = 'T' if scores['T'] >= scores['F'] else 'F'
    type_j_p = 'J' if scores['J'] >= scores['P'] else 'P'

    mbti_type = f"{type_e_i}{type_s_n}{type_t_f}{type_j_p}"

    mbti_dict = {
        'ISTJ': {'title': 'The Inspector / Pengamat Tekun', 'trait': 'Metodis, sangat teliti pada detail, menyukai struktur materi yang sistematis.'},
        'ISFJ': {'title': 'The Protector / Penjaga Setia', 'trait': 'Sabar, penuh ketekunan, belajar dengan tenang dan memperhatikan aturan.'},
        'INFJ': {'title': 'The Advocate / Pemikir Visi', 'trait': 'Reflektif, berorientasi pada pemahaman makna mendalam daripada sekadar nilai.'},
        'INTJ': {'title': 'The Architect / Perancang Strategis', 'trait': 'Analitis, mandiri, selalu mencari pola dan cara efisien menyelesaikan misi.'},
        'ISTP': {'title': 'The Craftsman / Eksen Strategis', 'trait': 'Praktikal, tenang di bawah tekanan waktu, pemecah masalah yang taktis.'},
        'ISFP': {'title': 'The Artist / Penjelajah Fleksibel', 'trait': 'Adaptif, menyukai pengalaman belajar visual & fleksibel tanpa keterpaksaan.'},
        'INFP': {'title': 'The Mediator / Pembelajar Idealis', 'trait': 'Kreatif, belajar berdasarkan antusiasme materi yang disukainya.'},
        'INTP': {'title': 'The Thinker / Logikawan Kuantum', 'trait': 'Penuh rasa ingin tahu, rasa analisis teoritis tinggi, fleksibel dalam berpikir.'},
        'ESTP': {'title': 'The Dynamo / Eksekutor Cepat', 'trait': 'Lincah, berani mengambil risiko, merespon kuis dengan kecepatan tinggi.'},
        'ESFP': {'title': 'The Performer / Motivator Aktif', 'trait': 'Antusias, bersemangat saat mendapat tantangan EXP & penghargaan kompetitif.'},
        'ENFP': {'title': 'The Campaigner / Inovator Antusias', 'trait': 'Kreatif, cepat menangkap ide baru dan menyukai simulasi interaktif.'},
        'ENTP': {'title': 'The Debater / Eksplorer Kritis', 'trait': 'Suka tantangan soal kompleks, berani mencoba berbagai kemungkinan opsi.'},
        'ESTJ': {'title': 'The Executive / Pengelola Disiplin', 'trait': 'Organisatoris, teratur, menargetkan skor maksimal dengan strategi jelas.'},
        'ESFJ': {'title': 'The Provider / Kolaborator Handal', 'trait': 'Kooperatif, bersemangat belajar bersama rekan kelas di leaderboard.'},
        'ENFJ': {'title': 'The Protagonist / Pemimpin Inspiratif', 'trait': 'Karismatis, konsisten, terdorong membantu & menjadi panutan kelas.'},
        'ENTJ': {'title': 'The Commander / Komandan Strategis', 'trait': 'Berjiwa pemimpin, kompetitif, fokus pada pencapaian target tertinggi.'}
    }

    profile = mbti_dict.get(mbti_type, mbti_dict['INTJ'])

    # Hitung Persentase Dimensi
    pct_e = round((scores['E'] / 3) * 100)
    pct_i = 100 - pct_e
    pct_s = round((scores['S'] / 3) * 100)
    pct_n = 100 - pct_s
    pct_t = round((scores['T'] / 3) * 100)
    pct_f = 100 - pct_t
    pct_j = round((scores['J'] / 3) * 100)
    pct_p = 100 - pct_j

    # Simpan hasil tes ke DB
    res = StudentMBTIResult(
        student_id=current_user.id,
        mbti_type=mbti_type,
        mbti_title=profile['title'],
        mbti_trait=profile['trait'],
        e_score=pct_e, i_score=pct_i,
        s_score=pct_s, n_score=pct_n,
        t_score=pct_t, f_score=pct_f,
        j_score=pct_j, p_score=pct_p
    )
    db.session.add(res)

    # Update profil resmi MBTI di tabel User
    current_user.mbti_type = mbti_type
    current_user.mbti_tested_at = datetime.utcnow()
    db.session.commit()

    flash(f'Tes MBTI Berhasil! Kepribadian resmi Anda terverifikasi sebagai {mbti_type} ({profile["title"]}).', 'success')
    return redirect(url_for('student.mbti_test'))

