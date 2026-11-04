[README.md](https://github.com/user-attachments/files/34396987/README.md)
NBA Alternate Props Lab

Upload app.py and requirements.txt to GitHub; deploy app.py in Streamlit Community Cloud.

Includes last 10 overall and last 10 vs today’s opponent (searches up to six regular seasons), exact alternate thresholds, per-line historical hit rates, and explicit UNVERIFIED availability warning.

NBA Stats endpoints may be blocked or rate-limited on cloud hosts; no guarantee of availability. The player list consists of players with a logged game for the selected team this season, not a confirmed roster. Injury verification is not implemented.

Home page Top 10 boards now show both Last 10 average and weighted Projected average for every ranked player. These are historical estimates, not injury-adjusted forecasts.\n
Homepage: category buttons for Points/Rebounds/Assists/3-pointers, followed by buttons for each exact alternate threshold. Top 10 table filters to the chosen category and threshold.

Full-slate home page: all players with season logs for today’s teams, all alternate thresholds side by side, last-10 hits and percentages, team/name filters, CSV export. Availability unverified.

Home page includes last-10 per-game stat bar charts and per-alternate hit-rate percentage bar charts for a selected player and prop category.

Hit rate cells and alternate hit-rate bars use continuous red (0%), yellow (50%), green (100%) gradient. Partial samples are colored using their true hit fraction.

