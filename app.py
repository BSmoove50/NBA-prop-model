import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from nba_api.stats.endpoints import leaguegamelog, playergamelog
from nba_api.stats.static import teams
from scipy.stats import poisson, nbinom

st.set_page_config(page_title="NBA Alternate Props Lab", layout="wide", page_icon="🏀")
st.title("🏀 NBA Alternate Props Lab")
st.caption("Today's matchups • last 10 overall • last 10 vs selected opponent • availability unverified")
LINES={"Points":("PTS",[10,15,20,25,30]),"Rebounds":("REB",[4,6,8,10,12]),"Assists":("AST",[2,4,6,8,10,12]),"3-pointers":("FG3M",[1,2,3,4,5])}
TEAM_MAP={t["abbreviation"]:t for t in teams.get_teams()}
TODAY=datetime.now(ZoneInfo("America/New_York")).date()
@st.cache_data(ttl=900,show_spinner=False)
def schedule(day):
    url="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    r=requests.get(url,params={"dates":day.strftime("%Y%m%d"),"limit":30},timeout=18)
    r.raise_for_status()
    games=[]
    for e in r.json().get("events",[]):
        comps=e.get("competitions",[])
        if not comps: continue
        cs=comps[0].get("competitors",[])
        home=next((x for x in cs if x.get("homeAway")=="home"),None)
        away=next((x for x in cs if x.get("homeAway")=="away"),None)
        if not home or not away: continue
        games.append({"home":home["team"].get("abbreviation"),"away":away["team"].get("abbreviation"),
                      "name":e.get("shortName",""),"status":e.get("status",{}).get("type",{}).get("description","")})
    return games

def season_for(day):
    y=day.year if day.month>=10 else day.year-1
    return f"{y}-{str(y+1)[-2:]}"
def previous_seasons(day, count=5):
    y=day.year if day.month>=10 else day.year-1
    return [f"{v}-{str(v+1)[-2:]}" for v in range(y,y-count,-1)]

@st.cache_data(ttl=3600,show_spinner=False)
def season_players(season):
    df=leaguegamelog.LeagueGameLog(season=season,player_or_team_abbreviation="P",season_type_all_star="Regular Season",timeout=35).get_data_frames()[0]
    return df

@st.cache_data(ttl=3600,show_spinner=False)
def player_season(pid,season):
    return playergamelog.PlayerGameLog(player_id=int(pid),season=season,season_type_all_star="Regular Season",timeout=35).get_data_frames()[0]

def normalize(df, season):
    if df.empty:return df
    x=df.copy()
    x["GAME_DATE"]=pd.to_datetime(x["GAME_DATE"],errors="coerce")
    x["SEASON"]=season
    x["OPP"]=x["MATCHUP"].astype(str).str.extract(r"(?:vs\.|@)\s*([A-Z]{2,3})",expand=False)
    for c in ["PTS","REB","AST","FG3M","MIN"]:
        x[c]=pd.to_numeric(x[c],errors="coerce")
    return x

def logs(pid,day,minimum=10,vs_team=None):
    frames=[]
    for season in previous_seasons(day,6):
        try:
            d=normalize(player_season(pid,season),season)
            frames.append(d)
        except Exception as e:
            st.warning(f"Could not load {season}: {str(e)[:120]}")
        if frames:
            combined=pd.concat(frames,ignore_index=True)
            combined=combined[combined["GAME_DATE"].dt.date < day]
            if vs_team:
                if (combined["OPP"]==vs_team).sum()>=minimum:break
            elif len(combined)>=minimum:break
    if not frames:return pd.DataFrame()
    return pd.concat(frames,ignore_index=True).drop_duplicates("Game_ID").query("GAME_DATE == GAME_DATE").sort_values("GAME_DATE",ascending=False).loc[lambda x:x["GAME_DATE"].dt.date<day]

def summary(df,category):
    col,lines=LINES[category]
    if df.empty:return pd.DataFrame()
    return pd.DataFrame([{"Line":f"{line}+","Hits":int((df[col]>=line).sum()),"Games":len(df),
                          "Hit rate":f"{(df[col]>=line).mean():.0%}"} for line in lines])

def game_table(df):
    cols=["GAME_DATE","SEASON","MATCHUP","WL","MIN","PTS","REB","AST","FG3M"]
    if df.empty:return pd.DataFrame(columns=cols)
    d=df[cols].copy()
    d["GAME_DATE"]=d["GAME_DATE"].dt.strftime("%Y-%m-%d")
    return d.rename(columns={"GAME_DATE":"Date","SEASON":"Season","MATCHUP":"Matchup","WL":"Result","MIN":"Minutes","PTS":"Points","REB":"Rebounds","AST":"Assists","FG3M":"3PM"})

