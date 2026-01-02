import os
import re
import urllib.parse
from datetime import date as Date

import requests
from bs4 import BeautifulSoup
from cs50 import SQL

# Point at the same DB file as app.py
here = os.path.dirname(__file__)
db_path = os.path.join(here, "annenbites.db")
db = SQL(f"sqlite:///{db_path}")

BASE_HOST = "https://www.foodpro.huds.harvard.edu"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Annenbites-CS50-Project)"
}


def fetch_html(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_showreport(meal_html):
    """
    From a 'longmenucopy.aspx' page (one meal's menu),
    extract (name, detail_url) for each menu item.
    """
    items = []
    links = meal_html.find_all("a", href=True)

    for a in links:
        href = a["href"]
        text = a.get_text(strip=True)
        if not text:
            continue

        # Only follow the item detail links
        if "menudetail.aspx" not in href.lower():
            continue

        # Build full URL
        if href.startswith("http"):
            detail_url = href
        elif href.startswith("/"):
            detail_url = BASE_HOST + href
        else:
            detail_url = BASE_HOST + "/foodpro/" + href

        items.append((text.title(), detail_url))

    print(f"Found {len(items)} menu items on this page")
    return items


def extract_nutrition(detail_url: str):
    """
    Given a menudetail.aspx URL with a Nutrition Facts label,
    parse out (calories, protein, carbs, fat).
    """
    soup = fetch_html(detail_url)

    def get_numeric(label_substring):
        label_node = soup.find(
            string=lambda t: t and label_substring.lower() in t.lower()
        )
        if not label_node:
            return None

        row = label_node
        while row and row.name != "tr":
            row = row.parent
        if not row:
            return None

        row_text = " ".join(
            td.get_text(" ", strip=True) for td in row.find_all("td")
        ) or row.get_text(" ", strip=True)

        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", row_text)
        if not m:
            return None

        try:
            return float(m.group(1))
        except ValueError:
            return None

    calories = get_numeric("Calories")
    protein = get_numeric("Protein")
    carbs = get_numeric("Total Carbohydrate")
    fat = get_numeric("Total Fat")

    return calories, protein, carbs, fat


def insert_items(date_iso: str, meal: str, items):
    for name, detail_url in items:
        calories, protein, carbs, fat = extract_nutrition(detail_url)
        print(f"{meal} – {name}: {calories} kcal, P{protein}, C{carbs}, F{fat}")

        db.execute(
            """
            INSERT INTO menu_items
                (date, meal, location, name, category, calories, protein, carbs, fat, tags)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            date_iso,
            meal,
            "Annenberg",
            name,
            None,
            calories,
            protein,
            carbs,
            fat,
            ""
        )


def build_report_url(dt: Date, meal_name: str) -> str:
    """
    Build the longmenucopy.aspx URL for a given date + meal.
    """
    dt_str = dt.strftime("%m/%d/%Y")
    encoded_date = urllib.parse.quote(dt_str, safe="")
    meal_param = urllib.parse.quote(meal_name, safe="+")
    return (
        f"{BASE_HOST}/foodpro/longmenucopy.aspx"
        f"?sName=HARVARD+UNIVERSITY+DINING+SERVICES"
        f"&locationNum=30"
        f"&locationName=Dining+Hall"
        f"&naFlag=1"
        f"&WeeksMenus=This+Week%27s+Menus"
        f"&dtdate={encoded_date}"
        f"&mealName={meal_param}"
    )


def scrape_day():
    """
    Scrape HUDS for *today* and replace any existing menu_items for this date.

    Because menu_items is referenced by user_meals (and possibly item_feedback),
    we first delete any dependent rows, then delete the old menu_items rows,
    then insert the fresh ones.
    """
    today = Date.today()
    date_iso = today.isoformat()
    print(f"Scraping HUDS for {date_iso}")

    # ---------------------------------------------------------
    # 0) Clear rows that *depend* on menu_items for this date
    #    so the FK constraint does not fail when we delete.
    # ---------------------------------------------------------

    # Delete user_meals that point at menu_items for this date
    db.execute("""
        DELETE FROM user_meals
        WHERE menu_item_id IN (
            SELECT id FROM menu_items WHERE date = ?
        )
    """, date_iso)

    # If you created an item_feedback / item_ratings table that has
    # menu_item_id as a foreign key, clear those rows too.
    # Comment this out if you don't have that table.
    db.execute("""
        DELETE FROM item_feedback
        WHERE menu_item_id IN (
            SELECT id FROM menu_items WHERE date = ?
        )
    """, date_iso)

    # Now it's safe to delete the old menu_items for this date
    db.execute("DELETE FROM menu_items WHERE date = ?", date_iso)

    # ---------------------------------------------------------
    # 1) Build the HUDS URLs for today's date
    # ---------------------------------------------------------
    # HUDS wants mm/dd/YYYY URL-encoded as 12%2F06%2F2025, etc.
    dt_param = today.strftime("%m/%d/%Y").replace("/", "%2f")

    base = (
        "https://www.foodpro.huds.harvard.edu/foodpro/longmenucopy.aspx"
        "?sName=HARVARD+UNIVERSITY+DINING+SERVICES"
        "&locationNum=30"
        "&locationName=Dining+Hall"
        "&naFlag=1"
        "&WeeksMenus=This+Week%27s+Menus"
        f"&dtdate={dt_param}"
        "&mealName="
    )

    breakfast_url = base + "Breakfast+Menu"
    lunch_url     = base + "Lunch+Menu"
    dinner_url    = base + "Dinner+Menu"

    # ---------------------------------------------------------
    # 2) Scrape each meal and insert into menu_items
    # ---------------------------------------------------------
    print("Scraping breakfast…")
    b_html = fetch_html(breakfast_url)
    b_items = parse_showreport(b_html)
    insert_items(date_iso, "breakfast", b_items)

    print("Scraping lunch…")
    l_html = fetch_html(lunch_url)
    l_items = parse_showreport(l_html)
    insert_items(date_iso, "lunch", l_items)

    print("Scraping dinner…")
    d_html = fetch_html(dinner_url)
    d_items = parse_showreport(d_html)
    insert_items(date_iso, "dinner", d_items)

    print("Done.")

if __name__ == "__main__":
    scrape_day()
