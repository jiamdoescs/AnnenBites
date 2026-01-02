# **Annenbites Technical Design Document**
*CS50 Final Project*


---


## 1. Overview


Annenbites is a personalized dining and nutrition assistant built with Python, Flask, SQLite, and Jinja2. This document explains how the system is structured under the hood: architecture, database schema, recommendation algorithm, HUDS scraping pipeline, and the key design choices that shaped the implementation.


A central goal was to **work with live HUDS data instead of a hard-coded menu**. To do that, Annenbites includes a custom scraper that visits Harvard’s FoodPro site, parses each day’s menus and Nutrition Facts, and normalizes them into the `menu_items` table before recommendations are generated.


The project’s goals were to:


- Build a full-stack web app with authentication 
- Use real HUDS menu data to drive recommendations (via the scraper) 
- Support user preferences and nutrition tracking 
- Implement a community-style interface 


---


## 2. Architecture & Framework Choices


We chose Flask as the main framework because it is lightweight but flexible enough to support custom routing, session management, and direct SQL access. It gives us control over:


- Request/response flow (through route functions) 
- How and when the database is queried 
- How business logic (e.g., scoring, filtering) is structured 


The app follows an **MVC-inspired** pattern:


- **Controllers (routes):** Functions in `app.py` that handle HTTP requests (`/`, `/login`, `/preferences`, `/dashboard`, `/community`, etc.), query the database, apply business logic, and call `render_template`. 
- **Views (templates):** Jinja templates in `templates/` that are responsible for HTML structure and presentation. 
- **Models (data):** SQLite tables accessed via the CS50 `SQL` library, using parameterized queries in `app.py`.


SQLite was chosen because:


- It doesn't require an external server. 
- The entire project can be shipped as a single `.db` file. 
- It is sufficient for the expected data volume (a few thousand menu items and user records). 


In addition, a separate module `scrape_huds.py` acts as a **data ingestion layer**: it connects to the same SQLite file, fetches HUDS pages, parses nutrition tables, and refreshes `menu_items` for the current date. This keeps scraping logic decoupled from request handling.


---


## 3. Database Schema & Design Rationale


The schema is small but comprehensive:


- `users` 
 - Stores usernames and password hashes (through Werkzeug). 
 - Provides an authentication layer using a session-stored user ID.


- `user_preferences` 
 - Stores the following data for every user: 
   - `dietary_restrictions` (comma-separated string) 
   - `wellness_goal` 
   - `fav_cuisines` 
   - `disliked_items` 
   - `height_cm`, `weight_kg` (optional) 
 - Stores preferences as text to keep queries simple. This is adequate for the small scale of the app.


- `menu_items` 
 - Stores HUDS menu data scraped from the website by `scrape_huds.py`: 
   - `date`, `meal`, `location`, `name` 
   - `category` (coarse type such as “pizza”, “salad”, etc.) 
   - macro information (`calories`, `protein`, `carbs`, `fat`) 
   - `tags` (e.g., “vegan”, “contains meat”) 
 - Includes both `date` and `meal` for filtering by day and service.


- `user_meals` 
 - Records which items a user has logged as eaten, with `user_id`, `menu_item_id`, `date`, and `meal`. 
 - Table powers both daily intake summaries and the “logged” button state.


- `item_feedback` 
 - Uses 1–5 star ratings per user per menu item. 
 - Ratings are used to calculate “top rated foods” on the community page and can feed into future personalized recommendation.


- `club_posts` 
 - Stores optional, user-generated club events related to food. 
 - Contains `clubName`, `foodName`, `description`, and optional `event_date`/`location`. 
 - Sorting by event date (with a fallback to creation time) showcases handling of nullable fields.


- `feedback’
 - Stores information about id and text and created at time of any user’s feedback. References the id of the user who posted it.
- `feedback_likes’
 - Is connected to the feedback and user id, counts the number of likes.


The goal of this design was to keep tables focused on a single task while avoiding overly complex relationships. This keeps SQL queries readable and easy to debug.


---


## 4. HUDS Scraping Pipeline


The **HUDS scraper** is one of the most technically challenging components:


- `scrape_huds.py` connects to the same `annenbites.db` file using CS50’s `SQL` helper. 
- For today’s date, it builds FoodPro `longmenucopy.aspx` URLs for breakfast, lunch, and dinner, fetches the HTML with `requests`, and parses it with BeautifulSoup. 
- From each meal page, it extracts links to `menudetail.aspx` pages for individual items, then follows those links to pull out Nutrition Facts. 
- A helper function walks the HTML table rows and uses regex to extract numeric values for calories, protein, carbs, and fat. 
- Before inserting fresh rows for today, the script deletes any existing `menu_items` for that date and cascades deletions to dependent `user_meals` and `item_feedback` rows to keep foreign keys consistent. 
- Finally, it inserts normalized rows into `menu_items` with date, meal, name, macros, and tags.


By running `python3 scrape_huds.py` once per day, `menu_items` will be clean nad up-to-date without ever touching the external HUDS site during normal user traffic.


---