day=st.date_input("Slate date (Eastern Time)",TODAY)
try:
    games=schedule(day)
except Exception as e:
    st.error(f"Schedule unavailable: {e}")
    st.stop()
if not games:
    st.info("No NBA games returned for this date.")
    st.stop()
st.write("**Games:** "+" | ".join(g["name"] for g in games))
opponents={}
for g in games:
    opponents[g["home"]]=g["away"]
    opponents[g["away"]]=g["home"]

st.header("🏆 Today's Top 10 Alternate Lines by Category")
st.caption("Ranked by actual last-10-game hit rates (including prior seasons when necessary). This may take time to load. Historical rates are not guaranteed probabilities. Player availability remains UNVERIFIED.")
@st.cache_data(ttl=3600,show_spinner=False)
def all_current_players(season):
    return season_players(season)
def generate_board(day, opponents):
    pool=all_current_players(season_for(day))
    if pool.empty:return pd.DataFrame()
    pool=pool[pool["TEAM_ABBREVIATION"].isin(opponents)].sort_values("GAME_DATE",ascending=False).drop_duplicates("PLAYER_ID")
    results=[]
    progress=st.progress(0,text="Loading player histories...")
    for i,(_,r) in enumerate(pool.iterrows()):
        progress.progress((i+1)/len(pool),text=f"Checking {i+1}/{len(pool)} players")
        pid=int(r["PLAYER_ID"])
        team_abbr=r["TEAM_ABBREVIATION"]
        try:
            d=logs(pid,day,minimum=10)
            d=d.head(10)
            if len(d)<5:continue
            for category,(col,thresholds) in LINES.items():
                for line in thresholds:
                    hits=int((d[col]>=line).sum())
                    results.append({"Category":category,"Player":r["PLAYER_NAME"],
                                    "Team":team_abbr,"Opponent":opponents[team_abbr],
                                    "Alternate":f"{line}+","Line value":line,
                                    "Hits":hits,"Games":len(d),"Hit rate":hits/len(d),
                                    "Last 10 average":round(float(d[col].mean()),1),
                                    "Availability":"⚠️ UNVERIFIED"})
        except Exception:
            continue
    progress.empty()
    return pd.DataFrame(results)
if st.button("🔄 Calculate today's Top 10 boards",type="primary"):
    with st.spinner("Calculating actual game-log hit rates for today's teams..."):
        st.session_state["board_data"]=generate_board(day,opponents)
        st.session_state["board_date"]=str(day)
board=st.session_state.get("board_data",pd.DataFrame())
if st.session_state.get("board_date")!=str(day):
    board=pd.DataFrame()
if not board.empty:
    for cat in LINES:
        st.subheader(f"Top 10 — {cat}")
        subset=board[board["Category"]==cat].copy()
        # Choose a single highest-confidence alternate for each player; break ties by harder threshold.
        subset=subset.sort_values(["Hit rate","Games","Line value"],ascending=[False,False,False]).drop_duplicates("Player").head(10)
        subset["Last 10 hit rate"]=subset.apply(lambda r:f"{r['Hits']}/{r['Games']} ({r['Hit rate']:.0%})",axis=1)
        st.dataframe(subset[["Player","Team","Opponent","Alternate","Last 10 hit rate","Last 10 average","Availability"]],hide_index=True,use_container_width=True)
elif st.session_state.get("board_date")==str(day):
    st.warning("No complete ranking data could be retrieved. NBA Stats may be rate-limiting requests.")
else:
    st.info("Select 'Calculate today's Top 10 boards' to load the full slate. The app does not substitute unverified picks when data is missing.")

team_names=sorted(opponents)
team=st.selectbox("Team playing on selected date",team_names,format_func=lambda t:f"{t} — {TEAM_MAP.get(t,{}).get('full_name',t)}")
opponent=opponents[team]
st.info(f"Scheduled opponent: {opponent}. Opponent history uses actual prior games against {opponent}, not the last opponent played.")
try:
    roster=season_players(season_for(day))
except Exception as e:
    st.error(f"NBA stats player list unavailable: {e}. Try refreshing later.")
    st.stop()
roster=roster[roster["TEAM_ABBREVIATION"]==team].sort_values("GAME_DATE",ascending=False).drop_duplicates("PLAYER_ID")
if roster.empty:
    st.warning("No players with logged games found for this team this season. This is not a verified active roster.")
    st.stop()
name_query=st.text_input("Search player name")
if name_query:
    roster=roster[roster["PLAYER_NAME"].str.contains(name_query,case=False,na=False,regex=False)]
