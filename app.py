import streamlit as st
import pandas as pd
from utils import (
    haversine_km,
    greedy_spatial_clustering,
    find_centroid_pincode,
    nearest_distance_to_workshops,
)
from streamlit_folium import st_folium
import folium
from folium import CircleMarker, Popup, Marker, Icon

st.set_page_config(layout="wide", page_title="KMA Mahindra Workshop Planner")

st.title("KMA Mahindra Workshop Planning Tool")

st.sidebar.header("Inputs / Controls")
uploaded_workshops = st.sidebar.file_uploader("Upload Mahindra workshops Excel", type=["xlsx","xls"], key="w")
uploaded_proj = st.sidebar.file_uploader("Upload F30 projections Excel", type=["xlsx","xls"], key="p")

max_ro = st.sidebar.slider("Max RO per cluster", 1000, 10000, 6000, step=500)
min_ro = st.sidebar.number_input("Min RO for cluster (informational)", value=5000, min_value=0)
min_dist_km = st.sidebar.slider("Min distance from existing workshop (km)", 1, 20, 5)

show_existing = st.sidebar.checkbox("Show existing workshops", value=True)
show_clusters = st.sidebar.checkbox("Show clusters", value=True)
show_suggested = st.sidebar.checkbox("Show suggested locations", value=True)

