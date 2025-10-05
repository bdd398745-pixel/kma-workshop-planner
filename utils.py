import pandas as pd
import math
from collections import deque

def haversine_km(lat1, lon1, lat2, lon2):
    # returns distance in kilometers between two points
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2.0)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2.0)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def greedy_spatial_clustering(df, max_ro=6000):
    """
    Greedy spatial clustering:
    - df must have columns: pincode, lat, lon, projected_ro
    - Start with highest projected_ro unassigned pincode as cluster seed
    - Keep adding nearest unassigned pincode to cluster until cluster_ro >= max_ro or no unassigned left
    - Continue until all pincodes assigned
    - Returns list of clusters: each is dict with members (DataFrame), total_ro, centroid (lat,lon)
    """
    working = df.copy().reset_index(drop=True)
    # ensure numeric
    working["projected_ro"] = pd.to_numeric(working["projected_ro"], errors="coerce").fillna(0)
    unassigned = set(working.index.tolist())
    clusters = []

    # precompute coords
    coords = working[["lat","lon"]].to_dict(orient="index")

    while unassigned:
        # pick seed = unassigned index with max projected_ro
        seed = max(unassigned, key=lambda idx: working.at[idx,"projected_ro"])
        cluster_members = [seed]
        unassigned.remove(seed)
        cluster_total = working.at[seed,"projected_ro"]
        # compute centroid (weighted by RO)
        centroid_lat = working.at[seed,"lat"]
        centroid_lon = working.at[seed,"lon"]
        while cluster_total < max_ro and unassigned:
            # find nearest unassigned index to current centroid
            nearest = min(unassigned, key=lambda idx: haversine_km(centroid_lat, centroid_lon, working.at[idx,"lat"], working.at[idx,"lon"]))
            # add it
            cluster_members.append(nearest)
            unassigned.remove(nearest)
            cluster_total += working.at[nearest,"projected_ro"]
            # update centroid weighted by projected_ro
            weights = working.loc[cluster_members,"projected_ro"].values
            lats = working.loc[cluster_members,"lat"].values
            lons = working.loc[cluster_members,"lon"].values
            if weights.sum() > 0:
                centroid_lat = (lats * weights).sum() / weights.sum()
                centroid_lon = (lons * weights).sum() / weights.sum()
            else:
                centroid_lat = lats.mean()
                centroid_lon = lons.mean()
        members_df = working.loc[cluster_members].copy().reset_index(drop=True)
        clusters.append({
            "members": members_df,
            "total_ro": float(cluster_total),
            "centroid": (float(centroid_lat), float(centroid_lon))
        })
    return clusters

def find_centroid_pincode(members_df, centroid):
    """
    Given members DataFrame (with pincode, lat, lon), and centroid (lat,lon),
    return pincode of member closest to centroid and its coords.
    """
    if members_df.empty:
        return None, None, None
    distances = members_df.apply(lambda r: haversine_km(centroid[0], centroid[1], r["lat"], r["lon"]), axis=1)
    idx = distances.idxmin()
    row = members_df.loc[idx]
    return row.get("pincode"), float(row.get("lat")), float(row.get("lon"))

def nearest_distance_to_workshops(lat, lon, workshops_df):
    """
    Return distance in km from (lat,lon) to nearest workshop in workshops_df (columns lat, lon).
    If workshops_df empty, return a large number.
    """
    if workshops_df.empty:
        return float("inf")
    dists = workshops_df.apply(lambda r: haversine_km(lat, lon, r["lat"], r["lon"]), axis=1)
    return float(dists.min())