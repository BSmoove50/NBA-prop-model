import math
import numpy as np
import pandas as pd
import streamlit as st
from scipy.stats import norm
from nba_api.stats.static import players, teams
from nba_api.stats.endpoints import playergamelog

st.set_page_config(page_title='NBA Prop Lab',page_icon='🏀',layout='wide')
st.title('🏀 NBA Prop Lab — Season + Last 10 + Edge')
st.caption('2026–27 regular season • Last 10 can include 2025–26 • Historical model estimates, not guaranteed outcomes')
SEASON='2026-27'; PREVIOUS='2025-26'
STATS={'Points':'PTS','Rebounds':'REB','Assists':'AST','3PM':'FG3M','Steals':'STL','Blocks':'BLK','Turnovers':'TOV','PRA':'PRA','Points + Rebounds':'PR','Points + Assists':'PA','Rebounds + Assists':'RA'}
TEAM_NAMES={t['abbreviation']:t['full_name'] for t in teams.get_teams()}
@st.cache_data(ttl=1800,show_spinner=False)
def logs(pid,season):
    df=playergamelog.PlayerGameLog(player_id=pid,season=season,season_type_all_star='Regular Season',timeout=35).get_data_frames()[0]
    if df.empty:return df
    df['GAME_DATE']=pd.to_datetime(df['GAME_DATE'])
    for k,parts in {'PRA':['PTS','REB','AST'],'PR':['PTS','REB'],'PA':['PTS','AST'],'RA':['REB','AST']}.items():df[k]=df[parts].sum(axis=1)
    return df.sort_values('GAME_DATE',ascending=False).reset_index(drop=True)

names=sorted(players.get_active_players(),key=lambda p:p['full_name'])
lookup={p['full_name']+' ('+str(p['id'])+')':p['id'] for p in names}
a,b,c=st.columns([2,1,1])
with a: selection=st.selectbox('Player',list(lookup))
with b: prop=st.selectbox('Prop',list(STATS))
with c: opponent=st.selectbox('Upcoming opponent', ['Select opponent']+sorted(TEAM_NAMES))
line=st.number_input('Sportsbook / PrizePicks line',min_value=0.0,value=25.5,step=0.5)
col1,col2,col3=st.columns(3)
with col1: venue=st.selectbox('Game location',['Any','Home','Away'])
with col2: minutes_override=st.number_input('Expected minutes (0 = automatic)',min_value=0.0,max_value=48.0,value=0.0,step=0.5)
with col3: adjustment=st.slider('Manual injury / matchup adjustment (%)',-30,30,0,1)
try:
    current=logs(lookup[selection],SEASON)
    previous=logs(lookup[selection],PREVIOUS)
except Exception as exc:
    st.error('NBA Stats data is unavailable or rate-limited. Retry later or run locally. '+str(exc));st.stop()
if current.empty and previous.empty:st.warning('No regular-season logs available for this player.');st.stop()
all_logs=pd.concat([current.assign(SEASON=SEASON),previous.assign(SEASON=PREVIOUS)],ignore_index=True).sort_values('GAME_DATE',ascending=False)
last10=all_logs.head(10)
key=STATS[prop]
def avg(frame):return float(frame[key].mean()) if not frame.empty else float('nan')
def fmt(x):return '—' if pd.isna(x) else f'{x:.1f}'
season_avg=avg(current);l10=avg(last10);l5=avg(last10.head(5));prev_avg=avg(previous)
season_n=len(current)
# Blend current season, last 10 (including previous season), and prior-season baseline.
# This is a heuristic projection, not a trained or validated prediction model.
parts=[]
if season_n:parts.append((season_avg,min(season_n/15,1)*0.50))
if len(last10):parts.append((l10,0.35))
if len(previous):parts.append((prev_avg,0.15 if season_n>=15 else 0.30))
base=sum(v*w for v,w in parts)/sum(w for _,w in parts)
venue_rows=all_logs[all_logs['MATCHUP'].str.contains(' vs. ' if venue=='Home' else ' @ ',regex=False)] if venue!='Any' else pd.DataFrame()
venue_avg=avg(venue_rows.head(15)) if len(venue_rows)>=3 else float('nan')
if np.isfinite(venue_avg):base=0.85*base+0.15*venue_avg
# Matchup history is reported separately; don't pretend it is a defensive adjustment.
opp_rows=all_logs[all_logs['MATCHUP'].str.contains(opponent,regex=False)] if opponent!='Select opponent' else pd.DataFrame()
opp_avg=avg(opp_rows) if len(opp_rows) else float('nan')
minutes_baseline=float(last10['MIN'].mean()) if len(last10) else float('nan')
if minutes_override and minutes_baseline>0:base*=min(1.5,minutes_override/minutes_baseline)
projection=max(0,base*(1+adjustment/100))
# Conservative dispersion estimate: observed variation, plus a floor for small samples.
series=all_logs[key].head(25).astype(float)
sd=float(series.std(ddof=1)) if len(series)>=5 else float('nan')
sd=max(sd if np.isfinite(sd) else 0, 0.18*projection,1.5)
more=float(norm.sf((line+0.5-projection)/sd))
edge=projection-line
st.divider()
metrics=st.columns(5)
for box,label,value in zip(metrics,['Projection','Line edge','MORE probability','LESS probability','Current season games'],[fmt(projection),f'{edge:+.1f}',f'{more:.1%}',f'{1-more:.1%}',str(season_n)]):box.metric(label,value)
st.caption('Probability uses an approximate normal distribution with a continuity adjustment. This is not a calibrated probability or a sportsbook EV calculation. For combo props, correlations are reflected only in observed historical totals.')
st.subheader('Historical averages')
st.dataframe(pd.DataFrame({'Window':['2026–27 season','Last 5 games','Last 10 games (cross-season)','2025–26 season','Home/Away selected','Against selected opponent'], 'Average':[fmt(season_avg),fmt(l5),fmt(l10),fmt(prev_avg),fmt(venue_avg),fmt(opp_avg)],'Games':[len(current),min(5,len(last10)),len(last10),len(previous),len(venue_rows),len(opp_rows)]}),hide_index=True,use_container_width=True)
for title,frame in [('Last 10 games (most recent first)',last10),('2026–27 season game logs',current)]:
    st.subheader(title)
    if frame.empty:st.info('No games available yet.')
    else:
        out=frame.copy();out['GAME_DATE']=out['GAME_DATE'].dt.strftime('%Y-%m-%d')
        cols=['GAME_DATE','MATCHUP','MIN','PTS','REB','AST','FG3M','STL','BLK','TOV',key]
        st.dataframe(out[list(dict.fromkeys(cols))],hide_index=True,use_container_width=True)
st.subheader('Hit rates versus selected line')
for label,frame in [('Last 5',last10.head(5)),('Last 10',last10),('Season',current)]:
    if len(frame):st.write(f"**{label}:** MORE {(frame[key]>line).sum()}/{len(frame)} • LESS {(frame[key]<line).sum()}/{len(frame)} • Push {(frame[key]==line).sum()}/{len(frame)}")
st.info('Opponent selection displays actual historical matchups only. For a reliable matchup adjustment, integrate opponent defensive ratings, pace, injuries and projected rotations from a verified source. Manual adjustment is explicitly user-controlled.')