## 5. Recommendation Algorithm


An important part of Annenbites is the recommendation logic, implemented in `score_menu_item()` inside `helpers.py`. The design intentionally uses a rules-based scoring system rather than machine learning because of the smaller dataset.


### Inputs to the Scoring Function


For each `menu_items` row, the function considers:


- **Dietary restrictions:** 
 Items that violate restrictions (e.g., a “Chicken Sandwich” when the user is vegetarian) are filtered out entirely using keyword and tag checks.


- **Wellness goal:** 
 Different wellness goals weight macros differently. For example, a “build muscle” goal will give a higher score to items with more protein.


- **Favorite cuisines and disliked items:** 
 Keyword matches on `name` and `tags` add a positive or negative bonus.


- **Macro profile:** 
 Calories, protein, carbs, and fat are combined into a normalized score so that nutritionally balanced items rank higher.


### Category Diversity


To avoid repetitive recommendations (e.g., three sandwiches in a row), the app assigns a category for each item using predefined keyword lists (e.g., “bagel”, “pizza”, “salad”). When building the final top-N recommendations, it only selects one item per category. This provides variety without adding complex algorithms.


---


## 6. Dashboard Logic


The `/dashboard` route coordinates several concerns:


1. **Date and meal selection** 
  - Reads `date` and `meal` from query parameters, defaulting to the most recent date and “breakfast” if missing. 
  - Queries all `menu_items` for that date/meal.


2. **Preference-aware recommendation** 
  - Loads `user_preferences` for the logged-in user. 
  - Filters and scores items via `score_menu_item()`. 
  - Sorts them by score and applies the category diversity rule to produce a short “recommended for you” list.


3. **Intake aggregation** 
  - Queries `user_meals` joined with `menu_items` to sum calories, protein, carbs, and fat for the selected date. 
  - The totals are passed to the template for the “Today’s intake” card.


4. **Button and rating state** 
  - Creates dictionaries mapping `menu_item_id` → `user_meal_id` and `menu_item_id` → `rating`. 
  - The Jinja templates use these maps to:
    - Switch “I ate this” to “✓ Logged” when appropriate. 
    - Pre-select rating values in dropdowns.


All of this is done server-side in Python; no custom JavaScript is required, which keeps the stack relatively simple.


---


## 7. Preferences & Form Handling


The `/preferences` route supports both GET and POST methods:


- On **GET**, it:
 - Fetches the user’s existing row in `user_preferences` (if any). 
 - Splits `dietary_restrictions` into a list.


- On **POST**, it:
 - Reads form inputs (multi-select dietary checkboxes, text inputs, etc.). 
 - Joins dietary selections into a comma-separated string. 
 - Either `INSERT`s a new row or `UPDATE`s the existing one based on whether a record exists for `user_id`.


This design allows the preferences form to create and edit data, and keeps the recommendation system’s inputs centralized in a single table.


---


## 8. Community Page Implementation


The `/community` route can both read and write:


- **POST:** inserts a new `club_posts` record from form data (club name, food name, description, optional event date/location). 
- **GET:** 
 - Runs an aggregate query on `item_feedback` joined with `menu_items` to compute average ratings and counts, sorted by rating and popularity. 
 - Retrieves all `club_posts` ordered by event date and creation time.


This page uses more advanced SQL functions (JOINs, GROUP BY, HAVING, ORDER BY with null handling) in a way that is still directly tied to the user experience.


—--


## 9. Feedback Page Implementation


The ‘/feedback’ route can both read and write:


- **POST:** inserts new feedback into the feedback database and ensures that the feedback is only 800 words. 


This page returns the feedback page that aggregates all of the rows of feedback from all users.


The ‘/feedback_like’ route:


Changes the like count of the feed_back likes database to change the like count of feedback.  


---

## 10. Security Considerations


Security considerations include:


- All non-public routes are decorated with `@login_required`, which checks `session["user_id"]` and redirects to `/login` if absent. 
- Passwords are hashed with Werkzeug before being inserted into `users`. 
- Sessions are stored server-side using `Flask-Session` with filesystem storage to avoid exposing sensitive data in cookies. 
- Scraping logic lives in `scrape_huds.py` and is intended to be run manually, which avoids exposing HUDS scraping endpoints to the public.


---


## 11. Extensibility


The project was structured so that new features can be added without major restructuring. Some ways to enhance the project further would be:


- Machine-learning–based personalization using past ratings and meals 
- Smarter ingredient parsing and allergen-aware recommendations 
- Integration with external APIs (e.g., nutrition databases or generative image APIs) 
- A mobile-friendly or SPA front-end consuming the same Flask routes as JSON 


These enhancements can be layered on without changing the core architecture.


---


## Conclusion


Annenbites combines a simple but comprehensive schema, a recommendation engine, and clear separation of concerns within Flask to deliver a personalized HUDS dining experience. The custom HUDS scraper ensures that recommendations are always based on fresh, real-world menu data. This design document outlined how data flows from external FoodPro pages into the database, through the recommendation logic, and finally into the templates, and why those choices were made.



