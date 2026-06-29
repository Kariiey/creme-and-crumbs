from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for, flash)
from datetime import datetime, date
import sqlite3, hashlib, secrets, os, base64

app = Flask(__name__)

# =============================================================================
# ✏️  EDITABLE CONFIGURATION — Change all your prices, fees, and info here
# =============================================================================

app.secret_key = "cremeandcrumbs-super-secret-key-2025"

# --- Bakery Info ---
BAKERY_NAME     = "Créme & Crumbs"
BAKERY_TAGLINE  = "Made with Crème, Baked with Love"
WHATSAPP_NUMBER = "27621351367"
PHONE_NUMBER    = "+27 62 135 1367"
TIKTOK_URL      = "https://www.tiktok.com/@creme_crumbs.sa"
EMAIL_ADDRESS   = "creme.crumbs@icloud.com"

# --- Bank Account Details ---
BANK_NAME           = "Capitec Bank"
BANK_ACCOUNT_NUMBER = "2231580892"
BANK_ACCOUNT_HOLDER = "Créme & Crumbs"

# --- Standard Flavours ---
FLAVOURS = ["Vanilla", "Chocolate", "Red Velvet", "Strawberry"]

# --- Custom Flavour Fees ---
CAKE_IN_CUP_CUSTOM_FLAVOUR_FEE = 15
CUPCAKE_CUSTOM_FLAVOUR_FEE     = 50
CAKE_CUSTOM_FLAVOUR_FEE        = 200

# --- Cake in a Cup ---
CAKE_IN_CUP_PRICE = 45

# --- Cupcake Prices ---
CUPCAKE_PRICES = {6: 120, 12: 220, 24: 420, 48: 800}

# --- Cake Prices ---
ONE_TIER_PRICES   = {18:580, 20:680, 22:780, 24:880, 26:990, 28:1200}
TWO_TIER_PRICES   = {18:1100,20:1300,22:1500,24:1700,26:1900,28:2200}
THREE_TIER_PRICES = {18:1800,20:2100,22:2400,24:2700,26:3000,28:3500}

# --- Layer Pricing ---
DEFAULT_MIN_LAYERS = 3
DEFAULT_MAX_LAYERS = 4
EXTRA_LAYER_FEE    = 50

# --- Rush Order (CAKES only) ---
RUSH_ORDER_DAYS = 14
RUSH_FEE        = 250

# --- Minimum Notice (Cake in a Cup & Cupcakes — no fee, just a minimum) ---
MIN_NOTICE_SMALL_ITEMS = 4

# --- Deposit ---
DEPOSIT_PERCENTAGE = 50

# --- Loyalty Discounts (✏️ edit % anytime) ---
FIRST_ORDER_DISCOUNT_PCT = 15   # % off a customer's 1st order
SIXTH_ORDER_DISCOUNT_PCT = 20   # % off a customer's 6th order

# --- Birthday Voucher ---
BIRTHDAY_VOUCHER_AMOUNT   = 50   # R amount off a cake order during birthday month
BIRTHDAY_VOUCHER_DAYS_VALID = 30 # Voucher valid for this many days around the birthday

# --- Scones Menu (✏️ edit prices/sizes anytime) ---
PLAIN_SCONES_PRICES = {
    "2.5 Litre": 180,
    "5 Litre":   300,
    "10 Litre":  470,
    "20 Litre":  780,
    "25 Litre":  970,
}
CUSTARD_SCONES_PRICES = {
    "2.5 Litre (Box)": 230,
    "5 Litre":         330,
    "10 Litre":        590,
    "20 Litre":        800,
    "25 Litre":        1000,
}
LEMON_BLUEBERRY_SCONES_PRICES = {
    "2.5 Litre (Box)": 280,
    "5 Litre":         400,
    "10 Litre":        650,
    "20 Litre":        1100,
}
ASSORTED_SCONES_PRICES = {
    "5 Litre":  420,
    "10 Litre": 720,
    "20 Litre": 1100,
    "25 Litre": 1300,
}
ASSORTED_BOX_PRICE       = 290   # Includes 8 Muffins, 4 Scones, 10 Biscuits
ASSORTED_BOX_CONTENTS    = ["8 Muffins", "4 Scones", "10 Biscuits"]

# =============================================================================
# END OF EDITABLE CONFIGURATION
# =============================================================================

DB_PATH = os.path.join(os.path.dirname(__file__), "bakery.db")


