from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from models import db, UniversityRecord, WeeklyGrowth, AppMeta
from datetime import datetime
import pandas as pd
import io
import os
import hashlib
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'database.db')

# Use Postgres (Render) when DATABASE_URL is set; fall back to local SQLite.
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'data-university-secret-key-2026')
app.config['ADMIN_USERNAME'] = os.environ.get('ADMIN_USERNAME', 'admin')
app.config['ADMIN_PASSWORD_HASH'] = generate_password_hash(
    os.environ.get('ADMIN_PASSWORD', 'password'), method='pbkdf2:sha256')

os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)

db.init_app(app)


@app.context_processor
def inject_user():
    # Public access: always treat as logged in so the UI shows the sidebar.
    return {
        'logged_in': True,
        'current_user': session.get('username') or 'Inspired Space'
    }


def login_required(view):
    # Login disabled: pass through without any authentication check.
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        return view(*args, **kwargs)
    return wrapped_view


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if username == app.config['ADMIN_USERNAME'] and check_password_hash(app.config['ADMIN_PASSWORD_HASH'], password):
            session['logged_in'] = True
            session['username'] = username
            flash('Đăng nhập thành công', 'success')
            return redirect(request.args.get('next') or url_for('index'))
        flash('Tên đăng nhập hoặc mật khẩu không đúng', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Đăng xuất thành công', 'success')
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# Seeding from data.xlsx (sheet "Data University")
# ---------------------------------------------------------------------------
# Column index (in the sheet) -> UniversityRecord field. Data starts at row 5.
SEED_SHEET = 'Data University'
SEED_SKIPROWS = 5
SEED_VERSION = '2-university-2026'

SEED_COLUMNS = {
    0: 'stt', 1: 'person_in_charge', 2: 'cooperation_status',
    3: 'status', 4: 'led_status', 5: 'approach_time',
    6: 'city', 7: 'ward', 8: 'level', 9: 'school_name', 10: 'address',
    12: 'price_range', 13: 'csvc', 14: 'student_count', 15: 'brand_strength',
    16: 'other_unit', 17: 'other_unit_screens', 18: 'num_elevators',
    19: 'total_screens', 20: 'screens_before_elevator', 21: 'screens_in_elevator',
    22: 'screens_stairs', 23: 'gp_count', 24: 'led_screens',
    25: 'p9000', 26: 'p6000',
}
INT_FIELDS = ['stt', 'other_unit_screens', 'num_elevators', 'total_screens',
              'screens_before_elevator', 'screens_in_elevator', 'screens_stairs',
              'gp_count', 'led_screens', 'p9000', 'p6000']

NORTH_CITIES = ['hà nội', 'ha noi', 'hanoi', 'hải phòng', 'hai phong', 'bắc ninh',
                'quảng ninh', 'hà nam', 'nam định', 'thái', 'vĩnh phúc', 'bắc',
                'hưng yên', 'hải dương', 'ninh bình', 'thanh hoá', 'thanh hóa',
                'nghệ an', 'lào cai', 'phú thọ']


def _derive_region(city):
    c = (city or '').lower().strip()
    return 'MB' if any(k in c for k in NORTH_CITIES) else 'MN'


# Light normalization of obvious duplicate/typo variants so dashboard groups cleanly
CITY_NORMALIZE = {
    'hcm': 'Hồ Chí Minh', 'tp hcm': 'Hồ Chí Minh', 'tp.hcm': 'Hồ Chí Minh',
    'hồ chí minh': 'Hồ Chí Minh', 'binh duong': 'Bình Dương',
}
LEVEL_NORMALIZE = {'học viện': 'Học viện', 'đại học': 'Đại học', 'cao đẳng': 'Cao đẳng'}


def _normalize(field, val):
    if field == 'city':
        return CITY_NORMALIZE.get(val.lower().strip(), val)
    if field == 'level':
        return LEVEL_NORMALIZE.get(val.lower().strip(), val)
    return val


# ---------------------------------------------------------------------------
# Funnel / dashboard config
# ---------------------------------------------------------------------------
FUNNEL_STAGES = ['Research', 'Plan B', 'Plan A', 'Deal', 'Done']
FUNNEL_WEIGHT = {'Research': 0.2, 'Plan B': 0.4, 'Plan A': 0.6, 'Deal': 0.8, 'Done': 1.0}

# "done" screens = sum of total_screens across these stages (Research excluded)
SCREEN_STAGES = ['Plan B', 'Plan A', 'Deal', 'Done']
SCREEN_TARGET = {'name': 'Mục tiêu màn hình', 'MB': 800, 'MN': 2200}

# Per-person screen target (Deal + Done), split equally among members
PERSON_TARGET = 3000
DEAL_DONE_STAGES = ['Deal', 'Done']

# Persons in charge — (display name, matching token, team)
DASHBOARD_PERSONS = [
    ('Xuân Tân', 'XUÂN TÂN', 'BD Host'),
    ('Ngọc Mai', 'NGỌC MAI', 'BD Host'),
    ('Quỳnh Hà', 'QUỲNH HÀ', 'BD Host'),
    ('Yên Nhiên', 'YÊN NHIÊN', 'BD Host'),
    ('Vinh Phú', 'VINH PHÚ', 'BD Host'),
    ('Duy Khánh', 'DUY KHÁNH', 'BD Host'),
    ('Ngọc Dũng', 'NGỌC DŨNG', 'BD Host'),
    ('Tân Đức', 'TÂN ĐỨC', 'BD Host'),
    ('Triều Vỹ', 'TRIỀU VỸ', 'BD Host'),
]


def _screen_progress():
    """Screen progress (Plan B → Done) vs target, split by region."""
    regions = {}
    sum_done = 0
    sum_target = 0
    for reg in ('MB', 'MN'):
        done = db.session.query(
            db.func.coalesce(db.func.sum(UniversityRecord.total_screens), 0)
        ).filter(
            UniversityRecord.region == reg,
            UniversityRecord.status.in_(SCREEN_STAGES),
        ).scalar() or 0
        done = int(done)
        target = SCREEN_TARGET[reg]
        regions[reg] = {'done': done, 'target': target}
        sum_done += done
        sum_target += target
    return {
        'name': SCREEN_TARGET['name'],
        'MB': regions['MB'],
        'MN': regions['MN'],
        'SUM': {'done': sum_done, 'target': sum_target},
    }


def _compute_person_progress():
    """Per-person funnel counts + screen achievement vs per-person target."""
    persons = DASHBOARD_PERSONS
    n = len(persons) or 1
    target = PERSON_TARGET / n

    counts = {disp: {stage: 0 for stage in FUNNEL_STAGES} for disp, _, _ in persons}
    screens = {disp: 0 for disp, _, _ in persons}
    token_to_disp = {token: disp for disp, token, _ in persons}

    for person, status in db.session.query(
        UniversityRecord.person_in_charge, UniversityRecord.status
    ).filter(
        UniversityRecord.person_in_charge.isnot(None),
        UniversityRecord.status.in_(FUNNEL_STAGES)
    ).all():
        for tok in str(person).split(','):
            disp = token_to_disp.get(tok.strip().upper())
            if disp:
                counts[disp][status] += 1

    for person, sc in db.session.query(
        UniversityRecord.person_in_charge, UniversityRecord.total_screens
    ).filter(
        UniversityRecord.person_in_charge.isnot(None),
        UniversityRecord.status.in_(DEAL_DONE_STAGES),
        UniversityRecord.total_screens.isnot(None)
    ).all():
        if not sc:
            continue
        for tok in str(person).split(','):
            disp = token_to_disp.get(tok.strip().upper())
            if disp:
                screens[disp] += int(sc)

    result = []
    for disp, _, team in persons:
        stage_counts = counts[disp]
        total = sum(stage_counts.values())
        weighted = sum(stage_counts[s] * FUNNEL_WEIGHT[s] for s in FUNNEL_STAGES)
        progress_project = round(weighted / total * 100, 1) if total else 0.0
        ach = screens[disp]
        progress_screens = round(ach / target * 100, 1) if target else 0.0
        result.append({
            'person': disp,
            'team': team,
            'stages': stage_counts,
            'total': total,
            'progress': progress_project,
            'progress_screens': progress_screens,
            'screens': ach,
            'target': round(target, 1),
        })
    return result


def _auto_seed():
    """(Re)seed university data from data.xlsx when the file changes."""
    data_file = os.path.join(BASE_DIR, 'data.xlsx')
    if not os.path.exists(data_file):
        print("Warning: data.xlsx not found, skipping seed")
        return
    try:
        with open(data_file, 'rb') as f:
            current_hash = f'{SEED_VERSION}:{hashlib.md5(f.read()).hexdigest()}'
        meta = db.session.get(AppMeta, 'data_hash')
        has_data = UniversityRecord.query.count() > 0
        if has_data and meta and meta.value == current_hash:
            return  # unchanged — keep all records (incl. manual edits)

        print("Seeding university data from data.xlsx (new/changed file)...")
        UniversityRecord.query.delete()
        db.session.commit()
        df = pd.read_excel(data_file, sheet_name=SEED_SHEET, header=None, skiprows=SEED_SKIPROWS)
        for _, row in df.iterrows():
            school = row.iloc[9] if len(row) > 9 else None
            if pd.isna(school) or not str(school).strip():
                continue
            rec = UniversityRecord(region='MN')
            for col_idx, field in SEED_COLUMNS.items():
                if col_idx >= len(row):
                    continue
                val = row.iloc[col_idx]
                if pd.isna(val):
                    continue
                if field in INT_FIELDS:
                    try:
                        val = int(float(str(val).replace("'", "").replace(",", "")))
                    except (ValueError, TypeError):
                        continue
                elif field == 'approach_time':
                    val = val.strftime('%m/%Y') if hasattr(val, 'strftime') else str(val)
                else:
                    val = _normalize(field, str(val).strip())
                setattr(rec, field, val)
            rec.region = _derive_region(rec.city)
            db.session.add(rec)
        db.session.commit()
        if meta is None:
            meta = AppMeta(key='data_hash')
            db.session.add(meta)
        meta.value = current_hash
        db.session.commit()
        print(f"Seeded {UniversityRecord.query.count()} records successfully!")
    except Exception as e:
        db.session.rollback()
        print(f"Seed error: {e}")


def _ensure_schema():
    """Add columns introduced after initial deploy (safe for SQLite & Postgres)."""
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    tables = insp.get_table_names()

    def add_col(table, col, ddl):
        if table not in tables:
            return
        existing = {c['name'] for c in insp.get_columns(table)}
        if col not in existing:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
            db.session.commit()

    add_col('university_record', 'must_have', "must_have VARCHAR(20)")


with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        db.session.rollback()
        print(f"create_all error: {e}")
    try:
        _ensure_schema()
    except Exception as e:
        db.session.rollback()
        print(f"ensure_schema error: {e}")
    try:
        _auto_seed()
    except Exception as e:
        db.session.rollback()
        print(f"auto_seed error: {e}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
STATUS_ORDER = ['Research', 'Plan B', 'Plan A', 'Deal', 'Done',
                'Code', 'Fail', 'Pending', 'Lost', 'Reject']


@app.route('/')
@login_required
def index():
    def count(region):
        return UniversityRecord.query.filter_by(region=region).count()

    mn = count('MN')
    mb = count('MB')

    # Level breakdown
    level_raw = dict(db.session.query(
        UniversityRecord.level, db.func.count(UniversityRecord.id)
    ).group_by(UniversityRecord.level).all())
    level_stats = sorted([(l, c) for l, c in level_raw.items() if l], key=lambda x: -x[1])

    raw = dict(db.session.query(
        UniversityRecord.status, db.func.count(UniversityRecord.id)
    ).group_by(UniversityRecord.status).all())
    status_stats = [(s, raw.get(s, 0)) for s in STATUS_ORDER]
    status_stats += [(s, c) for s, c in raw.items() if s and s not in STATUS_ORDER]

    total_screens = db.session.query(
        db.func.coalesce(db.func.sum(UniversityRecord.total_screens), 0)).scalar() or 0

    return render_template('index.html',
                           mn=mn, mb=mb,
                           total_screens=int(total_screens),
                           level_stats=level_stats,
                           status_stats=status_stats)


def _valid_region(region):
    return region in ('MN', 'MB')


@app.route('/database/<region>')
@login_required
def database(region):
    region = region.upper()
    if not _valid_region(region):
        flash('Invalid region', 'error')
        return redirect(url_for('index'))

    query = UniversityRecord.query.filter_by(region=region)

    search = request.args.get('search', '').strip()
    if search:
        query = query.filter(db.or_(
            UniversityRecord.school_name.contains(search),
            UniversityRecord.ward.contains(search),
            UniversityRecord.address.contains(search),
            UniversityRecord.person_in_charge.contains(search),
        ))

    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)
    person = request.args.get('person')
    if person:
        query = query.filter_by(person_in_charge=person)
    city = request.args.get('city')
    if city:
        query = query.filter_by(city=city)
    level = request.args.get('level')
    if level:
        query = query.filter_by(level=level)
    brand = request.args.get('brand_strength')
    if brand:
        query = query.filter_by(brand_strength=brand)
    coop = request.args.get('cooperation_status')
    if coop:
        query = query.filter_by(cooperation_status=coop)

    query = query.order_by(UniversityRecord.stt.is_(None), UniversityRecord.stt.asc(), UniversityRecord.id.asc())

    page = request.args.get('page', 1, type=int)
    records = query.paginate(page=page, per_page=50, error_out=False)

    opt = lambda col: db.session.query(col).filter_by(region=region).distinct().all()
    return render_template('database.html',
                           region=region,
                           records=records,
                           statuses=[s[0] for s in opt(UniversityRecord.status) if s[0]],
                           persons=[p[0] for p in opt(UniversityRecord.person_in_charge) if p[0]],
                           cities=sorted([c[0] for c in opt(UniversityRecord.city) if c[0]]),
                           levels=[l[0] for l in opt(UniversityRecord.level) if l[0]],
                           brands=sorted([b[0] for b in opt(UniversityRecord.brand_strength) if b[0]]),
                           coops=[c[0] for c in opt(UniversityRecord.cooperation_status) if c[0]],
                           school_names=sorted({s[0] for s in opt(UniversityRecord.school_name) if s[0]}),
                           search=search,
                           current_status=status,
                           current_person=person,
                           current_city=city,
                           current_level=level,
                           current_brand=brand,
                           current_coop=coop)


def _record_from_form(rec, form):
    rec.stt = form.get('stt', type=int)
    rec.person_in_charge = form.get('person_in_charge') or None
    rec.cooperation_status = form.get('cooperation_status') or None
    rec.status = form.get('status') or None
    rec.led_status = form.get('led_status') or None
    rec.approach_time = form.get('approach_time') or None
    rec.city = form.get('city') or None
    rec.ward = form.get('ward') or None
    rec.level = form.get('level') or None
    rec.school_name = form.get('school_name') or None
    rec.address = form.get('address') or None
    rec.price_range = form.get('price_range') or None
    rec.csvc = form.get('csvc') or None
    rec.student_count = form.get('student_count') or None
    rec.brand_strength = form.get('brand_strength') or None
    rec.other_unit = form.get('other_unit') or None
    rec.other_unit_screens = form.get('other_unit_screens', type=int)
    rec.num_elevators = form.get('num_elevators', type=int)
    rec.total_screens = form.get('total_screens', type=int)
    rec.screens_before_elevator = form.get('screens_before_elevator', type=int)
    rec.screens_in_elevator = form.get('screens_in_elevator', type=int)
    rec.screens_stairs = form.get('screens_stairs', type=int)
    rec.gp_count = form.get('gp_count', type=int)
    rec.led_screens = form.get('led_screens', type=int)
    rec.p9000 = form.get('p9000', type=int)
    rec.p6000 = form.get('p6000', type=int)
    rec.must_have = form.get('must_have') or None
    rec.region = _derive_region(rec.city)
    return rec


@app.route('/database/<region>/add', methods=['GET', 'POST'])
@login_required
def add_record(region):
    region = region.upper()
    if not _valid_region(region):
        flash('Invalid region', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        rec = _record_from_form(UniversityRecord(region=region), request.form)
        db.session.add(rec)
        db.session.commit()
        flash('Đã thêm bản ghi', 'success')
        return redirect(url_for('database', region=rec.region.lower()))
    max_stt = db.session.query(db.func.max(UniversityRecord.stt)).filter_by(region=region).scalar()
    return render_template('add_edit.html', region=region, record=None, next_stt=(max_stt or 0) + 1)


@app.route('/record/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_record(id):
    rec = UniversityRecord.query.get_or_404(id)
    if request.method == 'POST':
        _record_from_form(rec, request.form)
        db.session.commit()
        flash('Đã cập nhật bản ghi', 'success')
        return redirect(url_for('database', region=rec.region.lower()))
    return render_template('add_edit.html', region=rec.region, record=rec, next_stt=None)


@app.route('/record/<int:id>/delete', methods=['POST'])
@login_required
def delete_record(id):
    rec = UniversityRecord.query.get_or_404(id)
    region = rec.region
    db.session.delete(rec)
    db.session.commit()
    flash('Đã xóa bản ghi', 'success')
    return redirect(url_for('database', region=region.lower()))


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')


# ---------------------------------------------------------------------------
# Conversion (Tỷ lệ chuyển đổi)
# ---------------------------------------------------------------------------
CONVERSION_STAGES = ['Plan B', 'Plan A', 'Deal', 'Done']


def _conversion_table(region=None, level=None):
    q = db.session.query(
        UniversityRecord.status,
        db.func.coalesce(db.func.sum(UniversityRecord.total_screens), 0),
        db.func.count(UniversityRecord.id),
    ).filter(UniversityRecord.status.in_(CONVERSION_STAGES))
    if region:
        q = q.filter(UniversityRecord.region == region)
    if level:
        q = q.filter(UniversityRecord.level == level)
    q = q.group_by(UniversityRecord.status)
    table = {s: {'screens': 0, 'schools': 0} for s in CONVERSION_STAGES}
    for status, screens, count in q.all():
        table[status] = {'screens': int(screens or 0), 'schools': int(count or 0)}
    return table


def _snapshot_current_week():
    now = datetime.now()
    year, week, _ = now.isocalendar()
    rows = db.session.query(
        UniversityRecord.status,
        db.func.coalesce(db.func.sum(UniversityRecord.total_screens), 0),
        db.func.count(UniversityRecord.id),
    ).filter(UniversityRecord.status.in_(CONVERSION_STAGES)).group_by(UniversityRecord.status).all()
    screens = {s: 0 for s in CONVERSION_STAGES}
    schools = {s: 0 for s in CONVERSION_STAGES}
    for status, sc, ct in rows:
        screens[status] = int(sc or 0)
        schools[status] = int(ct or 0)
    snap = WeeklyGrowth.query.filter_by(year=year, week=week).first()
    if not snap:
        snap = WeeklyGrowth(year=year, week=week)
        db.session.add(snap)
    snap.plan_b, snap.plan_a, snap.deal, snap.done = (
        screens['Plan B'], screens['Plan A'], screens['Deal'], screens['Done'])
    snap.plan_b_schools, snap.plan_a_schools, snap.deal_schools, snap.done_schools = (
        schools['Plan B'], schools['Plan A'], schools['Deal'], schools['Done'])
    snap.updated_at = now
    db.session.commit()


def _weekly_growth_series():
    try:
        _snapshot_current_week()
    except Exception as e:
        db.session.rollback()
        print(f"weekly snapshot error: {e}")
    snaps = WeeklyGrowth.query.order_by(WeeklyGrowth.year, WeeklyGrowth.week).all()
    metrics = ['plan_b', 'plan_a', 'deal', 'done',
               'plan_b_schools', 'plan_a_schools', 'deal_schools', 'done_schools']
    out = {'labels': [f'Tuần {s.week}' for s in snaps]}
    for m in metrics:
        out[m] = [getattr(s, m, 0) or 0 for s in snaps]
    return out


@app.route('/conversion')
@login_required
def conversion():
    region = request.args.get('region', '').upper()
    region = region if region in ('MN', 'MB') else None
    level = request.args.get('level') or None
    now = datetime.now()
    levels = [l[0] for l in db.session.query(UniversityRecord.level).distinct().all() if l[0]]
    return render_template('conversion.html',
                           stages=CONVERSION_STAGES,
                           table=_conversion_table(region=region, level=level),
                           region=region,
                           level=level,
                           levels=sorted(levels),
                           week=now.isocalendar()[1],
                           updated=now.strftime('%d/%m/%Y'))


@app.route('/api/stats')
@login_required
def api_stats():
    status_stats = db.session.query(
        UniversityRecord.status, db.func.count(UniversityRecord.id)
    ).group_by(UniversityRecord.status).all()

    city_stats = db.session.query(
        UniversityRecord.city, db.func.count(UniversityRecord.id)
    ).filter(UniversityRecord.city.isnot(None)).group_by(UniversityRecord.city).order_by(
        db.func.count(UniversityRecord.id).desc()).all()

    person_stats = db.session.query(
        UniversityRecord.person_in_charge, db.func.count(UniversityRecord.id)
    ).filter(UniversityRecord.person_in_charge.isnot(None)).group_by(
        UniversityRecord.person_in_charge).all()

    level_stats = db.session.query(
        UniversityRecord.level, db.func.count(UniversityRecord.id)
    ).filter(UniversityRecord.level.isnot(None)).group_by(UniversityRecord.level).all()

    brand_stats = db.session.query(
        UniversityRecord.brand_strength, db.func.count(UniversityRecord.id)
    ).filter(UniversityRecord.brand_strength.isnot(None)).group_by(
        UniversityRecord.brand_strength).all()

    csvc_stats = db.session.query(
        UniversityRecord.csvc, db.func.count(UniversityRecord.id)
    ).filter(UniversityRecord.csvc.isnot(None)).group_by(UniversityRecord.csvc).all()

    coop_stats = db.session.query(
        UniversityRecord.cooperation_status, db.func.count(UniversityRecord.id)
    ).filter(UniversityRecord.cooperation_status.isnot(None)).group_by(
        UniversityRecord.cooperation_status).all()

    region_status = db.session.query(
        UniversityRecord.region, UniversityRecord.status, db.func.count(UniversityRecord.id)
    ).group_by(UniversityRecord.region, UniversityRecord.status).all()

    total = UniversityRecord.query.count()
    total_mn = UniversityRecord.query.filter_by(region='MN').count()
    total_mb = UniversityRecord.query.filter_by(region='MB').count()
    status_map = {s[0]: s[1] for s in status_stats}
    funnel = {stage: status_map.get(stage, 0) for stage in FUNNEL_STAGES}
    funnel_total = sum(funnel.values())
    overall_progress = round(
        sum(funnel[s] * FUNNEL_WEIGHT[s] for s in FUNNEL_STAGES) / funnel_total * 100, 1
    ) if funnel_total else 0.0

    return jsonify({
        'summary': {
            'total': total, 'total_mn': total_mn, 'total_mb': total_mb,
            'done': funnel['Done'], 'deal': funnel['Deal'],
            'funnel': funnel, 'funnel_total': funnel_total,
            'overall_progress': overall_progress,
        },
        'person_progress': _compute_person_progress(),
        'weekly_growth': _weekly_growth_series(),
        'screen_progress': _screen_progress(),
        'funnel_stages': FUNNEL_STAGES,
        'status': [{'label': s[0], 'count': s[1]} for s in status_stats if s[0]],
        'city': [{'label': c[0], 'count': c[1]} for c in city_stats][:10],
        'person': [{'label': p[0], 'count': p[1]} for p in person_stats],
        'level': [{'label': l[0], 'count': l[1]} for l in level_stats if l[0]],
        'brand': [{'label': b[0], 'count': b[1]} for b in brand_stats if b[0]],
        'csvc': [{'label': c[0], 'count': c[1]} for c in csvc_stats if c[0]],
        'cooperation': [{'label': c[0], 'count': c[1]} for c in coop_stats if c[0]],
        'region_status': [{'region': r[0], 'status': r[1], 'count': r[2]} for r in region_status if r[1]],
    })


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------
EXPORT_COLUMNS = [
    ('stt', 'STT'),
    ('person_in_charge', 'NS. Phụ trách'),
    ('cooperation_status', 'Tình trạng hợp tác'),
    ('status', 'Tiến độ LCD/DP/GP/DPS'),
    ('led_status', 'Tiến độ LED'),
    ('approach_time', 'Thời gian tiếp cận'),
    ('city', 'TP/Tỉnh'),
    ('ward', 'Xã/Phường'),
    ('level', 'Hệ'),
    ('school_name', 'Tên trường học'),
    ('address', 'Địa chỉ'),
    ('price_range', 'Giá bán'),
    ('csvc', 'CSVC'),
    ('student_count', 'Số lượng sinh viên'),
    ('brand_strength', 'Sức mạnh thương hiệu'),
    ('other_unit', 'Đơn vị khác'),
    ('other_unit_screens', 'SL màn đơn vị khác'),
    ('num_elevators', 'Số lượng thang máy'),
    ('total_screens', 'Tổng SL màn hình'),
    ('screens_before_elevator', 'SL màn trước thang'),
    ('screens_in_elevator', 'SL màn trong thang'),
    ('screens_stairs', 'SL màn thang bộ/trên cột'),
    ('gp_count', 'SL GP'),
    ('led_screens', 'SL màn LED'),
    ('p9000', 'P9000'),
    ('p6000', 'P6000'),
    ('must_have', 'Must have'),
]
IMPORT_INT_FIELDS = ['stt', 'other_unit_screens', 'num_elevators', 'total_screens',
                     'screens_before_elevator', 'screens_in_elevator', 'screens_stairs',
                     'gp_count', 'led_screens', 'p9000', 'p6000']


@app.route('/export/<region>')
@login_required
def export_data(region):
    region = region.upper()
    if not _valid_region(region):
        flash('Invalid region', 'error')
        return redirect(url_for('index'))
    records = UniversityRecord.query.filter_by(region=region).order_by(
        UniversityRecord.stt.is_(None), UniversityRecord.stt.asc(), UniversityRecord.id.asc()).all()
    rows = []
    for r in records:
        d = r.to_dict()
        rows.append({label: d.get(field) for field, label in EXPORT_COLUMNS})
    df = pd.DataFrame(rows, columns=[label for _, label in EXPORT_COLUMNS])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f'University_{region}')
    output.seek(0)
    filename = f'Database_University_{region}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/import/<region>', methods=['POST'])
@login_required
def import_data(region):
    region = region.upper()
    if not _valid_region(region):
        flash('Invalid region', 'error')
        return redirect(url_for('import_export'))
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('Chưa chọn file', 'error')
        return redirect(url_for('import_export'))
    file = request.files['file']
    try:
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        label_to_field = {label: field for field, label in EXPORT_COLUMNS}
        df = df.rename(columns=label_to_field)
        count = 0
        for _, row in df.iterrows():
            rec = UniversityRecord(region=region)
            for field in label_to_field.values():
                if field not in row:
                    continue
                val = row[field]
                if pd.isna(val):
                    continue
                if field in IMPORT_INT_FIELDS:
                    try:
                        val = int(float(str(val).replace("'", "").replace(",", "")))
                    except (ValueError, TypeError):
                        continue
                else:
                    val = str(val).strip()
                setattr(rec, field, val)
            if not rec.school_name:
                continue
            rec.region = _derive_region(rec.city) if rec.city else region
            db.session.add(rec)
            count += 1
        db.session.commit()
        flash(f'Đã import {count} bản ghi', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Lỗi import: {e}', 'error')
    return redirect(url_for('database', region=region.lower()))


@app.route('/import-export')
@login_required
def import_export():
    return render_template('import_export.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
