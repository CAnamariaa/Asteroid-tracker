# Near-Earth Object Monitor

A Streamlit dashboard for NASA's near-Earth object data.

Live: [https://asteroid-tracker.streamlit.app/]

## What it shows
- Objects passing Earth in a chosen date range (41 listed for 13-19 Oct 2026)
- Miss distance in lunar distances (1 LD = 384,400 km)
- Estimated size as a min-max range with error bars
- A filter for potentially hazardous objects
- How many objects passed closer than the Moon over the past 30 to 365 days

## Notes
- The NASA API accepts 7 days per request, so longer ranges are fetched week by week.
- Sizes are estimates from brightness, not measurements.
- "Potentially hazardous" is a classification based on orbit and size, not a prediction of impact.
- Small objects are mostly detected when they pass close, so the historical counts are biased toward close approaches.

## Run it
```
pip install -r requirements.txt
```
Put your key in a `.env` file: `NASA_API_KEY=your_key_here`

```
streamlit run app.py
```

Data: NASA NeoWs API (api.nasa.gov).