# ── Database setup ──────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            email        TEXT    NOT NULL UNIQUE,
            phone        TEXT    NOT NULL,
            password     TEXT    NOT NULL,
            birth_date   TEXT,
            created_at   TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS orders (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id               INTEGER NOT NULL,
            product               TEXT    NOT NULL,
            details               TEXT,
            flavour               TEXT,
            custom_flavour_detail TEXT,
            custom_request        TEXT,
            event_date            TEXT,
            base_price            REAL,
            rush_fee              REAL    DEFAULT 0,
            extra_layer_fee       REAL    DEFAULT 0,
            custom_flavour_fee    REAL    DEFAULT 0,
            discount_pct          REAL    DEFAULT 0,
            discount_amount       REAL    DEFAULT 0,
            birthday_voucher_used REAL    DEFAULT 0,
            total                 REAL,
            deposit               REAL,
            is_rush               INTEGER DEFAULT 0,
            status                TEXT    DEFAULT 'Pending',
            created_at            TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS password_resets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            token      TEXT    NOT NULL UNIQUE,
            expires_at TEXT    NOT NULL,
            used       INTEGER DEFAULT 0,
            created_at TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)
        # In case the users table existed before from an older version, add birth_date safely
        try:
            db.execute("ALTER TABLE users ADD COLUMN birth_date TEXT")
        except sqlite3.OperationalError:
            pass  # already exists
    print("Database ready.")


# ── Password helpers ─────────────────────────────────────────────────────────