if uploaded_workshops and uploaded_proj:
    try:
        ws_df = pd.read_excel(uploaded_workshops)
        proj_df = pd.read_excel(uploaded_proj)
    except Exception as e:
        st.error(f"Error reading uploaded files: {e}")
        st.stop()

    st.subheader("Input file headers (detected)")
    st.write("Workshops columns:", list(ws_df.columns))
    st.write("Projections columns:", list(proj_df.columns))

    # try to infer column names with common possibilities
    # Workshops expected: workshop_name, pincode, latitude, longitude
    # Projections expected: pincode, F30_ROs (or projected_ro), latitude, longitude, NRC_VIN_count
    st.info("Make sure your files contain columns for pin code, latitude, longitude, and projected RO count (F30).")

    # Standardize column names by lowercasing
    ws = ws_df.copy()
    proj = proj_df.copy()
    ws.columns = [c.strip() if isinstance(c, str) else c for c in ws.columns]
    proj.columns = [c.strip() if isinstance(c, str) else c for c in proj.columns]

    # Try common column name matches
    def find_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        # try case-insensitive
        low_map = {col.lower(): col for col in df.columns if isinstance(col, str)}
        for c in candidates:
            if c.lower() in low_map:
                return low_map[c.lower()]
        return None

    ws_name_col = find_col(ws, ["workshop_name", "name", "dealer_name", "workshop", "dealer"])
    ws_pincode_col = find_col(ws, ["pincode", "pin", "pin_code", "postalcode", "postal_code"])
    ws_lat_col = find_col(ws, ["latitude","lat","y"])
    ws_lon_col = find_col(ws, ["longitude","lon","lng","long","x"])

    proj_pincode_col = find_col(proj, ["pincode", "pin", "pin_code", "postalcode", "postal_code"])
    proj_lat_col = find_col(proj, ["latitude","lat","y"])
    proj_lon_col = find_col(proj, ["longitude","lon","lng","long","x"])
    proj_ro_col = find_col(proj, ["F30_ROs","F30_RO","F30_RO_projection","projected_ro","projected_ros","projected_ro_count","projected_ro_count","f30_ro","f30_ro_projection","f30_projection","projected_ro_count","projected_ro"])

    missing = []
    for name, col in [
        ("workshop name", ws_name_col),
        ("workshop pincode", ws_pincode_col),
        ("workshop latitude", ws_lat_col),
        ("workshop longitude", ws_lon_col),
        ("proj pincode", proj_pincode_col),
        ("proj latitude", proj_lat_col),
        ("proj longitude", proj_lon_col),
        ("proj projected RO", proj_ro_col),
    ]:
        if col is None:
            missing.append(name)
    if missing:
        st.warning("Could not confidently detect these columns: " + ", ".join(missing))
        st.stop()

    # rename for internal use
    ws = ws.rename(columns={ws_name_col: "workshop_name", ws_pincode_col: "pincode", ws_lat_col: "lat", ws_lon_col: "lon"})
    proj = proj.rename(columns={proj_pincode_col: "pincode", proj_lat_col: "lat", proj_lon_col: "lon", proj_ro_col: "projected_ro"})

    # keep numeric columns properly cast
    proj["projected_ro"] = pd.to_numeric(proj["projected_ro"], errors="coerce").fillna(0)
    proj["lat"] = pd.to_numeric(proj["lat"], errors="coerce")
    proj["lon"] = pd.to_numeric(proj["lon"], errors="coerce")
    ws["lat"] = pd.to_numeric(ws["lat"], errors="coerce")
    ws["lon"] = pd.to_numeric(ws["lon"], errors="coerce")

    # drop rows missing coords
    proj = proj.dropna(subset=["lat","lon"])
    ws = ws.dropna(subset=["lat","lon"])

    # clustering
    clusters = greedy_spatial_clustering(proj, max_ro=max_ro)
    st.write(f"Formed {len(clusters)} clusters (max_ro={max_ro})")

    # Build folium map centered at mean location
    center_lat = float(proj["lat"].mean())
    center_lon = float(proj["lon"].mean())
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8)

    if show_clusters:
        # draw cluster markers and popups
        for i, c in enumerate(clusters, start=1):
            members = c["members"]
            total_ro = c["total_ro"]
            centroid = c["centroid"]
            # draw small circle at centroid
            popup_html = f"Cluster {i}<br/>Total RO: {int(total_ro)}<br/>Members: {len(members)}"
            CircleMarker(location=[centroid[0], centroid[1]], radius=8, fill=True, fill_opacity=0.9, popup=Popup(popup_html)).add_to(m)
            # draw lines to members
            for _, row in members.iterrows():
                folium.PolyLine(locations=[[centroid[0], centroid[1]],[row["lat"], row["lon"]]], weight=1).add_to(m)

    if show_existing:
        for _, r in ws.iterrows():
            tooltip = f"{r.get('workshop_name','')} (Pincode: {r.get('pincode','')})"
            Marker(location=[r["lat"], r["lon"]], tooltip=tooltip, icon=Icon(color="red",icon="wrench", prefix='fa')).add_to(m)

    # suggested locations: centroid pincode of each cluster, then filter by min_dist_km
    suggested = []
    for i, c in enumerate(clusters, start=1):
        centroid = c["centroid"]
        centroid_pincode, centroid_lat, centroid_lon = find_centroid_pincode(c["members"], centroid)
        dist_to_nearest = nearest_distance_to_workshops(centroid_lat, centroid_lon, ws)
        is_far = dist_to_nearest >= min_dist_km
        suggested.append({
            "cluster_id": i,
            "centroid_pincode": centroid_pincode,
            "centroid_lat": centroid_lat,
            "centroid_lon": centroid_lon,
            "total_ro": c["total_ro"],
            "dist_to_nearest_workshop_km": dist_to_nearest,
            "suggested": is_far
        })
    suggested_df = pd.DataFrame(suggested)
    st.subheader("Suggested Locations (centroid pincode per cluster)")
    st.write(suggested_df)

    if show_suggested:
        for _, s in suggested_df[suggested_df["suggested"]].iterrows():
            popup = f"Cluster {s['cluster_id']}<br/>RO: {int(s['total_ro'])}<br/>Pincode: {s['centroid_pincode']}<br/>Dist to nearest WS: {s['dist_to_nearest_workshop_km']:.2f} km"
            Marker(location=[s["centroid_lat"], s["centroid_lon"]], tooltip=popup, icon=Icon(color="green", icon="plus", prefix='fa')).add_to(m)

    # show map
    st_data = st_folium(m, width=1000, height=600)

    # export suggested and cluster summary
    st.subheader("Export")
    csv = suggested_df.to_csv(index=False).encode('utf-8')
    st.download_button("Download suggested locations CSV", data=csv, file_name="suggested_locations.csv", mime="text/csv")
    # cluster details
    all_clusters = []
    for i, c in enumerate(clusters, start=1):
        members = c["members"].copy()
        members["cluster_id"] = i
        members["cluster_total_ro"] = c["total_ro"]
        all_clusters.append(members)
    all_clusters_df = pd.concat(all_clusters, ignore_index=True)
    st.download_button("Download clusters detail CSV", data=all_clusters_df.to_csv(index=False).encode('utf-8'), file_name="clusters_detail.csv", mime="text/csv")

else:
    st.info("Please upload both required Excel files in the sidebar.")