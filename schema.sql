/* ===========================================================
   AnnenBites database schema

   This file defines all tables used by the Flask application.
   Running it against a fresh SQLite database will create the
   full schema for app.py and scrape_huds.py.
   =========================================================== */

-- Users and authentication
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Main HUDS menu table: one row per item per date/meal/location
CREATE TABLE IF NOT EXISTS menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,          -- e.g. "2025-12-01"
    meal TEXT NOT NULL,          -- "breakfast", "lunch", "dinner"
    location TEXT NOT NULL,      -- e.g. "Annenberg"
    name TEXT NOT NULL,
    category TEXT,               -- e.g. "entree", "side", "dessert"
    calories REAL,
    protein REAL,
    carbs REAL,
    fat REAL,
    tags TEXT                    -- e.g. "vegetarian, gluten-free"
);

-- One preference row per user
CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    dietary_restrictions TEXT,   -- comma-separated (e.g. "vegetarian, gluten-free")
    wellness_goal TEXT,
    fav_cuisines TEXT,
    disliked_items TEXT,
    height_cm REAL,
    weight_kg REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Item-level ratings and optional comments
CREATE TABLE IF NOT EXISTS item_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    menu_item_id INTEGER NOT NULL,
    rating INTEGER,                  -- 1–5 stars
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
);

-- Simple club posts used on the Community page
CREATE TABLE IF NOT EXISTS club_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clubName TEXT NOT NULL,
    foodName TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reset and recreate feedback tables (for app’s feedback feature)
DROP TABLE IF EXISTS feedback;

CREATE TABLE feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    likes INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Track which user liked which feedback, one like per pair
CREATE TABLE IF NOT EXISTS feedback_likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    feedback_id INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (feedback_id) REFERENCES feedback(id),
    UNIQUE (user_id, feedback_id)
);
