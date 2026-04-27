from flask import Flask, request, jsonify, send_from_directory
import mysql.connector
from mysql.connector import pooling
import os

app = Flask(__name__)

import time

# Cấu hình Database
def get_db_config():
    mysql_url = os.environ.get("MYSQL_URL") or os.environ.get("DATABASE_URL")
    if mysql_url and mysql_url.startswith("mysql://"):
        try:
            from urllib.parse import urlparse
            result = urlparse(mysql_url)
            return {
                "host": result.hostname,
                "user": result.username,
                "password": result.password,
                "database": result.path[1:],
                "port": result.port or 3306,
                "connect_timeout": 20
            }
        except Exception as e:
            print(f"Lỗi parse URL: {e}")
    
    return {
        "host": os.environ.get("MYSQLHOST", "localhost"),
        "user": os.environ.get("MYSQLUSER", "root"),
        "password": os.environ.get("MYSQLPASSWORD", ""),
        "database": os.environ.get("MYSQLDATABASE", "railway"),
        "port": int(os.environ.get("MYSQLPORT", 3306)),
        "connect_timeout": 20
    }

db_config = get_db_config()
db_pool = None

def init_db_with_retry():
    global db_pool
    max_retries = 5
    retry_delay = 5
    
    for i in range(max_retries):
        try:
            print(f"Thử kết nối DB lần {i+1}/{max_retries} (Host: {db_config['host']})...")
            db_pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="mypool",
                pool_size=5,
                **db_config
            )
            
            # Thử lấy một kết nối để kiểm tra và chạy init script
            conn = db_pool.get_connection()
            cursor = conn.cursor()
            
            if os.path.exists('database.sql'):
                print("Đang nạp file database.sql...")
                with open('database.sql', 'r', encoding='utf-8') as f:
                    # Đọc toàn bộ file và tách theo dấu ; nhưng thông minh hơn
                    sql_content = f.read()
                    # Loại bỏ các comment SQL
                    sql_content = "\n".join([line for line in sql_content.split("\n") if not line.strip().startswith("--")])
                    commands = sql_content.split(';')
                    
                    for cmd in commands:
                        c = cmd.strip()
                        if not c: continue
                        
                        # Bỏ qua các lệnh tạo db hoặc use db vì Railway đã quản lý việc này
                        if c.upper().startswith(('CREATE DATABASE', 'USE')):
                            continue
                            
                        try:
                            cursor.execute(c)
                        except Exception as sql_e:
                            # Chỉ in lỗi nếu không phải lỗi "đã tồn tại"
                            if "already exists" not in str(sql_e).lower():
                                print(f"Lỗi thực thi SQL: {sql_e}")
                                
            conn.commit()
            cursor.close()
            conn.close()
            print("Kết nối và khởi tạo Database THÀNH CÔNG!")
            return True
            
        except Exception as e:
            print(f"Lỗi kết nối DB: {e}")
            if i < max_retries - 1:
                print(f"Thử lại sau {retry_delay} giây...")
                time.sleep(retry_delay)
            else:
                print("ĐÃ THỬ HẾT CÁCH NHƯNG KHÔNG KẾT NỐI ĐƯỢC DB.")
    return False

# Chạy khởi tạo
init_db_with_retry()

def get_db():
    try: 
        if db_pool:
            return db_pool.get_connection()
        # Fallback kết nối trực tiếp nếu pool hỏng
        return mysql.connector.connect(**db_config)
    except Exception as e:
        print(f"Lỗi lấy kết nối DB: {e}")
        return None

# --- API ---
@app.route('/api/login', methods=['POST'])
def login():
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "Lỗi kết nối DB"}), 500
    try:
        d = request.json
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (d['tk'], d['mk']))
        
        u = cursor.fetchone()  # Lấy dòng đầu tiên
        cursor.fetchall()      # Đọc hết kết quả còn lại để tránh lỗi "Unread result"

        if u:
            if u.get('status') == 'cho_duyet': 
                return jsonify({"success": False, "message": "Tài khoản đang chờ duyệt"}), 401
            return jsonify({
                "success": True, 
                "user": {"tk": u['username'], "quyen": u.get('role', 'admin')}
            })
        return jsonify({"success": False, "message": "Sai tài khoản hoặc mật khẩu"}), 401
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/register', methods=['POST'])
def register():
    conn = get_db()
    try:
        d = request.json
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password, status, role) VALUES (%s, %s, 'cho_duyet', 'nhan_vien')", (d['tk'], d['mk']))
        conn.commit()
        return jsonify({"success": True})
    except: return jsonify({"success": False}), 400
    finally:
        if conn: conn.close()

@app.route('/api/khach-hang')
def get_kh():
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, ho_ten, so_dt, email, lat_khach_hang, long_khach_hang, DATE_FORMAT(Ngay_rao, '%d/%m/%Y') as Ngay_rao FROM khach_hang ORDER BY id DESC")
        return jsonify(cursor.fetchall())
    finally:
        if conn: conn.close()

@app.route('/api/cua-hang')
def get_ch():
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, ten_cua_hang, dia_chi, lat_cua_hang, long_cua_hang FROM cua_hang")
        return jsonify(cursor.fetchall())
    finally:
        if conn: conn.close()

@app.route('/api/khach-hang/add', methods=['POST'])
def add_kh():
    conn = get_db()
    try:
        d = request.json
        cursor = conn.cursor()
        cursor.execute("INSERT INTO khach_hang (ho_ten, so_dt, email) VALUES (%s, %s, %s)", (d['hoten'], d['sdt'], d.get('email', '')))
        conn.commit()
        return jsonify({"success": True})
    finally:
        if conn: conn.close()

