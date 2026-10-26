import os, sqlite3, secrets
from functools import wraps
from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "campusshare.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_IMAGES = {"jpg", "jpeg", "png", "webp"}
app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# Set this to your actual college email domain(s), comma-separated.
ALLOWED_DOMAINS = [x.strip().lower() for x in os.getenv("ALLOWED_DOMAINS", "snsct.org").split(",") if x.strip()]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS listings(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL,
          category TEXT NOT NULL, listing_type TEXT NOT NULL, price REAL DEFAULT 0,
          location TEXT DEFAULT '', description TEXT DEFAULT '', image TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(user_id) REFERENCES users(id))""")
        columns = {row["name"] for row in c.execute("PRAGMA table_info(listings)").fetchall()}
        if "image" not in columns:
            c.execute("ALTER TABLE listings ADD COLUMN image TEXT DEFAULT ''")
        c.execute("""CREATE TABLE IF NOT EXISTS requests(
          id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL, requester_id INTEGER NOT NULL,
          status TEXT DEFAULT 'Pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(listing_id, requester_id),
          FOREIGN KEY(listing_id) REFERENCES listings(id), FOREIGN KEY(requester_id) REFERENCES users(id))""")

def user_dict(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"]} if row else None

def current_user():
    uid = session.get("user_id")
    if not uid: return None
    with db() as c:
        return user_dict(c.execute("SELECT id,name,email FROM users WHERE id=?", (uid,)).fetchone())

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user(): return jsonify(error="Please log in to continue."), 401
        return fn(*args, **kwargs)
    return wrapper

def valid_college_email(email):
    if "@" not in email: return False
    domain = email.rsplit("@", 1)[1].lower()
    return any(domain == allowed or domain.endswith("." + allowed) for allowed in ALLOWED_DOMAINS)

@app.get("/")
def home(): return send_from_directory(BASE_DIR, "index.html")
@app.get("/style.css")
def style(): return send_from_directory(BASE_DIR, "style.css")
@app.get("/app.js")
def javascript(): return send_from_directory(BASE_DIR, "app.js")

@app.get("/api/me")
def me(): return jsonify(user=current_user())

@app.get("/uploads/<path:filename>")
def uploaded_image(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if len(name) < 2: return jsonify(error="Enter your full name."), 400
    if not valid_college_email(email): return jsonify(error="Use your approved college email address."), 400
    if len(password) < 8: return jsonify(error="Password must be at least 8 characters."), 400
    try:
        with db() as c:
            cur = c.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)", (name,email,generate_password_hash(password)))
            uid = cur.lastrowid
    except sqlite3.IntegrityError:
        return jsonify(error="An account already exists for this email. Please log in."), 409
    session["user_id"] = uid
    return jsonify(user={"id":uid,"name":name,"email":email}), 201

@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    with db() as c: row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify(error="Incorrect email or password."), 401
    session["user_id"] = row["id"]
    return jsonify(user=user_dict(row))

@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(message="Logged out.")

@app.get("/api/listings")
def get_listings():
    with db() as c:
        rows = c.execute("""SELECT l.*,u.name AS owner_name FROM listings l JOIN users u ON u.id=l.user_id
          ORDER BY l.created_at DESC,l.id DESC""").fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["image_url"] = "/uploads/" + item["image"] if item.get("image") else None
        items.append(item)
    return jsonify(listings=items)

@app.post("/api/listings")
@login_required
def create_listing():
    # The form uses multipart/form-data so the actual image reaches the backend.
    data = request.form
    image_file = request.files.get("image")
    title = str(data.get("title", "")).strip()
    category = str(data.get("category", "Other")).strip()
    listing_type = str(data.get("listing_type", "share")).strip()
    location = str(data.get("location", "")).strip()
    description = str(data.get("description", "")).strip()
    try:
        price = float(data.get("price", 0) or 0)
        if price < 0: raise ValueError
    except (TypeError, ValueError):
        return jsonify(error="Enter a valid price."), 400
    if not title: return jsonify(error="Enter a resource name."), 400
    if category not in {"Books", "Electronics", "Lab Equipment", "Sports", "Other"}:
        return jsonify(error="Choose a valid category."), 400
    if listing_type not in {"borrow", "lend", "sell", "share"}:
        return jsonify(error="Choose a valid sharing type."), 400
    if not image_file or not image_file.filename:
        return jsonify(error="Please upload a photo of your actual product."), 400
    original_name = secure_filename(image_file.filename)
    if "." not in original_name or original_name.rsplit(".", 1)[1].lower() not in ALLOWED_IMAGES:
        return jsonify(error="Photo must be JPG, JPEG, PNG or WEBP."), 400
    if image_file.mimetype not in {"image/jpeg", "image/png", "image/webp"}:
        return jsonify(error="Please upload a valid image file."), 400
    extension = original_name.rsplit(".", 1)[1].lower()
    saved_name = f"{uuid.uuid4().hex}.{extension}"
    image_file.save(os.path.join(UPLOAD_DIR, saved_name))
    u = current_user()
    try:
        with db() as c:
            cur = c.execute("INSERT INTO listings(user_id,title,category,listing_type,price,location,description,image) VALUES(?,?,?,?,?,?,?,?)",
                            (u["id"], title, category, listing_type, price, location, description, saved_name))
            item_id = cur.lastrowid
            row = c.execute("SELECT l.*,u.name AS owner_name FROM listings l JOIN users u ON u.id=l.user_id WHERE l.id=?", (item_id,)).fetchone()
        item = dict(row)
        item["image_url"] = "/uploads/" + saved_name
        return jsonify(listing=item, message="Your product has been published."), 201
    except Exception:
        try: os.remove(os.path.join(UPLOAD_DIR, saved_name))
        except OSError: pass
        app.logger.exception("Failed to create listing")
        return jsonify(error="Could not save your product. Please try again."), 500

@app.delete("/api/listings/<int:listing_id>")
@login_required
def delete_listing(listing_id):
    u = current_user()
    with db() as c:
        item = c.execute("SELECT user_id,image FROM listings WHERE id=?", (listing_id,)).fetchone()
        if not item:
            return jsonify(error="This product is no longer available."), 404
        if int(item["user_id"]) != int(u["id"]):
            return jsonify(error="You can delete only products you added."), 403
        c.execute("DELETE FROM requests WHERE listing_id=?", (listing_id,))
        c.execute("DELETE FROM listings WHERE id=?", (listing_id,))
    if item["image"]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, item["image"]))
        except OSError:
            pass
    return jsonify(message="Product deleted.")

@app.post("/api/requests")
@login_required
def create_request():
    data = request.get_json(silent=True) or {}
    try: listing_id = int(data.get("listing_id"))
    except (TypeError, ValueError): return jsonify(error="Invalid resource."), 400
    u = current_user()
    with db() as c:
        item = c.execute("SELECT user_id FROM listings WHERE id=?", (listing_id,)).fetchone()
        if not item: return jsonify(error="This resource is no longer available."), 404
        if item["user_id"] == u["id"]: return jsonify(error="You cannot request your own listing."), 400
        try: c.execute("INSERT INTO requests(listing_id,requester_id) VALUES(?,?)", (listing_id,u["id"]))
        except sqlite3.IntegrityError: return jsonify(error="You already requested this resource."), 409
    return jsonify(message="Request sent."), 201

@app.get("/api/requests")
@login_required
def get_requests():
    u = current_user()
    with db() as c:
        rows = c.execute("""SELECT r.id,r.status,r.created_at,l.title,l.location,u2.name AS owner_name
          FROM requests r JOIN listings l ON l.id=r.listing_id JOIN users u2 ON u2.id=l.user_id
          WHERE r.requester_id=? ORDER BY r.created_at DESC""", (u["id"],)).fetchall()
    return jsonify(requests=[dict(r) for r in rows])

if __name__ == "__main__":
    init_db()
    print("\\nCampusShare is running at http://127.0.0.1:5000")
    print("Allowed college email domain(s): " + ", ".join(ALLOWED_DOMAINS))
    app.run(debug=True, host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
