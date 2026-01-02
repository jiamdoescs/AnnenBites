import csv
from cs50 import SQL

# Connect to the same SQLite database used by the Flask app
db = SQL("sqlite:///annenbites.db")

# Read rows from a sample CSV and insert them into the menu_items table.
# This script is just a quick way to seed the database for testing.
with open("sample_menu.csv") as f:
    reader = csv.DictReader(f)

    for row in reader:
        db.execute(
            """
            INSERT INTO menu_items
                (date, meal, location, name, category,
                 calories, protein, carbs, fat, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row["date"],
            row["meal"],
            row["location"],
            row["name"],
            row["category"],
            # Convert numeric fields to floats when present;
            # store NULL in SQLite if the cell is empty.
            float(row["calories"]) if row["calories"] else None,
            float(row["protein"]) if row["protein"] else None,
            float(row["carbs"]) if row["carbs"] else None,
            float(row["fat"]) if row["fat"] else None,
            row["tags"],
        )

print("Menu imported!")
