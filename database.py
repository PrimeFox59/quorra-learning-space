import random
import string
from models import db, User, Workspace, Class, ClassEnrollment, Quiz, Question, Option, Badge, UserBadge, QuizAttempt, SystemConfig, LandingTeacher, LandingStudent, LandingFAQ, StudentReport

from sqlalchemy import text

def generate_class_code(length=6):
    prefix = "QUORRA-"
    chars = string.ascii_uppercase + string.digits
    return prefix + ''.join(random.choice(chars) for _ in range(length - 2))

def init_db(app):
    with app.app_context():
        db.create_all()
        migrate_schema()
        seed_data()
        seed_landing_cms()
        ensure_configs()

def seed_landing_cms():
    if not LandingTeacher.query.first():
        t1 = LandingTeacher(
            name="Dr. Alistair Vance",
            title="Master Astrofisika & Kosmologi",
            experience="10+ Tahun Pengalaman",
            description="Mantan Peneliti Utama Observatorium Galaksi. Berpengalaman membimbing ratusan siswa menembus Olimpiade Sains Internasional.",
            rating="4.98 / 5.0",
            total_students="420+ Siswa",
            photo_path="uploads/landing/teacher_alistair.png"
        )
        t2 = LandingTeacher(
            name="Elena Rostova, M.Sc.",
            title="Pakar Quantum AI & Algoritma",
            experience="8+ Tahun Pengalaman",
            description="Mantan Tech Lead Lab AI Space Station. Spesialis pengembang soal AI otomatis dan kurikulum pemrograman sains.",
            rating="4.95 / 5.0",
            total_students="380+ Siswa",
            photo_path="uploads/landing/teacher_elena.png"
        )
        t3 = LandingTeacher(
            name="Marcus Thorne, S.T.",
            title="Spesialis Robotika & Planetologi",
            experience="7+ Tahun Pengalaman",
            description="Instruktur Utama Tim Robotika Mars. Pembimbing praktikum simulasi perancangan wahana luar angkasa interaktif.",
            rating="4.92 / 5.0",
            total_students="310+ Siswa",
            photo_path="uploads/landing/teacher_marcus.png"
        )
        db.session.add_all([t1, t2, t3])

    if not LandingStudent.query.first():
        s1 = LandingStudent(
            name="Arya Pratama",
            achievement="🥇 Juara 1 OSN Astrofisika 2026",
            level_title="Level 8 Galactic Admiral",
            testimonial="Bimbingan di Quorra Space sangat interaktif! Fitur kuis AI dan grafik performanya bikin aku selalu bersemangat latihan tiap hari.",
            class_name="Kelas ASTRA-9X",
            exp_points="1,240 EXP",
            photo_path="uploads/landing/student_arya.png"
        )
        s2 = LandingStudent(
            name="Maya Kirana",
            achievement="💯 Perfect Score 100 Ujian Kuantum",
            level_title="Level 7 Fleet Commander",
            testimonial="Fitur kuis quest dan rank title bikin belajar sains serasa main game RPG. Nilai fisika di sekolah aku naik drastis dari 65 ke 98!",
            class_name="Kelas MARS-77",
            exp_points="980 EXP",
            photo_path="uploads/landing/student_maya.png"
        )
        s3 = LandingStudent(
            name="Rizky Febrian",
            achievement="🎓 Beasiswa Space Tech Academy 2026",
            level_title="Level 6 Astral Pilot",
            testimonial="Guru-gurunya sangat suportif dan berpengalaman. Sistem leaderboard kelas membuat kami sesama siswa saling mendukung dan kompetitif!",
            class_name="Kelas ASTRA-9X",
            exp_points="750 EXP",
            photo_path="uploads/landing/student_rizky.png"
        )
        db.session.add_all([s1, s2, s3])

    if not LandingFAQ.query.first():
        f1 = LandingFAQ(
            question="Bagaimana alur pendaftaran siswa baru?",
            answer="Klik tombol 'Daftar Astronot Baru', isi formulir pendaftaran, lalu akun Anda akan diverifikasi oleh Superuser stasiun sebelum dapat login."
        )
        f2 = LandingFAQ(
            question="Apa itu fitur AI Question Generator?",
            answer="Fitur canggih berbasis Google Gemini AI yang memungkinkan Guru/Mentor membuat kuis pilihan ganda otomatis secara otomatis berdasarkan materi teks rangkuman."
        )
        f3 = LandingFAQ(
            question="Bagaimana sistem perolehan EXP dan Level?",
            answer="Setiap pengerjaan kuis yang lulus memberikan poin EXP. Kumpulkan 100 EXP untuk naik ke Level berikutnya dan membuka gelar rank seperti Cadet, Pilot, hingga Admiral."
        )
        db.session.add_all([f1, f2, f3])

    db.session.commit()

