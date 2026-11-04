import streamlit as st
import pandas as pd
import altair as alt
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

# Clickable category and alternate-line buttons on the home page
if "selected_category" not in st.session_state:
    st.session_state.selected_category="Points"
if "selected_alt_line" not in st.session_state:
    st.session_state.selected_alt_line=None

st.subheader("Choose a prop category")
category_columns=st.columns(4)
for column, label in zip(category_columns, LINES):
    with column:
        if st.button(label, key=f"category_{label}", use_container_width=True,
                     type="primary" if st.session_state.selected_category==label else "secondary"):
            if st.session_state.selected_category!=label:
                st.session_state.selected_category=label
                st.session_state.selected_alt_line=None

selected_category=st.session_state.selected_category
st.markdown(f"**{selected_category} — select an alternate line**")
line_columns=st.columns(len(LINES[selected_category][1])+1)
with line_columns[0]:
    if st.button("All", key="line_all", use_container_width=True,
                 type="primary" if st.session_state.selected_alt_line is None else "secondary"):
        st.session_state.selected_alt_line=None
for column, threshold in zip(line_columns[1:], LINES[selected_category][1]):
    with column:
        if st.button(f"{threshold}+", key=f"line_{selected_category}_{threshold}",
                     use_container_width=True,
                     type="primary" if st.session_state.selected_alt_line==threshold else "secondary"):
            st.session_state.selected_alt_line=threshold

# Continuous hit-rate gradient: red (0%) → yellow (50%) → green (100%).
def hit_color(rate):
    rate=max(0.0,min(1.0,float(rate)))
    red=(220,53,69)
    yellow=(255,214,64)
    green=(34,170,95)
    low,high,t=(red,yellow,rate*2) if rate<=0.5 else (yellow,green,(rate-0.5)*2)
    return "#" + "".join(f"{round(a+(b-a)*t):02x}" for a,b in zip(low,high))

def hit_cell_style(text):
    try:
        numerator,denominator=text.split(" ",1)[0].split("/")
        ratio=int(numerator)/int(denominator)
        if int(denominator)==0:return ""
        return f"background-color: {hit_color(ratio)}; color: #151515; font-weight: 650;"
    except (ValueError,ZeroDivisionError,AttributeError):
        return ""

st.header("🏀 Today's Full-Slate Alternate Hit Rates")
st.caption("All players with a recorded game for a team on the selected slate, not a confirmed active roster. Last 10 completed regular-season games; previous season included when needed. Every threshold appears as hits/games (percent).")
@st.cache_data(ttl=3600,show_spinner=False)
def full_slate_logs(day):
    seasons=previous_seasons(day,2)
    frames=[]
    for season in seasons:
        frame=normalize(season_players(season),season)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    result=pd.concat(frames,ignore_index=True)
    result=result[result["GAME_DATE"].dt.date<day]
    return result.sort_values("GAME_DATE",ascending=False)

def full_slate_board(day,opponents):
    history=full_slate_logs(day)
    if history.empty:return pd.DataFrame()
    current=history[history["SEASON"]==season_for(day)]
    latest=current.drop_duplicates("PLAYER_ID")
    latest=latest[latest["TEAM_ABBREVIATION"].isin(opponents)]
    rows=[]
    for _,p in latest.iterrows():
        games=history[history["PLAYER_ID"]==p["PLAYER_ID"]].head(10)
        if games.empty:continue
        for category,(col,thresholds) in LINES.items():
            row={"Category":category,"Player":p["PLAYER_NAME"],"Team":p["TEAM_ABBREVIATION"],
                 "Opponent":opponents[p["TEAM_ABBREVIATION"]],"Games":len(games),
                 "Last 10 avg":round(float(games[col].mean()),1),"Availability":"⚠️ UNVERIFIED"}
            for line in thresholds:
                hits=int((games[col]>=line).sum())
                row[f"{line}+"]=f"{hits}/{len(games)} ({hits/len(games):.0%})"
                row[f"_hits_{line}"]=hits/len(games)
            rows.append(row)
    return pd.DataFrame(rows)

if st.button("🔄 Load all players and alternate hit rates",type="primary"):
    try:
        with st.spinner("Loading game logs for today's teams..."):
            st.session_state["full_board"]=full_slate_board(day,opponents)
            st.session_state["full_board_date"]=str(day)
    except Exception as e:
        st.error(f"Unable to retrieve complete player logs: {e}")
board=st.session_state.get("full_board",pd.DataFrame())
if st.session_state.get("full_board_date")!=str(day):
    board=pd.DataFrame()