def hash_password(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def check_password(stored, provided):
    try:
        salt, hashed = stored.split(":")
        return hashed == hashlib.sha256((salt + provided).encode()).hexdigest()
    except Exception:
        return False


# ── Auth helpers ─────────────────────────────────────────────────────────────

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def login_required(f):
    import functools
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Loyalty / Birthday helpers ────────────────────────────────────────────────

def get_completed_order_count(user_id, db=None):
    """Counts how many orders this user has placed before (used to know if next order is their 1st or 6th)."""
    close = False
    if db is None:
        db = get_db()
        close = True
    count = db.execute("SELECT COUNT(*) as c FROM orders WHERE user_id=?", (user_id,)).fetchone()["c"]
    if close:
        db.close()
    return count


def get_order_discount_pct(previous_order_count):
    """
    previous_order_count = how many orders the user has ALREADY placed.
    The order about to be placed will be number (previous_order_count + 1).
    1st order  -> 15% off
    6th order  -> 20% off
    All others -> 0%
    """
    upcoming_order_number = previous_order_count + 1
    if upcoming_order_number == 1:
        return FIRST_ORDER_DISCOUNT_PCT
    elif upcoming_order_number == 6:
        return SIXTH_ORDER_DISCOUNT_PCT
    return 0


def is_birthday_voucher_active(birth_date_str):
    """Returns True if today falls within BIRTHDAY_VOUCHER_DAYS_VALID days of the user's birthday (any year)."""
    if not birth_date_str:
        return False
    try:
        bday = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
        today = date.today()
        # Build this year's birthday (handle Feb 29 safely)
        try:
            this_year_bday = bday.replace(year=today.year)
        except ValueError:
            this_year_bday = bday.replace(year=today.year, day=28)
        days_diff = (today - this_year_bday).days
        # Also check next year's birthday wrap-around (e.g. birthday was in Dec, now it's Jan)
        try:
            last_year_bday = bday.replace(year=today.year - 1)
        except ValueError:
            last_year_bday = bday.replace(year=today.year - 1, day=28)
        days_diff_prev = (today - last_year_bday).days

        return (0 <= days_diff <= BIRTHDAY_VOUCHER_DAYS_VALID) or \
               (0 <= days_diff_prev <= BIRTHDAY_VOUCHER_DAYS_VALID)
    except Exception:
        return False


# ── Price calculation ─────────────────────────────────────────────────────────

def calculate_price(product, options, user=None, db=None):
    price = rush_fee = extra_layer_fee = custom_flavour_fee = 0
    rush      = False
    too_soon  = False
    days_left = None

    if options.get("event_date"):
        try:
            event     = datetime.strptime(options["event_date"], "%Y-%m-%d").date()
            days_left = (event - date.today()).days
        except Exception:
            pass

    # Rush fee applies ONLY to celebration cakes — needs 14+ days notice
    if product == "cake" and days_left is not None and days_left < RUSH_ORDER_DAYS:
        rush     = True
        rush_fee = RUSH_FEE

    # Cake in a Cup & Cupcakes just need 4+ days notice — no fee, just blocked if too soon
    if product in ("cake_in_cup", "cupcakes") and days_left is not None and days_left < MIN_NOTICE_SMALL_ITEMS:
        too_soon = True

    if product == "cake_in_cup":
        qty       = int(options.get("quantity", 1))
        flavours  = options.get("flavours", []) or []
        price     = CAKE_IN_CUP_PRICE * qty
        custom_count = flavours.count("Custom")
        if custom_count:
            custom_flavour_fee = CAKE_IN_CUP_CUSTOM_FLAVOUR_FEE * qty * custom_count

    elif product == "cupcakes":
        qty       = int(options.get("quantity", 6))
        flavours  = options.get("flavours", []) or []
        price     = CUPCAKE_PRICES.get(qty, CUPCAKE_PRICES[6])
        custom_count = flavours.count("Custom")
        if custom_count:
            custom_flavour_fee = CUPCAKE_CUSTOM_FLAVOUR_FEE * custom_count

    elif product == "cake":
        tiers  = int(options.get("tiers", 1))
        layers = int(options.get("layers", DEFAULT_MIN_LAYERS))
        s1     = int(options.get("size_tier1", 20))

        if tiers == 1:
            price = ONE_TIER_PRICES.get(s1, ONE_TIER_PRICES[20])
        elif tiers == 2:
            s2    = int(options.get("size_tier2", 18))
            price = TWO_TIER_PRICES.get(s1, TWO_TIER_PRICES[20]) + \
                    ONE_TIER_PRICES.get(s2, ONE_TIER_PRICES[18])
        elif tiers == 3:
            s2    = int(options.get("size_tier2", 20))
            s3    = int(options.get("size_tier3", 18))
            price = THREE_TIER_PRICES.get(s1, THREE_TIER_PRICES[24]) + \
                    TWO_TIER_PRICES.get(s2, TWO_TIER_PRICES[20]) + \
                    ONE_TIER_PRICES.get(s3, ONE_TIER_PRICES[18])

        if layers > DEFAULT_MAX_LAYERS:
            extra_layer_fee = (layers - DEFAULT_MAX_LAYERS) * EXTRA_LAYER_FEE

        # Each tier has its own flavour list — "Custom" in any tier adds a fee for that tier
        flavours_tier1 = options.get("flavours_tier1", []) or []
        flavours_tier2 = options.get("flavours_tier2", []) or []
        flavours_tier3 = options.get("flavours_tier3", []) or []
        custom_count = flavours_tier1.count("Custom") + flavours_tier2.count("Custom") + flavours_tier3.count("Custom")
        if custom_count:
            custom_flavour_fee = CAKE_CUSTOM_FLAVOUR_FEE * custom_count

    elif product == "scones":
        scone_type = options.get("scone_type", "")
        size       = options.get("scone_size", "")
        price_map  = {
            "plain": PLAIN_SCONES_PRICES,
            "custard": CUSTARD_SCONES_PRICES,
            "lemon_blueberry": LEMON_BLUEBERRY_SCONES_PRICES,
            "assorted": ASSORTED_SCONES_PRICES,
        }
        if scone_type == "assorted_box":
            price = ASSORTED_BOX_PRICE
        else:
            sizes = price_map.get(scone_type, {})
            price = sizes.get(size, 0)

    subtotal_before_discount = price + rush_fee + extra_layer_fee + custom_flavour_fee

    # ── Loyalty discount (1st order 15%, 6th order 20%) ──
    discount_pct    = 0
    discount_amount = 0
    if user is not None:
        previous_orders = get_completed_order_count(user["id"], db=db)
        discount_pct    = get_order_discount_pct(previous_orders)
        if discount_pct > 0:
            discount_amount = subtotal_before_discount * (discount_pct / 100)

    # ── Birthday voucher (R50 off CAKE orders only, during birthday month) ──
    birthday_voucher_used = 0
    birthday_active = False
    if user is not None and product == "cake":
        birth_date = user["birth_date"] if "birth_date" in user.keys() else None
        if is_birthday_voucher_active(birth_date):
            birthday_active = True
            birthday_voucher_used = min(BIRTHDAY_VOUCHER_AMOUNT, subtotal_before_discount - discount_amount)

    total   = subtotal_before_discount - discount_amount - birthday_voucher_used
    total   = max(total, 0)
    deposit = total * (DEPOSIT_PERCENTAGE / 100)

    return dict(base_price=price, rush_fee=rush_fee, extra_layer_fee=extra_layer_fee,
                custom_flavour_fee=custom_flavour_fee, discount_pct=discount_pct,
                discount_amount=discount_amount, birthday_voucher_used=birthday_voucher_used,
                birthday_active=birthday_active, total=total, deposit=deposit,
                is_rush=rush, too_soon=too_soon)



# ════════════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html", bakery_name=BAKERY_NAME,
        tagline=BAKERY_TAGLINE, whatsapp=WHATSAPP_NUMBER,
        phone=PHONE_NUMBER, tiktok=TIKTOK_URL, flavours=FLAVOURS,
        user=current_user())