def migrate_schema():
    with db.engine.connect() as conn:
        try:
            conn.execute(text("SELECT is_approved FROM users LIMIT 1"))
        except Exception:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT 1"))
                conn.execute(text("UPDATE users SET is_approved = 1"))
                conn.commit()
            except Exception as e:
                print("Users migration notice:", e)

        try:
            conn.execute(text("SELECT image_path FROM questions LIMIT 1"))
        except Exception:
            try:
                conn.execute(text("ALTER TABLE questions ADD COLUMN image_path VARCHAR(255)"))
                conn.commit()
            except Exception as e:
                print("Questions migration notice:", e)

        try:
            conn.execute(text("SELECT image_path FROM options LIMIT 1"))
        except Exception:
            try:
                conn.execute(text("ALTER TABLE options ADD COLUMN image_path VARCHAR(255)"))
                conn.commit()
            except Exception as e:
                print("Options migration notice:", e)

        try:
            conn.execute(text("SELECT mbti_type FROM users LIMIT 1"))
        except Exception:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN mbti_type VARCHAR(10)"))
                conn.execute(text("ALTER TABLE users ADD COLUMN mbti_tested_at DATETIME"))
                conn.commit()
            except Exception as e:
                print("Users MBTI migration notice:", e)

def ensure_configs():
    if not SystemConfig.query.filter_by(key='gemini_model').first():
        db.session.add(SystemConfig(key='gemini_model', value='gemini-2.5-flash'))
    if not SystemConfig.query.filter_by(key='gemini_api_key').first():
        db.session.add(SystemConfig(key='gemini_api_key', value=''))
    db.session.commit()

