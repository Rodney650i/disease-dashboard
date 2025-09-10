import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Disease Tracker", layout="wide")
st.title("🗺️ Disease Tracker — Heat Map + Trend (public API)")
st.caption("Live public data • disease.sh API • Perfect for your portfolio")

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

USPS = {
    "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO","Connecticut":"CT",
    "Delaware":"DE","District of Columbia":"DC","Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL",
    "Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA","Maine":"ME","Maryland":"MD","Massachusetts":"MA",
    "Michigan":"MI","Minnesota":"MN","Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV",
    "New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND",
    "Ohio":"OH","Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD",
    "Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA","West Virginia":"WV","Wisconsin":"WI",
    "Wyoming":"WY"
}

@st.cache_data(ttl=60*30)
def fetch_states_snapshot():
        """
        Returns a DataFrame with:
            state, cases, deaths, todayCases (computed), todayDeaths (computed), state_code
        """
        # Pull "today" snapshot
        url_today = "https://disease.sh/v3/covid-19/states?allowNull=true"
        r1 = requests.get(url_today, timeout=30)
        r1.raise_for_status()
        today = pd.DataFrame(r1.json())

        # Pull "yesterday" snapshot to compute deltas
        url_yest = "https://disease.sh/v3/covid-19/states?yesterday=true&allowNull=true"
        r2 = requests.get(url_yest, timeout=30)
        r2.raise_for_status()
        yest = pd.DataFrame(r2.json())

        # Keep only the columns we need and merge
        keep_cols = ["state", "cases", "deaths"]
        today = today[keep_cols].rename(columns={"cases": "cases_today", "deaths": "deaths_today"})
        yest = yest[keep_cols].rename(columns={"cases": "cases_yest", "deaths": "deaths_yest"})

        df = today.merge(yest, on="state", how="left")

        # Compute deltas safely (clip negatives to 0)
        df["todayCases"] = (df["cases_today"] - df["cases_yest"]).fillna(0).astype("int64").clip(lower=0)
        df["todayDeaths"] = (df["deaths_today"] - df["deaths_yest"]).fillna(0).astype("int64").clip(lower=0)

        # Map to USPS codes for the choropleth
        df["state_code"] = df["state"].map(USPS)

        # Clean up & keep only valid states for the map
        df = df[df["state_code"].notna()].copy()

        return df

@st.cache_data(ttl=60*30)
def fetch_national_timeseries(days:int=180):
    # National timeseries (NYT)
    url = f"https://disease.sh/v3/covid-19/nyt/usa?lastdays={days}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df["new_cases"] = df["cases"].diff().fillna(0).clip(lower=0).astype(int)
    return df[["date","cases","new_cases"]]

@st.cache_data(ttl=60*30)
def fetch_state_timeseries(state_name:str, days:int=180):
    # Timeseries for a single state (NYT)
    url = f"https://disease.sh/v3/covid-19/nyt/states/{state_name}?lastdays={days}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df["new_cases"] = df["cases"].diff().fillna(0).clip(lower=0).astype(int)
    return df[["date","cases","new_cases"]]

# ------------------------------------------------------------------
# Sidebar controls
# ------------------------------------------------------------------
DEFAULT_DAYS = 180
days = st.sidebar.slider("How many days for the trend line?", 60, 365, DEFAULT_DAYS, step=30)
state_choice = st.sidebar.selectbox("Trend line for", ["United States"] + sorted(list(USPS.keys())))

# ------------------------------------------------------------------
# KPIs + Heat map
# ------------------------------------------------------------------
try:
    snap = fetch_states_snapshot()
except Exception as e:
    st.error(f"Could not load state snapshot: {e}")
    st.stop()

latest_total_cases = int(snap["todayCases"].sum())
latest_total_deaths = int(snap["todayDeaths"].sum())

col1, col2, col3 = st.columns(3)
col1.metric("States reporting", f"{snap.shape[0]}")
col2.metric("New cases (today, sum of states)", f"{latest_total_cases:,}")
col3.metric("New deaths (today, sum of states)", f"{latest_total_deaths:,}")

st.subheader("🧊 Heat Map — Today’s New Cases by State")
map_fig = px.choropleth(
    snap,
    locations="state_code",
    locationmode="USA-states",
    color="todayCases",
    scope="usa",
    hover_name="state",
    hover_data={"todayCases": True, "todayDeaths": True, "state_code": False},
    title="New Cases by State (today)",
    color_continuous_scale="Viridis",
)
st.plotly_chart(map_fig, use_container_width=True)

# ------------------------------------------------------------------
# Trend line
# ------------------------------------------------------------------
st.subheader("📈 Trend Line — New Cases Over Time")

try:
    if state_choice == "United States":
        ts = fetch_national_timeseries(days)
        title = "United States"
    else:
        ts = fetch_state_timeseries(state_choice, days)
        title = state_choice
except Exception as e:
    st.error(f"Could not load timeseries: {e}")
    st.stop()

line = px.line(
    ts,
    x="date",
    y="new_cases",
    markers=True,
    title=f"New Cases — {title} (last {days} days)"
)
line.update_layout(xaxis_title="Date", yaxis_title="New Cases")
st.plotly_chart(line, use_container_width=True)

# Table of top states (today)
st.subheader("🏅 Top 10 States — Today’s New Cases")
top10 = snap.sort_values("todayCases", ascending=False).head(10)
st.dataframe(
    top10[["state","todayCases","todayDeaths"]].rename(
        columns={"state":"State","todayCases":"New Cases (today)","todayDeaths":"New Deaths (today)"}),
    use_container_width=True
)

st.caption("Data: https://disease.sh (public, free). Note: numbers depend on state reporting cadence.")
