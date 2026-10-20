import sqlite3
from datetime import datetime


DB_NAME = "takhfifkodeh.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # ---------------------------------------------------------
    # جدول قدیمی تخفیف‌ها - برای حفظ سازگاری با نسخه قبلی
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS discounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            store TEXT NOT NULL,
            code TEXT NOT NULL,
            discount_percent INTEGER NOT NULL,
            link TEXT NOT NULL,
            image_url TEXT,
            original_price INTEGER,
            discounted_price INTEGER,
            market_avg_price INTEGER,
            is_verified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---------------------------------------------------------
    # فروشگاه‌ها
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            slug TEXT NOT NULL UNIQUE,
            website_url TEXT NOT NULL,
            logo_url TEXT,
            category TEXT,
            source_type TEXT NOT NULL DEFAULT 'WEBSITE',
            is_active INTEGER NOT NULL DEFAULT 1,
            last_checked_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---------------------------------------------------------
    # محصولات
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT,
            brand TEXT,
            model TEXT,
            category TEXT,
            description TEXT,
            image_url TEXT,
            canonical_url TEXT UNIQUE,
            external_product_id TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---------------------------------------------------------
    # پیشنهاد فروش / Offer
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            store_id INTEGER NOT NULL,
            product_url TEXT NOT NULL,
            seller_name TEXT,
            seller_type TEXT,
            current_price INTEGER,
            original_price INTEGER,
            currency TEXT NOT NULL DEFAULT 'IRR',
            availability TEXT,
            shipping_cost INTEGER,
            discount_percent INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (product_id)
                REFERENCES products(id)
                ON DELETE CASCADE,

            FOREIGN KEY (store_id)
                REFERENCES stores(id)
                ON DELETE CASCADE,

            UNIQUE(product_id, store_id, product_url)
        )
    """)

    # ---------------------------------------------------------
    # تاریخچه قیمت
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER NOT NULL,
            price INTEGER NOT NULL,
            original_price INTEGER,
            discount_percent INTEGER,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT,

            FOREIGN KEY (offer_id)
                REFERENCES offers(id)
                ON DELETE CASCADE
        )
    """)

    # ---------------------------------------------------------
    # نتایج بررسی واقعی بودن تخفیف
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verification_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            offer_id INTEGER,
            status TEXT NOT NULL DEFAULT 'UNKNOWN',
            score REAL NOT NULL DEFAULT 0,
            claimed_discount_percent INTEGER,
            historical_discount_percent REAL,
            market_discount_percent REAL,
            lowest_market_price INTEGER,
            average_market_price INTEGER,
            reason TEXT,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (product_id)
                REFERENCES products(id)
                ON DELETE CASCADE,

            FOREIGN KEY (offer_id)
                REFERENCES offers(id)
                ON DELETE SET NULL
        )
    """)

    # ---------------------------------------------------------
    # اجرای عملیات اسکراپ
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER,
            status TEXT NOT NULL DEFAULT 'PENDING',
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            products_found INTEGER NOT NULL DEFAULT 0,
            products_saved INTEGER NOT NULL DEFAULT 0,
            offers_saved INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (store_id)
                REFERENCES stores(id)
                ON DELETE SET NULL
        )
    """)

    # ---------------------------------------------------------
    # ایندکس‌ها برای سرعت بیشتر
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_stores_active
        ON stores(is_active)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_stores_category
        ON stores(category)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_products_active
        ON products(is_active)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_products_category
        ON products(category)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_products_brand
        ON products(brand)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_offers_product
        ON offers(product_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_offers_store
        ON offers(store_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_offers_active
        ON offers(is_active)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_price_history_offer
        ON price_history(offer_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_price_history_recorded
        ON price_history(recorded_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_verification_product
        ON verification_results(product_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_verification_status
        ON verification_results(status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_verification_offer_checked
        ON verification_results(offer_id, checked_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_scrape_jobs_store
        ON scrape_jobs(store_id)
    """)

    conn.commit()
    conn.close()


# =============================================================
# توابع قدیمی discounts
# =============================================================

def add_discount(
    title,
    store,
    code,
    discount_percent,
    link,
    image_url=None,
    original_price=None,
    discounted_price=None,
    market_avg_price=None,
    is_verified=0,
):
    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO discounts
        (
            title,
            store,
            code,
            discount_percent,
            link,
            image_url,
            original_price,
            discounted_price,
            market_avg_price,
            is_verified
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            store,
            code,
            discount_percent,
            link,
            image_url,
            original_price,
            discounted_price,
            market_avg_price,
            is_verified,
        ),
    )

    conn.commit()
    conn.close()


def get_all_discounts():
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM discounts
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return rows


# =============================================================
# فروشگاه‌ها
# =============================================================

def get_all_stores():
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM stores
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()

    conn.close()

    return rows


def seed_stores():
    from stores import STORE_CATALOG

    conn = get_connection()
    cursor = conn.cursor()

    added_count = 0

    for store in STORE_CATALOG:
        cursor.execute(
            """
            INSERT OR IGNORE INTO stores
            (
                name,
                slug,
                website_url,
                logo_url,
                category,
                source_type,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                store["name"],
                store["slug"],
                store["website_url"],
                store.get("logo_url"),
                store.get("category"),
                store.get("source_type", "WEBSITE"),
                store.get("is_active", 1),
            ),
        )

        if cursor.rowcount == 1:
            added_count += 1

    conn.commit()
    conn.close()

    return added_count


# =============================================================
# محصولات
# =============================================================

def get_or_create_product(
    title,
    canonical_url=None,
    image_url=None,
    brand=None,
    model=None,
    category=None,
    description=None,
    slug=None,
    external_product_id=None,
):
    conn = get_connection()
    cursor = conn.cursor()

    product = None

    if canonical_url:
        product = cursor.execute(
            """
            SELECT *
            FROM products
            WHERE canonical_url = ?
            LIMIT 1
            """,
            (canonical_url,),
        ).fetchone()

    if product:
        cursor.execute(
            """
            UPDATE products
            SET
                title = ?,
                image_url = COALESCE(?, image_url),
                brand = COALESCE(?, brand),
                model = COALESCE(?, model),
                category = COALESCE(?, category),
                description = COALESCE(?, description),
                slug = COALESCE(?, slug),
                external_product_id = COALESCE(
                    ?,
                    external_product_id
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                title,
                image_url,
                brand,
                model,
                category,
                description,
                slug,
                external_product_id,
                product["id"],
            ),
        )

        product = cursor.execute(
            """
            SELECT *
            FROM products
            WHERE id = ?
            """,
            (product["id"],),
        ).fetchone()

        conn.commit()
        conn.close()

        return product

    cursor.execute(
        """
        INSERT INTO products
        (
            title,
            slug,
            brand,
            model,
            category,
            description,
            image_url,
            canonical_url,
            external_product_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            slug,
            brand,
            model,
            category,
            description,
            image_url,
            canonical_url,
            external_product_id,
        ),
    )

    product_id = cursor.lastrowid

    product = cursor.execute(
        """
        SELECT *
        FROM products
        WHERE id = ?
        """,
        (product_id,),
    ).fetchone()

    conn.commit()
    conn.close()

    return product


# =============================================================
# محاسبه درصد تخفیف
# =============================================================

def calculate_discount_percent(original_price, current_price):
    if not original_price or not current_price:
        return None

    if original_price <= 0 or current_price <= 0:
        return None

    if current_price >= original_price:
        return 0

    discount = (
        (original_price - current_price)
        / original_price
    ) * 100

    return round(discount)


# =============================================================
# پیشنهاد فروش
# =============================================================

def get_or_create_offer(
    product_id,
    store_id,
    product_url,
    seller_name=None,
    seller_type=None,
    current_price=None,
    original_price=None,
    currency="IRR",
    availability=None,
    shipping_cost=None,
):
    conn = get_connection()
    cursor = conn.cursor()

    discount_percent = calculate_discount_percent(
        original_price,
        current_price,
    )

    offer = cursor.execute(
        """
        SELECT *
        FROM offers
        WHERE product_id = ?
          AND store_id = ?
          AND product_url = ?
        LIMIT 1
        """,
        (
            product_id,
            store_id,
            product_url,
        ),
    ).fetchone()

    if offer:
        cursor.execute(
            """
            UPDATE offers
            SET
                seller_name = COALESCE(?, seller_name),
                seller_type = COALESCE(?, seller_type),
                current_price = ?,
                original_price = ?,
                currency = ?,
                availability = COALESCE(?, availability),
                shipping_cost = COALESCE(
                    ?,
                    shipping_cost
                ),
                discount_percent = ?,
                is_active = 1,
                last_seen_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                seller_name,
                seller_type,
                current_price,
                original_price,
                currency,
                availability,
                shipping_cost,
                discount_percent,
                offer["id"],
            ),
        )

        offer = cursor.execute(
            """
            SELECT *
            FROM offers
            WHERE id = ?
            """,
            (offer["id"],),
        ).fetchone()

        conn.commit()
        conn.close()

        return offer

    cursor.execute(
        """
        INSERT INTO offers
        (
            product_id,
            store_id,
            product_url,
            seller_name,
            seller_type,
            current_price,
            original_price,
            currency,
            availability,
            shipping_cost,
            discount_percent
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            store_id,
            product_url,
            seller_name,
            seller_type,
            current_price,
            original_price,
            currency,
            availability,
            shipping_cost,
            discount_percent,
        ),
    )

    offer_id = cursor.lastrowid

    offer = cursor.execute(
        """
        SELECT *
        FROM offers
        WHERE id = ?
        """,
        (offer_id,),
    ).fetchone()

    conn.commit()
    conn.close()

    return offer


# =============================================================
# تاریخچه قیمت
# =============================================================

def add_price_history(
    offer_id,
    price,
    original_price=None,
    discount_percent=None,
    source=None,
):
    """
    ثبت تاریخچه قیمت.

    اگر آخرین رکورد همین Offer از نظر:
        - price
        - original_price
        - discount_percent
        - source

    کاملاً مشابه رکورد جدید باشد، رکورد تکراری ثبت نمی‌شود.

    در این حالت همان رکورد قبلی برگردانده می‌شود.

    اگر هرکدام از مقادیر تغییر کرده باشند، یک رکورد
    جدید در تاریخچه ثبت می‌شود.
    """

    conn = get_connection()
    cursor = conn.cursor()

    if discount_percent is None:
        discount_percent = calculate_discount_percent(
            original_price,
            price,
        )

    # ---------------------------------------------------------
    # آخرین رکورد تاریخچه این Offer
    # ---------------------------------------------------------
    last_row = cursor.execute(
        """
        SELECT *
        FROM price_history
        WHERE offer_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (offer_id,),
    ).fetchone()

    # ---------------------------------------------------------
    # جلوگیری از ثبت رکورد تکراری
    # ---------------------------------------------------------
    if last_row:
        same_price = last_row["price"] == price
        same_original_price = (
            last_row["original_price"] == original_price
        )
        same_discount = (
            last_row["discount_percent"] == discount_percent
        )
        same_source = last_row["source"] == source

        if (
            same_price
            and same_original_price
            and same_discount
            and same_source
        ):
            conn.close()
            return last_row

    # ---------------------------------------------------------
    # در صورت تغییر واقعی، رکورد جدید ثبت می‌شود
    # ---------------------------------------------------------
    cursor.execute(
        """
        INSERT INTO price_history
        (
            offer_id,
            price,
            original_price,
            discount_percent,
            source
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            offer_id,
            price,
            original_price,
            discount_percent,
            source,
        ),
    )

    history_id = cursor.lastrowid

    row = cursor.execute(
        """
        SELECT *
        FROM price_history
        WHERE id = ?
        """,
        (history_id,),
    ).fetchone()

    conn.commit()
    conn.close()

    return row


# =============================================================
# نتیجه بررسی تخفیف
# =============================================================

def add_verification_result(
    product_id,
    offer_id=None,
    status="UNKNOWN",
    score=0,
    claimed_discount_percent=None,
    historical_discount_percent=None,
    market_discount_percent=None,
    lowest_market_price=None,
    average_market_price=None,
    reason=None,
):
    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO verification_results
        (
            product_id,
            offer_id,
            status,
            score,
            claimed_discount_percent,
            historical_discount_percent,
            market_discount_percent,
            lowest_market_price,
            average_market_price,
            reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            offer_id,
            status,
            score,
            claimed_discount_percent,
            historical_discount_percent,
            market_discount_percent,
            lowest_market_price,
            average_market_price,
            reason,
        ),
    )

    result_id = cursor.lastrowid

    row = cursor.execute(
        """
        SELECT *
        FROM verification_results
        WHERE id = ?
        """,
        (result_id,),
    ).fetchone()

    conn.commit()
    conn.close()

    return row


# =============================================================
# Latest verification helpers
# =============================================================

def get_latest_verification(offer_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM verification_results
        WHERE offer_id = ?
        ORDER BY checked_at DESC, id DESC
        LIMIT 1
        """,
        (offer_id,),
    ).fetchone()
    conn.close()
    return row


def get_latest_verifications():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT vr.*
        FROM verification_results vr
        WHERE vr.id = (
            SELECT vr2.id
            FROM verification_results vr2
            WHERE vr2.offer_id = vr.offer_id
            ORDER BY vr2.checked_at DESC, vr2.id DESC
            LIMIT 1
        )
        ORDER BY vr.checked_at DESC, vr.id DESC
        """
    ).fetchall()
    conn.close()
    return rows


def create_scrape_job(store_id=None):
    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO scrape_jobs
        (
            store_id,
            status,
            started_at
        )
        VALUES (?, 'RUNNING', CURRENT_TIMESTAMP)
        """,
        (store_id,),
    )

    job_id = cursor.lastrowid

    row = cursor.execute(
        """
        SELECT *
        FROM scrape_jobs
        WHERE id = ?
        """,
        (job_id,),
    ).fetchone()

    conn.commit()
    conn.close()

    return row


def finish_scrape_job(
    job_id,
    status="SUCCESS",
    products_found=0,
    products_saved=0,
    offers_saved=0,
    error_count=0,
    error_message=None,
):
    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE scrape_jobs
        SET
            status = ?,
            finished_at = CURRENT_TIMESTAMP,
            products_found = ?,
            products_saved = ?,
            offers_saved = ?,
            error_count = ?,
            error_message = ?
        WHERE id = ?
        """,
        (
            status,
            products_found,
            products_saved,
            offers_saved,
            error_count,
            error_message,
            job_id,
        ),
    )

    row = cursor.execute(
        """
        SELECT *
        FROM scrape_jobs
        WHERE id = ?
        """,
        (job_id,),
    ).fetchone()

    conn.commit()
    conn.close()

    return row


# =============================================================
# دریافت پیشنهادهای فعال (معماری جدید)
# =============================================================

def get_all_active_offers(limit=50):
    """
    دریافت پیشنهادهای فعال از جدول‌های مدرن.
    این تابع محصولات فعال را با آخرین پیشنهاد آنها برمی‌گرداند.
    """
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            p.id AS product_id,
            p.title,
            p.image_url,
            p.category,
            p.canonical_url AS link,
            s.name AS store_name,
            s.slug AS store_slug,
            o.id AS offer_id,
            o.current_price AS discounted_price,
            o.original_price,
            o.discount_percent,
            o.last_seen_at,
            vr.status AS verification_status,
            vr.score AS verification_score,
            vr.reason AS verification_reason
        FROM products p
        JOIN offers o ON o.product_id = p.id
        JOIN stores s ON s.id = o.store_id
        LEFT JOIN verification_results vr ON vr.offer_id = o.id
            AND vr.id = (
                SELECT vr2.id
                FROM verification_results vr2
                WHERE vr2.offer_id = o.id
                ORDER BY vr2.checked_at DESC, vr2.id DESC
                LIMIT 1
            )
        WHERE p.is_active = 1
          AND o.is_active = 1
          AND o.current_price IS NOT NULL
          AND o.current_price > 0
        ORDER BY vr.score DESC, o.discount_percent DESC, o.last_seen_at DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    conn.close()
    return rows


def get_offers_count():
    """تعداد کل پیشنهادهای فعال"""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT COUNT(*) as total
        FROM offers o
        JOIN products p ON p.id = o.product_id
        WHERE p.is_active = 1 AND o.is_active = 1
        """
    ).fetchone()
    conn.close()
    return row["total"] if row else 0


# =============================================================
# توابع صفحه جزئیات محصول
# =============================================================

def get_product_details(product_id):
    """دریافت جزئیات کامل یک محصول با آخرین وضعیت اعتبار."""
    conn = get_connection()

    product = conn.execute(
        """
        SELECT * FROM products WHERE id = ?
        """,
        (product_id,)
    ).fetchone()

    if not product:
        conn.close()
        return None

    verification = conn.execute(
        """
        SELECT *
        FROM verification_results
        WHERE product_id = ?
        ORDER BY checked_at DESC, id DESC
        LIMIT 1
        """,
        (product_id,)
    ).fetchone()

    conn.close()

    return {
        "product": product,
        "verification": verification,
    }


def get_offers_for_product(product_id):
    """دریافت همه پیشنهادهای فعال یک محصول از فروشگاه‌های مختلف."""
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            o.*,
            s.name AS store_name,
            s.slug AS store_slug,
            s.website_url AS store_website,
            vr.status AS verification_status,
            vr.score AS verification_score,
            vr.reason AS verification_reason,
            vr.claimed_discount_percent,
            vr.historical_discount_percent,
            vr.market_discount_percent
        FROM offers o
        JOIN stores s ON s.id = o.store_id
        LEFT JOIN verification_results vr ON vr.offer_id = o.id
            AND vr.id = (
                SELECT vr2.id
                FROM verification_results vr2
                WHERE vr2.offer_id = o.id
                ORDER BY vr2.checked_at DESC, vr2.id DESC
                LIMIT 1
            )
        WHERE o.product_id = ?
          AND o.is_active = 1
          AND o.current_price IS NOT NULL
        ORDER BY o.current_price ASC
        """,
        (product_id,)
    ).fetchall()

    conn.close()
    return rows


def get_price_history_for_offer(offer_id):
    """دریافت تاریخچه قیمت یک پیشنهاد به ترتیب زمانی."""
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            id,
            price,
            original_price,
            discount_percent,
            recorded_at,
            source
        FROM price_history
        WHERE offer_id = ?
        ORDER BY recorded_at ASC, id ASC
        """,
        (offer_id,)
    ).fetchall()

    conn.close()
    return rows


# =============================================================
# مقداردهی اولیه دیتابیس
# =============================================================

init_db()