if not board.empty:
    cat=st.session_state.selected_category
    chosen=st.session_state.selected_alt_line
    team_filter=st.selectbox("Filter full slate by team",["All teams"]+sorted(opponents),key="full_slate_team")
    search=st.text_input("Search full-slate players",key="full_slate_search")
    subset=board[board["Category"]==cat].copy()
    if team_filter!="All teams":subset=subset[subset["Team"]==team_filter]
    if search:subset=subset[subset["Player"].str.contains(search,case=False,regex=False,na=False)]
    thresholds=LINES[cat][1]
    sort_line=chosen if chosen is not None else thresholds[0]
    subset=subset.sort_values([f"_hits_{sort_line}","Last 10 avg"],ascending=False)
    visible=["Player","Team","Opponent","Games","Last 10 avg"]+[f"{n}+" for n in thresholds]+["Availability"]
    st.subheader(f"{cat}: {len(subset)} players"+(f" • ranked by {chosen}+" if chosen is not None else ""))
    hit_columns=[f"{n}+" for n in thresholds]
    styled=subset[visible].style.map(hit_cell_style,subset=hit_columns)
    st.dataframe(styled,hide_index=True,use_container_width=True)
    st.caption("Color scale: 🟥 0/10 (0%) → 🟨 5/10 (50%) → 🟩 10/10 (100%). In-between hit rates blend smoothly. Colors use the actual hits/games ratio when fewer than 10 games are available.")
    st.download_button("Download this category (CSV)",subset[visible].to_csv(index=False),
                       file_name=f"nba_{cat.lower().replace(' ','_')}_hit_rates.csv",mime="text/csv")
    st.markdown("### 📊 Player stats and hit-rate bar graphs")
    if not subset.empty:
        chart_players=subset[["Player","Team"]].copy()
        chart_players["Label"]=chart_players["Player"]+" ("+chart_players["Team"]+")"
        chosen_player=st.selectbox("Select a player to graph",chart_players["Label"].tolist(),key="chart_player")
        selected_row=chart_players.loc[chart_players["Label"]==chosen_player].iloc[0]
        selected_name=selected_row["Player"]
        selected_team=selected_row["Team"]
        player_pool=full_slate_logs(day)
        selected_logs=player_pool[
            player_pool["PLAYER_ID"]==int(
                player_pool.loc[
                    (player_pool["PLAYER_NAME"]==selected_name)
                    & (player_pool["TEAM_ABBREVIATION"]==selected_team),
                    "PLAYER_ID"
                ].iloc[0]
            )
        ].head(10).sort_values("GAME_DATE")
        stat_col, alternate_thresholds=LINES[cat]
        if not selected_logs.empty:
            chart_data=selected_logs[["GAME_DATE","MATCHUP",stat_col]].copy()
            chart_data["Game"]=chart_data["GAME_DATE"].dt.strftime("%b %d")+" "+chart_data["MATCHUP"]
            chart_data=chart_data.set_index("Game")[[stat_col]].rename(columns={stat_col:cat})
            st.markdown(f"**{selected_name} — last {len(chart_data)} games ({cat})**")
            st.bar_chart(chart_data,use_container_width=True)
            percentages=pd.DataFrame({
                "Alternate":[f"{n}+" for n in alternate_thresholds],
                "Hit rate (%)":[round(100*(selected_logs[stat_col]>=n).mean(),1) for n in alternate_thresholds]
            }).set_index("Alternate")
            st.markdown("**Hit rate for each alternate line**")
            graph_data=percentages.reset_index()
            graph_data["Color"]=graph_data["Hit rate (%)"].apply(lambda v:hit_color(v/100))
            graph=alt.Chart(graph_data).mark_bar(cornerRadiusTopLeft=3,cornerRadiusTopRight=3).encode(
                x=alt.X("Alternate:N",sort=[f"{n}+" for n in alternate_thresholds],title="Alternate line"),
                y=alt.Y("Hit rate (%):Q",scale=alt.Scale(domain=[0,100]),title="Last-10 hit rate (%)"),
                color=alt.Color("Color:N",scale=None,legend=None),
                tooltip=["Alternate:N",alt.Tooltip("Hit rate (%):Q",format=".1f")]
            ).properties(height=260)
            st.altair_chart(graph,use_container_width=True)
            st.caption("Each game bar is the actual stat total. Hit-rate bars show the percentage of the available last 10 games reaching each alternate.")

    st.caption("An absent player is not confirmed out. All availability flags remain unverified; check official injury reports and lineups. Historical hit rates are not future probabilities.")
elif st.session_state.get("full_board_date")==str(day):
    st.warning("No players could be loaded for this slate. The data service may be unavailable or the selected season has no logged games.")
else:
    st.info("Click 'Load all players and alternate hit rates' to populate the full-slate table.")

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
category=st.selectbox("Prop category",list(LINES),index=list(LINES).index(st.session_state.selected_category))
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