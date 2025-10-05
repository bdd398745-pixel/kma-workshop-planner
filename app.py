import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from geopy.distance import geodesic
from io import BytesIO

# ---------------------------
# PAGE CONFIG
# ---------------------------
st.set_page_config(page_title="Mahindra Workshop Planning Tool - KMA Region", layout="wide")

st.title("🔧 Mahindra Workshop Planning Tool - KMA Region")
st.markdown("""
This tool visualizes existing Mahindra workshops and identifies potential new workshop locations 
based on **F30 RO projections** and **distance constraints**.
""")

# ---------------------------
# DATA SOURCE SELECTION
# ---------------------------
st.sidebar.header("📂 Data Source")

data_source = st.sidebar.radio(
    "Select Data Source",
    ["Use GitHub Files (Default)", "Upload Files"],
    index=0
)

# Change this to your repo path:
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/bdd398745-pixel/kma-workshop-planner/main/data/"

# ---------------------------
# USER CONTROLS
# ---------------------------
st.sidebar.header("⚙️ Controls")
max_ro = st.sidebar.slider("Max RO per Cluster", 1000, 10000, 6000, step=500)
min_distance_km = st.sidebar.slider("Min Distance from Existing Workshop (km)", 1, 10, 5, step=1)

# ---------------------------
# LOAD DATA
# ---------------------------
df_workshops, df_proj = None, None

try:
    if data_source == "Use GitHub Files (Default)":
        workshop_url = GITHUB_RAW_BASE + "KMA_Mahindra_Workshops_Lat_Long.xlsx"
        proj_url = GITHUB_RAW_BASE + "KMA_NRC_F30_Retail_RO_Projections_PV_Lat_Long_Pincode.xlsx"
        df_workshops = pd.read_excel(workshop_url)
        df_proj = pd.read_excel(proj_url)
        st.sidebar.success("✅ Loaded data from GitHub repository.")
    else:
        workshop_file = st.sidebar.file_uploader("Upload Workshop File", type=["xlsx"], key="workshop")
        projection_file = st.sidebar.file_uploader("Upload F30 Projection File", type=["xlsx"], key="projection")
        if workshop_file and projection_file:
            df_workshops = pd.read_excel(workshop_file)
            df_proj = pd.read_excel(projection_file)
            st.sidebar.success("✅ Files uploaded successfully.")
        else:
            st.info("⬆️ Please upload both Excel files to begin.")
            st.stop()
except Exception as e:
    st.error(f"❌ Error loading data: {e}")
    st.stop()

# ---------------------------
# PROCESS DATA
# ---------------------------
try:
    df_workshops.columns = df_workshops.columns.str.strip()
    df_proj.columns = df_proj.columns.str.strip()

    # Rename based on actual headers
    df_workshops = df_workshops.rename(columns={
        "Mabindra Workshop Location": "Workshop",
        "Pincode": "Workshop_Pincode",
        "Latitude": "Workshop_Lat",
        "Longitude": "Workshop_Lon"
    })

    df_proj = df_proj.rename(columns={
        "Customer Pin Code": "Proj_Pincode",
        "Latitude": "Proj_Lat",
        "Longitude": "Proj_Lon",
        "F30_RO_Projection": "Proj_RO"
    })

    # Sort and cluster
    df_proj = df_proj.sort_values("Proj_RO", ascending=False).reset_index(drop=True)
    clusters = []
    current_cluster = []
    current_sum = 0
    cluster_id = 1

    for _, row in df_proj.iterrows():
        if current_sum + row["Proj_RO"] <= max_ro or current_sum == 0:
            current_cluster.append(row)
            current_sum += row["Proj_RO"]
        else:
            clusters.append(pd.DataFrame(current_cluster).assign(Cluster_ID=f"Cluster_{cluster_id}"))
            cluster_id += 1
            current_cluster = [row]
            current_sum = row["Proj_RO"]

    if current_cluster:
        clusters.append(pd.DataFrame(current_cluster).assign(Cluster_ID=f"Cluster_{cluster_id}"))

    df_clusters = pd.concat(clusters, ignore_index=True)

    # Cluster centroids
    centroids = (
        df_clusters.groupby("Cluster_ID")
        .agg({"Proj_Lat": "mean", "Proj_Lon": "mean", "Proj_RO": "sum"})
        .reset_index()
    )

    # Filter based on proximity
    suggested_locations = []
    for _, row in centroids.iterrows():
        cluster_latlon = (row["Proj_Lat"], row["Proj_Lon"])
        too_close = False
        for _, ws in df_workshops.iterrows():
            dist = geodesic(cluster_latlon, (ws["Workshop_Lat"], ws["Workshop_Lon"])).km
            if dist < min_distance_km:
                too_close = True
                break
        if not too_close:
            suggested_locations.append(row)

    df_suggested = pd.DataFrame(suggested_locations)

    # ---------------------------
    # MAP VISUALIZATION
    # ---------------------------
    st.subheader("🗺️ Interactive Map")

    map_center = [df_proj["Proj_Lat"].mean(), df_proj["Proj_Lon"].mean()]
    m = folium.Map(location=map_center, zoom_start=7)

    if st.sidebar.checkbox("Show Existing Workshops", value=True):
        for _, row in df_workshops.iterrows():
            folium.Marker(
                [row["Workshop_Lat"], row["Workshop_Lon"]],
                popup=f"🏭 {row['Workshop']}<br>Pincode: {row['Workshop_Pincode']}",
                icon=folium.Icon(color="red", icon="wrench", prefix="fa")
            ).add_to(m)

    if st.sidebar.checkbox("Show Clusters", value=True):
        marker_cluster = MarkerCluster().add_to(m)
        for _, row in df_clusters.iterrows():
            folium.CircleMarker(
                [row["Proj_Lat"], row["Proj_Lon"]],
                radius=4,
                color="blue",
                fill=True,
                fill_opacity=0.6,
                popup=f"Cluster: {row['Cluster_ID']}<br>ROs: {row['Proj_RO']}"
            ).add_to(marker_cluster)

    if not df_suggested.empty and st.sidebar.checkbox("Show Suggested Locations", value=True):
        for _, row in df_suggested.iterrows():
            folium.Marker(
                [row["Proj_Lat"], row["Proj_Lon"]],
                popup=f"🟢 Suggested Workshop<br>Cluster: {row['Cluster_ID']}<br>ROs: {int(row['Proj_RO'])}",
                icon=folium.Icon(color="green", icon="plus", prefix="fa")
            ).add_to(m)

    st_folium(m, width=1200, height=700)

    # ---------------------------
    # CLUSTER SUMMARY + DOWNLOAD
    # ---------------------------
    st.subheader("📊 Cluster Summary")
    st.dataframe(centroids.rename(columns={"Proj_RO": "Total_ROs"}))

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_suggested.to_excel(writer, index=False, sheet_name="Suggested_Locations")
        centroids.to_excel(writer, index=False, sheet_name="Cluster_Summary")

    st.download_button(
        label="📥 Download Suggested Locations (Excel)",
        data=buffer.getvalue(),
        file_name="Suggested_Workshop_Locations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

except Exception as e:
    st.error(f"❌ Error processing data: {e}")
