# KMA Mahindra Workshop Planner

Streamlit app to visualize existing Mahindra workshops, cluster F30 RO projections by geography, and suggest new workshop locations.

## Features
- Plot existing workshops on a map
- Greedy spatial clustering of pin codes capped by "Max RO per cluster"
- Identify centroid pincode for each cluster and suggest new workshop locations not within a minimum distance of existing workshops
- Export suggested locations and detailed cluster CSVs

## How to run locally
1. Install dependencies: `pip install -r requirements.txt`
2. Run: `streamlit run app.py`
3. Upload the two Excel files through the app sidebar:
   - `KMA_Mahindra_Workshops_Lat_Long.xlsx`
   - `KMA_NRC_F30_Retail_RO_Projections_PV_Lat_Long_Pincode.xlsx`

## Notes
- The clustering algorithm is greedy: it seeds from the highest-projection pincode and grows by nearest neighbors until cluster RO >= max_ro.
- The app attempts to auto-detect common column names. If your files use different headers, rename them to include latitude/longitude/pincode/projected RO columns.