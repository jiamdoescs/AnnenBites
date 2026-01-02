import os
from datetime import date

# Database layer (CS50’s SQL helper on top of SQLite)
from cs50 import SQL

# Flask core imports
from flask import (
    Flask,
    render_template,
    redirect,
    request,
    session,
    jsonify,
    url_for,
)
from flask_session import Session

# Password hashing
from werkzeug.security import check_password_hash, generate_password_hash

# Local helper functions: login_required decorator + scoring algorithm
from helpers import login_required, score_menu_item


# ============================================================================
# App + session configuration
# ============================================================================

app = Flask(__name__)

# Use server-side sessions, stored on the filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Point SQLite at annenbites.db in this folder.
# If the file does not exist, create an empty file first.
db_path = os.path.join(os.path.dirname(__file__), "annenbites.db")
if not os.path.exists(db_path):
    open(db_path, "w").close()

db = SQL(f"sqlite:///{db_path}")


# ============================================================================
# Database initialization
# ============================================================================

def init_db() -> None:
    """
    Create all tables if they don’t already exist.

    This runs before *every* request (via @app.before_request), but because we
    use CREATE TABLE IF NOT EXISTS, it is idempotent and cheap.
    """

    # Users table: authentication
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # HUDS menu items
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            meal TEXT NOT NULL,
            location TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            calories REAL,
            protein REAL,
            carbs REAL,
            fat REAL,
            tags TEXT,
            image_path TEXT
        )
        """
    )

    # Per-user preferences used for recommendations
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            dietary_restrictions TEXT,
            wellness_goal TEXT,
            fav_cuisines TEXT,
            disliked_items TEXT,
            height_cm REAL,
            weight_kg REAL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # Community posts from clubs
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS club_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clubName TEXT NOT NULL,
            foodName TEXT NOT NULL,
            description TEXT,
            event_date TEXT,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Meals that a user logs as “I ate this”
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            meal TEXT NOT NULL,
            menu_item_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
        )
        """
    )

    # 1–5 ratings for each menu item
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS item_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            menu_item_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
        )
        """
    )

    # Free-form feedback posts
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # Many-to-many link table for which user liked which feedback
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            feedback_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (feedback_id) REFERENCES feedback(id)
        )
        """
    )


@app.before_request
def _init():
    """Ensure schema exists before servicing any request."""
    init_db()


# ============================================================================
# Helper functions
# ============================================================================

# Very lightweight categorization to avoid recommending 3 waffles at once
CATEGORY_KEYWORDS = {
    "waffle": ["waffle"],
    "pancake": ["pancake"],
    "bagel": ["bagel"],
    "bread": ["toast", "bread"],
    "eggs": ["egg", "omelet", "omelette"],
    "yogurt": ["yogurt"],
    "oatmeal": ["oatmeal", "oats"],
    "salad": ["salad"],
    "soup": ["soup"],
    "sandwich": ["sandwich", "wrap"],
    "pizza": ["pizza"],
    "burger": ["burger"],
}

# Keywords for dietary filtering
MEAT_WORDS = [
    "chicken",
    "beef",
    "pork",
    "bacon",
    "ham",
    "turkey",
    "sausage",
    "pepperoni",
    "meatball",
    "meatballs",
    "steak",
]

SEAFOOD_WORDS = [
    "fish",
    "salmon",
    "tuna",
    "shrimp",
    "crab",
    "lobster",
    "cod",
    "tilapia",
]


def infer_category(name: str) -> str:
    """Return a coarse food category based on keywords in the item name."""
    lower = (name or "").lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return cat
    return "other"


def get_latest_menu_date():
    """Return the most recent date for which we have menu_items, or None."""
    rows = db.execute("SELECT MAX(date) AS d FROM menu_items")
    if rows and rows[0]["d"]:
        return rows[0]["d"]
    return None


# --------------------------- dietary helpers ---------------------------

def _load_dietary_flags(prefs_row):
    """
    Parse the dietary_restrictions string into a set of normalized flags.

    Example: "Vegetarian, Gluten Free" -> {"vegetarian", "gluten free"}
    """
    flags = set()
    if not prefs_row:
        return flags

    raw = prefs_row.get("dietary_restrictions") or ""
    for part in raw.lower().replace(";", ",").split(","):
        part = part.strip()
        if part:
            flags.add(part)
    return flags


