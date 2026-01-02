from functools import wraps
from flask import redirect, session


def login_required(f):
    """
    Decorator that requires a user to be logged in.

    If session["user_id"] is missing, redirect to /login.
    Otherwise, call the original view function.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def parse_list_field(field):
    """
    Convert a comma-separated string into a list of lowercase strings.

    Examples:
        "Italian, Indian " -> ["italian", "indian"]
        "" or None         -> []
    """
    if not field:
        return []
    return [item.strip().lower() for item in field.split(",")]


def score_menu_item(item, prefs):
    """
    Compute a numeric score for a menu item.

    Higher score = better recommendation.
    Scoring uses:
      - dietary restrictions
      - wellness goal
      - favorite cuisines
      - disliked items
      - calories and protein
    """

    # If the user has no preferences yet, use a simple macro-based heuristic.
    if not prefs:
        calories = item["calories"] or 0
        protein = item["protein"] or 0
        return protein * 0.3 - calories * 0.05

    score = 0.0

    # --- Pull user preferences ---
    dietary = parse_list_field(prefs.get("dietary_restrictions"))
    fav_cuisines = parse_list_field(prefs.get("fav_cuisines"))
    dislikes = parse_list_field(prefs.get("disliked_items"))
    goal = (prefs.get("wellness_goal") or "").lower()

    # --- Pull item data ---
    tags = parse_list_field(item.get("tags"))
    name = (item.get("name") or "").lower()
    calories = item.get("calories") or 0
    protein = item.get("protein") or 0

    # 1) Hard dietary rules: big penalties if an item violates them.
    if "vegetarian" in dietary and "vegetarian" not in tags:
        score -= 100
    if "vegan" in dietary and "vegan" not in tags:
        score -= 100
    if "gluten-free" in dietary and "gluten-free" not in tags:
        score -= 50

    # 2) Wellness goal: adjust weight on protein and calories.
    if goal == "gain muscle":
        score += protein * 0.6
        score -= calories * 0.05
    elif goal == "lose weight":
        score -= calories * 0.1
        score += protein * 0.2
    elif goal == "maintain":
        score += protein * 0.3

    # 3) Favorite cuisines / keywords in name.
    for fav in fav_cuisines:
        if fav and fav in name:
            score += 5

    # 4) Disliked ingredients in name.
    for bad in dislikes:
        if bad and bad in name:
            score -= 20

    return score
