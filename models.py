from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class UniversityRecord(db.Model):
    """A university / college campus in the BD Host database."""
    __tablename__ = "university_record"

    id = db.Column(db.Integer, primary_key=True)
    region = db.Column(db.String(10), nullable=False, index=True)  # "MN" or "MB" (derived from city)
    stt = db.Column(db.Integer)
    person_in_charge = db.Column(db.String(255), index=True)        # NS. Phụ trách
    cooperation_status = db.Column(db.String(50), index=True)       # Đã hợp tác / Chưa hợp tác
    status = db.Column(db.String(50), index=True)                   # Tiến độ LCD/DP/GP/DPS (funnel)
    led_status = db.Column(db.String(50))                           # Tiến độ LED
    approach_time = db.Column(db.String(100))                       # Thời gian tiếp cận
    city = db.Column(db.String(100), index=True)                    # TP/Tỉnh
    ward = db.Column(db.String(120))                                # Xã/Phường
    level = db.Column(db.String(50), index=True)                    # HỆ: Đại học / Cao đẳng / Học viện
    school_name = db.Column(db.String(255))                         # Tên trường học
    address = db.Column(db.String(255))                             # Địa chỉ
    price_range = db.Column(db.String(100))                         # Giá bán
    csvc = db.Column(db.String(50))                                 # CSVC: Premium / Standard / Substandard
    student_count = db.Column(db.String(50))                        # Số lượng sinh viên: High / Middle / Low
    brand_strength = db.Column(db.String(50), index=True)          # Sức mạnh thương hiệu / Xếp loại: A/B/C
    other_unit = db.Column(db.String(100))                          # Đơn vị khác (Không / Focus...)
    other_unit_screens = db.Column(db.Integer)                      # SL màn hình đơn vị khác
    num_elevators = db.Column(db.Integer)                           # Số lượng thang máy
    total_screens = db.Column(db.Integer)                          # Tổng SL màn hình
    screens_before_elevator = db.Column(db.Integer)                # SL màn trước thang
    screens_in_elevator = db.Column(db.Integer)                    # SL màn trong thang
    screens_stairs = db.Column(db.Integer)                         # SL màn thang bộ / trên cột
    gp_count = db.Column(db.Integer)                               # SL GP
    led_screens = db.Column(db.Integer)                            # SL màn LED
    p9000 = db.Column(db.Integer)
    p6000 = db.Column(db.Integer)
    must_have = db.Column(db.String(20), index=True)              # "Must have" or None
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "region": self.region,
            "stt": self.stt,
            "person_in_charge": self.person_in_charge,
            "cooperation_status": self.cooperation_status,
            "status": self.status,
            "led_status": self.led_status,
            "approach_time": self.approach_time,
            "city": self.city,
            "ward": self.ward,
            "level": self.level,
            "school_name": self.school_name,
            "address": self.address,
            "price_range": self.price_range,
            "csvc": self.csvc,
            "student_count": self.student_count,
            "brand_strength": self.brand_strength,
            "other_unit": self.other_unit,
            "other_unit_screens": self.other_unit_screens,
            "num_elevators": self.num_elevators,
            "total_screens": self.total_screens,
            "screens_before_elevator": self.screens_before_elevator,
            "screens_in_elevator": self.screens_in_elevator,
            "screens_stairs": self.screens_stairs,
            "gp_count": self.gp_count,
            "led_screens": self.led_screens,
            "p9000": self.p9000,
            "p6000": self.p6000,
            "must_have": self.must_have,
        }


class WeeklyGrowth(db.Model):
    """Weekly snapshot of screen + school counts per funnel stage."""
    __tablename__ = "weekly_growth"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    week = db.Column(db.Integer, nullable=False)
    # Screen totals per stage
    plan_b = db.Column(db.Integer, default=0)
    plan_a = db.Column(db.Integer, default=0)
    deal = db.Column(db.Integer, default=0)
    done = db.Column(db.Integer, default=0)
    # School (record) counts per stage
    plan_b_schools = db.Column(db.Integer, default=0)
    plan_a_schools = db.Column(db.Integer, default=0)
    deal_schools = db.Column(db.Integer, default=0)
    done_schools = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('year', 'week', name='uq_weekly_year_week'),)


class AppMeta(db.Model):
    """Simple key/value store for app state (e.g. seeded data.xlsx hash)."""
    __tablename__ = "app_meta"

    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(255))
