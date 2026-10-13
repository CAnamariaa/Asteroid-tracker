"""Near-Earth object dashboard built on the NASA NeoWs API."""
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.nasa.gov/neo/rest/v1/feed"
MOON_KM = 384_400
MAX_DAYS_PER_REQUEST = 7  # NeoWs limit
LABELS = {True: "Potentially hazardous", False: "Not classified hazardous"}
COLORS = {"Potentially hazardous": "#D9694F", "Not classified hazardous": "#6C8EBF"}

try:
    API_KEY = st.secrets["NASA_API_KEY"]
except Exception:
    API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")

st.set_page_config(page_title="Near-Earth Object Monitor", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_week(start: str, end: str) -> pd.DataFrame:
    """Fetch one request window (max 7 days) and flatten it to one row per object."""
    response = requests.get(
        API_URL,
        params={"start_date": start, "end_date": end, "api_key": API_KEY},
        timeout=30,
    )
    response.raise_for_status()

    rows = []
    for day, objects in response.json()["near_earth_objects"].items():
        for obj in objects:
            diameter = obj["estimated_diameter"]["meters"]
            approaches = obj["close_approach_data"]
            # Use the approach matching this date, not simply the first entry.
            approach = next(
                (a for a in approaches if a["close_approach_date"] == day),
                approaches[0],
            )
            rows.append({
                "name": obj["name"],
                "date": day,
                "diameter_min_m": diameter["estimated_diameter_min"],
                "diameter_max_m": diameter["estimated_diameter_max"],
                "miss_km": float(approach["miss_distance"]["kilometers"]),
                "speed_kmh": float(approach["relative_velocity"]["kilometers_per_hour"]),
                "hazardous": obj["is_potentially_hazardous_asteroid"],
            })
    return pd.DataFrame(rows)


def fetch_range(start: date, end: date) -> pd.DataFrame:
    """Fetch an arbitrary date range by splitting it into 7-day windows."""
    frames, current = [], start
    while current <= end:
        window_end = min(current + timedelta(days=MAX_DAYS_PER_REQUEST - 1), end)
        frames.append(fetch_week(str(current), str(window_end)))
        current = window_end + timedelta(days=1)
    combined = pd.concat(frames, ignore_index=True)
    return combined.drop_duplicates(["name", "date"]).reset_index(drop=True)


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["lunar_distances"] = df["miss_km"] / MOON_KM
    df["diameter_mid_m"] = (df["diameter_min_m"] + df["diameter_max_m"]) / 2
    df["err_plus"] = df["diameter_max_m"] - df["diameter_mid_m"]
    df["err_minus"] = df["diameter_mid_m"] - df["diameter_min_m"]
    df["classification"] = df["hazardous"].map(LABELS)
    return df


def load(start: date, end: date) -> pd.DataFrame:
    """Fetch data and translate API failures into readable messages."""
    try:
        return add_derived_columns(fetch_range(start, end))
    except requests.HTTPError as err:
        status = err.response.status_code
        if status == 429:
            st.error("NASA API rate limit reached. Use a personal API key or retry later.")
        else:
            st.error(f"NASA API returned status {status}.")
    except requests.RequestException:
        st.error("Could not reach the NASA API. Check your connection.")
    st.stop()


# ------------------------------------------------------------------ header
st.title("Near-Earth Object Monitor")
st.caption(
    "Close approaches reported by the NASA NeoWs API. Distances are expressed in "
    "lunar distances (LD); 1 LD = 384,400 km."
)
if API_KEY == "DEMO_KEY":
    st.warning("Running with DEMO_KEY. Rate limits are strict; set a personal key.")

# ------------------------------------------------------------------ inputs
col_a, col_b, col_c = st.columns([1, 1, 2])
start = col_a.date_input("Start date", date.today())
end = col_b.date_input("End date", date.today() + timedelta(days=6))
hazardous_only = col_c.checkbox("Potentially hazardous objects only")

if end < start:
    st.error("The end date must not precede the start date.")
    st.stop()
if (end - start).days > 366:
    st.error("Please select a range of at most one year.")
    st.stop()

with st.spinner("Loading data"):
    df = load(start, end)

if hazardous_only:
    df = df[df["hazardous"]]

if df.empty:
    st.info("No objects match the selected filters.")
    st.stop()

# ------------------------------------------------------------------ summary
closest = df.loc[df["miss_km"].idxmin()]
largest = df.loc[df["diameter_max_m"].idxmax()]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Objects", f"{len(df):,}")
m2.metric("Potentially hazardous", f"{int(df['hazardous'].sum()):,}")
m3.metric(
    "Closest approach",
    f"{closest['lunar_distances']:.2f} LD",
    help=f"{closest['name']}, {closest['date']}, {closest['miss_km']:,.0f} km",
)
m4.metric(
    "Largest object",
    f"up to {largest['diameter_max_m']:,.0f} m",
    help=f"{largest['name']}, {largest['date']}",
)

# ------------------------------------------------------------------ table
st.subheader("Objects by size")
table = df.sort_values("diameter_max_m", ascending=False)[
    ["name", "date", "diameter_min_m", "diameter_max_m",
     "lunar_distances", "miss_km", "speed_kmh", "classification"]
]
st.dataframe(
    table,
    hide_index=True,
    column_config={
        "name": "Designation",
        "date": "Approach date",
        "diameter_min_m": st.column_config.NumberColumn("Diameter min (m)", format="%.0f"),
        "diameter_max_m": st.column_config.NumberColumn("Diameter max (m)", format="%.0f"),
        "lunar_distances": st.column_config.NumberColumn("Miss distance (LD)", format="%.2f"),
        "miss_km": st.column_config.NumberColumn("Miss distance (km)", format="%.0f"),
        "speed_kmh": st.column_config.NumberColumn("Relative speed (km/h)", format="%.0f"),
        "classification": "Classification",
    },
)

# ------------------------------------------------------------------ charts
st.subheader("Miss distance versus estimated diameter")
scatter = px.scatter(
    df,
    x="lunar_distances",
    y="diameter_mid_m",
    color="classification",
    color_discrete_map=COLORS,
    hover_name="name",
    hover_data={"date": True, "lunar_distances": ":.2f", "classification": False,
                "diameter_mid_m": False, "err_plus": False, "err_minus": False},
    error_y="err_plus",
    error_y_minus="err_minus",
    log_x=True,
    log_y=True,
    labels={
        "lunar_distances": "Miss distance (LD, log scale)",
        "diameter_mid_m": "Estimated diameter (m, log scale)",
        "date": "Approach date",
    },
)
scatter.add_vline(x=1, line_dash="dot", line_color="#8A93A6",
                  annotation_text="Moon (1 LD)")
scatter.update_layout(legend_title_text="", legend_orientation="h",
                      legend_y=1.08, margin=dict(t=40))
st.plotly_chart(scatter, use_container_width=True)
st.caption(
    "Error bars span the minimum and maximum diameter estimate. Sizes are inferred "
    "from brightness, not measured directly."
)

st.subheader("Approaches per day")
daily = df.groupby(["date", "classification"]).size().reset_index(name="count")
bars = px.bar(
    daily, x="date", y="count", color="classification",
    color_discrete_map=COLORS,
    labels={"date": "Approach date", "count": "Objects"},
)
bars.update_layout(legend_title_text="", legend_orientation="h",
                   legend_y=1.15, margin=dict(t=40))
st.plotly_chart(bars, use_container_width=True)

st.caption(
    '"Potentially hazardous" is a classification based on orbit and size. '
    "It is not a prediction of impact."
)

# ------------------------------------------------------------------ analysis
st.divider()
st.header("How rare are approaches closer than the Moon?")
st.write("Counts objects that passed within 1 LD over a past period, independent "
         "of the filters above.")

period = st.slider("Period (days back from today)", 30, 365, 180, step=30)

if st.button("Run analysis"):
    with st.spinner("Fetching historical data"):
        st.session_state["history"] = (
            period,
            load(date.today() - timedelta(days=period), date.today()),
        )

if "history" in st.session_state:
    days_back, history = st.session_state["history"]
    close = history[history["lunar_distances"] < 1].copy()

    a, b, c = st.columns(3)
    a.metric("Objects analysed", f"{len(history):,}")
    b.metric("Within 1 LD", f"{len(close):,}")
    c.metric("Share", f"{100 * len(close) / max(len(history), 1):.1f}%")

    if not close.empty:
        biggest = close.loc[close["diameter_max_m"].idxmax()]
        st.write(
            f"Over the last {days_back} days, {len(close)} of {len(history)} listed "
            f"objects passed closer than the Moon. The largest was {biggest['name']} "
            f"(up to {biggest['diameter_max_m']:.0f} m) on {biggest['date']}."
        )
        close["month"] = pd.to_datetime(close["date"]).dt.to_period("M").astype(str)
        monthly = close.groupby("month").size().reset_index(name="count")
        chart = px.bar(monthly, x="month", y="count",
                       labels={"month": "Month", "count": "Approaches within 1 LD"})
        chart.update_traces(marker_color=COLORS["Not classified hazardous"])
        st.plotly_chart(chart, use_container_width=True)

    st.caption(
        "Small objects are mostly detected when they pass close to Earth, so distant "
        "small objects are under-represented in this sample."
    )

st.divider()
st.caption("Data: NASA Near Earth Object Web Service (NeoWs).")