if roster.empty:st.warning("No matching players.");st.stop()
names=roster.sort_values("PLAYER_NAME")
player=st.selectbox("Player",names["PLAYER_NAME"].tolist())
pid=int(names.loc[names["PLAYER_NAME"]==player,"PLAYER_ID"].iloc[0])
st.image(f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png",width=160)
st.warning("⚠️ UNVERIFIED availability — this app does not confirm today's injury report, lineup, or active status. A historical game log does not mean a player is available.")
category=st.selectbox("Prop category",list(LINES))
with st.spinner("Loading historical game logs..."):
    all_logs=logs(pid,day,minimum=10)
    vs_logs=logs(pid,day,minimum=10,vs_team=opponent)
recent=all_logs.head(10)
h2h=vs_logs[vs_logs["OPP"]==opponent].head(10) if not vs_logs.empty else pd.DataFrame()
a,b=st.columns(2)
with a:
    st.subheader("Last 10 games — overall")
    st.dataframe(game_table(recent),use_container_width=True,hide_index=True)
    st.dataframe(summary(recent,category),use_container_width=True,hide_index=True)
with b:
    st.subheader(f"Last 10 games vs {opponent}")
    if len(h2h)<10:
        st.info(f"Found {len(h2h)} prior regular-season matchup(s) within the six seasons checked. No games have been fabricated.")
    if len(h2h):
        st.dataframe(game_table(h2h),use_container_width=True,hide_index=True)
        st.dataframe(summary(h2h,category),use_container_width=True,hide_index=True)
    else:st.info("No head-to-head logs found.")

st.subheader("📈 Weighted alternate-line projections")
st.caption("Model estimate: 55% last 10 overall, 25% last 10 vs today's opponent, 20% longer-term form. Head-to-head weight is reduced when fewer than 10 matchups are available. This is a heuristic, not a calibrated probability.")
def weighted_projection(recent, h2h, all_logs, category):
    col, thresholds=LINES[category]
    long_term=all_logs.head(40)
    groups=[(recent,0.55),(h2h,0.25),(long_term,0.20)]
    valid=[(d,w) for d,w in groups if not d.empty]
    if not valid:return pd.DataFrame()
    # Downweight limited head-to-head evidence and redistribute unused weight.
    weighted=[]
    for d,w in valid:
        if d is h2h: w*=min(1,len(d)/10)
        weighted.append((d,w))
    total=sum(w for _,w in weighted)
    mean=sum(d[col].mean()*w for d,w in weighted)/total
    # Approximate distribution from game-level variance, with a conservative floor.
    variance=sum((max(float(d[col].var(ddof=1)) if len(d)>1 else 0,1)+(d[col].mean()-mean)**2)*w for d,w in weighted)/total
    std=max(variance**0.5,1.0)
    from scipy.stats import norm
    rows=[]
    for threshold in thresholds:
        prob=float(norm.sf(threshold-0.5,loc=mean,scale=std))
        rows.append({"Alternate line":f"{threshold}+","Projected average":round(mean,1),
                     "Estimated hit probability":round(100*prob,1),
                     "Last 10 hit rate":round(100*(recent[col]>=threshold).mean(),1) if len(recent) else None,
                     "Vs opponent hit rate":round(100*(h2h[col]>=threshold).mean(),1) if len(h2h) else None,
                     "Opponent sample":len(h2h)})
    return pd.DataFrame(rows).sort_values("Estimated hit probability",ascending=False)
projections=weighted_projection(recent,h2h,all_logs,category)
if not projections.empty:
    st.metric(f"Weighted projected {category.lower()}",f"{projections['Projected average'].iloc[0]:.1f}")
    st.dataframe(projections,hide_index=True,use_container_width=True)
    st.caption("Percentages are model estimates, not sportsbook-implied odds. No betting edge can be computed without the offered odds. The normal approximation can be inaccurate for low-count props such as three-pointers.")
else:
    st.info("Insufficient game logs to calculate a projection.")

st.subheader("Side-by-side averages")
col=LINES[category][0]
st.dataframe(pd.DataFrame([
    {"Sample":"Last 10 overall","Games":len(recent),"Average":round(recent[col].mean(),2) if len(recent) else None,"Average minutes":round(recent["MIN"].mean(),1) if len(recent) else None},
    {"Sample":f"Last 10 vs {opponent}","Games":len(h2h),"Average":round(h2h[col].mean(),2) if len(h2h) else None,"Average minutes":round(h2h["MIN"].mean(),1) if len(h2h) else None}
]),hide_index=True,use_container_width=True)
st.caption("Historical hit rates are descriptive, not calibrated probabilities or sportsbook edges. Regular season only. Current and previous seasons are combined, newest first. Data source: NBA Stats via nba_api; schedule: ESPN.")