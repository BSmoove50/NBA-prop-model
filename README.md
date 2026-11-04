# NBA Prop Lab

## Run locally
1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Run `pip install -r requirements.txt`.
4. Run `streamlit run app.py`.

Uses NBA.com game logs through nba_api. NBA.com can rate-limit or block some hosted environments. Data is cached for 30 minutes. No live sportsbook line or automatic injury feed is included; enter the line and injury adjustment yourself. Current season is 2026–27 and the last 10 games can include 2025–26. This model is a transparent heuristic, not a backtested betting system.
