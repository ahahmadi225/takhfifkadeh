import os
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_from_directory
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "takhfifkadeh-secret-key"

DB_PATH = '/home/entezar77/takhfifkadeh/takhfifkodeh.db'
UPDATE_SECRET_KEY = "takhfifkadeh-secret-2024-entezar77"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

SORT_OPTIONS = {"newest": "جدیدترین", "discount": "بیشترین تخفیف", "price_asc": "ارزان‌ترین", "price_desc": "گران‌ترین"}
STATUS_OPTIONS = {"": "همه وضعیت‌ها", "VERIFIED": "✅ تخفیف واقعی", "LIKELY_REAL": "🟡 احتمالاً واقعی", "SUSPICIOUS": "⚠️ تخفیف ساختگی"}
MIN_DISCOUNT_OPTIONS = {"": "همه تخفیف‌ها", "10": "حداقل ۱۰٪", "20": "حداقل ۲۰٪", "30": "حداقل ۳۰٪", "50": "حداقل ۵۰٪"}

def get_all_offers_with_verification(limit=500):
    """دریافت محصولات فعال با فیلتر NEEDS_RECHECK"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            o.id, o.product_id, o.product_url, o.seller_name as store_name,
            o.current_price, o.original_price, o.discount_percent,
            o.last_seen_at,
            p.title, p.image_url, p.category,
            s.slug as store_slug, s.name as store_display_name,
            v.status as verification_status, v.score, v.reason, v.checked_at
        FROM offers o
        JOIN products p ON p.id = o.product_id
        LEFT JOIN stores s ON s.id = o.store_id
        LEFT JOIN (
            SELECT product_id, status, score, reason, checked_at,
                   ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY checked_at DESC) as rn
            FROM verification_results
        ) v ON v.product_id = o.product_id AND v.rn = 1
        WHERE o.is_active = 1 
          AND p.is_active = 1 
          AND o.discount_percent > 0
          AND (v.status IS NULL OR v.status != 'NEEDS_RECHECK')
        ORDER BY o.last_seen_at DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_product_by_id(product_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    row = cur.fetchone()
    product = dict(row) if row else None
    conn.close()
    return product

def get_verification_for_product(product_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM verification_results WHERE product_id = ? ORDER BY checked_at DESC LIMIT 1", (product_id,))
    row = cur.fetchone()
    verification = dict(row) if row else None
    conn.close()
    return verification

def get_offers_for_product(product_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT o.*, s.name as store_name, s.slug as store_slug
        FROM offers o
        LEFT JOIN stores s ON s.id = o.store_id
        WHERE o.product_id = ? AND o.is_active = 1 AND o.discount_percent > 0
        ORDER BY o.current_price ASC
    """, (product_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_all_stores():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM stores ORDER BY name")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def apply_filters(offers, search=None, store_slug=None, sort="newest", min_discount=None, verification_status=None):
    result = list(offers)
    if search: result = [o for o in result if search.lower() in (o.get("title") or "").lower()]
    if store_slug: result = [o for o in result if o.get("store_slug") == store_slug]
    if min_discount is not None: result = [o for o in result if (o.get("discount_percent") or 0) >= min_discount]
    if verification_status: result = [o for o in result if o.get("verification_status") == verification_status]
    if sort == "discount": result.sort(key=lambda o: o.get("discount_percent") or 0, reverse=True)
    elif sort == "price_asc": result.sort(key=lambda o: o.get("current_price") or 0)
    elif sort == "price_desc": result.sort(key=lambda o: o.get("current_price") or 0, reverse=True)
    else: result.sort(key=lambda o: o.get("last_seen_at") or "", reverse=True)
    return result

def read_filter_args():
    search = request.args.get("q", "").strip()
    store_slug = request.args.get("store", "").strip()
    sort = request.args.get("sort", "newest").strip()
    verification_status = request.args.get("verification", "").strip()
    min_disc_raw = request.args.get("min_disc", "").strip()
    try: min_discount = int(min_disc_raw) if min_disc_raw else None
    except: min_discount = None; min_disc_raw = ""
    if sort not in SORT_OPTIONS: sort = "newest"
    if verification_status not in STATUS_OPTIONS: verification_status = ""
    return search, store_slug, sort, min_discount, verification_status, min_disc_raw

@app.after_request
def add_cache_control(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route("/")
def index():
    try:
        offers = get_all_offers_with_verification(limit=500)
        search, store_slug, sort, min_discount, verification_status, min_disc_raw = read_filter_args()
        filtered = apply_filters(offers, search=search or None, store_slug=store_slug or None,
                                 sort=sort, min_discount=min_discount, verification_status=verification_status or None)
        return render_template("index.html", discounts=filtered, stores=get_all_stores(), q=search,
                               current_store=store_slug, current_sort=sort, current_verification=verification_status,
                               current_min_disc=min_disc_raw,
                               has_filter=bool(search or store_slug or min_discount is not None or verification_status),
                               sort_options=SORT_OPTIONS, status_options=STATUS_OPTIONS,
                               min_discount_options=MIN_DISCOUNT_OPTIONS)
    except Exception as e:
        print(f"ERROR in index: {e}")
        import traceback
        traceback.print_exc()
        return f"Error: {e}", 500

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    try:
        product = get_product_by_id(product_id)
        if not product:
            flash("محصول مورد نظر پیدا نشد.", "warning")
            return redirect(url_for("index"))
        verification = get_verification_for_product(product_id)
        offers = get_offers_for_product(product_id)
        safe_offers = []
        for offer in offers:
            safe_offers.append({
                "store_name": offer.get("store_name") or offer.get("seller_name") or "نامشخص",
                "current_price": int(offer.get("current_price") or 0),
                "original_price": int(offer.get("original_price") or 0),
                "discount_percent": int(offer.get("discount_percent") or 0),
                "product_url": offer.get("product_url") or "#"
            })
        return render_template("product.html", product=product, verification=verification, offers=safe_offers)
    except Exception as e:
        print(f"ERROR in product_detail: {e}")
        import traceback
        traceback.print_exc()
        flash("خطا در بارگذاری جزئیات محصول.", "danger")
        return redirect(url_for("index"))

@app.route("/api/auto-update")
def auto_update():
    """Endpoint به‌روزرسانی خودکار با در نظر گرفتن سن داده‌ها"""
    try:
        secret = request.args.get("secret", "")
        if secret != UPDATE_SECRET_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # 1. غیرفعال کردن محصولات قدیمی (بیشتر از 14 روز)
        cutoff_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
        cur.execute("UPDATE offers SET is_active = 0 WHERE last_seen_at < ? AND is_active = 1", (cutoff_date,))
        deactivated = cur.rowcount
        
        # 2. به‌روزرسانی اعتبارسنجی با در نظر گرفتن سن داده
        cur.execute("""
            UPDATE verification_results 
            SET status = CASE
                -- اگر داده قدیمی است (بیشتر از 7 روز)، نیاز به بررسی مجدد
                WHEN julianday('now') - julianday(checked_at) > 7 THEN 'NEEDS_RECHECK'
                -- اگر داده تازه است، بر اساس discount و score
                WHEN claimed_discount_percent >= 50 AND score >= 50 THEN 'VERIFIED'
                WHEN claimed_discount_percent >= 20 AND score >= 30 THEN 'LIKELY_REAL'
                WHEN claimed_discount_percent < 10 THEN 'SUSPICIOUS'
                WHEN score >= 60 THEN 'LIKELY_REAL'
                WHEN score >= 40 THEN 'VERIFIED'
                ELSE 'SUSPICIOUS'
            END
            WHERE status != 'NEEDS_RECHECK'
        """)
        updated = cur.rowcount
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "deactivated_offers": deactivated,
            "updated_verifications": updated,
            "note": "Products older than 14 days deactivated, verifications older than 7 days marked as NEEDS_RECHECK"
        })
    except Exception as e:
        print(f"ERROR in auto_update: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/analytics")
def analytics_page():
    return "<h1>آمار - به زودی</h1>"

@app.route("/admin")
def admin():
    return "<h1>مدیریت - به زودی</h1>"

@app.route('/manifest.json')
def manifest():
    return send_from_directory('templates', 'manifest.json', mimetype='application/json')

@app.route('/service-worker.js')
def service_worker():
    return send_from_directory('static', 'service-worker.js', mimetype='application/javascript')

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=5000)