def seed_data():
    # Check if admin already exists
    if User.query.filter_by(username='admin').first():
        return

    print("Seeding default space LMS accounts & initial data...")

    # 1. Create Default Users
    admin = User(
        username='admin',
        email='admin@space.com',
        role='SUPERUSER',
        is_approved=True,
        level=10,
        exp=950
    )
    admin.set_password('admin123')

    guru = User(
        username='guru1',
        email='guru@space.com',
        role='GURU',
        is_approved=True,
        level=5,
        exp=450
    )
    guru.set_password('guru123')

    murid = User(
        username='murid1',
        email='murid@space.com',
        role='MURID',
        is_approved=True,
        level=2,
        exp=150
    )
    murid.set_password('murid123')

    murid2 = User(
        username='astronaut2',
        email='astronaut2@space.com',
        role='MURID',
        is_approved=True,
        level=3,
        exp=280
    )
    murid2.set_password('murid123')

    db.session.add_all([admin, guru, murid, murid2])
    db.session.commit()

    # 2. Create Default Badges
    b1 = Badge(name="Stellar Launch", description="Menyelesaikan quest/kuis pertama kamu di galaksi!", icon_slug="rocket", exp_required=10, condition_type="QUIZ_COUNT")
    b2 = Badge(name="Super Brain", description="Mendapatkan nilai sempurna (100) pada ujian ruang angkasa.", icon_slug="brain", exp_required=50, condition_type="SCORE")
    b3 = Badge(name="Speed Navigator", description="Menyelesaikan kuis dalam waktu kurang dari 60 detik.", icon_slug="zap", exp_required=30, condition_type="SPEED")
    b4 = Badge(name="Fleet Captain", description="Mencapai Level 5 Astral Pilot.", icon_slug="crown", exp_required=400, condition_type="EXP")
    b5 = Badge(name="Galactic Explorer", description="Bergabung dengan lebih dari 2 kelas antar galaksi.", icon_slug="shield", exp_required=100, condition_type="CLASS_COUNT")

    db.session.add_all([b1, b2, b3, b4, b5])
    db.session.commit()

    # Grant initial badge to murid1
    ub1 = UserBadge(user_id=murid.id, badge_id=b1.id)
    db.session.add(ub1)
    db.session.commit()

    # 3. Create Sample Workspace & Class for Guru
    ws = Workspace(
        name="Sektor Fisika Kuantum & Astronomi",
        description="Workspace pembelajaran astrofisika dasar, mekanika kuantum, dan eksplorasi planet.",
        owner_id=guru.id
    )
    db.session.add(ws)
    db.session.commit()

    c1 = Class(
        workspace_id=ws.id,
        name="Astronavigasi & Planetologi A1",
        code="ASTRA-9X",
        subject="Astrofisika"
    )
    c2 = Class(
        workspace_id=ws.id,
        name="Pemrograman Robotika Mars B2",
        code="MARS-77",
        subject="Robotika Space"
    )
    db.session.add_all([c1, c2])
    db.session.commit()

    # Enroll murid1 & murid2 into c1
    e1 = ClassEnrollment(class_id=c1.id, student_id=murid.id)
    e2 = ClassEnrollment(class_id=c1.id, student_id=murid2.id)
    db.session.add_all([e1, e2])
    db.session.commit()

    # 4. Create Sample Quiz with ABCD Options
    q1 = Quiz(
        class_id=c1.id,
        title="Misi 01: Pengenalan Tata Surya & Orbit Planet",
        description="Kuis interaktif menguji pengetahuan dasar planet-planet di Tata Surya kita.",
        quiz_type="KUIS",
        time_limit_seconds=120, # 2 minutes
        max_attempts=3,
        exp_reward=50
    )
    db.session.add(q1)
    db.session.commit()

    # Add Questions
    ques1 = Question(quiz_id=q1.id, question_text="Planet manakah yang dikenal sebagai 'Planet Merah' di Tata Surya?", points=10)
    db.session.add(ques1)
    db.session.commit()

    opts1 = [
        Option(question_id=ques1.id, option_letter="A", option_text="Venus", is_correct=False),
        Option(question_id=ques1.id, option_letter="B", option_text="Mars", is_correct=True),
        Option(question_id=ques1.id, option_letter="C", option_text="Jupiter", is_correct=False),
        Option(question_id=ques1.id, option_letter="D", option_text="Saturnus", is_correct=False)
    ]
    db.session.add_all(opts1)

    ques2 = Question(quiz_id=q1.id, question_text="Bintang terdekat dari Bumi selain Matahari adalah...", points=10)
    db.session.add(ques2)
    db.session.commit()

    opts2 = [
        Option(question_id=ques2.id, option_letter="A", option_text="Proxima Centauri", is_correct=True),
        Option(question_id=ques2.id, option_letter="B", option_text="Sirius B", is_correct=False),
        Option(question_id=ques2.id, option_letter="C", option_text="Betelgeuse", is_correct=False),
        Option(question_id=ques2.id, option_letter="D", option_text="Alpha Andromeda", is_correct=False)
    ]
    db.session.add_all(opts2)

    ques3 = Question(quiz_id=q1.id, question_text="Gaya yang menyebabkan planet-planet tetap mengorbit Matahari adalah...", points=10)
    db.session.add(ques3)
    db.session.commit()

    opts3 = [
        Option(question_id=ques3.id, option_letter="A", option_text="Gaya Elektromagnetik", is_correct=False),
        Option(question_id=ques3.id, option_letter="B", option_text="Gaya Gesek Atmosfer", is_correct=False),
        Option(question_id=ques3.id, option_letter="C", option_text="Gaya Gravitasi", is_correct=True),
        Option(question_id=ques3.id, option_letter="D", option_text="Gaya Sentrifugal", is_correct=False)
    ]
    db.session.add_all(opts3)

    # Sample Quiz Attempt for Murid2
    att1 = QuizAttempt(
        quiz_id=q1.id,
        student_id=murid2.id,
        score=100,
        total_questions=3,
        correct_answers=3,
        time_taken_seconds=45,
        attempt_number=1
    )
    db.session.add(att1)
    db.session.commit()

    # 5. Seed Landing Page CMS Data
    if not LandingTeacher.query.first():
        t1 = LandingTeacher(
            name="Dr. Alistair Vance",
            title="Master Astrofisika & Kosmologi",
            experience="10+ Tahun Pengalaman",
            description="Mantan Peneliti Utama Observatorium Galaksi. Berpengalaman membimbing ratusan siswa menembus Olimpiade Sains Internasional.",
            rating="4.98 / 5.0",
            total_students="420+ Siswa",
            photo_path="uploads/landing/teacher_alistair.png"
        )
        t2 = LandingTeacher(
            name="Elena Rostova, M.Sc.",
            title="Pakar Quantum AI & Algoritma",
            experience="8+ Tahun Pengalaman",
            description="Mantan Tech Lead Lab AI Space Station. Spesialis pengembang soal AI otomatis dan kurikulum pemrograman sains.",
            rating="4.95 / 5.0",
            total_students="380+ Siswa",
            photo_path="uploads/landing/teacher_elena.png"
        )
        t3 = LandingTeacher(
            name="Marcus Thorne, S.T.",
            title="Spesialis Robotika & Planetologi",
            experience="7+ Tahun Pengalaman",
            description="Instruktur Utama Tim Robotika Mars. Pembimbing praktikum simulasi perancangan wahana luar angkasa interaktif.",
            rating="4.92 / 5.0",
            total_students="310+ Siswa",
            photo_path="uploads/landing/teacher_marcus.png"
        )
        db.session.add_all([t1, t2, t3])

    if not LandingStudent.query.first():
        s1 = LandingStudent(
            name="Arya Pratama",
            achievement="🥇 Juara 1 OSN Astrofisika 2026",
            level_title="Level 8 Galactic Admiral",
            testimonial="Bimbingan di Quorra Space sangat interaktif! Fitur kuis AI dan grafik performanya bikin aku selalu bersemangat latihan tiap hari.",
            class_name="Kelas ASTRA-9X",
            exp_points="1,240 EXP",
            photo_path="uploads/landing/student_arya.png"
        )
        s2 = LandingStudent(
            name="Maya Kirana",
            achievement="💯 Perfect Score 100 Ujian Kuantum",
            level_title="Level 7 Fleet Commander",
            testimonial="Fitur kuis quest dan rank title bikin belajar sains serasa main game RPG. Nilai fisika di sekolah aku naik drastis dari 65 ke 98!",
            class_name="Kelas MARS-77",
            exp_points="980 EXP",
            photo_path="uploads/landing/student_maya.png"
        )
        s3 = LandingStudent(
            name="Rizky Febrian",
            achievement="🎓 Beasiswa Space Tech Academy 2026",
            level_title="Level 6 Astral Pilot",
            testimonial="Guru-gurunya sangat suportif dan berpengalaman. Sistem leaderboard kelas membuat kami sesama siswa saling mendukung dan kompetitif!",
            class_name="Kelas ASTRA-9X",
            exp_points="750 EXP",
            photo_path="uploads/landing/student_rizky.png"
        )
        db.session.add_all([s1, s2, s3])

    if not LandingFAQ.query.first():
        f1 = LandingFAQ(
            question="Bagaimana alur pendaftaran siswa baru?",
            answer="Klik tombol 'Daftar Astronot Baru', isi formulir pendaftaran, lalu akun Anda akan diverifikasi oleh Superuser stasiun sebelum dapat login."
        )
        f2 = LandingFAQ(
            question="Apa itu fitur AI Question Generator?",
            answer="Fitur canggih berbasis Google Gemini AI yang memungkinkan Guru/Mentor membuat kuis pilihan ganda otomatis secara otomatis berdasarkan materi teks rangkuman."
        )
        f3 = LandingFAQ(
            question="Bagaimana sistem perolehan EXP dan Level?",
            answer="Setiap pengerjaan kuis yang lulus memberikan poin EXP. Kumpulkan 100 EXP untuk naik ke Level berikutnya dan membuka gelar rank seperti Cadet, Pilot, hingga Admiral."
        )
        db.session.add_all([f1, f2, f3])

    db.session.commit()

    print("Space LMS initial database seed complete!")