@app.route("/menu")
def menu():
    return render_template("menu.html", bakery_name=BAKERY_NAME,
        flavours=FLAVOURS, cake_cup_price=CAKE_IN_CUP_PRICE,
        cupcake_prices=CUPCAKE_PRICES, one_tier=ONE_TIER_PRICES,
        two_tier=TWO_TIER_PRICES, three_tier=THREE_TIER_PRICES,
        plain_scones=PLAIN_SCONES_PRICES,
        custard_scones=CUSTARD_SCONES_PRICES,
        lemon_blueberry_scones=LEMON_BLUEBERRY_SCONES_PRICES,
        assorted_scones=ASSORTED_SCONES_PRICES,
        assorted_box_price=ASSORTED_BOX_PRICE,
        assorted_box_contents=ASSORTED_BOX_CONTENTS,
        whatsapp=WHATSAPP_NUMBER, phone=PHONE_NUMBER,
        tiktok=TIKTOK_URL, user=current_user())


@app.route("/terms")
def terms():
    return render_template("terms.html", bakery_name=BAKERY_NAME,
        whatsapp=WHATSAPP_NUMBER, phone=PHONE_NUMBER,
        tiktok=TIKTOK_URL, user=current_user())


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name       = request.form.get("name", "").strip()
        email      = request.form.get("email", "").strip().lower()
        phone      = request.form.get("phone", "").strip()
        birth_date = request.form.get("birth_date", "").strip()
        password   = request.form.get("password", "")
        confirm    = request.form.get("confirm", "")

        if not all([name, email, phone, birth_date, password]):
            flash("Please fill in all fields, including your birth date.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        else:
            try:
                with get_db() as db:
                    db.execute(
                        "INSERT INTO users (name,email,phone,password,birth_date) VALUES (?,?,?,?,?)",
                        (name, email, phone, hash_password(password), birth_date)
                    )
                flash("Account created! Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.", "error")

    return render_template("signup.html", bakery_name=BAKERY_NAME)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password(user["password"], password):
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}! 🎂", "success")
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "error")

    return render_template("login.html", bakery_name=BAKERY_NAME)


@app.route("/forgot-password")
def forgot_password():
    """Customers who forget their password are directed to WhatsApp the bakery directly.
    The bakery owner then resets the password manually via the Admin Panel."""
    return render_template("forgot_password.html", bakery_name=BAKERY_NAME,
                           whatsapp=WHATSAPP_NUMBER)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ── Customer dashboard ────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    with get_db() as db:
        orders = db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC",
            (user["id"],)
        ).fetchall()
        previous_orders = get_completed_order_count(user["id"], db=db)

    next_order_number  = previous_orders + 1
    next_discount_pct  = get_order_discount_pct(previous_orders)
    birthday_active    = is_birthday_voucher_active(user["birth_date"] if "birth_date" in user.keys() else None)

    return render_template("dashboard.html", bakery_name=BAKERY_NAME,
                           user=user, orders=orders,
                           whatsapp=WHATSAPP_NUMBER, phone=PHONE_NUMBER,
                           tiktok=TIKTOK_URL,
                           next_order_number=next_order_number,
                           next_discount_pct=next_discount_pct,
                           birthday_active=birthday_active,
                           birthday_voucher_amount=BIRTHDAY_VOUCHER_AMOUNT)


# ── Order page ────────────────────────────────────────────────────────────────

