# **Annenbites -- A Personalized Dining and Nutrition Assistant**
*CS50 Final Project*


Note: We had a great time making this project and would definitely use this resource. We hope that you enjoy using it as well!


---


## Overview


Annenbites is a personalized dining and nutrition assistant designed for Harvard students navigating the HUDS menu. The app **scrapes the live HUDS FoodPro website** via `scrape_huds.py`, imports that data into SQLite, and then recommends meals based on your dietary preferences and wellness goals, tracks basic nutrition, and gathers community favorites and club food events. The app is built with Python, Flask, SQLite, and Jinja templates.


---


## Features


- Personalized daily meal recommendations based on your preferences 
- Nutrition tracking (calories, protein, carbohydrates, fat) 
- Dietary restriction filtering (vegetarian, vegan, gluten-free, etc.) 
- Preference-based scoring (favorite cuisines, disliked foods, goals) 
- **Daily HUDS menu scraping** with macro data pulled from Nutrition Facts pages 
- Community page with top-rated foods and club food events 
- Secure user accounts and preferences 


---


## Project Structure


The key files and directories are:


- `app.py`: main Flask app, routes, DB initialization, and overall logic 
- `helpers.py`: `login_required`, recommendation scoring, dietary preferences helper 
- `scrape_huds.py`: HUDS scraper that fetches FoodPro pages, parses nutrition, and refreshes `menu_items` for today 
- `annenbites.db`: SQLite database (automatically created and migrated) 
- `requirements.txt`: Python dependencies 
- `templates/`: Jinja templates (`layout`, `index`, `login`, `register`, `preferences`, `dashboard`, `community`, `feedback`, `summary`) 
- `static/`: `dashboard.css` and image assets for styling 


---


## Installation & Setup


1. Navigate to the project directory.


2. Create and activate a virtual environment.


- **macOS/Linux:**
   - `python3 -m venv .venv` 
   - `source .venv/bin/activate`


- **Windows:**
   - `python -m venv .venv` 
   - `.venv\Scripts\activate`


3. Install dependencies:


- `pip install -r requirements.txt`


4. **Scrape HUDS menu (required before using the dashboard):**


- `python3 scrape_huds.py` 


This script contacts the HUDS FoodPro site, pulls today’s breakfast/lunch/dinner menus plus Nutrition Facts labels, and populates the `menu_items` table. If you skip this step, the dashboard will not show any items.


5. Run the Flask app:


- `python3 app.py`


Then visit the printed URL (typically `http://127.0.0.1:5000/`) in your browser.


---


## Using the App


From the landing page:


- Choose **Register** to create an account. 
- Passwords are stored as secure hashes (using Werkzeug). 
- After registration/login, the user’s id is stored in the session and used by `login_required` to protect routes.


Next, the Preferences page drives the recommendations. You can set:


- Dietary restrictions (e.g., vegetarian, vegan, gluten-free) 
- Wellness goal (e.g., lose weight, gain muscle, maintain) 
- Favorite cuisines (e.g., Italian, Indian, sushi) 
- Disliked items (e.g., olives, mushrooms) 
- Height and weight (optional) 


Preferences are stored in `user_preferences`. Upon submit, the app inserts/updates a row for `user_id` and redirects to `/dashboard`. On later visits, the form is pre-filled so you can adjust settings easily.


The `/dashboard` route:


- Determines the date from a `date` query parameter, or defaults to the most recent scraped date. 
- Determines the meal from a `meal` parameter, defaulting to breakfast. 
- Loads preferences and all matching menu items for that date and meal from `menu_items`. 
- Ranks the items using a scoring function that considers macros, wellness goals, favorite cuisines, and disliked items. 
- Displays: today’s intake, a “recommended for you” section, and an “all menu items for this meal” section.


**Logging Meals and Ratings**


When you click **“I ate this”**, the app:


- Sends a POST to `/add_meal` with menu item id, meal, and date. 
- Inserts into `user_meals`. 
- Redirects back to `/dashboard`, where daily totals update and the button changes to show the item is logged.


The `/community` page uses existing data to display:


- Top-rated foods (joining `item_feedback` and `menu_items` to calculate ratings and rating counts per item). 
- Club posts, read from `club_posts` where clubs can submit: club name, food name, description, event date, and location. 
- A typed feedback form for community input.


The `/feedback` and `/summary` routes provide an anonymous comments wall and a daily intake summary, respectively.


---


## Troubleshooting


If something is not working, here are common fixes:


- **Dashboard is empty:** 
 Make sure you scraped from the HUDS website: 
 `python3 scrape_huds.py` 


- **Missing module errors:** 
 Confirm your virtual environment is active and run: 
 `pip install -r requirements.txt`


---


## Summary


Annenbites is our CS50 final project that uses authentication, user preferences, data-driven recommendations, nutrition tracking, and community features. Powered by a custom HUDS scraper, SQLite, and Flask, Annenbites provides a complete, personalized HUDS dining experience based on real menus rather than hard-coded data.