@app.route('/api/khach-hang/delete', methods=['POST'])
def del_kh():
    conn = get_db()
    try:
        d = request.json
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chi_tiet_don_hang WHERE id_don_hang IN (SELECT id FROM don_hang WHERE id_khach_hang = %s)", (d['id'],))
        cursor.execute("DELETE FROM don_hang WHERE id_khach_hang = %s", (d['id'],))
        cursor.execute("DELETE FROM khach_hang WHERE id = %s", (d['id'],))
        conn.commit()
        return jsonify({"success": True})
    finally:
        if conn: conn.close()

@app.route('/api/san-pham')
def get_sp():
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM san_pham ORDER BY id DESC")
        return jsonify(cursor.fetchall())
    finally:
        if conn: conn.close()

@app.route('/api/san-pham/add', methods=['POST'])
def add_sp():
    conn = get_db()
    try:
        d = request.json
        cursor = conn.cursor()
        cursor.execute("INSERT INTO san_pham (ten_san_pham, loai_cf, gia_ban, don_vi) VALUES (%s, %s, %s, %s)", (d['ten'], d['loai'], d['gia'], d['donvi']))
        conn.commit()
        return jsonify({"success": True})
    finally:
        if conn: conn.close()

@app.route('/api/san-pham/delete', methods=['POST'])
def del_sp():
    conn = get_db()
    try:
        d = request.json
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chi_tiet_don_hang WHERE id_san_pham = %s", (d['id'],))
        cursor.execute("DELETE FROM san_pham WHERE id = %s", (d['id'],))
        conn.commit()
        return jsonify({"success": True})
    finally:
        if conn: conn.close()

@app.route('/api/don-hang')
def get_dh():
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT d.id, k.ho_ten as khach_hang, DATE_FORMAT(d.ngay_mua, '%d/%m/%Y %H:%i') as ngay, d.tong_tien, d.trang_thai FROM don_hang d JOIN khach_hang k ON d.id_khach_hang = k.id ORDER BY d.id DESC")
        return jsonify(cursor.fetchall())
    finally:
        if conn: conn.close()

@app.route('/api/don-hang/add', methods=['POST'])
def add_dh():
    conn = get_db()
    try:
        d = request.json
        cursor = conn.cursor()
        cursor.execute("INSERT INTO don_hang (id_khach_hang, id_cua_hang, tong_tien, trang_thai) VALUES (%s, 1, %s, 'hoan_thanh')", (d['id_khach'], d['tong_tien']))
        conn.commit()
        return jsonify({"success": True})
    finally:
        if conn: conn.close()

@app.route('/api/kho')
def get_kho():
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, ma_hang as ma, ten_nguyen_lieu as ten, ton_kho as ton, muc_bao_dong as min FROM nguon_nguyen_lieu ORDER BY id DESC")
        return jsonify(cursor.fetchall())
    finally:
        if conn: conn.close()

@app.route('/api/kho/add', methods=['POST'])
def add_kho():
    conn = get_db()
    try:
        d = request.json
        cursor = conn.cursor()
        cursor.execute("INSERT INTO nguon_nguyen_lieu (ma_hang, ten_nguyen_lieu, ton_kho, muc_bao_dong) VALUES (%s, %s, %s, %s)", (d['ma'], d['ten'], d['ton'], d['min']))
        conn.commit()
        return jsonify({"success": True})
    finally:
        if conn: conn.close()

@app.route('/api/kho/delete', methods=['POST'])
def del_kho():
    conn = get_db()
    try:
        d = request.json
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM nguon_nguyen_lieu WHERE ma_hang = %s", (d['ma'],))
        res = cursor.fetchone()
        if res:
            cursor.execute("DELETE FROM kho_nguyen_lieu WHERE id_nguyen_lieu = %s", (res[0],))
            cursor.execute("DELETE FROM chi_tiet_san_xuat WHERE id_nguyen_lieu = %s", (res[0],))
            cursor.execute("DELETE FROM nguon_nguyen_lieu WHERE id = %s", (res[0],))
            conn.commit()
        return jsonify({"success": True})
    finally:
        if conn: conn.close()

@app.route('/api/doanh-thu')
def get_dt():
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT DATE_FORMAT(ngay_mua, '%d/%m/%Y') as ngay, SUM(tong_tien) as tien FROM don_hang WHERE trang_thai = 'hoan_thanh' GROUP BY ngay ORDER BY ngay DESC")
        res = cursor.fetchall()
        for r in res: r['tien'] = float(r['tien']) if r['tien'] else 0
        return jsonify(res)
    finally:
        if conn: conn.close()

# --- API ADMIN (QUẢN LÝ TÀI KHOẢN) ---
@app.route('/api/admin/users')
def admin_get_users():
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT username as tk, role as quyen, status as trangThai FROM users ORDER BY id DESC")
        return jsonify(cursor.fetchall())
    finally:
        if conn: conn.close()

@app.route('/api/admin/approve', methods=['POST'])
def admin_approve():
    d = request.json
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'da_duyet' WHERE username = %s", (d['tk'],))
        conn.commit()
        return jsonify({"success": True})
    finally:
        if conn: conn.close()

@app.route('/api/admin/delete-user', methods=['POST'])
def admin_delete_user():
    d = request.json
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE username = %s AND role != 'admin'", (d['tk'],))
        conn.commit()
        return jsonify({"success": True})
    finally:
        if conn: conn.close()

# --- FILE TĨNH ---
@app.route('/')
def h(): return send_from_directory('.', 'index.html')

@app.route('/<path:p>')
def s(p):
    if p.startswith('api/'): return jsonify({"error": "Not Found"}), 404
    return send_from_directory('.', p)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)