def _violates_dietary_restrictions(item, dietary_flags) -> bool:
    """
    Return True if this menu item should be excluded based on the user's
    dietary flags (e.g., vegetarian or vegan).
    """
    name = (item.get("name") or "").lower()
    tags = (item.get("tags") or "").lower()
    text = f"{name} {tags}"

    # Vegetarian: no meat or seafood
    if "vegetarian" in dietary_flags:
        if any(w in text for w in MEAT_WORDS + SEAFOOD_WORDS):
            return True

    # Vegan: vegetarian + no obvious dairy/egg words
    if "vegan" in dietary_flags:
        if any(w in text for w in MEAT_WORDS + SEAFOOD_WORDS):
            return True
        if any(w in text for w in ["cheese", "egg", "eggs", "milk", "yogurt", "butter", "cream"]):
            return True

    return False


# ============================================================================
# JSON API route (for React club posts)
# ============================================================================

@app.route("/api/clubPosts", methods=["POST"])
def club_posts_api():
    """Simple JSON API used by the React community component to log posts."""
    data = request.get_json()
    clubName = data.get("clubName")
    foodName = data.get("foodName")
    description = data.get("description")

    db.execute(
        "INSERT INTO club_posts (clubName, foodName, description) VALUES (?, ?, ?)",
        clubName,
        foodName,
        description,
    )
    return jsonify({"status": "success"})


# ============================================================================
# Authentication routes
# ============================================================================

@app.route("/")
def index():
    """
    Landing page.

    - If logged in with preferences → go straight to /dashboard.
    - If logged in without preferences → redirect to /preferences.
    - Otherwise → show index.html.
    """
    if session.get("user_id"):
        uid = session["user_id"]
        prefs = db.execute(
            "SELECT 1 FROM user_preferences WHERE user_id = ? LIMIT 1",
            uid,
        )
        if prefs:
            return redirect("/dashboard")
        return redirect("/preferences")

    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Handle user registration and validation."""
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username")
    password = request.form.get("password")
    confirmation = request.form.get("confirmation")

    if not username or not password or not confirmation:
        return render_template(
            "register.html",
            errorMessage="Must provide username, password, and confirmation",
        )

    if password != confirmation:
        return render_template(
            "register.html",
            errorMessage="Passwords must match",
        )

    if db.execute("SELECT 1 FROM users WHERE username = ?", username):
        return render_template(
            "register.html",
            errorMessage="Username already taken",
        )

    hash_pw = generate_password_hash(password)
    new_id = db.execute(
        "INSERT INTO users (username, hash) VALUES (?, ?)",
        username,
        hash_pw,
    )

    session["user_id"] = new_id
    return redirect("/preferences")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate existing users and start a session."""
    session.clear()

    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username")
    password = request.form.get("password")

    if not username or not password:
        return render_template(
            "login.html",
            errorMessage="Must provide username and password",
        )

    rows = db.execute("SELECT * FROM users WHERE username = ?", username)
    if len(rows) != 1 or not check_password_hash(rows[0]["hash"], password):
        return render_template(
            "login.html",
            errorMessage="Invalid Username or Password",
        )

    session["user_id"] = rows[0]["id"]
    return redirect("/dashboard")


@app.route("/logout")
def logout():
    """Log the user out by clearing the session."""
    session.clear()
    return redirect("/")


# ============================================================================
# Preferences
# ============================================================================

