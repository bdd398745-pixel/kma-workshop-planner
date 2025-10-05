import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from geopy.distance import geodesic
import math
from io import BytesIO

# ---------------------------
# PAGE CONFIG
# ---------------------------
st.set_page_config(page_title="Mahindra Workshop Planning Tool - KMA Region", layout="wide")

st.title("🔧 Mahindra Workshop Planning Tool - KMA Region")
st.markdown("""
This tool helps visualize existing Mahindra workshops and identify potential new workshop locations 
based on **F30 RO projections** and **distance constraints**.
""")

# ---------------------------
# FILE INPUTS
# ---------------------------
st.sidebar.header("📂 Input Files")

workshop_file = st.sidebar.file_uploader("Upload Workshop File", type=["xlsx"], key="workshop")
projection_file = st.sidebar.file_uploader("Upload F30 Projection File", type=["xlsx"], key="projection")

# Default values
max_ro_default = 6000
min_dist_default = 5

# ---------------------------
# USER CONTROLS
# ---------------------------
st.sidebar.header("⚙️ Controls")
max_ro = st.sidebar.slider("Max RO per Cluster", 1000, 10000, max_ro_default, step=500)
min_distance_km = st.sidebar.slider("Min Distance from Existing Workshop (km)", 1, 10, min_dist_default, step=1)

# ---------------------------
# LOAD AND VALIDATE DATA
# ---------------------------
if workshop_file and projection_file:
    try:
        df_workshops = pd.read_excel(workshop_file)
        df_proj = pd.read_excel(projection_file)

        # Normalize column names
        df_workshops.columns = df_workshops.columns.str.strip()
        df_proj.columns = df_proj.columns.str.strip()

        # Use exact columns from your uploaded files
        workshop_name_col = "Mabindra Workshop Location"
        workshop_pincode_col = "Pincode"
        proj_pincode_col = "Customer Pin Code"
        proj_ro_col = "F30_RO_Projection"

        # Rename for clarity
        df_workshops = df_workshops.rename(columns={
            workshop_name_col: "Workshop",
            workshop_pincode_col: "Workshop_Pincode",
            "Latitude": "Workshop_Lat",
            "Longitude": "Workshop_Lon"
        })

        df_proj = df_proj.rename(columns={
            proj_pincode_col: "Proj_Pincode",
            "Latitude": "Proj_Lat",
            "Longitude": "Proj_Lon",
            proj_ro_col: "Proj_RO"
        })

        # ---------------------------
        # CLUSTERING LOGIC
        # ---------------------------
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

        # Add remaining
        if current_cluster:
            clusters.append(pd.DataFrame(current_cluster).assign(Cluster_ID=f"Cluster_{cluster_id}"))

        df_clusters = pd.concat(clusters, ignore_index=True)

        # ---------------------------
        # CALCULATE CLUSTER CENTROIDS
        # ---------------------------
        centroids = (
            df_clusters.groupby("Cluster_ID")
            .agg({"Proj_Lat": "mean", "Proj_Lon": "mean", "Proj_RO": "sum"})
            .reset_index()
        )

        # ---------------------------
        # FILTER EXISTING WORKSHOPS (DISTANCE)
        # ---------------------------
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

        # Existing Workshops
        if st.sidebar.checkbox("Show Existing Workshops", value=True):
            for _, row in df_workshops.iterrows():
                folium.Marker(
                    [row["Workshop_Lat"], row["Workshop_Lon"]],
                    popup=f"🏭 {row['Workshop']}<br>Pincode: {row['Workshop_Pincode']}",
                    icon=folium.Icon(color="red", icon="wrench", prefix="fa")
                ).add_to(m)

        # Clusters
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

        # Suggested Locations
        if not df_suggested.empty and st.sidebar.checkbox("Show Suggested Locations", value=True):
            for _, row in df_suggested.iterrows():
                folium.Marker(
                    [row["Proj_Lat"], row["Proj_Lon"]],
                    popup=f"🟢 Suggested New Workshop<br>ROs: {int(row['Proj_RO'])}<br>Cluster: {row['Cluster_ID']}",
                    icon=folium.Icon(color="green", icon="plus", prefix="fa")
                ).add_to(m)

        st_folium(m, width=1200, height=700)

        # ---------------------------
        # SUMMARY TABLES
        # ---------------------------
        st.subheader("📊 Cluster Summary")
        st.dataframe(centroids.rename(columns={"Proj_RO": "Total_ROs"}))

        # Export
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
        st.error(f"❌ Error processing files: {e}")

else:
    st.info("⬆️ Please upload both Excel files to begin.")