@app.route("/order")
@login_required
def order():
    user = current_user()
    with get_db() as db:
        previous_orders = get_completed_order_count(user["id"], db=db)
    next_discount_pct = get_order_discount_pct(previous_orders)
    birthday_active   = is_birthday_voucher_active(user["birth_date"] if "birth_date" in user.keys() else None)

    return render_template("order.html", bakery_name=BAKERY_NAME,
        flavours=FLAVOURS,
        cupcake_quantities=list(CUPCAKE_PRICES.keys()),
        cake_sizes=list(ONE_TIER_PRICES.keys()),
        rush_days=RUSH_ORDER_DAYS, rush_fee=RUSH_FEE,
        deposit_pct=DEPOSIT_PERCENTAGE,
        whatsapp=WHATSAPP_NUMBER, phone=PHONE_NUMBER,
        tiktok=TIKTOK_URL, bank_name=BANK_NAME,
        bank_account=BANK_ACCOUNT_NUMBER, bank_holder=BANK_ACCOUNT_HOLDER,
        cup_custom_fee=CAKE_IN_CUP_CUSTOM_FLAVOUR_FEE,
        cupcake_custom_fee=CUPCAKE_CUSTOM_FLAVOUR_FEE,
        cake_custom_fee=CAKE_CUSTOM_FLAVOUR_FEE,
        plain_scones=PLAIN_SCONES_PRICES,
        custard_scones=CUSTARD_SCONES_PRICES,
        lemon_blueberry_scones=LEMON_BLUEBERRY_SCONES_PRICES,
        assorted_scones=ASSORTED_SCONES_PRICES,
        assorted_box_price=ASSORTED_BOX_PRICE,
        next_discount_pct=next_discount_pct,
        birthday_active=birthday_active,
        birthday_voucher_amount=BIRTHDAY_VOUCHER_AMOUNT,
        user=user)


@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json()
    user = current_user()
    with get_db() as db:
        result = calculate_price(data.get("product"), data, user=user, db=db)
    return jsonify(result)


def format_flavour_text(data):
    """Builds a readable flavour summary string depending on the product type,
    since cake_in_cup/cupcakes use a single flavour list, but cakes have
    a separate flavour list per tier."""
    product = data.get("product")

    if product == "cake":
        parts = []
        for i, key in enumerate(["flavours_tier1", "flavours_tier2", "flavours_tier3"], start=1):
            flavours = data.get(key) or []
            if flavours:
                parts.append(f"Tier {i}: {', '.join(flavours)}")
        return " | ".join(parts) if parts else "N/A"
    else:
        flavours = data.get("flavours") or []
        return ", ".join(flavours) if flavours else "N/A"


def format_custom_flavour_detail(data):
    """Builds a readable custom-flavour description string, since cakes can have
    a different custom flavour description per tier."""
    product = data.get("product")

    if product == "cake":
        parts = []
        for i, key in enumerate(["custom_flavour_detail_tier1", "custom_flavour_detail_tier2", "custom_flavour_detail_tier3"], start=1):
            detail = (data.get(key) or "").strip()
            if detail:
                parts.append(f"Tier {i}: {detail}")
        return " | ".join(parts) if parts else ""
    else:
        return (data.get("custom_flavour_detail") or "").strip()