@app.route("/preferences", methods=["GET", "POST"])
@login_required
def preferences():
    """
    Show or update the current user's preferences.

    POST:
        - Save dietary restrictions, goals, etc.
    GET:
        - Prepopulate form with existing values.
        - Also show this user's feedback posts (ordered by likes).
    """
    user_id = session["user_id"]

    if request.method == "POST":
        # Read form fields
        dietary = request.form.getlist("dietary")
        goal = request.form.get("wellness_goal")
        favs = request.form.get("fav_cuisines")
        dislikes = request.form.get("disliked_items")
        height_cm = request.form.get("height_cm") or None
        weight_kg = request.form.get("weight_kg") or None

        dietary_str = ", ".join(dietary)

        # UPSERT into user_preferences
        existing = db.execute(
            "SELECT id FROM user_preferences WHERE user_id = ?",
            user_id,
        )

        if existing:
            db.execute(
                """
                UPDATE user_preferences
                SET dietary_restrictions = ?, wellness_goal = ?,
                    fav_cuisines = ?, disliked_items = ?,
                    height_cm = ?, weight_kg = ?
                WHERE user_id = ?
                """,
                dietary_str,
                goal,
                favs,
                dislikes,
                height_cm,
                weight_kg,
                user_id,
            )
        else:
            db.execute(
                """
                INSERT INTO user_preferences
                    (user_id, dietary_restrictions, wellness_goal,
                     fav_cuisines, disliked_items, height_cm, weight_kg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                user_id,
                dietary_str,
                goal,
                favs,
                dislikes,
                height_cm,
                weight_kg,
            )

        return redirect("/dashboard")

    # ----- GET -----
    prefs_rows = db.execute(
        "SELECT * FROM user_preferences WHERE user_id = ?",
        user_id,
    )
    prefs = prefs_rows[0] if prefs_rows else None
    dietary = (
        prefs["dietary_restrictions"].lower().split(",")
        if prefs and prefs["dietary_restrictions"]
        else []
    )

    # GET: load this user's feedback, ordered by likes
    user_feedback = db.execute(
        """
        SELECT text, created_at, likes
        FROM feedback
        WHERE user_id = ?
        ORDER BY likes DESC, created_at DESC
        """,
        user_id,
    )

    return render_template(
        "preferences.html",
        prefs=prefs,
        dietary=dietary,
        user_feedback=user_feedback,
    )


# ============================================================================
# Community
# ============================================================================

@app.route("/community", methods=["GET", "POST"])
@login_required
def community():
    """
    Community page:

    - POST: create a new club post.
    - GET: show top-rated foods and all club posts.
    """
    if request.method == "POST":
        club_name = request.form.get("clubName")
        food_name = request.form.get("foodName")
        description = request.form.get("description")
        event_date = request.form.get("event_date") or None
        location = request.form.get("location") or None

        if club_name and food_name:
            db.execute(
                """
                INSERT INTO club_posts
                    (clubName, foodName, description, event_date, location)
                VALUES (?, ?, ?, ?, ?)
                """,
                club_name,
                food_name,
                description,
                event_date,
                location,
            )

        return redirect(url_for("community"))

    # Top-rated menu items (based on item_feedback)
    favorites = db.execute(
        """
        SELECT
            m.name,
            ROUND(AVG(f.rating), 1) AS avg_rating,
            COUNT(*) AS num_ratings
        FROM item_feedback AS f
        JOIN menu_items AS m ON m.id = f.menu_item_id
        GROUP BY f.menu_item_id
        HAVING COUNT(*) >= 1
        ORDER BY avg_rating DESC, num_ratings DESC, m.name
        LIMIT 10
        """
    )

    # Club posts ordered by upcoming event date, then recency
    posts = db.execute(
        """
        SELECT clubName, foodName, description, event_date, location, created_at
        FROM club_posts
        ORDER BY
            event_date IS NULL,
            event_date,
            created_at DESC
        """
    )

    return render_template("community.html", favorites=favorites, posts=posts)


# ============================================================================
# Dashboard: recommendations + intake tracking
# ============================================================================

@app.route("/dashboard")
@login_required
def dashboard():
    """
    Core dashboard:

    - Computes recommended foods for this user for a given date+meal.
    - Shows all menu items for that meal.
    - Shows daily macro totals from items the user has logged.
    """
    user_id = session["user_id"]

    # Which date to show? Default = most recent menu date we have.
    current_date = request.args.get("date") or get_latest_menu_date()
    if not current_date:
        # No menu data at all yet
        return render_template(
            "dashboard.html",
            meal="breakfast",
            current_date=None,
            recommendations=[],
            items=[],
            selected_ids={},
            totals={"calories": 0, "protein": 0, "carbs": 0, "fat": 0},
            ratings={},
        )

    meal = (request.args.get("meal") or "breakfast").lower()

    # Load preferences and dietary flags
    prefs_rows = db.execute(
        "SELECT * FROM user_preferences WHERE user_id = ?",
        user_id,
    )
    prefs = prefs_rows[0] if prefs_rows else None
    dietary_flags = _load_dietary_flags(prefs)

    # All items for this date+meal
    raw_items = db.execute(
        """
        SELECT * FROM menu_items
        WHERE date = ? AND LOWER(meal) = ?
        ORDER BY name
        """,
        current_date,
        meal,
    )

    # Filter out items that violate dietary restrictions,
    # and compute recommendation scores for the rest.
    items = []
    scored = []
    for item in raw_items:
        if _violates_dietary_restrictions(item, dietary_flags):
            continue
        items.append(item)
        scored.append((item, score_menu_item(item, prefs)))

    # Sort by score descending
    scored.sort(key=lambda t: t[1], reverse=True)

    # Pick up to 3 items with distinct categories
    recommendations = []
    used_cats = set()
    for item, sc in scored:
        cat = infer_category(item["name"])
        if cat in used_cats:
            continue
        recommendations.append(item)
        used_cats.add(cat)
        if len(recommendations) == 3:
            break

    # Items the user has already logged for this date+meal
    intake_rows = db.execute(
        """
        SELECT menu_item_id, id
        FROM user_meals
        WHERE user_id = ? AND date = ? AND LOWER(meal) = ?
        """,
        user_id,
        current_date,
        meal,
    )
    selected_ids = {row["menu_item_id"]: row["id"] for row in intake_rows}

    # Ratings by this user across all items
    ratings_rows = db.execute(
        "SELECT menu_item_id, rating FROM item_feedback WHERE user_id = ?",
        user_id,
    )
    ratings = {row["menu_item_id"]: row["rating"] for row in ratings_rows}

    # Aggregate daily totals for macros
    totals_rows = db.execute(
        """
        SELECT m.calories, m.protein, m.carbs, m.fat
        FROM user_meals um
        JOIN menu_items m ON um.menu_item_id = m.id
        WHERE um.user_id = ? AND um.date = ?
        """,
        user_id,
        current_date,
    )
    totals = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    for r in totals_rows:
        totals["calories"] += r["calories"] or 0
        totals["protein"] += r["protein"] or 0
        totals["carbs"] += r["carbs"] or 0
        totals["fat"] += r["fat"] or 0

    return render_template(
        "dashboard.html",
        meal=meal,
        current_date=current_date,
        recommendations=recommendations,
        items=items,
        selected_ids=selected_ids,
        totals=totals,
        ratings=ratings,
    )


# ============================================================================
# Meal logging routes
# ============================================================================

@app.route("/add_meal", methods=["POST"])
@login_required
def add_meal():
    """Log that the user ate a specific menu item."""
    user_id = session["user_id"]
    menu_item_id = request.form.get("menu_item_id")
    meal = (request.form.get("meal") or "breakfast").lower()
    date_str = request.form.get("date") or date.today().isoformat()

    if menu_item_id:
        db.execute(
            """
            INSERT INTO user_meals (user_id, date, meal, menu_item_id)
            VALUES (?, ?, ?, ?)
            """,
            user_id,
            date_str,
            meal,
            menu_item_id,
        )

    return redirect(url_for("dashboard", meal=meal, date=date_str))


@app.route("/remove_meal", methods=["POST"])
@login_required
def remove_meal():
    """Remove a single logged menu item for the current user."""
    user_id = session["user_id"]
    user_meal_id = request.form.get("user_meal_id")
    meal = (request.form.get("meal") or "dinner").lower()
    date_str = request.form.get("date") or date.today().isoformat()

    if user_meal_id:
        db.execute(
            "DELETE FROM user_meals WHERE id = ? AND user_id = ?",
            user_meal_id,
            user_id,
        )

    return redirect(url_for("dashboard", meal=meal, date=date_str))


@app.route("/reset_intake", methods=["POST"])
@login_required
def reset_intake():
    """Clear *all* meals the user has logged for a particular date."""
    user_id = session["user_id"]
    meal = (request.form.get("meal") or "breakfast").lower()
    date_str = request.form.get("date") or date.today().isoformat()

    db.execute(
        "DELETE FROM user_meals WHERE user_id = ? AND date = ?",
        user_id,
        date_str,
    )

    return redirect(url_for("dashboard", meal=meal, date=date_str))


# ============================================================================
# Item feedback routes (1–5 ratings)
# ============================================================================

@app.route("/item_feedback", methods=["POST"])
@login_required
def item_feedback():
    """Insert or update a 1–5 rating for a specific menu item."""
    user_id = session["user_id"]
    menu_item_id = request.form.get("menu_item_id")
    meal = (request.form.get("meal") or "breakfast").lower()
    date_str = request.form.get("date") or date.today().isoformat()
    rating_str = request.form.get("rating")

    # Validate input
    if not menu_item_id or not rating_str:
        return redirect(url_for("dashboard", meal=meal, date=date_str))

    try:
        rating = int(rating_str)
    except ValueError:
        return redirect(url_for("dashboard", meal=meal, date=date_str))

    if rating < 1 or rating > 5:
        return redirect(url_for("dashboard", meal=meal, date=date_str))

    # Upsert rating
    existing = db.execute(
        "SELECT id FROM item_feedback WHERE user_id = ? AND menu_item_id = ?",
        user_id,
        menu_item_id,
    )
    if existing:
        db.execute(
            """
            UPDATE item_feedback
            SET rating = ?, created_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            rating,
            existing[0]["id"],
        )
    else:
        db.execute(
            """
            INSERT INTO item_feedback (user_id, menu_item_id, rating)
            VALUES (?, ?, ?)
            """,
            user_id,
            menu_item_id,
            rating,
        )

    return redirect(url_for("dashboard", meal=meal, date=date_str))


