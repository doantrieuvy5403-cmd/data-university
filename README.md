# 🎓 DATA - University

Hệ thống quản lý & dashboard database trường Đại học / Cao đẳng (BD Host · Inspired Space).
Xây dựng tương tự dự án **DATA - AP - OB**, nhưng cho dữ liệu trường học.

## Tính năng
- **Tổng quan**: số trường theo khu vực (MN/MB), theo hệ đào tạo, theo tiến độ, tổng số màn hình.
- **Database**: bảng dữ liệu theo khu vực (Miền Nam / Miền Bắc) với tìm kiếm, lọc (tiến độ, người phụ trách, thành phố, hệ, thương hiệu, hợp tác), phân trang, thêm / sửa / xóa.
- **Dashboard**: biểu đồ tiến độ màn hình (donut theo target MN/MB), tăng trưởng theo tuần, khối lượng công việc theo người, phân bố theo hệ / thương hiệu / CSVC / tỉnh thành / hợp tác.
- **Tỷ lệ chuyển đổi**: bảng phễu Plan B → Done theo màn hình & số trường.
- **Import / Export** Excel.

## Cấu trúc dữ liệu nguồn
File `data.xlsx`, sheet `Data University`. App tự seed dữ liệu vào DB khi khởi động (chỉ seed lại khi file thay đổi — không ghi đè dữ liệu nhập tay).

## Chạy local
```bash
pip install -r requirements.txt
python app.py
# http://localhost:5002
```
Mặc định dùng SQLite (`instance/database.db`). Khi có biến môi trường `DATABASE_URL` (Render Postgres) thì dùng Postgres.

## Triển khai Render (Blueprint)
1. Push repo này lên GitHub.
2. Trên Render: **New → Blueprint** → chọn repo này. Render đọc `render.yaml` và tạo:
   - Web service `data-university`
   - Postgres database `data-university-db`
3. Khi được hỏi, nhập giá trị cho `ADMIN_PASSWORD` (mật khẩu trang đăng nhập — hiện login đang để public).
4. Apply → chờ build & deploy xong.

## Biến môi trường
| Biến | Mô tả |
|------|-------|
| `DATABASE_URL` | Postgres connection string (Render tự gắn) |
| `SECRET_KEY` | Flask secret (Render tự sinh) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Tài khoản đăng nhập |