@app.route("/submit-order", methods=["POST"])
@login_required
def submit_order():
    user = current_user()
    data = request.get_json()
    with get_db() as db:
        p = calculate_price(data.get("product"), data, user=user, db=db)

    details        = data.get("details", "")
    flavour_text    = format_flavour_text(data)
    custom_flavour_text = format_custom_flavour_detail(data)

    with get_db() as db:
        db.execute("""
            INSERT INTO orders
            (user_id, product, details, flavour, custom_flavour_detail,
             custom_request, event_date, base_price, rush_fee,
             extra_layer_fee, custom_flavour_fee, discount_pct, discount_amount,
             birthday_voucher_used, total, deposit, is_rush, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            user["id"], data.get("product"), details,
            flavour_text, custom_flavour_text,
            data.get("custom_request",""), data.get("event_date"),
            p["base_price"], p["rush_fee"], p["extra_layer_fee"],
            p["custom_flavour_fee"], p["discount_pct"], p["discount_amount"],
            p["birthday_voucher_used"], p["total"], p["deposit"],
            1 if p["is_rush"] else 0, "Pending"
        ))

    order_data = {**data, **p}
    order_data["flavour"] = flavour_text
    order_data["custom_flavour_detail"] = custom_flavour_text
    # Email notifications removed — Render's free tier can't reliably reach
    # iCloud's mail servers. Order notifications now go through WhatsApp instead
    # (see owner_wa_link below), and every order is always visible in /admin.

    discount_line = ""
    if p["discount_pct"] > 0:
        discount_line = f"🎉 Loyalty Discount ({p['discount_pct']:.0f}%): -R{p['discount_amount']:.2f}\n"
    if p["birthday_voucher_used"] > 0:
        discount_line += f"🎂 Birthday Voucher: -R{p['birthday_voucher_used']:.2f}\n"

    wa_msg = (
        f"🎂 *New Order — {BAKERY_NAME}*\n\n"
        f"*Customer:* {user['name']}\n"
        f"*Phone:* {user['phone']}\n"
        f"*Email:* {user['email']}\n"
        f"*Product:* {data.get('product')}\n"
        f"*Flavour(s):* {flavour_text}\n"
        f"*Custom Flavour:* {custom_flavour_text or 'N/A'}\n"
        f"*Details:* {details}\n"
        f"*Event Date:* {data.get('event_date')}\n"
        f"*Custom Request:* {data.get('custom_request','None')}\n\n"
        + (f"⚠️ RUSH ORDER — Rush Fee: R{RUSH_FEE}\n" if p["is_rush"] else "")
        + (f"✨ Custom Flavour Fee: R{p['custom_flavour_fee']}\n" if p["custom_flavour_fee"] else "")
        + discount_line
        + f"*Total: R{p['total']:.2f}*\n"
        f"*50% Deposit: R{p['deposit']:.2f}*\n"
        f"_Deposit is non-refundable._\n\n"
        f"💳 *Payment:*\n{BANK_NAME}\n"
        f"Account: *{BANK_ACCOUNT_NUMBER}*\n"
        f"Name: *{BANK_ACCOUNT_HOLDER}*\n"
        f"_Use your name as reference._"
    )

    return jsonify(success=True, total=p["total"], deposit=p["deposit"],
                   is_rush=p["is_rush"], rush_fee=p["rush_fee"],
                   custom_flavour_fee=p["custom_flavour_fee"],
                   discount_pct=p["discount_pct"], discount_amount=p["discount_amount"],
                   birthday_voucher_used=p["birthday_voucher_used"],
                   whatsapp_message=wa_msg, whatsapp_number=WHATSAPP_NUMBER)


# ── Admin ──────────────────────────────────────────────────────────────────────

ADMIN_PASSWORD = "cremecrumbs2025"   # ✏️ Change this to your own admin password

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST" and request.form.get("admin_pass") == ADMIN_PASSWORD:
        session["is_admin"] = True

    if not session.get("is_admin"):
        return render_template("admin_login.html", bakery_name=BAKERY_NAME)

    with get_db() as db:
        orders = db.execute("""
            SELECT o.*, u.name as customer_name, u.email, u.phone
            FROM orders o JOIN users u ON o.user_id = u.id
            ORDER BY o.created_at DESC
        """).fetchall()

    return render_template("admin.html", bakery_name=BAKERY_NAME, orders=orders)


@app.route("/admin/update-status", methods=["POST"])
def admin_update_status():
    if not session.get("is_admin"):
        return jsonify(error="Unauthorized"), 403
    data       = request.get_json()
    order_id   = data.get("order_id")
    new_status = data.get("status")
    allowed    = ["Pending", "Confirmed", "In Progress", "Ready", "Completed", "Cancelled"]
    if new_status not in allowed:
        return jsonify(error="Invalid status"), 400
    with get_db() as db:
        db.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    return jsonify(success=True)


@app.route("/admin/reset-password", methods=["POST"])
def admin_reset_password():
    """Bakery owner manually resets a customer's password (used when a customer
    WhatsApps in saying they forgot their password)."""
    if not session.get("is_admin"):
        return jsonify(error="Unauthorized"), 403

    data         = request.get_json()
    email        = data.get("email", "").strip().lower()
    new_password = data.get("new_password", "")

    if not email or not new_password:
        return jsonify(error="Email and new password are required"), 400
    if len(new_password) < 6:
        return jsonify(error="Password must be at least 6 characters"), 400

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            return jsonify(error="No account found with that email"), 404
        db.execute("UPDATE users SET password=? WHERE id=?",
                   (hash_password(new_password), user["id"]))

    return jsonify(success=True, name=user["name"])


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=10000)