# ============================================================================
# Feedback + likes system
# ============================================================================

@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    """
    Simple feedback wall.

    - POST: create a new feedback entry for this user.
    - GET: display all feedback entries and which ones the user has liked.
    """
    user_id = session["user_id"]

    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text and len(text) <= 800:
            db.execute(
                "INSERT INTO feedback (user_id, text) VALUES (?, ?)",
                user_id,
                text,
            )
        return redirect("/feedback")

    feedbacks = db.execute(
        """
        SELECT f.id, f.text, f.likes, f.created_at
        FROM feedback f
        ORDER BY f.created_at DESC
        """
    )

    liked_rows = db.execute(
        "SELECT feedback_id FROM feedback_likes WHERE user_id = ?",
        user_id,
    )
    liked_map = {row["feedback_id"] for row in liked_rows}

    return render_template(
        "feedback.html",
        feedbacks=feedbacks,
        liked_map=liked_map,
    )


@app.route("/feedback_like", methods=["POST"])
@login_required
def feedback_like():
    """
    Toggle a like on a feedback entry for the current user.

    If the user has already liked it → unlike.
    Otherwise → like and increment the count.
    """
    user_id = session["user_id"]
    feedback_id = request.form.get("feedback_id")

    if not feedback_id:
        return redirect("/feedback")

    # Did the user already like this feedback?
    exists = db.execute(
        "SELECT 1 FROM feedback_likes WHERE user_id = ? AND feedback_id = ?",
        user_id,
        feedback_id,
    )

    if exists:
        # Unlike: remove the row and decrement likes
        db.execute(
            "DELETE FROM feedback_likes WHERE user_id = ? AND feedback_id = ?",
            user_id,
            feedback_id,
        )
        db.execute(
            "UPDATE feedback SET likes = likes - 1 WHERE id = ?",
            feedback_id,
        )
    else:
        # Like: insert row and increment likes
        db.execute(
            "INSERT INTO feedback_likes (user_id, feedback_id) VALUES (?, ?)",
            user_id,
            feedback_id,
        )
        db.execute(
            "UPDATE feedback SET likes = likes + 1 WHERE id = ?",
            feedback_id,
        )

    # Re-render page after toggle
    feedbacks = db.execute(
        """
        SELECT f.id, f.text, f.likes, f.created_at
        FROM feedback f
        ORDER BY f.created_at DESC
        """
    )
    liked_rows = db.execute(
        "SELECT feedback_id FROM feedback_likes WHERE user_id = ?",
        user_id,
    )
    liked_map = {row["feedback_id"] for row in liked_rows}

    return render_template(
        "feedback.html",
        feedbacks=feedbacks,
        liked_map=liked_map,
    )


# ============================================================================
# Run development server
# ============================================================================

if __name__ == "__main__":
    # Debug mode: auto-reload on code changes. For production, set debug=False.
    app.run(debug=True)
