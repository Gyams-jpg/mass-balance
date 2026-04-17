
import os
import io
import json
import zipfile
import shutil
import tempfile
import traceback
import contextlib
import base64
import textwrap
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Glacier Mass Balance Calculation", layout="wide")

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"

def image_to_data_uri(path):
    path = Path(path)
    if not path.exists():
        return ""
    suffix = path.suffix.lower().replace(".", "")
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/{mime};base64,{data}"

top_banner_uri = image_to_data_uri(ASSETS_DIR / "logo.jpg")
bg_uri = image_to_data_uri(ASSETS_DIR / "glacier_background.png")

banner_html = textwrap.dedent(f"""
<style>
.hero-wrap {{
    border-radius: 28px;
    overflow: hidden;
    margin-bottom: 1rem;
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow: 0 12px 32px rgba(0,0,0,0.18);
}}
.hero-top-banner {{
    background: #ffffff;
}}
.hero-top-banner img {{
    display: block;
    width: 100%;
    height: auto;
}}
.hero-main {{
    min-height: 470px;
    background-image:
        linear-gradient(rgba(8,20,45,0.20), rgba(8,20,45,0.62)),
        url('{bg_uri}');
    background-size: cover;
    background-position: center;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 42px;
}}
.hero-card {{
    width: min(1260px, 86%);
    background: rgba(20,30,45,0.34);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 30px;
    padding: 52px 40px;
    text-align: center;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    box-shadow: 0 18px 40px rgba(0,0,0,0.18);
}}
.hero-card h1 {{
    margin: 0;
    font-size: 4rem;
    color: white;
    font-weight: 800;
}}
.hero-card p {{
    margin-top: 22px;
    font-size: 1.3rem;
    color: rgba(255,255,255,0.94);
}}
.hero-note {{
    margin-top: 16px;
    background: rgba(49,99,190,0.18);
    color: #79b0ff;
    border-radius: 14px;
    padding: 18px 20px;
    font-size: 1rem;
}}
</style>

<div class="hero-wrap">
    <div class="hero-top-banner">
        <img src="{top_banner_uri}">
    </div>
    <div class="hero-main">
        <div class="hero-card">
            <h1>Glacier Mass Balance Calculation</h1>
            <p>Cryosphere Services Division - Glacier mass balance notebook workflow.</p>
        </div>
    </div>
</div>

<div class="hero-note">
    This app is script based glacier mass balance workflow:
    IDW interpolation → DEM bias correction → glacier-clipped hypsometry
    → nearest-point differencing → optional snow correction
    → amb and uncertainty summary.
</div>
""")

st.markdown(banner_html, unsafe_allow_html=True)

NOTEBOOK_CELLS = json.loads('["# Import necessary modules\\n\\nimport os\\nimport numpy as np\\nimport matplotlib.pyplot as plt\\nimport pandas as pd\\nimport geopandas as gpd\\nfrom shapely.geometry import Point\\nimport geopandas as gpd\\nimport rasterio\\nfrom rasterio.mask import mask\\nfrom sklearn.linear_model import TheilSenRegressor\\nfrom shapely.geometry import Point, LineString, MultiLineString", "import pandas as pd\\nimport numpy as np\\nfrom scipy.spatial import cKDTree\\n\\n# -----------------------------\\n# 1. Paths & parameters\\n# -----------------------------\\n# csv_path_1 provided by Streamlit\\n# gdf_1 provided by Streamlit\\n\\n# Column names in your CSV (edit if needed)\\nx_col = \\"Longitude\\"      # UTM Easting in your file\\ny_col = \\"Latitude\\"       # UTM Northing in your file\\nz_col = \\"Elevation\\"      # Elevation\\n\\ncell_size = 1.0          # 1 m grid\\nsearch_radius = 0.7      # in metres (UTM)\\npower = 2                # IDW power\\n\\n# -----------------------------\\n# 2. Read CSV\\n# -----------------------------\\ndf = pd.read_csv(csv_path_1)\\n\\nif not set([x_col, y_col, z_col]).issubset(df.columns):\\n    raise ValueError(f\\"CSV must contain {x_col}, {y_col}, {z_col} columns. \\"\\n                     f\\"Found: {list(df.columns)}\\")\\n\\nx = df[x_col].to_numpy(dtype=float)\\ny = df[y_col].to_numpy(dtype=float)\\nz = df[z_col].to_numpy(dtype=float)\\n\\n# Drop NaNs if any\\nvalid_mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)\\nx = x[valid_mask]\\ny = y[valid_mask]\\nz = z[valid_mask]\\n\\nif x.size == 0:\\n    raise ValueError(\\"No valid points after removing NaNs. Check your CSV.\\")\\n\\n# -----------------------------\\n# 3. Build 1 m grid (UTM)\\n# -----------------------------\\nminx, maxx = x.min(), x.max()\\nminy, maxy = y.min(), y.max()\\n\\npad = cell_size * 0.5\\nminx -= pad\\nminy -= pad\\nmaxx += pad\\nmaxy += pad\\n\\nif maxx <= minx or maxy <= miny:\\n    raise ValueError(\\n        f\\"Invalid bounds: minx={minx}, maxx={maxx}, miny={miny}, maxy={maxy}\\"\\n    )\\n\\ngrid_x = np.arange(minx, maxx, cell_size)\\ngrid_y = np.arange(miny, maxy, cell_size)\\n\\ngrid_xx, grid_yy = np.meshgrid(grid_x, grid_y)\\ngrid_points = np.vstack((grid_xx.ravel(), grid_yy.ravel())).T\\n\\n# -----------------------------\\n# 4. IDW interpolation (in UTM)\\n# -----------------------------\\ntree = cKDTree(np.vstack((x, y)).T)\\nneighbors_idx = tree.query_ball_point(grid_points, r=search_radius)\\n\\ninterp_z = np.full(grid_points.shape[0], np.nan, dtype=float)\\n\\nfor i, idx_list in enumerate(neighbors_idx):\\n    if len(idx_list) == 0:\\n        continue  # no neighbors within radius\\n\\n    x_neighbors = x[idx_list]\\n    y_neighbors = y[idx_list]\\n    z_neighbors = z[idx_list]\\n\\n    dx = x_neighbors - grid_points[i, 0]\\n    dy = y_neighbors - grid_points[i, 1]\\n    d = np.sqrt(dx**2 + dy**2)\\n\\n    # Exact sample point -> copy value\\n    zero_mask = d == 0\\n    if np.any(zero_mask):\\n        interp_z[i] = z_neighbors[zero_mask][0]\\n        continue\\n\\n    w = 1.0 / (d**power)\\n    interp_z[i] = np.sum(w * z_neighbors) / np.sum(w)\\n\\n# -----------------------------\\n# 5. Build output table (UTM 45N)\\n# -----------------------------\\nvalid = ~np.isnan(interp_z)\\ngrid_valid = grid_points[valid]\\nz_valid = interp_z[valid]\\n\\nutm_x = grid_valid[:, 0]\\nutm_y = grid_valid[:, 1]\\n\\nout_df = pd.DataFrame({\\n    \\"Point_id\\": np.arange(1, len(z_valid) + 1),\\n    \\"Latitude\\": utm_y,      # UTM 45N Easting\\n    \\"Longitude\\": utm_x ,    # UTM 45N Northing\\n    \\"Elevation\\": z_valid\\n})\\nfinal_df = out_df.sort_values(\'Elevation\', ascending = False)\\nfinal_df[\'sorted_order\'] = np.arange(1, len(final_df) + 1)\\nfinal_df.to_csv(gdf_1, index=False)\\nprint(f\\"Saved interpolated UTM points to: {gdf_1}\\")\\nprint(final_df.head())", "import pandas as pd\\nimport numpy as np\\nfrom scipy.spatial import cKDTree\\n\\n# -----------------------------\\n# 1. Paths & parameters\\n# -----------------------------\\n# csv_path_2 provided by Streamlit\\n# gdf_2 provided by Streamlit\\n\\n# Column names in your CSV (edit if needed)\\nx_col = \\"Longitude\\"      # UTM Easting in your file\\ny_col = \\"Latitude\\"       # UTM Northing in your file\\nz_col = \\"Elevation\\"      # Elevation\\n\\ncell_size = 1.0          # 1 m grid\\nsearch_radius = 0.7      # in metres (UTM)\\npower = 2                # IDW power\\n\\n# -----------------------------\\n# 2. Read CSV\\n# -----------------------------\\ndf = pd.read_csv(csv_path_2)\\n\\nif not set([x_col, y_col, z_col]).issubset(df.columns):\\n    raise ValueError(f\\"CSV must contain {x_col}, {y_col}, {z_col} columns. \\"\\n                     f\\"Found: {list(df.columns)}\\")\\n\\nx = df[x_col].to_numpy(dtype=float)\\ny = df[y_col].to_numpy(dtype=float)\\nz = df[z_col].to_numpy(dtype=float)\\n\\n# Drop NaNs if any\\nvalid_mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)\\nx = x[valid_mask]\\ny = y[valid_mask]\\nz = z[valid_mask]\\n\\nif x.size == 0:\\n    raise ValueError(\\"No valid points after removing NaNs. Check your CSV.\\")\\n\\n# -----------------------------\\n# 3. Build 1 m grid (UTM)\\n# -----------------------------\\nminx, maxx = x.min(), x.max()\\nminy, maxy = y.min(), y.max()\\n\\npad = cell_size * 0.5\\nminx -= pad\\nminy -= pad\\nmaxx += pad\\nmaxy += pad\\n\\nif maxx <= minx or maxy <= miny:\\n    raise ValueError(\\n        f\\"Invalid bounds: minx={minx}, maxx={maxx}, miny={miny}, maxy={maxy}\\"\\n    )\\n\\ngrid_x = np.arange(minx, maxx, cell_size)\\ngrid_y = np.arange(miny, maxy, cell_size)\\n\\ngrid_xx, grid_yy = np.meshgrid(grid_x, grid_y)\\ngrid_points = np.vstack((grid_xx.ravel(), grid_yy.ravel())).T\\n\\n# -----------------------------\\n# 4. IDW interpolation (in UTM)\\n# -----------------------------\\ntree = cKDTree(np.vstack((x, y)).T)\\nneighbors_idx = tree.query_ball_point(grid_points, r=search_radius)\\n\\ninterp_z = np.full(grid_points.shape[0], np.nan, dtype=float)\\n\\nfor i, idx_list in enumerate(neighbors_idx):\\n    if len(idx_list) == 0:\\n        continue  # no neighbors within radius\\n\\n    x_neighbors = x[idx_list]\\n    y_neighbors = y[idx_list]\\n    z_neighbors = z[idx_list]\\n\\n    dx = x_neighbors - grid_points[i, 0]\\n    dy = y_neighbors - grid_points[i, 1]\\n    d = np.sqrt(dx**2 + dy**2)\\n\\n    # Exact sample point -> copy value\\n    zero_mask = d == 0\\n    if np.any(zero_mask):\\n        interp_z[i] = z_neighbors[zero_mask][0]\\n        continue\\n\\n    w = 1.0 / (d**power)\\n    interp_z[i] = np.sum(w * z_neighbors) / np.sum(w)\\n\\n# -----------------------------\\n# 5. Build output table (UTM 45N)\\n# -----------------------------\\nvalid = ~np.isnan(interp_z)\\ngrid_valid = grid_points[valid]\\nz_valid = interp_z[valid]\\n\\nutm_x = grid_valid[:, 0]\\nutm_y = grid_valid[:, 1]\\n\\nout_df = pd.DataFrame({\\n    \\"Point_id\\": np.arange(1, len(z_valid) + 1),\\n    \\"Latitude\\": utm_y,      # UTM 45N Easting\\n    \\"Longitude\\": utm_x ,    # UTM 45N Northing\\n    \\"Elevation\\": z_valid\\n})\\nfinal_df_1 = out_df.sort_values(\'Elevation\', ascending = False)\\n\\nfinal_df_1[\'sorted_order\'] = np.arange(1, len(final_df_1) + 1)\\n\\nfinal_df_1.to_csv(gdf_2, index=False)\\nprint(f\\"Saved interpolated UTM points to: {gdf_2}\\")\\nprint(final_df_1.head())", "\\"\\"\\"Only this section needs u\\"\\"\\"\\n# gdf1 = \\"/mnt/d/NCHM_Data/tracks/Gangju la_2024_01.csv\\" # New csv file (e.g., 2024) path\\n# gdf2 = \\"/mnt/d/NCHM_Data/tracks/Gangju_La_rawdata_2023.csv\\" # Old csv file (e.g., 2023) path\\n\\n# merged_gdf[\'elev_diff\'] = merged_gdf[\'Elevation_left\'] - merged_gdf[\'Elevation_right\'] # e.g., 5m (2023)  2m in (2024): 2m - 5m\\n\\ngdf11 = gdf_1\\ngdf22 = gdf_2\\n\\n# raster_file provided by Streamlit\\n# glacier_shp_path provided by Streamlit\\n\\n\\n\\"\\"\\"Snow depth data at stakes\\"\\"\\"\\n\\n# snd1 provided by Streamlit\\n# snd2 provided by Streamlit\\n\\n\\"\\"\\"Change if necessary\\"\\"\\"\\n\\n# distance_threshold provided by Streamlit\\n# corrected_dem_name provided by Streamlit\\n# output_clipped_dem_name provided by Streamlit\\n# corrected_dem_name_old provided by Streamlit\\n# output_clipped_dem_name_old provided by Streamlit", "\\n\\nif snd1 is not None and os.path.exists(snd1):\\n    snd11 = pd.read_csv(snd1)\\nelse:\\n    print(\\"snd1 not provided or file missing\\")\\n\\nif snd2 is not None and os.path.exists(snd2):\\n    snd22 = pd.read_csv(snd2)\\nelse:\\n    print(\\"snd2 not provided or file missing\\")\\n\\nif snd1 is not None:\\n    print(snd11.head(3))\\n\\nif snd2 is not None:\\n    print(snd22.head(3))", "master_path = os.path.split(raster_file)[0]\\ncorrected_dem = os.path.join(master_path, corrected_dem_name)  \\noutput_clipped_dem = os.path.join(master_path, output_clipped_dem_name)  \\ncorrected_dem1 = os.path.join(master_path, corrected_dem_name_old)  \\noutput_clipped_dem1 = os.path.join(master_path, output_clipped_dem_name_old)\\ngdf1 = pd.read_csv(gdf11) # 2024 # Left\\ngdf2 = pd.read_csv(gdf22) # 2023 # Right\\ngdf2.head(3)", "gdf1[\'geometry\'] = gdf1.apply(lambda row: Point(row.iloc[2], row.iloc[1]), axis=1)\\ngdf2[\'geometry\'] = gdf2.apply(lambda row: Point(row.iloc[2], row.iloc[1]), axis=1)\\n\\ngeo_gdf1 = gpd.GeoDataFrame(gdf1, geometry=\'geometry\', crs=\\"EPSG:32646\\") # 2024\\ngeo_gdf2 = gpd.GeoDataFrame(gdf2, geometry=\'geometry\', crs=\\"EPSG:32646\\") # 2023", "geo_gdf1", "glacier_gdf_01 = gpd.read_file(glacier_shp_path)\\nfig, ax = plt.subplots(figsize=(10, 12))  # Adjust figure size for higher resolution\\nglacier_gdf_01.plot(ax=ax,facecolor=\'none\',edgecolor=\'black\',linewidth=1.5,label=\\"Glacier boundary\\")\\n\\ngeo_gdf1.plot(ax=ax, color=\'blue\', alpha=0.6, markersize=30, label=\\"2025 dGPS survey track\\")  # Customize style for geo_gdf1\\ngeo_gdf2.plot(ax=ax, color=\'red\', alpha=0.6, markersize=30, label= \\"2024 dGPS survey track\\")  # Customize style for geo_gdf2\\n\\n# Add labels and legend\\nax.set_xlabel(\\"Easting (m)\\", fontsize=12)\\nax.set_ylabel(\\"Northing (m)\\", fontsize=12)\\nax.legend(fontsize=12, loc=\\"upper left\\")\\n\\nax.grid(visible=True, linestyle=\'--\', alpha=0.5)\\n\\n# Improve axis style\\nax.tick_params(axis=\'both\', labelsize=10)\\nplt.tight_layout()\\nplt.show()", "import matplotlib.patches as mpatches\\n\\nglacier_gdf_01 = gpd.read_file(glacier_shp_path)\\nfig, ax = plt.subplots(figsize=(8, 12))  # Adjust figure size\\n\\n# Plot glacier boundary (transparent fill)\\nglacier_gdf_01.plot(ax=ax, facecolor=\'none\', edgecolor=\'black\', linewidth=1.5)\\n\\n# Plot dGPS tracks\\ngeo_gdf1.plot(ax=ax, color=\'blue\', alpha=0.6, markersize=30, label=\\"2025 dGPS survey track\\")\\ngeo_gdf2.plot(ax=ax, color=\'red\', alpha=0.6, markersize=30, label=\\"2024 dGPS survey track\\")\\n\\n# Create manual legend patch for glacier boundary\\nboundary_patch = mpatches.Patch(facecolor=\'none\', edgecolor=\'black\', linewidth=1.5, label=\'Glacier boundary\')\\n\\n# Get existing legend handles (from tracks) and add boundary patch\\nhandles, labels = ax.get_legend_handles_labels()\\nhandles.append(boundary_patch)\\n\\n# Add legend\\nax.legend(handles=handles, loc=\\"upper left\\")\\n\\n# Labels, grid, ticks\\nax.set_xlabel(\\"Easting (m)\\")\\nax.set_ylabel(\\"Northing (m)\\")\\nax.grid(visible=True, linestyle=\'--\', alpha=0.5)\\nax.tick_params(axis=\'both\', labelsize=10)\\n\\nplt.tight_layout()\\nplt.savefig(os.path.join(output_dir, \\"dGPS_with_boundary.png\\"), dpi=300)\\nplt.show()", "coordinates = [(point.x, point.y) for point in geo_gdf1.geometry]\\nwith rasterio.open(raster_file ) as src:\\n    raster_values = list(src.sample(coordinates))\\n    geo_gdf1[\'raster_raw_value\'] = [val[0] for val in raster_values]\\n\\n    geo_gdf1[\'dgps_dem_diff\'] = np.abs(geo_gdf1[\'raster_raw_value\']-geo_gdf1[\'Elevation\'])\\n    dgps_dem_diff_avg = np.mean(geo_gdf1[\'dgps_dem_diff\']) # Bias correction approach using mean difference\\n\\n    from rasterio.plot import show\\n    fig, ax = plt.subplots()\\n    # transform rasterio plot to real world coords\\n    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]\\n    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap=\\"pink\\")\\n    geo_gdf1.plot(ax=ax)\\n    ax.set_title(\'Raw Dem\')\\n    profile = src.profile\\n    data = src.read(1) \\n\\n    corrected_dem_arr = data - dgps_dem_diff_avg\\n\\n    profile.update(dtype=\'float32\')  \\n\\nwith rasterio.open(corrected_dem, \\"w\\", **profile) as dst:\\n    dst.write(corrected_dem_arr.astype(\'float32\'), 1)\\n\\nwith rasterio.open(corrected_dem) as src:\\n    raster_values = list(src.sample(coordinates))\\n    geo_gdf1[\'raster_corr_value\'] = [val[0] for val in raster_values]\\n\\n    from rasterio.plot import show\\n    fig, ax = plt.subplots()\\n    # transform rasterio plot to real world coords\\n    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]\\n    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap=\\"pink\\")\\n    ax.set_title(\'Corr Dem\')\\n    geo_gdf1.plot(ax=ax)", "geo_gdf2.head(3)", "fig, ax = plt.subplots()\\nplt.plot( geo_gdf1[\'sorted_order\'],geo_gdf1[\'Elevation\'], label=\'dGPS\')\\nplt.plot( geo_gdf1[\'sorted_order\'],geo_gdf1[\'raster_raw_value\'], label=\'DEM-Sat-Raw\')\\nplt.legend()\\nplt.tight_layout\\nplt.savefig(os.path.join(output_dir, \\"difference_dem.png\\"),dpi=300)\\nplt.show()", "geo_gdf1[\'dem_corr\'] = geo_gdf1[\'raster_raw_value\'] - dgps_dem_diff_avg\\n\\nfig, ax = plt.subplots()\\nplt.plot(geo_gdf1[\'sorted_order\'],geo_gdf1[\'dgps_dem_diff\'])\\nplt.show()\\n\\nfig, ax = plt.subplots()\\nplt.plot(geo_gdf1[\'sorted_order\'],geo_gdf1[\'Elevation\'], label=\'dGPS\')\\nplt.plot(geo_gdf1[\'sorted_order\'],geo_gdf1[\'raster_corr_value\'], label=\'DEM-Sat-Correct\')\\nplt.legend()\\nplt.tight_layout()\\nplt.savefig(os.path.join(output_dir, \\"corrected_Dem.png\\"),dpi=300)\\nplt.show()\\n\\nfig, ax = plt.subplots()\\nplt.hist(geo_gdf1[\'dgps_dem_diff\'], bins=50)\\nplt.axvline(dgps_dem_diff_avg, color=\'red\', ls=\'--\', lw=2)\\nplt.show()", "# Step 1: Clip the Corrected DEM with the glacier outline\\nfrom rasterio.mask import mask\\ndef clip_dem(dem_path, glacier_shp_path, output_clipped_dem):\\n    # Load glacier shapefile\\n    glacier_gdf = gpd.read_file(glacier_shp_path)\\n    # Open the DEM\\n    with rasterio.open(dem_path) as dem_src:\\n        # Mask DEM with glacier geometry\\n        glacier_geometry = glacier_gdf.geometry\\n        clipped_dem, clipped_transform = mask(dem_src, glacier_geometry, crop=True)\\n        clipped_meta = dem_src.meta.copy()\\n\\n        # Update metadata for the clipped DEM\\n        clipped_meta.update({\\n            \\"driver\\": \\"GTiff\\",\\n            \\"height\\": clipped_dem.shape[1],\\n            \\"width\\": clipped_dem.shape[2],\\n            \\"transform\\": clipped_transform\\n        })\\n\\n        # Save the clipped DEM\\n        with rasterio.open(output_clipped_dem, \\"w\\", **clipped_meta) as dest:\\n            dest.write(clipped_dem)\\n    return output_clipped_dem\\n\\n# Step 2: Classify elevations and calculate area in each class\\ndef classify_and_calculate_area(path, elevation_interval=50):\\n    with rasterio.open(path) as src:\\n        dem_data = src.read(1)\\n        dem_data = dem_data[dem_data > 0]  # Filter out no-data values\\n        pixel_area = abs(src.transform[0] * src.transform[4])  # Calculate pixel area\\n\\n    # Classify elevations\\n    min_elevation = int(np.floor(dem_data.min()))\\n    max_elevation = int(np.ceil(dem_data.max()))\\n    \\n    bins = np.arange(min_elevation, max_elevation + elevation_interval, elevation_interval)\\n    print(bins)\\n    elevation_classes = np.digitize(dem_data, bins)\\n    print(elevation_classes)\\n\\n    # Calculate area for each elevation class\\n    area_per_class = []\\n    for i in range(1, len(bins)):\\n        area = (elevation_classes == i).sum() * pixel_area\\n        area_per_class.append(area)\\n    print(area_per_class)\\n\\n    return bins, area_per_class\\n\\ndef plot_elevation_vs_area(bins, area_per_class):\\n    mid_bins = (bins[:-1] + bins[1:]) / 2\\n    plt.figure()\\n    plt.barh(\\n        mid_bins, \\n        area_per_class, \\n        height=30,\\n        color=\\"skyblue\\",  \\n        edgecolor=\\"black\\", \\n        alpha=0.9\\n    )\\n    plt.xlabel(\\"Area (m\\u00b2)\\", fontsize=12)\\n    plt.ylabel(\\"Elevation (m)\\", fontsize=12)\\n    plt.grid(axis=\'x\', linestyle=\'--\', alpha=0.6)\\n    plt.xticks(fontsize=12)\\n    plt.yticks(mid_bins,fontsize=12)\\n    plt.tight_layout()\\n    plt.savefig(os.path.join(output_dir, \\"hypsometry.png\\"),dpi=450)\\n    plt.show()\\n    return mid_bins\\n\\nclipped_dem = clip_dem(corrected_dem, glacier_shp_path, output_clipped_dem)\\nprint(corrected_dem, output_clipped_dem)\\nelev_bins, area_per_class = classify_and_calculate_area(output_clipped_dem, elevation_interval=50)\\nmid_bins = plot_elevation_vs_area(elev_bins, area_per_class)\\nprint(\'Mid Bins\', mid_bins)\\nprint(area_per_class)", "coordinates = [(point.x, point.y) for point in geo_gdf2.geometry]\\nwith rasterio.open(raster_file ) as src:\\n    raster_values = list(src.sample(coordinates))\\n    geo_gdf2[\'raster_raw_value\'] = [val[0] for val in raster_values]\\n\\n    geo_gdf2[\'dgps_dem_diff\'] = np.abs(geo_gdf2[\'raster_raw_value\']-geo_gdf2[\'Elevation\'])\\n    dgps_dem_diff_avg1 = np.mean(geo_gdf2[\'dgps_dem_diff\']) # Bias correction approach using mean difference\\n\\n    from rasterio.plot import show\\n    fig, ax = plt.subplots()\\n    # transform rasterio plot to real world coords\\n    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]\\n    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap=\\"pink\\")\\n    geo_gdf2.plot(ax=ax)\\n    ax.set_title(\'Raw Dem\')\\n    profile = src.profile\\n    data = src.read(1) \\n\\n    corrected_dem_arr1 = data - dgps_dem_diff_avg1\\n\\n    profile.update(dtype=\'float32\')  \\n\\nwith rasterio.open(corrected_dem1, \\"w\\", **profile) as dst:\\n    dst.write(corrected_dem_arr1.astype(\'float32\'), 1)\\n\\nwith rasterio.open(corrected_dem1) as src:\\n    raster_values = list(src.sample(coordinates))\\n    geo_gdf2[\'raster_corr_value\'] = [val[0] for val in raster_values]\\n\\n    from rasterio.plot import show\\n    fig, ax = plt.subplots()\\n    # transform rasterio plot to real world coords\\n    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]\\n    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap=\\"pink\\")\\n    ax.set_title(\'Corr Dem\')\\n    geo_gdf2.plot(ax=ax)", "geo_gdf2[\'dem_corr\'] = geo_gdf2[\'raster_raw_value\'] - dgps_dem_diff_avg1\\n\\nfig, ax = plt.subplots()\\nplt.plot(geo_gdf2[\'sorted_order\'],geo_gdf2[\'dgps_dem_diff\'])\\nplt.show()\\n\\nfig, ax = plt.subplots()\\nplt.plot(geo_gdf2[\'Elevation\'], label=\'dGPS\')\\nplt.plot(geo_gdf2[\'raster_corr_value\'], label=\'DEM-Sat-Correct\')\\nplt.legend()\\nplt.show()\\n\\nfig, ax = plt.subplots()\\nplt.hist(geo_gdf2[\'dgps_dem_diff\'], bins=50)\\nplt.axvline(dgps_dem_diff_avg1, color=\'red\', ls=\'--\', lw=2)", "# Step 1: Clip the Corrected DEM with the glacier outline\\nfrom rasterio.mask import mask\\ndef clip_dem(dem_path, glacier_shp_path, output_clipped_dem1):\\n    # Load glacier shapefile\\n    glacier_gdf2 = gpd.read_file(glacier_shp_path)\\n    # Open the DEM\\n    with rasterio.open(dem_path) as dem_src:\\n        # Mask DEM with glacier geometry\\n        glacier_geometry2 = glacier_gdf2.geometry\\n        clipped_dem1, clipped_transform = mask(dem_src, glacier_geometry2, crop=True)\\n        clipped_meta1 = dem_src.meta.copy()\\n\\n        # Update metadata for the clipped DEM\\n        clipped_meta1.update({\\n            \\"driver\\": \\"GTiff\\",\\n            \\"height\\": clipped_dem1.shape[1],\\n            \\"width\\": clipped_dem1.shape[2],\\n            \\"transform\\": clipped_transform\\n        })\\n\\n        # Save the clipped DEM\\n        with rasterio.open(output_clipped_dem1, \\"w\\", **clipped_meta1) as dest:\\n            dest.write(clipped_dem1)\\n    return output_clipped_dem1\\n\\n# Step 2: Classify elevations and calculate area in each class\\ndef classify_and_calculate_area(path, elevation_interval=50):\\n    with rasterio.open(path) as src:\\n        dem_data = src.read(1)\\n        dem_data = dem_data[dem_data > 0]  # Filter out no-data values\\n        pixel_area = abs(src.transform[0] * src.transform[4])  # Calculate pixel area\\n\\n    # Classify elevations\\n    min_elevation = elev_bins[0]\\n    max_elevation = elev_bins[-1]\\n    \\n    bins = np.arange(min_elevation, max_elevation + elevation_interval, elevation_interval)\\n    print(bins)\\n    elevation_classes = np.digitize(dem_data, bins)\\n    print(elevation_classes)\\n\\n    # Calculate area for each elevation class\\n    area_per_class1 = []\\n    for i in range(1, len(bins)):\\n        area1 = (elevation_classes == i).sum() * pixel_area\\n        area_per_class1.append(area1)\\n    print(area_per_class1)\\n\\n    return bins, area_per_class1\\n\\ndef plot_elevation_vs_area(bins, area_per_class1):\\n    mid_bins = (bins[:-1] + bins[1:]) / 2\\n    plt.figure()\\n    plt.barh(\\n        mid_bins, \\n        area_per_class1, \\n        height=30,\\n        color=\\"skyblue\\",  \\n        edgecolor=\\"black\\", \\n        alpha=0.9\\n    )\\n    plt.xlabel(\\"Area (m\\u00b2)\\", fontsize=12)\\n    plt.ylabel(\\"Elevation (m)\\", fontsize=12)\\n    plt.grid(axis=\'x\', linestyle=\'--\', alpha=0.6)\\n    plt.xticks(fontsize=12)\\n    plt.yticks(mid_bins,fontsize=12)\\n    plt.tight_layout()\\n    plt.savefig(os.path.join(output_dir, \\"hypsometry.png\\"),dpi=450)\\n    plt.show()\\n    return mid_bins\\n\\nclipped_dem1 = clip_dem(corrected_dem1, glacier_shp_path, output_clipped_dem1)\\nprint(corrected_dem1, output_clipped_dem1)\\nelev_bins, area_per_class1 = classify_and_calculate_area(output_clipped_dem1, elevation_interval=50)\\nmid_bins = plot_elevation_vs_area(elev_bins, area_per_class1)\\nprint(\'Mid Bins\', mid_bins)\\nprint(area_per_class1)", "def plot_hypsometry_comparison(bins_a, area_a, bins_b, area_b,\\n                              label_a=\\"DEM A\\", label_b=\\"DEM B\\"):\\n    # --- If bins differ, restrict to their common range ---\\n    if not np.array_equal(bins_a, bins_b):\\n        raise ValueError(\\"Elevation bins differ between the two datasets. \\"\\n                        \\"Re-bin them to a common set before plotting.\\")\\n\\n    # Mid-points for elevation bands\\n    mid_bins = (bins_a[:-1] + bins_a[1:]) / 2\\n    bar_height = int(bins_a[1] - bins_a[0])  # should be 50 m\\n\\n    plt.figure(figsize=(8, 6))\\n\\n    # Calculate bar dimensions for perfect stacking\\n    bar_height_half = bar_height * 0.4\\n    offset = bar_height_half  # Offset for the second bar\\n\\n    # First dataset - top half\\n    plt.barh(\\n        mid_bins + offset/2,  # Position in the top half\\n        area_a,\\n        height=bar_height_half,  # Half the total height\\n        color=\\"skyblue\\",\\n        edgecolor=\\"black\\",\\n        alpha=0.8,\\n        label=label_a,\\n    )\\n\\n    # Second dataset - bottom half\\n    plt.barh(\\n        mid_bins - offset/2,  # Position in the bottom half\\n        area_b,\\n        height=bar_height_half,  # Half the total height\\n        color=\\"blue\\",\\n        edgecolor=\\"black\\",\\n        alpha=0.5,\\n        label=label_b,\\n        linewidth=1\\n    )\\n\\n    plt.xlabel(\\"Area (m\\u00b2)\\", fontsize=12)\\n    plt.ylabel(\\"Elevation (m)\\", fontsize=12)\\n\\n    # y-axis ticks exactly at the centre of the combined bars\\n    plt.yticks(mid_bins, labels=mid_bins.astype(int), fontsize=12)\\n\\n\\n    # Grid only in x direction, alpha 0.5\\n    plt.grid(axis=\\"x\\", linestyle=\\"--\\", alpha=0.5)\\n\\n    plt.xticks(np.round(plt.xticks()[0]).astype(int))\\n    plt.legend(fontsize=11)\\n    plt.tight_layout()\\n\\n    plt.show()", "# Old / auto-binned\\nelev_bins, area_per_class = classify_and_calculate_area(output_clipped_dem, elevation_interval=50)\\n\\n# New / fixed 4873\\u20135173\\nelev_bins1, area_per_class1 = classify_and_calculate_area(output_clipped_dem1, elevation_interval=50)\\n\\n# Plot comparison\\nplot_hypsometry_comparison(\\n    elev_bins,\\n    area_per_class,\\n    elev_bins1,\\n    area_per_class1,\\n    label_a=\\"2025\\",\\n    label_b=\\"2024\\"\\n)", "# Perform the nearest spatial join with a max distance of 50 meters\\nmerged_gdf = gpd.sjoin_nearest(\\n    geo_gdf1, \\n    geo_gdf2, \\n    how=\\"inner\\", \\n    distance_col=\\"nearest_distance\\", \\n    max_distance=50\\n)\\nmerged_gdf.head(3)", "merged_gdf.shape", "fig, ax = plt.subplots()\\nax.scatter(\\n    merged_gdf[\'nearest_distance\'], \\n    merged_gdf[\'Elevation_right\'], \\n    color=\'darkblue\', \\n    # edgecolor=\'black\', \\n    alpha=0.8, \\n    s=20,\\n)\\nax.set_xlabel(\'Merged distance (m)\', fontsize=12)\\nax.set_ylabel(\'Elevation (m)\', fontsize=12)\\nax.grid(linestyle=\'--\', alpha=0.6)\\nax.tick_params(axis=\'both\', labelsize=12)\\nplt.tight_layout()\\nplt.show()", "fig, ax = plt.subplots()\\nax.plot(\\n    range(merged_gdf[\'raster_corr_value_left\'].shape[0]), \\n    merged_gdf[\'raster_corr_value_left\'], \\n    label=\'DEM-Sat\', \\n    color=\'blue\', \\n    linewidth=2, \\n    linestyle=\'-\'\\n)\\nax.plot(\\n    range(merged_gdf[\'Elevation_left\'].shape[0]), \\n    merged_gdf[\'Elevation_left\'], \\n    label=\'dGPS 2024\', \\n    color=\'green\', \\n    linewidth=2, \\n    linestyle=\'--\'\\n)\\nax.plot(\\n    range(merged_gdf[\'Elevation_right\'].shape[0]), \\n    merged_gdf[\'Elevation_right\'], \\n    label=\'dGPS 2023\', \\n    color=\'red\', \\n    linewidth=2, \\n    linestyle=\':\'\\n)\\nax.legend(\\n    fontsize=12, \\n    loc=\'best\', \\n    frameon=True, \\n    framealpha=0.8, \\n    edgecolor=\'black\'\\n)\\nax.set_xlabel(\'Smaples\', fontsize=12)\\nax.set_ylabel(\'Elevation Values (m)\', fontsize=12)\\nax.grid(linestyle=\'--\', alpha=0.6)\\nax.tick_params(axis=\'both\', labelsize=12)\\nplt.tight_layout()\\nplt.show()", "merged_gdf[\'elev_diff\'] = merged_gdf[\'Elevation_left\'] - merged_gdf[\'Elevation_right\'] # e.g., 5m (2023)  2m in (2024): 2m - 5m\\ngdf_threshold = merged_gdf[(merged_gdf[\'nearest_distance\'] <= distance_threshold) & (merged_gdf[\'elev_diff\'] != 0)]\\ngdf_threshold.head(3)\\nprint(gdf_threshold.shape)", "x_elev = gdf_threshold[\'Elevation_left\'].astype(float).values.reshape(-1, 1)\\ny_diff = gdf_threshold[\'elev_diff\'].values\\ntheil_sen_non_agg = TheilSenRegressor(random_state=42).fit(x_elev, y_diff)\\npred_diff_values = theil_sen_non_agg.predict(x_elev)\\n\\nplt.figure()\\nplt.scatter(\\n    gdf_threshold[\'Elevation_left\'],\\n    y_diff,\\n    color=\'royalblue\', \\n    edgecolor=\'black\', \\n    alpha=0.7, \\n    label=\'Data points\'\\n)\\nplt.plot(\\n    gdf_threshold[\'Elevation_left\'],\\n    pred_diff_values,\\n    color=\'darkred\', \\n    linewidth=2, \\n    linestyle=\'--\', \\n    label=\'Theil-Sen regression line\'\\n)\\n\\nplt.ylabel(\'Elevation difference (m)\', fontsize=12)\\nplt.xlabel(\'Elevation (m)\', fontsize=12)\\nplt.legend(fontsize=12, loc=\'best\')\\n\\nplt.grid(linestyle=\'--\', alpha=0.6)\\nplt.xticks(fontsize=12)\\nplt.yticks(fontsize=12)\\nplt.tight_layout()\\nplt.savefig(os.path.join(output_dir, \\"elevation.png\\"),dpi=300)\\nplt.show()", "fig, ax = plt.subplots()\\nn, bin, patches = plt.hist(\\n    gdf_threshold[\'elev_diff\'], \\n    bins=20, \\n    color=\'skyblue\', \\n    edgecolor=\'black\', \\n    alpha=0.7\\n)\\nmean_value = gdf_threshold[\'elev_diff\'].mean()\\nplt.axvline(mean_value, color=\'red\', linestyle=\'--\', linewidth=2, label=f\'Mean = {mean_value:.2f}\')\\n\\nfor i in range(len(n)):\\n    plt.text(bin[i] + (bin[i+1] - bin[i]) / 2, n[i] + 0.5, f\\"{int(n[i])}\\", \\n             ha=\'center\', va=\'bottom\', fontsize=10, color=\'black\')\\n\\nplt.xlabel(\'Elevation difference (m)\', fontsize=14)\\nplt.ylabel(\'Frequency\', fontsize=14)\\nplt.xticks(fontsize=12)\\nplt.yticks(fontsize=12)\\nplt.grid(axis=\'y\', linestyle=\'--\', alpha=0.7)\\nplt.legend(fontsize=12)\\nplt.tight_layout()\\nplt.savefig(os.path.join(output_dir, \\"Frequency.png\\"),dpi=300)\\nplt.show()", "xx_elev = gdf_threshold[\'elev_diff\'].astype(float).values.reshape(-1, 1)\\nyy_diff = gdf_threshold[\'Elevation_left\'].values\\ntheil_sen_lg = TheilSenRegressor(random_state=42).fit(xx_elev, yy_diff)\\npredicted_values = theil_sen_lg.predict(xx_elev)\\n\\nplt.figure()\\nplt.scatter(\\n    gdf_threshold[\'elev_diff\'], \\n    gdf_threshold[\'Elevation_left\'], \\n    color=\'royalblue\', \\n    edgecolor=\'black\', \\n    alpha=0.7, \\n    label=\'Data points\'\\n)\\nplt.plot(\\n    gdf_threshold[\'elev_diff\'], \\n    predicted_values, \\n    color=\'darkred\', \\n    linewidth=2, \\n    linestyle=\'--\', \\n    label=\'Theil-Sen regression line\'\\n)\\n\\nplt.xlabel(\'Elevation difference (m)\', fontsize=12)\\nplt.ylabel(\'Elevation (m)\', fontsize=12)\\nplt.legend(fontsize=12, loc=\'best\')\\n\\nplt.grid(linestyle=\'--\', alpha=0.6)\\nplt.xticks(fontsize=12)\\nplt.yticks(fontsize=12)\\nplt.tight_layout()\\nplt.show()", "# Use pandas `cut` function to categorize \'raster_value\' into bins\\ngdf_threshold = gdf_threshold.copy()\\ngdf_threshold[\'elevation_bin\'] = pd.cut(gdf_threshold[\'Elevation_left\'], bins=elev_bins, right=False)", "gdf_threshold.tail(3) # Check the output", "# Group by the elevation bins and calculate count and average\\nbin_stats = gdf_threshold.groupby(\'elevation_bin\', observed=False)[\'elev_diff\'].agg(\\n    count=\'count\', \\n    average_elev_diff=\'mean\'\\n).reset_index()\\n\\n# Print the result\\nbin_stats.shape", "bin_stats", "import numpy as np\\nimport pandas as pd\\nfrom sklearn.linear_model import TheilSenRegressor\\n\\n# --- 1) Build bin stats (raw means) ---\\nbin_stats = (\\n    gdf_threshold\\n    .groupby(\'elevation_bin\', observed=False)[\'elev_diff\']\\n    .agg(count=\'count\', average_elev_diff=\'mean\')\\n    .reset_index()\\n)\\n\\n# midpoint elevation for each bin\\nbin_stats[\'mean_bin\'] = bin_stats[\'elevation_bin\'].apply(\\n    lambda itv: (itv.left + itv.right) / 2\\n)\\n\\n# --- 2) Fit regression ONLY on bins that have raw data ---\\ntrain = bin_stats.dropna(subset=[\'average_elev_diff\']).copy()\\n\\nX_train = train[\'mean_bin\'].to_numpy().reshape(-1, 1)\\ny_train = train[\'average_elev_diff\'].to_numpy()\\n\\ntheil_sen = TheilSenRegressor(random_state=42)\\ntheil_sen.fit(X_train, y_train)\\n\\n# --- 3) Predict for ALL bins (including empty ones) ---\\nX_all = bin_stats[\'mean_bin\'].to_numpy().reshape(-1, 1)\\nbin_stats[\'pred_mean\'] = theil_sen.predict(X_all)\\n\\n# --- 4) Hybrid: use raw where available, else predicted ---\\nbin_stats[\'final_mean\'] = bin_stats[\'average_elev_diff\'].fillna(bin_stats[\'pred_mean\'])\\n\\n# Optional: flag which values were filled\\nbin_stats[\'source\'] = np.where(bin_stats[\'average_elev_diff\'].isna(), \'predicted\', \'raw\')\\n\\n# Result you want:\\n# mean_bin = mid-bin elevation\\n# final_mean = raw mean if exists else predicted", "# Calculate the mean of each interval in the elevation_bin column\\nbin_stats[\'mean_bin\'] = bin_stats[\'elevation_bin\'].apply(lambda interval: (interval.left + interval.right) / 2)\\n\\n\\nbin_stats[\'area\'] = area_per_class \\nbin_stats[\'area1\'] = area_per_class1\\nbin_stats[\'area_average\'] = (bin_stats[\'area\']+bin_stats[\'area1\']) / 2\\n\\nbin_stats[\'diff_pred\'] = bin_stats[\'final_mean\']", "print(area_per_class)\\nprint(area_per_class1)", "bin_stats", "bin_stats[\'amb\'] = (880 * bin_stats[\'diff_pred\'] * bin_stats[\'area_average\'])\\nbin_stats", "\\nif snd1 is not None and os.path.exists(snd1):\\n    snd11.head(7)\\n    \\n    snd11.sort_values(by = \'Elevation\')\\nelse:\\n    print(\\"snd1 not provided or file missing\\")\\n\\nif snd2 is not None and os.path.exists(snd2):\\n    snd22.head(7)\\n    \\n    snd22.sort_values(by = \'Elevation\')\\nelse:\\n    print(\\"snd2 not provided or file missing\\")\\n\\nif snd1 is not None:\\n    print(snd11.head(3))\\n\\nif snd2 is not None:\\n    print(snd22.head(3))", "from sklearn.linear_model import LinearRegression\\nimport matplotlib.pyplot as plt\\n\\nif snd1 is not None and os.path.exists(snd1):\\n    # Assuming snd11 is defined somewhere above this snippet if needed\\n    # For this snippet to run, you likely need a definition:\\n    # snd11 = pd.read_csv(snd1) \\n\\n    x_snd1 = snd11[\'Elevation\'].astype(float).values.reshape(-1, 1)\\n    y_snd1 = snd11[\'Snow_depth\'].values\\n\\n    # --- Fit normal linear regression ---\\n    lin_reg = LinearRegression().fit(x_snd1, y_snd1)\\n\\n    # --- Scatter plot of data points ---\\n    plt.figure()\\n    plt.scatter(\\n        x_snd1, \\n        y_snd1,\\n        color=\'royalblue\', \\n        edgecolor=\'black\', \\n        alpha=0.7, \\n        label=\'Stake locations\'\\n    )\\n\\n    # --- Regression line ---\\n    plt.plot(\\n        x_snd1,  # or x_snd if defined elsewhere\\n        lin_reg.predict(x_snd1),\\n        color=\'darkred\', \\n        linewidth=2, \\n        linestyle=\'--\', \\n        label=\'Linear regression line\'\\n    )\\n\\n    plt.grid(linestyle=\'--\', alpha=0.6)\\n    plt.xlabel(\'Elevation (m)\')\\n    plt.ylabel(\'Snow depth (m)\')\\n    plt.legend()\\n    # Use plt.show() to display the plot window\\n    plt.show() \\n\\n    # --- Predict for mid-bin values ---\\n    mid_bin1 = bin_stats[\'mean_bin\'].astype(float).values.reshape(-1, 1)\\n    mid_bin_snd1 = lin_reg.predict(mid_bin1)\\n\\n    # Use print() to display these values in the console\\n    print(mid_bin1)\\n    print(mid_bin_snd1)\\n    # --- Prepare data ---\\n\\nelse:\\n    print(\\"no files\\")", "\\nif snd2 is not None and os.path.exists(snd2):\\n    # --- Prepare data ---\\n    x_snd2 = snd22[\'Elevation\'].astype(float).values.reshape(-1, 1)\\n    y_snd2 = snd22[\'Snow_depth\'].values\\n\\n    # --- Fit normal linear regression ---\\n    lin_reg = LinearRegression().fit(x_snd2, y_snd2)\\n\\n    # --- Scatter plot of data points ---\\n    plt.figure()\\n    plt.scatter(\\n        x_snd2, \\n        y_snd2,\\n        color=\'royalblue\', \\n        edgecolor=\'black\', \\n        alpha=0.7, \\n        label=\'Stake locations\'\\n    )\\n\\n    # --- Regression line ---\\n    plt.plot(\\n        x_snd2,  # or x_snd if defined elsewhere\\n        lin_reg.predict(x_snd2),\\n        color=\'darkred\', \\n        linewidth=2, \\n        linestyle=\'--\', \\n        label=\'Linear regression line\'\\n    )\\n\\n    plt.grid(linestyle=\'--\', alpha=0.6)\\n    plt.xlabel(\'Elevation (m)\')\\n    plt.ylabel(\'Snow depth (m)\')\\n    plt.legend()\\n    plt.show()\\n\\n    # --- Predict for mid-bin values ---\\n    mid_bin2 = bin_stats[\'mean_bin\'].astype(float).values.reshape(-1, 1)\\n    mid_bin_snd2 = lin_reg.predict(mid_bin2)\\n    mid_bin_snd2 = np.where(mid_bin_snd2 > 0, mid_bin_snd2, 0)\\n\\n\\n    print(mid_bin2)\\n    print(mid_bin_snd2)\\nelse:\\n   print(\\"no such files\\")", "bin_stats", "\\nif (\\n    snd1 is not None and os.path.exists(snd1) and\\n    snd2 is not None and os.path.exists(snd2)\\n):\\n    bin_stats[\'snow_depth_2024\'] = mid_bin_snd1\\n    bin_stats[\'snow_depth_2025\'] = mid_bin_snd2\\n    bin_stats[\'diff_snow_depth_2025\'] = mid_bin_snd2 - mid_bin_snd1\\nelse:\\n    print(\\"snow files not fully provided or missing\\")", "\\nif (\\n    snd1 is not None and os.path.exists(snd1) and\\n    snd2 is not None and os.path.exists(snd2)\\n):\\n    bin_stats[\'Annual_MB\'] = (\\n        880 * bin_stats[\'diff_pred\']\\n        + bin_stats[\'diff_snow_depth_2025\'] * (400 - 880)\\n    )\\nelse:\\n    bin_stats[\'Annual_MB_no_snow\'] = (880 * bin_stats[\'diff_pred\'])", "bin_stats", "\\nif \'Annual_MB\' in bin_stats.columns:\\n    amb = np.sum(bin_stats[\'Annual_MB\'] * bin_stats[\'area_average\']) / np.sum(bin_stats[\'area_average\'])\\n    print(amb)\\nelse:\\n    amb = np.sum(bin_stats[\'Annual_MB_no_snow\'] * bin_stats[\'area_average\']) / np.sum(bin_stats[\'area_average\'])\\n    print(f\\"Mass balance(no snow) is:\'{amb}\'\\")", "x_agg = bin_stats[\'mean_bin\'].astype(float).values.reshape(-1, 1)\\ny_agg = bin_stats[\'average_elev_diff\'].values\\narea = bin_stats[\'area\'].values\\nmask = ~np.isnan(y_agg)\\nx_agg_clean = x_agg[mask]\\ny_agg_clean = y_agg[mask]\\narea_clean = area[mask]\\n\\ntheil_sen_agg = TheilSenRegressor().fit(x_agg_clean, y_agg_clean)\\n\\nfig, ax1 = plt.subplots(figsize=(10,6))\\nax1.scatter(x_agg_clean, y_agg_clean, color=\'blue\', label=\'Elevation difference\')\\nax1.plot(x_agg_clean, theil_sen_agg.predict(x_agg_clean), color=\'blue\', label=\'Theil-Sen regression line\')\\nax1.set_xlabel(\'Elevation (mean_bin)\',fontsize=14)\\nax1.set_ylabel(\'Elevation difference (m)\', color=\'blue\',fontsize=14)\\nax1.tick_params(axis=\'y\', labelcolor=\'blue\')\\nax1.legend(loc=\'upper left\')\\nax1.grid(True, linestyle=\'--\', alpha=0.6)\\n\\nax2 = ax1.twinx()\\nax2.scatter(x_agg_clean, area_clean, color=\'red\', marker=\'o\', alpha=0.7,label=\'Glacier area(m$^2$)\')\\nax2.set_ylabel(\'Glacier area (m$^2$)\', color=\'red\',fontsize=14)\\nax2.tick_params(axis=\'y\', labelcolor=\'red\')\\nplt.legend(loc=\'upper left\', bbox_to_anchor=(0.004, 0.86))\\nplt.savefig(os.path.join(output_dir, \\"elevation.png\\"),dpi=450)\\nplt.show()", "bin_stats[\'diff_pred2\'] = theil_sen_agg.predict(x_agg)\\n\\nif snd1 is not None and os.path.exists(snd1):\\n    bin_stats[\'Annual_MB_Aggregated\'] = (880 * bin_stats[\'diff_pred2\']+ bin_stats[\'diff_snow_depth_2025\'] * (400-880))\\nelse:\\n    bin_stats[\'Annual_MB_Aggregated\'] = (880 * bin_stats[\'diff_pred2\'])\\n    \\nbin_stats", "amb2 = np.sum(bin_stats[\'Annual_MB_Aggregated\']* bin_stats[\'area_average\'])/np.sum(bin_stats[\'area_average\'])\\nprint(amb2)", "amb_agg_data = np.sum(bin_stats[\'Annual_MB_Aggregated\']* bin_stats[\'area_average\'])/np.sum(bin_stats[\'area_average\'])\\namb_agg_data\\nnp.sum(bin_stats[\'area\'])/1000000\\n\\namb_array = [amb, amb_agg_data]\\nprint(amb_array)\\n\\nlabels = [\'Non-aggregated data\', \'Aggregated data\']\\n\\nplt.figure()\\nbars = plt.bar(labels, amb_array, color=[\'steelblue\', \'orange\'], alpha=0.8, edgecolor=\'black\')\\n\\nfor bar in bars:\\n    height = bar.get_height()\\n    plt.text(\\n        bar.get_x() + bar.get_width() / 2,\\n        height, \\n        f\\"{height:.2f}\\", \\n        ha=\'center\', \\n        va=\'bottom\' if height > 0 else \'top\',\\n        fontsize=12,\\n        color=\'black\'\\n    )\\nplt.ylabel(\'Annual mass balance (mm w.e.a)\', fontsize=12)\\nplt.grid(axis=\'y\', linestyle=\'--\', alpha=0.6)\\nplt.xticks(fontsize=12)\\nplt.yticks(fontsize=12)\\nplt.axhline(0, color=\'black\', linewidth=1)\\nplt.tight_layout()\\nplt.show()", "\\n\\n# --------------------------------------------------------------------\\n# 1. Get glacier boundary segments\\n# --------------------------------------------------------------------\\n\\nfrom shapely.geometry import LineString, MultiLineString\\ndef get_boundary_segments(glacier_shp_path):\\n    gdf = gpd.read_file(glacier_shp_path)\\n    boundary = gdf.geometry.boundary.unary_union\\n\\n    if boundary.geom_type == \\"MultiLineString\\":\\n        lines = list(boundary.geoms)\\n    else:\\n        lines = [boundary]\\n\\n    segments = []\\n    for line in lines:\\n        coords = list(line.coords)\\n        for i in range(len(coords) - 1):\\n            segments.append((coords[i], coords[i + 1]))\\n\\n    return segments, gdf.crs\\n\\n# --------------------------------------------------------------------\\n# 2. Sample DEM elevation at coordinate points\\n# --------------------------------------------------------------------\\ndef get_elevation_for_coords(dem_path, coords):\\n    \\"\\"\\"\\n    Samples elevation from DEM at given (x, y) coordinates.\\n    Returns a numpy array of elevation values.\\n    \\"\\"\\"\\n    with rasterio.open(dem_path) as src:\\n        band = src.read(1)\\n        values = []\\n        for x, y in coords:\\n            row, col = src.index(x, y)\\n            elev = band[row, col]\\n            values.append(elev)\\n    return np.array(values)\\n\\n# --------------------------------------------------------------------\\n# 3. Compute boundary length in fixed elevation bands (5101\\u20135501)\\n# --------------------------------------------------------------------\\ndef compute_segment_band_lengths_fixed(segments, start_elev, end_elev, interval=50):\\n    \\"\\"\\"\\n    Computes total boundary length in each elevation band, using\\n    a fixed elevation range from 5101 m to 5501 m with given interval.\\n    \\"\\"\\"\\n    avg_elevations = (start_elev + end_elev) / 2.0\\n\\n    # --- FIXED BIN RANGE HERE ---\\n    min_elev = elev_bins[0]\\n    max_elev = elev_bins[-1]\\n    bins = np.arange(min_elev, max_elev + interval, interval)\\n    # ----------------------------\\n\\n    labels = [f\\"{int(bins[i])}-{int(bins[i+1])} m\\" for i in range(len(bins) - 1)]\\n\\n    # Digitize avg elevations into these fixed bins\\n    band_indices = np.digitize(avg_elevations, bins) - 1  # shift to 0-based\\n\\n    band_lengths = {}\\n    for (p1, p2), band_idx in zip(segments, band_indices):\\n        if 0 <= band_idx < len(labels):\\n            band = labels[band_idx]\\n            length = np.hypot(p2[0] - p1[0], p2[1] - p1[1])  # length in CRS units (e.g. meters)\\n            band_lengths[band] = band_lengths.get(band, 0) + length\\n\\n    df = pd.DataFrame(\\n        list(band_lengths.items()),\\n        columns=[\\"Elevation Band\\", \\"Boundary Length (m)\\"]\\n    ).sort_values(\\"Elevation Band\\")\\n\\n    return df, bins\\n\\n# --------------------------------------------------------------------\\n# 4. Create segment GeoDataFrame using same fixed bins\\n# --------------------------------------------------------------------\\ndef create_segment_gdf_fixed(segments, start_elev, end_elev, crs, interval=50):\\n    \\"\\"\\"\\n    Creates a GeoDataFrame of boundary segments, each labeled with an\\n    elevation band using the fixed 5101\\u20135501 m range.\\n    \\"\\"\\"\\n    avg_elevations = (start_elev + end_elev) / 2.0\\n\\n    # --- FIXED BIN RANGE HERE ---\\n    min_elev = elev_bins[0]\\n    max_elev = elev_bins[-1]\\n    bins = np.arange(min_elev, max_elev + interval, interval)\\n    # ----------------------------\\n\\n    labels = [f\\"{int(bins[i])}-{int(bins[i+1])} m\\" for i in range(len(bins) - 1)]\\n    band_indices = np.digitize(avg_elevations, bins) - 1\\n\\n    bands = [labels[i] if 0 <= i < len(labels) else None for i in band_indices]\\n    lines = [LineString([p1, p2]) for (p1, p2) in segments]\\n\\n    gdf = gpd.GeoDataFrame(\\n        {\\n            \\"geometry\\": lines,\\n            \\"Elevation Band\\": bands\\n        },\\n        crs=crs\\n    )\\n\\n    return gdf\\n\\n# --------------------------------------------------------------------\\n# 5. Plot segments colored by elevation band\\n# --------------------------------------------------------------------\\ndef plot_segments_by_band(segment_gdf):\\n    \\"\\"\\"\\n    Plots glacier boundary segments colored by elevation band.\\n    \\"\\"\\"\\n    fig, ax = plt.subplots(figsize=(10, 10))\\n    segment_gdf.plot(\\n        ax=ax,\\n        column=\\"Elevation Band\\",\\n        cmap=\\"viridis\\",\\n        linewidth=2,\\n        legend=True\\n    )\\n    ax.set_title(\\"Glacier Boundary Segments by Elevation Band\\", fontsize=14)\\n    ax.set_axis_off()\\n    plt.tight_layout()\\n    plt.show()\\n\\n# --------------------------------------------------------------------\\n# 6. USAGE EXAMPLE\\n# --------------------------------------------------------------------\\n# Make sure these paths are defined before running:\\n# glacier_shp_path = r\\"path\\\\to\\\\your\\\\glacier.shp\\"\\n# corrected_dem    = r\\"path\\\\to\\\\your\\\\corrected_dem.tif\\"\\n\\n# Get boundary segments and CRS\\nsegments, crs = get_boundary_segments(glacier_shp_path)\\n\\n# Build list of coords (start and end of each segment)\\nstart_coords = [seg[0] for seg in segments]\\nend_coords   = [seg[1] for seg in segments]\\nall_coords   = start_coords + end_coords\\n\\n# Sample DEM elevations at all these coords\\nelevations_raw = get_elevation_for_coords(corrected_dem, all_coords)\\n\\n# Split into start and end elevation arrays\\nstart_elev = elevations_raw[:len(segments)]\\nend_elev   = elevations_raw[len(segments):]\\n\\n# Compute boundary lengths in fixed bands 5101\\u20135501 m\\ndf_result, used_bins = compute_segment_band_lengths_fixed(\\n    segments, start_elev, end_elev, interval=50\\n)\\n\\nprint(\\"Boundary length per elevation band:\\")\\nprint(df_result)\\nprint(\\"\\\\nBins used:\\", used_bins)\\n\\n\\n# Create GeoDataFrame of segments with band labels and plot\\nsegment_gdf = create_segment_gdf_fixed(\\n    segments, start_elev, end_elev, crs, interval=50\\n)\\n\\nplot_segments_by_band(segment_gdf)\\ndf_result", "df_result", "bin_stats[\'Perimeter\'] = df_result[\'Boundary Length (m)\'].values", "bin_stats", "if snd1 is not None and os.path.exists(snd1) and snd2 is not None and os.path.exists(snd2):\\n    mb_col = \'Annual_MB\'\\nelse:\\n    mb_col = \'Annual_MB_no_snow\'\\n\\nbin_stats[\'Area_Average_MB\'] = (\\n    bin_stats[mb_col] * bin_stats[\'area_average\']\\n) / np.sum(bin_stats[\'area_average\'])", "bin_stats", "\\n#for you to use this code you should have csv file with column name bg(area average mass balance),Absolute bg,Average Area and Per\\n# Constants\\nPIXEL_CONSTANT = 10\\nUNCERTAINTY_ICE_DENSITY = 30\\nUNCERTAINTY_SNOW_DENSITY = 100\\n\\n# Load CSV\\n\\n\\n# Clean column names\\nbin_stats.columns = bin_stats.columns.str.strip().str.replace(\'\\\\xa0\', \' \', regex=True)\\nbin_stats[\'Absolute bg\']=abs(bin_stats[\'Area_Average_MB\'])\\n# ---- STEP 1: Average of bg ----\\navg_bg = bin_stats[\'Area_Average_MB\'].mean()\\n\\n# ---- STEP 2: Total Area Average ----\\ntotal_area_avg = bin_stats[\'area\'].sum()\\n\\n# ---- STEP 3: (x - X)^2 ----\\nbin_stats[\'(x - X)^2\'] = (bin_stats[\'Area_Average_MB\'] - avg_bg) ** 2\\n\\n# ---- STEP 4: Total Summation of (x - X)^2 ----\\ntotal_summation = bin_stats[\'(x - X)^2\'].sum()\\n\\n# ---- STEP 5: dbz ----\\ndbz = np.sqrt(total_summation / len(bin_stats))\\n\\n# ---- STEP 6: dAz = 0.5 * pixel * Perimeter ----\\nbin_stats[\'dAz\'] = 0.5 * PIXEL_CONSTANT * bin_stats[\'Perimeter\']\\n\\n# ---- STEP 7: Uncertainty for Ice ----\\nbin_stats[\'Uncertainty Ice\'] = (\\n    (bin_stats[\'area\'] * dbz) +\\n    (bin_stats[\'dAz\'] * bin_stats[\'Absolute bg\']) +\\n    (bin_stats[\'area\'] * UNCERTAINTY_ICE_DENSITY)\\n) / total_area_avg\\n\\n# ---- STEP 8: Uncertainty for Snow ----\\nbin_stats[\'Uncertainty Snow\'] = (\\n    (bin_stats[\'area\'] * dbz) +\\n    (bin_stats[\'dAz\'] * bin_stats[\'Absolute bg\']) +\\n    (bin_stats[\'area\'] * UNCERTAINTY_SNOW_DENSITY)\\n) / total_area_avg\\n\\n# ---- STEP 9: Total Sum of Each ----\\ntotal_uncertainty_ice = bin_stats[\'Uncertainty Ice\'].sum()\\ntotal_uncertainty_snow = bin_stats[\'Uncertainty Snow\'].sum()\\n\\n# ---- STEP 10: Overall Uncertainty Average ----\\nuncertainty_overall = (total_uncertainty_ice + total_uncertainty_snow) / 2\\n\\n# ---- Round and Output ----\\nbin_stats = bin_stats.round(3)\\n\\nprint(bin_stats)\\nprint(\\"\\\\nAverage bg:\\", round(avg_bg, 3))\\nprint(\\"Total Area Average:\\", round(total_area_avg, 3))\\nprint(\\"Total Summation (x - X)^2:\\", round(total_summation, 3))\\nprint(\\"dbz:\\", round(dbz, 3))\\nprint(\\"Total Uncertainty Ice:\\", round(total_uncertainty_ice, 3))\\nprint(\\"Total Uncertainty Snow:\\", round(total_uncertainty_snow, 3))\\nprint(\\"Overall Uncertainty Average:\\", round(uncertainty_overall, 3))\\n\\n# Optional: Save output\\nbin_stats.to_csv(os.path.join(output_dir, \\"uncertainty_results.csv\\"), index=False)"]')

def save_uploaded_file(uploaded_file, dest_path):
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(dest_path)

def extract_shapefile_zip(uploaded_zip, dest_dir):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / uploaded_zip.name
    with open(zip_path, "wb") as f:
        f.write(uploaded_zip.getbuffer())
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)
    shp_files = list(dest_dir.rglob("*.shp"))
    if not shp_files:
        raise FileNotFoundError("No .shp file found in the uploaded ZIP.")
    return str(shp_files[0])

def find_output_files(output_dir):
    out = []
    for p in sorted(Path(output_dir).glob("*")):
        if p.is_file():
            out.append(p)
    return out

def render_namespace_outputs(ns):
    if "geo_gdf1" in ns:
        st.subheader("geo_gdf1")
        st.dataframe(ns["geo_gdf1"].head(10))
    if "geo_gdf2" in ns:
        st.subheader("geo_gdf2")
        st.dataframe(ns["geo_gdf2"].head(10))
    if "merged_gdf" in ns:
        st.subheader("merged_gdf")
        st.write(f"Shape: {ns['merged_gdf'].shape}")
        st.dataframe(ns["merged_gdf"].head(10))
    if "gdf_threshold" in ns:
        st.subheader("gdf_threshold")
        st.write(f"Shape: {ns['gdf_threshold'].shape}")
        st.dataframe(ns["gdf_threshold"].head(10))
    if "bin_stats" in ns:
        st.subheader("bin_stats")
        st.dataframe(ns["bin_stats"])
    if "df_result" in ns:
        st.subheader("Boundary-segment result")
        st.dataframe(ns["df_result"])
    summary = {}
    for key in ["amb", "amb2", "amb_agg_data"]:
        if key in ns:
            summary[key] = ns[key]
    if summary:
        st.subheader("Key summary values")
        st.json(summary)

def main():
    import streamlit as st
    user_epsg = st.sidebar.text_input("Projected CRS (EPSG)", value="32646")
    with st.sidebar:
        st.header("Inputs")

        dgps_2025 = st.file_uploader("2025 dGPS CSV (raw input for csv_path_1)", type=["csv"])
        dgps_2024 = st.file_uploader("2024 dGPS CSV (raw input for csv_path_2)", type=["csv"])
        raster_tif = st.file_uploader("DEM raster (.tif)", type=["tif", "tiff"])
        glacier_zip = st.file_uploader("Glacier shapefile ZIP (.zip)", type=["zip"])
        snow_2024 = st.file_uploader("Previous year Snow depth CSV  (optional)", type=["csv"])
        snow_2025 = st.file_uploader("Current year Snow depth CSV  (optional)", type=["csv"])

        st.header("Parameters from notebook")
        cell_size = st.number_input("cell_size", value=1.0, step=0.1)
        search_radius = st.number_input("search_radius", value=0.7, step=0.1)
        power = st.number_input("power", value=2, step=1)
        distance_threshold = st.number_input("distance_threshold", value=3.0, step=0.5)

        corrected_dem_name = st.text_input("corrected_dem_name", value="dem_corr1.tif")
        output_clipped_dem_name = st.text_input("output_clipped_dem_name", value="dem_sub_corr1.tif")
        corrected_dem_name_old = st.text_input("corrected_dem_name_old", value="dem_corr2.tif")
        output_clipped_dem_name_old = st.text_input("output_clipped_dem_name_old", value="dem_sub_corr2.tif")

        run_btn = st.button("Run notebook workflow", type="primary", use_container_width=True)

    st.info("Required files: both dGPS CSVs, raster TIFF, and glacier shapefile ZIP. Snow depth files are optional.")

    if not run_btn:
        return

    missing = []
    if dgps_2025 is None:
        missing.append("2025 dGPS CSV")
    if dgps_2024 is None:
        missing.append("2024 dGPS CSV")
    if raster_tif is None:
        missing.append("DEM raster")
    if glacier_zip is None:
        missing.append("Glacier shapefile ZIP")
    if missing:
        st.error("Missing required inputs: " + ", ".join(missing))
        return

    workdir = tempfile.mkdtemp(prefix="thana_streamlit_")
    input_dir = Path(workdir) / "inputs"
    output_dir = Path(workdir) / "outputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        csv_path_1 = save_uploaded_file(dgps_2025, input_dir / "csv_path_1.csv")
        csv_path_2 = save_uploaded_file(dgps_2024, input_dir / "csv_path_2.csv")
        raster_file = save_uploaded_file(raster_tif, input_dir / raster_tif.name)
        glacier_shp_path = extract_shapefile_zip(glacier_zip, input_dir / "glacier_shapefile")

        snd1 = save_uploaded_file(snow_2024, input_dir / "snow_1.csv") if snow_2024 is not None else None
        snd2 = save_uploaded_file(snow_2025, input_dir / "snow_2.csv") if snow_2025 is not None else None

        gdf_1 = str(output_dir / "Thana_idw_interpolated_1m_utm.csv")
        gdf_2 = str(output_dir / "Thana_idw_interpolated_1m_utm_old.csv")

        ns = {
            "__name__": "__main__",
            "csv_path_1": csv_path_1,
            "csv_path_2": csv_path_2,
            "gdf_1": gdf_1,
            "gdf_2": gdf_2,
            "gdf11": gdf_1,
            "gdf22": gdf_2,
            "raster_file": raster_file,
            "glacier_shp_path": glacier_shp_path,
            "snd1": snd1,
            "snd2": snd2,
            "cell_size": cell_size,
            "search_radius": search_radius,
            "power": power,
            "distance_threshold": distance_threshold,
            "corrected_dem_name": corrected_dem_name,
            "output_clipped_dem_name": output_clipped_dem_name,
            "corrected_dem_name_old": corrected_dem_name_old,
            "output_clipped_dem_name_old": output_clipped_dem_name_old,
            "output_dir": str(output_dir),
            "user_epsg": user_epsg,
        }

        progress = st.progress(0.0)
        status = st.empty()
        log_box = st.expander("Execution log", expanded=True)

        import matplotlib.pyplot as plt  # noqa


import os
import io
import json
import zipfile
import shutil
import tempfile
import traceback
import contextlib
import base64
import textwrap
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Glacier Mass Balance Calculation", layout="wide")

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"

def image_to_data_uri(path):
    path = Path(path)
    if not path.exists():
        return ""
    suffix = path.suffix.lower().replace(".", "")
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/{mime};base64,{data}"

top_banner_uri = image_to_data_uri(ASSETS_DIR / "logo.jpg")
bg_uri = image_to_data_uri(ASSETS_DIR / "glacier_background.png")

banner_html = textwrap.dedent(f"""
<style>
.hero-wrap {{
    border-radius: 28px;
    overflow: hidden;
    margin-bottom: 1rem;
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow: 0 12px 32px rgba(0,0,0,0.18);
}}
.hero-top-banner {{
    background: #ffffff;
}}
.hero-top-banner img {{
    display: block;
    width: 100%;
    height: auto;
}}
.hero-main {{
    min-height: 470px;
    background-image:
        linear-gradient(rgba(8,20,45,0.20), rgba(8,20,45,0.62)),
        url('{bg_uri}');
    background-size: cover;
    background-position: center;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 42px;
}}
.hero-card {{
    width: min(1260px, 86%);
    background: rgba(20,30,45,0.34);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 30px;
    padding: 52px 40px;
    text-align: center;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    box-shadow: 0 18px 40px rgba(0,0,0,0.18);
}}
.hero-card h1 {{
    margin: 0;
    font-size: 4rem;
    color: white;
    font-weight: 800;
}}
.hero-card p {{
    margin-top: 22px;
    font-size: 1.3rem;
    color: rgba(255,255,255,0.94);
}}
.hero-note {{
    margin-top: 16px;
    background: rgba(49,99,190,0.18);
    color: #79b0ff;
    border-radius: 14px;
    padding: 18px 20px;
    font-size: 1rem;
}}
</style>

<div class="hero-wrap">
    <div class="hero-top-banner">
        <img src="{top_banner_uri}">
    </div>
    <div class="hero-main">
        <div class="hero-card">
            <h1>Glacier Mass Balance Calculation</h1>
            <p>Cryosphere Services Division - Glacier mass balance notebook workflow.</p>
        </div>
    </div>
</div>

<div class="hero-note">
    This app is script based glacier mass balance workflow:
    IDW interpolation → DEM bias correction → glacier-clipped hypsometry
    → nearest-point differencing → optional snow correction
    → amb and uncertainty summary.
</div>
""")

st.markdown(banner_html, unsafe_allow_html=True)

NOTEBOOK_CELLS = json.loads('["# Import necessary modules\\n\\nimport os\\nimport numpy as np\\nimport matplotlib.pyplot as plt\\nimport pandas as pd\\nimport geopandas as gpd\\nfrom shapely.geometry import Point\\nimport geopandas as gpd\\nimport rasterio\\nfrom rasterio.mask import mask\\nfrom sklearn.linear_model import TheilSenRegressor\\nfrom shapely.geometry import Point, LineString, MultiLineString", "import pandas as pd\\nimport numpy as np\\nfrom scipy.spatial import cKDTree\\n\\n# -----------------------------\\n# 1. Paths & parameters\\n# -----------------------------\\n# csv_path_1 provided by Streamlit\\n# gdf_1 provided by Streamlit\\n\\n# Column names in your CSV (edit if needed)\\nx_col = \\"Longitude\\"      # UTM Easting in your file\\ny_col = \\"Latitude\\"       # UTM Northing in your file\\nz_col = \\"Elevation\\"      # Elevation\\n\\ncell_size = 1.0          # 1 m grid\\nsearch_radius = 0.7      # in metres (UTM)\\npower = 2                # IDW power\\n\\n# -----------------------------\\n# 2. Read CSV\\n# -----------------------------\\ndf = pd.read_csv(csv_path_1)\\n\\nif not set([x_col, y_col, z_col]).issubset(df.columns):\\n    raise ValueError(f\\"CSV must contain {x_col}, {y_col}, {z_col} columns. \\"\\n                     f\\"Found: {list(df.columns)}\\")\\n\\nx = df[x_col].to_numpy(dtype=float)\\ny = df[y_col].to_numpy(dtype=float)\\nz = df[z_col].to_numpy(dtype=float)\\n\\n# Drop NaNs if any\\nvalid_mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)\\nx = x[valid_mask]\\ny = y[valid_mask]\\nz = z[valid_mask]\\n\\nif x.size == 0:\\n    raise ValueError(\\"No valid points after removing NaNs. Check your CSV.\\")\\n\\n# -----------------------------\\n# 3. Build 1 m grid (UTM)\\n# -----------------------------\\nminx, maxx = x.min(), x.max()\\nminy, maxy = y.min(), y.max()\\n\\npad = cell_size * 0.5\\nminx -= pad\\nminy -= pad\\nmaxx += pad\\nmaxy += pad\\n\\nif maxx <= minx or maxy <= miny:\\n    raise ValueError(\\n        f\\"Invalid bounds: minx={minx}, maxx={maxx}, miny={miny}, maxy={maxy}\\"\\n    )\\n\\ngrid_x = np.arange(minx, maxx, cell_size)\\ngrid_y = np.arange(miny, maxy, cell_size)\\n\\ngrid_xx, grid_yy = np.meshgrid(grid_x, grid_y)\\ngrid_points = np.vstack((grid_xx.ravel(), grid_yy.ravel())).T\\n\\n# -----------------------------\\n# 4. IDW interpolation (in UTM)\\n# -----------------------------\\ntree = cKDTree(np.vstack((x, y)).T)\\nneighbors_idx = tree.query_ball_point(grid_points, r=search_radius)\\n\\ninterp_z = np.full(grid_points.shape[0], np.nan, dtype=float)\\n\\nfor i, idx_list in enumerate(neighbors_idx):\\n    if len(idx_list) == 0:\\n        continue  # no neighbors within radius\\n\\n    x_neighbors = x[idx_list]\\n    y_neighbors = y[idx_list]\\n    z_neighbors = z[idx_list]\\n\\n    dx = x_neighbors - grid_points[i, 0]\\n    dy = y_neighbors - grid_points[i, 1]\\n    d = np.sqrt(dx**2 + dy**2)\\n\\n    # Exact sample point -> copy value\\n    zero_mask = d == 0\\n    if np.any(zero_mask):\\n        interp_z[i] = z_neighbors[zero_mask][0]\\n        continue\\n\\n    w = 1.0 / (d**power)\\n    interp_z[i] = np.sum(w * z_neighbors) / np.sum(w)\\n\\n# -----------------------------\\n# 5. Build output table (UTM 45N)\\n# -----------------------------\\nvalid = ~np.isnan(interp_z)\\ngrid_valid = grid_points[valid]\\nz_valid = interp_z[valid]\\n\\nutm_x = grid_valid[:, 0]\\nutm_y = grid_valid[:, 1]\\n\\nout_df = pd.DataFrame({\\n    \\"Point_id\\": np.arange(1, len(z_valid) + 1),\\n    \\"Latitude\\": utm_y,      # UTM 45N Easting\\n    \\"Longitude\\": utm_x ,    # UTM 45N Northing\\n    \\"Elevation\\": z_valid\\n})\\nfinal_df = out_df.sort_values(\'Elevation\', ascending = False)\\nfinal_df[\'sorted_order\'] = np.arange(1, len(final_df) + 1)\\nfinal_df.to_csv(gdf_1, index=False)\\nprint(f\\"Saved interpolated UTM points to: {gdf_1}\\")\\nprint(final_df.head())", "import pandas as pd\\nimport numpy as np\\nfrom scipy.spatial import cKDTree\\n\\n# -----------------------------\\n# 1. Paths & parameters\\n# -----------------------------\\n# csv_path_2 provided by Streamlit\\n# gdf_2 provided by Streamlit\\n\\n# Column names in your CSV (edit if needed)\\nx_col = \\"Longitude\\"      # UTM Easting in your file\\ny_col = \\"Latitude\\"       # UTM Northing in your file\\nz_col = \\"Elevation\\"      # Elevation\\n\\ncell_size = 1.0          # 1 m grid\\nsearch_radius = 0.7      # in metres (UTM)\\npower = 2                # IDW power\\n\\n# -----------------------------\\n# 2. Read CSV\\n# -----------------------------\\ndf = pd.read_csv(csv_path_2)\\n\\nif not set([x_col, y_col, z_col]).issubset(df.columns):\\n    raise ValueError(f\\"CSV must contain {x_col}, {y_col}, {z_col} columns. \\"\\n                     f\\"Found: {list(df.columns)}\\")\\n\\nx = df[x_col].to_numpy(dtype=float)\\ny = df[y_col].to_numpy(dtype=float)\\nz = df[z_col].to_numpy(dtype=float)\\n\\n# Drop NaNs if any\\nvalid_mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)\\nx = x[valid_mask]\\ny = y[valid_mask]\\nz = z[valid_mask]\\n\\nif x.size == 0:\\n    raise ValueError(\\"No valid points after removing NaNs. Check your CSV.\\")\\n\\n# -----------------------------\\n# 3. Build 1 m grid (UTM)\\n# -----------------------------\\nminx, maxx = x.min(), x.max()\\nminy, maxy = y.min(), y.max()\\n\\npad = cell_size * 0.5\\nminx -= pad\\nminy -= pad\\nmaxx += pad\\nmaxy += pad\\n\\nif maxx <= minx or maxy <= miny:\\n    raise ValueError(\\n        f\\"Invalid bounds: minx={minx}, maxx={maxx}, miny={miny}, maxy={maxy}\\"\\n    )\\n\\ngrid_x = np.arange(minx, maxx, cell_size)\\ngrid_y = np.arange(miny, maxy, cell_size)\\n\\ngrid_xx, grid_yy = np.meshgrid(grid_x, grid_y)\\ngrid_points = np.vstack((grid_xx.ravel(), grid_yy.ravel())).T\\n\\n# -----------------------------\\n# 4. IDW interpolation (in UTM)\\n# -----------------------------\\ntree = cKDTree(np.vstack((x, y)).T)\\nneighbors_idx = tree.query_ball_point(grid_points, r=search_radius)\\n\\ninterp_z = np.full(grid_points.shape[0], np.nan, dtype=float)\\n\\nfor i, idx_list in enumerate(neighbors_idx):\\n    if len(idx_list) == 0:\\n        continue  # no neighbors within radius\\n\\n    x_neighbors = x[idx_list]\\n    y_neighbors = y[idx_list]\\n    z_neighbors = z[idx_list]\\n\\n    dx = x_neighbors - grid_points[i, 0]\\n    dy = y_neighbors - grid_points[i, 1]\\n    d = np.sqrt(dx**2 + dy**2)\\n\\n    # Exact sample point -> copy value\\n    zero_mask = d == 0\\n    if np.any(zero_mask):\\n        interp_z[i] = z_neighbors[zero_mask][0]\\n        continue\\n\\n    w = 1.0 / (d**power)\\n    interp_z[i] = np.sum(w * z_neighbors) / np.sum(w)\\n\\n# -----------------------------\\n# 5. Build output table (UTM 45N)\\n# -----------------------------\\nvalid = ~np.isnan(interp_z)\\ngrid_valid = grid_points[valid]\\nz_valid = interp_z[valid]\\n\\nutm_x = grid_valid[:, 0]\\nutm_y = grid_valid[:, 1]\\n\\nout_df = pd.DataFrame({\\n    \\"Point_id\\": np.arange(1, len(z_valid) + 1),\\n    \\"Latitude\\": utm_y,      # UTM 45N Easting\\n    \\"Longitude\\": utm_x ,    # UTM 45N Northing\\n    \\"Elevation\\": z_valid\\n})\\nfinal_df_1 = out_df.sort_values(\'Elevation\', ascending = False)\\n\\nfinal_df_1[\'sorted_order\'] = np.arange(1, len(final_df_1) + 1)\\n\\nfinal_df_1.to_csv(gdf_2, index=False)\\nprint(f\\"Saved interpolated UTM points to: {gdf_2}\\")\\nprint(final_df_1.head())", "\\"\\"\\"Only this section needs u\\"\\"\\"\\n# gdf1 = \\"/mnt/d/NCHM_Data/tracks/Gangju la_2024_01.csv\\" # New csv file (e.g., 2024) path\\n# gdf2 = \\"/mnt/d/NCHM_Data/tracks/Gangju_La_rawdata_2023.csv\\" # Old csv file (e.g., 2023) path\\n\\n# merged_gdf[\'elev_diff\'] = merged_gdf[\'Elevation_left\'] - merged_gdf[\'Elevation_right\'] # e.g., 5m (2023)  2m in (2024): 2m - 5m\\n\\ngdf11 = gdf_1\\ngdf22 = gdf_2\\n\\n# raster_file provided by Streamlit\\n# glacier_shp_path provided by Streamlit\\n\\n\\n\\"\\"\\"Snow depth data at stakes\\"\\"\\"\\n\\n# snd1 provided by Streamlit\\n# snd2 provided by Streamlit\\n\\n\\"\\"\\"Change if necessary\\"\\"\\"\\n\\n# distance_threshold provided by Streamlit\\n# corrected_dem_name provided by Streamlit\\n# output_clipped_dem_name provided by Streamlit\\n# corrected_dem_name_old provided by Streamlit\\n# output_clipped_dem_name_old provided by Streamlit", "\\n\\nif snd1 is not None and os.path.exists(snd1):\\n    snd11 = pd.read_csv(snd1)\\nelse:\\n    print(\\"snd1 not provided or file missing\\")\\n\\nif snd2 is not None and os.path.exists(snd2):\\n    snd22 = pd.read_csv(snd2)\\nelse:\\n    print(\\"snd2 not provided or file missing\\")\\n\\nif snd1 is not None:\\n    print(snd11.head(3))\\n\\nif snd2 is not None:\\n    print(snd22.head(3))", "master_path = os.path.split(raster_file)[0]\\ncorrected_dem = os.path.join(master_path, corrected_dem_name)  \\noutput_clipped_dem = os.path.join(master_path, output_clipped_dem_name)  \\ncorrected_dem1 = os.path.join(master_path, corrected_dem_name_old)  \\noutput_clipped_dem1 = os.path.join(master_path, output_clipped_dem_name_old)\\ngdf1 = pd.read_csv(gdf11) # 2024 # Left\\ngdf2 = pd.read_csv(gdf22) # 2023 # Right\\ngdf2.head(3)", "gdf1[\'geometry\'] = gdf1.apply(lambda row: Point(row.iloc[2], row.iloc[1]), axis=1)\\ngdf2[\'geometry\'] = gdf2.apply(lambda row: Point(row.iloc[2], row.iloc[1]), axis=1)\\n\\ngeo_gdf1 = gpd.GeoDataFrame(gdf1, geometry=\'geometry\', crs=\\"EPSG:32646\\") # 2024\\ngeo_gdf2 = gpd.GeoDataFrame(gdf2, geometry=\'geometry\', crs=\\"EPSG:32646\\") # 2023", "geo_gdf1", "glacier_gdf_01 = gpd.read_file(glacier_shp_path)\\nfig, ax = plt.subplots(figsize=(10, 12))  # Adjust figure size for higher resolution\\nglacier_gdf_01.plot(ax=ax,facecolor=\'none\',edgecolor=\'black\',linewidth=1.5,label=\\"Glacier boundary\\")\\n\\ngeo_gdf1.plot(ax=ax, color=\'blue\', alpha=0.6, markersize=30, label=\\"2025 dGPS survey track\\")  # Customize style for geo_gdf1\\ngeo_gdf2.plot(ax=ax, color=\'red\', alpha=0.6, markersize=30, label= \\"2024 dGPS survey track\\")  # Customize style for geo_gdf2\\n\\n# Add labels and legend\\nax.set_xlabel(\\"Easting (m)\\", fontsize=12)\\nax.set_ylabel(\\"Northing (m)\\", fontsize=12)\\nax.legend(fontsize=12, loc=\\"upper left\\")\\n\\nax.grid(visible=True, linestyle=\'--\', alpha=0.5)\\n\\n# Improve axis style\\nax.tick_params(axis=\'both\', labelsize=10)\\nplt.tight_layout()\\nplt.show()", "import matplotlib.patches as mpatches\\n\\nglacier_gdf_01 = gpd.read_file(glacier_shp_path)\\nfig, ax = plt.subplots(figsize=(8, 12))  # Adjust figure size\\n\\n# Plot glacier boundary (transparent fill)\\nglacier_gdf_01.plot(ax=ax, facecolor=\'none\', edgecolor=\'black\', linewidth=1.5)\\n\\n# Plot dGPS tracks\\ngeo_gdf1.plot(ax=ax, color=\'blue\', alpha=0.6, markersize=30, label=\\"2025 dGPS survey track\\")\\ngeo_gdf2.plot(ax=ax, color=\'red\', alpha=0.6, markersize=30, label=\\"2024 dGPS survey track\\")\\n\\n# Create manual legend patch for glacier boundary\\nboundary_patch = mpatches.Patch(facecolor=\'none\', edgecolor=\'black\', linewidth=1.5, label=\'Glacier boundary\')\\n\\n# Get existing legend handles (from tracks) and add boundary patch\\nhandles, labels = ax.get_legend_handles_labels()\\nhandles.append(boundary_patch)\\n\\n# Add legend\\nax.legend(handles=handles, loc=\\"upper left\\")\\n\\n# Labels, grid, ticks\\nax.set_xlabel(\\"Easting (m)\\")\\nax.set_ylabel(\\"Northing (m)\\")\\nax.grid(visible=True, linestyle=\'--\', alpha=0.5)\\nax.tick_params(axis=\'both\', labelsize=10)\\n\\nplt.tight_layout()\\nplt.savefig(os.path.join(output_dir, \\"dGPS_with_boundary.png\\"), dpi=300)\\nplt.show()", "coordinates = [(point.x, point.y) for point in geo_gdf1.geometry]\\nwith rasterio.open(raster_file ) as src:\\n    raster_values = list(src.sample(coordinates))\\n    geo_gdf1[\'raster_raw_value\'] = [val[0] for val in raster_values]\\n\\n    geo_gdf1[\'dgps_dem_diff\'] = np.abs(geo_gdf1[\'raster_raw_value\']-geo_gdf1[\'Elevation\'])\\n    dgps_dem_diff_avg = np.mean(geo_gdf1[\'dgps_dem_diff\']) # Bias correction approach using mean difference\\n\\n    from rasterio.plot import show\\n    fig, ax = plt.subplots()\\n    # transform rasterio plot to real world coords\\n    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]\\n    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap=\\"pink\\")\\n    geo_gdf1.plot(ax=ax)\\n    ax.set_title(\'Raw Dem\')\\n    profile = src.profile\\n    data = src.read(1) \\n\\n    corrected_dem_arr = data - dgps_dem_diff_avg\\n\\n    profile.update(dtype=\'float32\')  \\n\\nwith rasterio.open(corrected_dem, \\"w\\", **profile) as dst:\\n    dst.write(corrected_dem_arr.astype(\'float32\'), 1)\\n\\nwith rasterio.open(corrected_dem) as src:\\n    raster_values = list(src.sample(coordinates))\\n    geo_gdf1[\'raster_corr_value\'] = [val[0] for val in raster_values]\\n\\n    from rasterio.plot import show\\n    fig, ax = plt.subplots()\\n    # transform rasterio plot to real world coords\\n    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]\\n    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap=\\"pink\\")\\n    ax.set_title(\'Corr Dem\')\\n    geo_gdf1.plot(ax=ax)", "geo_gdf2.head(3)", "fig, ax = plt.subplots()\\nplt.plot( geo_gdf1[\'sorted_order\'],geo_gdf1[\'Elevation\'], label=\'dGPS\')\\nplt.plot( geo_gdf1[\'sorted_order\'],geo_gdf1[\'raster_raw_value\'], label=\'DEM-Sat-Raw\')\\nplt.legend()\\nplt.tight_layout\\nplt.savefig(os.path.join(output_dir, \\"difference_dem.png\\"),dpi=300)\\nplt.show()", "geo_gdf1[\'dem_corr\'] = geo_gdf1[\'raster_raw_value\'] - dgps_dem_diff_avg\\n\\nfig, ax = plt.subplots()\\nplt.plot(geo_gdf1[\'sorted_order\'],geo_gdf1[\'dgps_dem_diff\'])\\nplt.show()\\n\\nfig, ax = plt.subplots()\\nplt.plot(geo_gdf1[\'sorted_order\'],geo_gdf1[\'Elevation\'], label=\'dGPS\')\\nplt.plot(geo_gdf1[\'sorted_order\'],geo_gdf1[\'raster_corr_value\'], label=\'DEM-Sat-Correct\')\\nplt.legend()\\nplt.tight_layout()\\nplt.savefig(os.path.join(output_dir, \\"corrected_Dem.png\\"),dpi=300)\\nplt.show()\\n\\nfig, ax = plt.subplots()\\nplt.hist(geo_gdf1[\'dgps_dem_diff\'], bins=50)\\nplt.axvline(dgps_dem_diff_avg, color=\'red\', ls=\'--\', lw=2)\\nplt.show()", "# Step 1: Clip the Corrected DEM with the glacier outline\\nfrom rasterio.mask import mask\\ndef clip_dem(dem_path, glacier_shp_path, output_clipped_dem):\\n    # Load glacier shapefile\\n    glacier_gdf = gpd.read_file(glacier_shp_path)\\n    # Open the DEM\\n    with rasterio.open(dem_path) as dem_src:\\n        # Mask DEM with glacier geometry\\n        glacier_geometry = glacier_gdf.geometry\\n        clipped_dem, clipped_transform = mask(dem_src, glacier_geometry, crop=True)\\n        clipped_meta = dem_src.meta.copy()\\n\\n        # Update metadata for the clipped DEM\\n        clipped_meta.update({\\n            \\"driver\\": \\"GTiff\\",\\n            \\"height\\": clipped_dem.shape[1],\\n            \\"width\\": clipped_dem.shape[2],\\n            \\"transform\\": clipped_transform\\n        })\\n\\n        # Save the clipped DEM\\n        with rasterio.open(output_clipped_dem, \\"w\\", **clipped_meta) as dest:\\n            dest.write(clipped_dem)\\n    return output_clipped_dem\\n\\n# Step 2: Classify elevations and calculate area in each class\\ndef classify_and_calculate_area(path, elevation_interval=50):\\n    with rasterio.open(path) as src:\\n        dem_data = src.read(1)\\n        dem_data = dem_data[dem_data > 0]  # Filter out no-data values\\n        pixel_area = abs(src.transform[0] * src.transform[4])  # Calculate pixel area\\n\\n    # Classify elevations\\n    min_elevation = int(np.floor(dem_data.min()))\\n    max_elevation = int(np.ceil(dem_data.max()))\\n    \\n    bins = np.arange(min_elevation, max_elevation + elevation_interval, elevation_interval)\\n    print(bins)\\n    elevation_classes = np.digitize(dem_data, bins)\\n    print(elevation_classes)\\n\\n    # Calculate area for each elevation class\\n    area_per_class = []\\n    for i in range(1, len(bins)):\\n        area = (elevation_classes == i).sum() * pixel_area\\n        area_per_class.append(area)\\n    print(area_per_class)\\n\\n    return bins, area_per_class\\n\\ndef plot_elevation_vs_area(bins, area_per_class):\\n    mid_bins = (bins[:-1] + bins[1:]) / 2\\n    plt.figure()\\n    plt.barh(\\n        mid_bins, \\n        area_per_class, \\n        height=30,\\n        color=\\"skyblue\\",  \\n        edgecolor=\\"black\\", \\n        alpha=0.9\\n    )\\n    plt.xlabel(\\"Area (m\\u00b2)\\", fontsize=12)\\n    plt.ylabel(\\"Elevation (m)\\", fontsize=12)\\n    plt.grid(axis=\'x\', linestyle=\'--\', alpha=0.6)\\n    plt.xticks(fontsize=12)\\n    plt.yticks(mid_bins,fontsize=12)\\n    plt.tight_layout()\\n    plt.savefig(os.path.join(output_dir, \\"hypsometry.png\\"),dpi=450)\\n    plt.show()\\n    return mid_bins\\n\\nclipped_dem = clip_dem(corrected_dem, glacier_shp_path, output_clipped_dem)\\nprint(corrected_dem, output_clipped_dem)\\nelev_bins, area_per_class = classify_and_calculate_area(output_clipped_dem, elevation_interval=50)\\nmid_bins = plot_elevation_vs_area(elev_bins, area_per_class)\\nprint(\'Mid Bins\', mid_bins)\\nprint(area_per_class)", "coordinates = [(point.x, point.y) for point in geo_gdf2.geometry]\\nwith rasterio.open(raster_file ) as src:\\n    raster_values = list(src.sample(coordinates))\\n    geo_gdf2[\'raster_raw_value\'] = [val[0] for val in raster_values]\\n\\n    geo_gdf2[\'dgps_dem_diff\'] = np.abs(geo_gdf2[\'raster_raw_value\']-geo_gdf2[\'Elevation\'])\\n    dgps_dem_diff_avg1 = np.mean(geo_gdf2[\'dgps_dem_diff\']) # Bias correction approach using mean difference\\n\\n    from rasterio.plot import show\\n    fig, ax = plt.subplots()\\n    # transform rasterio plot to real world coords\\n    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]\\n    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap=\\"pink\\")\\n    geo_gdf2.plot(ax=ax)\\n    ax.set_title(\'Raw Dem\')\\n    profile = src.profile\\n    data = src.read(1) \\n\\n    corrected_dem_arr1 = data - dgps_dem_diff_avg1\\n\\n    profile.update(dtype=\'float32\')  \\n\\nwith rasterio.open(corrected_dem1, \\"w\\", **profile) as dst:\\n    dst.write(corrected_dem_arr1.astype(\'float32\'), 1)\\n\\nwith rasterio.open(corrected_dem1) as src:\\n    raster_values = list(src.sample(coordinates))\\n    geo_gdf2[\'raster_corr_value\'] = [val[0] for val in raster_values]\\n\\n    from rasterio.plot import show\\n    fig, ax = plt.subplots()\\n    # transform rasterio plot to real world coords\\n    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]\\n    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap=\\"pink\\")\\n    ax.set_title(\'Corr Dem\')\\n    geo_gdf2.plot(ax=ax)", "geo_gdf2[\'dem_corr\'] = geo_gdf2[\'raster_raw_value\'] - dgps_dem_diff_avg1\\n\\nfig, ax = plt.subplots()\\nplt.plot(geo_gdf2[\'sorted_order\'],geo_gdf2[\'dgps_dem_diff\'])\\nplt.show()\\n\\nfig, ax = plt.subplots()\\nplt.plot(geo_gdf2[\'Elevation\'], label=\'dGPS\')\\nplt.plot(geo_gdf2[\'raster_corr_value\'], label=\'DEM-Sat-Correct\')\\nplt.legend()\\nplt.show()\\n\\nfig, ax = plt.subplots()\\nplt.hist(geo_gdf2[\'dgps_dem_diff\'], bins=50)\\nplt.axvline(dgps_dem_diff_avg1, color=\'red\', ls=\'--\', lw=2)", "# Step 1: Clip the Corrected DEM with the glacier outline\\nfrom rasterio.mask import mask\\ndef clip_dem(dem_path, glacier_shp_path, output_clipped_dem1):\\n    # Load glacier shapefile\\n    glacier_gdf2 = gpd.read_file(glacier_shp_path)\\n    # Open the DEM\\n    with rasterio.open(dem_path) as dem_src:\\n        # Mask DEM with glacier geometry\\n        glacier_geometry2 = glacier_gdf2.geometry\\n        clipped_dem1, clipped_transform = mask(dem_src, glacier_geometry2, crop=True)\\n        clipped_meta1 = dem_src.meta.copy()\\n\\n        # Update metadata for the clipped DEM\\n        clipped_meta1.update({\\n            \\"driver\\": \\"GTiff\\",\\n            \\"height\\": clipped_dem1.shape[1],\\n            \\"width\\": clipped_dem1.shape[2],\\n            \\"transform\\": clipped_transform\\n        })\\n\\n        # Save the clipped DEM\\n        with rasterio.open(output_clipped_dem1, \\"w\\", **clipped_meta1) as dest:\\n            dest.write(clipped_dem1)\\n    return output_clipped_dem1\\n\\n# Step 2: Classify elevations and calculate area in each class\\ndef classify_and_calculate_area(path, elevation_interval=50):\\n    with rasterio.open(path) as src:\\n        dem_data = src.read(1)\\n        dem_data = dem_data[dem_data > 0]  # Filter out no-data values\\n        pixel_area = abs(src.transform[0] * src.transform[4])  # Calculate pixel area\\n\\n    # Classify elevations\\n    min_elevation = elev_bins[0]\\n    max_elevation = elev_bins[-1]\\n    \\n    bins = np.arange(min_elevation, max_elevation + elevation_interval, elevation_interval)\\n    print(bins)\\n    elevation_classes = np.digitize(dem_data, bins)\\n    print(elevation_classes)\\n\\n    # Calculate area for each elevation class\\n    area_per_class1 = []\\n    for i in range(1, len(bins)):\\n        area1 = (elevation_classes == i).sum() * pixel_area\\n        area_per_class1.append(area1)\\n    print(area_per_class1)\\n\\n    return bins, area_per_class1\\n\\ndef plot_elevation_vs_area(bins, area_per_class1):\\n    mid_bins = (bins[:-1] + bins[1:]) / 2\\n    plt.figure()\\n    plt.barh(\\n        mid_bins, \\n        area_per_class1, \\n        height=30,\\n        color=\\"skyblue\\",  \\n        edgecolor=\\"black\\", \\n        alpha=0.9\\n    )\\n    plt.xlabel(\\"Area (m\\u00b2)\\", fontsize=12)\\n    plt.ylabel(\\"Elevation (m)\\", fontsize=12)\\n    plt.grid(axis=\'x\', linestyle=\'--\', alpha=0.6)\\n    plt.xticks(fontsize=12)\\n    plt.yticks(mid_bins,fontsize=12)\\n    plt.tight_layout()\\n    plt.savefig(os.path.join(output_dir, \\"hypsometry.png\\"),dpi=450)\\n    plt.show()\\n    return mid_bins\\n\\nclipped_dem1 = clip_dem(corrected_dem1, glacier_shp_path, output_clipped_dem1)\\nprint(corrected_dem1, output_clipped_dem1)\\nelev_bins, area_per_class1 = classify_and_calculate_area(output_clipped_dem1, elevation_interval=50)\\nmid_bins = plot_elevation_vs_area(elev_bins, area_per_class1)\\nprint(\'Mid Bins\', mid_bins)\\nprint(area_per_class1)", "def plot_hypsometry_comparison(bins_a, area_a, bins_b, area_b,\\n                              label_a=\\"DEM A\\", label_b=\\"DEM B\\"):\\n    # --- If bins differ, restrict to their common range ---\\n    if not np.array_equal(bins_a, bins_b):\\n        raise ValueError(\\"Elevation bins differ between the two datasets. \\"\\n                        \\"Re-bin them to a common set before plotting.\\")\\n\\n    # Mid-points for elevation bands\\n    mid_bins = (bins_a[:-1] + bins_a[1:]) / 2\\n    bar_height = int(bins_a[1] - bins_a[0])  # should be 50 m\\n\\n    plt.figure(figsize=(8, 6))\\n\\n    # Calculate bar dimensions for perfect stacking\\n    bar_height_half = bar_height * 0.4\\n    offset = bar_height_half  # Offset for the second bar\\n\\n    # First dataset - top half\\n    plt.barh(\\n        mid_bins + offset/2,  # Position in the top half\\n        area_a,\\n        height=bar_height_half,  # Half the total height\\n        color=\\"skyblue\\",\\n        edgecolor=\\"black\\",\\n        alpha=0.8,\\n        label=label_a,\\n    )\\n\\n    # Second dataset - bottom half\\n    plt.barh(\\n        mid_bins - offset/2,  # Position in the bottom half\\n        area_b,\\n        height=bar_height_half,  # Half the total height\\n        color=\\"blue\\",\\n        edgecolor=\\"black\\",\\n        alpha=0.5,\\n        label=label_b,\\n        linewidth=1\\n    )\\n\\n    plt.xlabel(\\"Area (m\\u00b2)\\", fontsize=12)\\n    plt.ylabel(\\"Elevation (m)\\", fontsize=12)\\n\\n    # y-axis ticks exactly at the centre of the combined bars\\n    plt.yticks(mid_bins, labels=mid_bins.astype(int), fontsize=12)\\n\\n\\n    # Grid only in x direction, alpha 0.5\\n    plt.grid(axis=\\"x\\", linestyle=\\"--\\", alpha=0.5)\\n\\n    plt.xticks(np.round(plt.xticks()[0]).astype(int))\\n    plt.legend(fontsize=11)\\n    plt.tight_layout()\\n\\n    plt.show()", "# Old / auto-binned\\nelev_bins, area_per_class = classify_and_calculate_area(output_clipped_dem, elevation_interval=50)\\n\\n# New / fixed 4873\\u20135173\\nelev_bins1, area_per_class1 = classify_and_calculate_area(output_clipped_dem1, elevation_interval=50)\\n\\n# Plot comparison\\nplot_hypsometry_comparison(\\n    elev_bins,\\n    area_per_class,\\n    elev_bins1,\\n    area_per_class1,\\n    label_a=\\"2025\\",\\n    label_b=\\"2024\\"\\n)", "# Perform the nearest spatial join with a max distance of 50 meters\\nmerged_gdf = gpd.sjoin_nearest(\\n    geo_gdf1, \\n    geo_gdf2, \\n    how=\\"inner\\", \\n    distance_col=\\"nearest_distance\\", \\n    max_distance=50\\n)\\nmerged_gdf.head(3)", "merged_gdf.shape", "fig, ax = plt.subplots()\\nax.scatter(\\n    merged_gdf[\'nearest_distance\'], \\n    merged_gdf[\'Elevation_right\'], \\n    color=\'darkblue\', \\n    # edgecolor=\'black\', \\n    alpha=0.8, \\n    s=20,\\n)\\nax.set_xlabel(\'Merged distance (m)\', fontsize=12)\\nax.set_ylabel(\'Elevation (m)\', fontsize=12)\\nax.grid(linestyle=\'--\', alpha=0.6)\\nax.tick_params(axis=\'both\', labelsize=12)\\nplt.tight_layout()\\nplt.show()", "fig, ax = plt.subplots()\\nax.plot(\\n    range(merged_gdf[\'raster_corr_value_left\'].shape[0]), \\n    merged_gdf[\'raster_corr_value_left\'], \\n    label=\'DEM-Sat\', \\n    color=\'blue\', \\n    linewidth=2, \\n    linestyle=\'-\'\\n)\\nax.plot(\\n    range(merged_gdf[\'Elevation_left\'].shape[0]), \\n    merged_gdf[\'Elevation_left\'], \\n    label=\'dGPS 2024\', \\n    color=\'green\', \\n    linewidth=2, \\n    linestyle=\'--\'\\n)\\nax.plot(\\n    range(merged_gdf[\'Elevation_right\'].shape[0]), \\n    merged_gdf[\'Elevation_right\'], \\n    label=\'dGPS 2023\', \\n    color=\'red\', \\n    linewidth=2, \\n    linestyle=\':\'\\n)\\nax.legend(\\n    fontsize=12, \\n    loc=\'best\', \\n    frameon=True, \\n    framealpha=0.8, \\n    edgecolor=\'black\'\\n)\\nax.set_xlabel(\'Smaples\', fontsize=12)\\nax.set_ylabel(\'Elevation Values (m)\', fontsize=12)\\nax.grid(linestyle=\'--\', alpha=0.6)\\nax.tick_params(axis=\'both\', labelsize=12)\\nplt.tight_layout()\\nplt.show()", "merged_gdf[\'elev_diff\'] = merged_gdf[\'Elevation_left\'] - merged_gdf[\'Elevation_right\'] # e.g., 5m (2023)  2m in (2024): 2m - 5m\\ngdf_threshold = merged_gdf[(merged_gdf[\'nearest_distance\'] <= distance_threshold) & (merged_gdf[\'elev_diff\'] != 0)]\\ngdf_threshold.head(3)\\nprint(gdf_threshold.shape)", "x_elev = gdf_threshold[\'Elevation_left\'].astype(float).values.reshape(-1, 1)\\ny_diff = gdf_threshold[\'elev_diff\'].values\\ntheil_sen_non_agg = TheilSenRegressor(random_state=42).fit(x_elev, y_diff)\\npred_diff_values = theil_sen_non_agg.predict(x_elev)\\n\\nplt.figure()\\nplt.scatter(\\n    gdf_threshold[\'Elevation_left\'],\\n    y_diff,\\n    color=\'royalblue\', \\n    edgecolor=\'black\', \\n    alpha=0.7, \\n    label=\'Data points\'\\n)\\nplt.plot(\\n    gdf_threshold[\'Elevation_left\'],\\n    pred_diff_values,\\n    color=\'darkred\', \\n    linewidth=2, \\n    linestyle=\'--\', \\n    label=\'Theil-Sen regression line\'\\n)\\n\\nplt.ylabel(\'Elevation difference (m)\', fontsize=12)\\nplt.xlabel(\'Elevation (m)\', fontsize=12)\\nplt.legend(fontsize=12, loc=\'best\')\\n\\nplt.grid(linestyle=\'--\', alpha=0.6)\\nplt.xticks(fontsize=12)\\nplt.yticks(fontsize=12)\\nplt.tight_layout()\\nplt.savefig(os.path.join(output_dir, \\"elevation.png\\"),dpi=300)\\nplt.show()", "fig, ax = plt.subplots()\\nn, bin, patches = plt.hist(\\n    gdf_threshold[\'elev_diff\'], \\n    bins=20, \\n    color=\'skyblue\', \\n    edgecolor=\'black\', \\n    alpha=0.7\\n)\\nmean_value = gdf_threshold[\'elev_diff\'].mean()\\nplt.axvline(mean_value, color=\'red\', linestyle=\'--\', linewidth=2, label=f\'Mean = {mean_value:.2f}\')\\n\\nfor i in range(len(n)):\\n    plt.text(bin[i] + (bin[i+1] - bin[i]) / 2, n[i] + 0.5, f\\"{int(n[i])}\\", \\n             ha=\'center\', va=\'bottom\', fontsize=10, color=\'black\')\\n\\nplt.xlabel(\'Elevation difference (m)\', fontsize=14)\\nplt.ylabel(\'Frequency\', fontsize=14)\\nplt.xticks(fontsize=12)\\nplt.yticks(fontsize=12)\\nplt.grid(axis=\'y\', linestyle=\'--\', alpha=0.7)\\nplt.legend(fontsize=12)\\nplt.tight_layout()\\nplt.savefig(os.path.join(output_dir, \\"Frequency.png\\"),dpi=300)\\nplt.show()", "xx_elev = gdf_threshold[\'elev_diff\'].astype(float).values.reshape(-1, 1)\\nyy_diff = gdf_threshold[\'Elevation_left\'].values\\ntheil_sen_lg = TheilSenRegressor(random_state=42).fit(xx_elev, yy_diff)\\npredicted_values = theil_sen_lg.predict(xx_elev)\\n\\nplt.figure()\\nplt.scatter(\\n    gdf_threshold[\'elev_diff\'], \\n    gdf_threshold[\'Elevation_left\'], \\n    color=\'royalblue\', \\n    edgecolor=\'black\', \\n    alpha=0.7, \\n    label=\'Data points\'\\n)\\nplt.plot(\\n    gdf_threshold[\'elev_diff\'], \\n    predicted_values, \\n    color=\'darkred\', \\n    linewidth=2, \\n    linestyle=\'--\', \\n    label=\'Theil-Sen regression line\'\\n)\\n\\nplt.xlabel(\'Elevation difference (m)\', fontsize=12)\\nplt.ylabel(\'Elevation (m)\', fontsize=12)\\nplt.legend(fontsize=12, loc=\'best\')\\n\\nplt.grid(linestyle=\'--\', alpha=0.6)\\nplt.xticks(fontsize=12)\\nplt.yticks(fontsize=12)\\nplt.tight_layout()\\nplt.show()", "# Use pandas `cut` function to categorize \'raster_value\' into bins\\ngdf_threshold = gdf_threshold.copy()\\ngdf_threshold[\'elevation_bin\'] = pd.cut(gdf_threshold[\'Elevation_left\'], bins=elev_bins, right=False)", "gdf_threshold.tail(3) # Check the output", "# Group by the elevation bins and calculate count and average\\nbin_stats = gdf_threshold.groupby(\'elevation_bin\', observed=False)[\'elev_diff\'].agg(\\n    count=\'count\', \\n    average_elev_diff=\'mean\'\\n).reset_index()\\n\\n# Print the result\\nbin_stats.shape", "bin_stats", "import numpy as np\\nimport pandas as pd\\nfrom sklearn.linear_model import TheilSenRegressor\\n\\n# --- 1) Build bin stats (raw means) ---\\nbin_stats = (\\n    gdf_threshold\\n    .groupby(\'elevation_bin\', observed=False)[\'elev_diff\']\\n    .agg(count=\'count\', average_elev_diff=\'mean\')\\n    .reset_index()\\n)\\n\\n# midpoint elevation for each bin\\nbin_stats[\'mean_bin\'] = bin_stats[\'elevation_bin\'].apply(\\n    lambda itv: (itv.left + itv.right) / 2\\n)\\n\\n# --- 2) Fit regression ONLY on bins that have raw data ---\\ntrain = bin_stats.dropna(subset=[\'average_elev_diff\']).copy()\\n\\nX_train = train[\'mean_bin\'].to_numpy().reshape(-1, 1)\\ny_train = train[\'average_elev_diff\'].to_numpy()\\n\\ntheil_sen = TheilSenRegressor(random_state=42)\\ntheil_sen.fit(X_train, y_train)\\n\\n# --- 3) Predict for ALL bins (including empty ones) ---\\nX_all = bin_stats[\'mean_bin\'].to_numpy().reshape(-1, 1)\\nbin_stats[\'pred_mean\'] = theil_sen.predict(X_all)\\n\\n# --- 4) Hybrid: use raw where available, else predicted ---\\nbin_stats[\'final_mean\'] = bin_stats[\'average_elev_diff\'].fillna(bin_stats[\'pred_mean\'])\\n\\n# Optional: flag which values were filled\\nbin_stats[\'source\'] = np.where(bin_stats[\'average_elev_diff\'].isna(), \'predicted\', \'raw\')\\n\\n# Result you want:\\n# mean_bin = mid-bin elevation\\n# final_mean = raw mean if exists else predicted", "# Calculate the mean of each interval in the elevation_bin column\\nbin_stats[\'mean_bin\'] = bin_stats[\'elevation_bin\'].apply(lambda interval: (interval.left + interval.right) / 2)\\n\\n\\nbin_stats[\'area\'] = area_per_class \\nbin_stats[\'area1\'] = area_per_class1\\nbin_stats[\'area_average\'] = (bin_stats[\'area\']+bin_stats[\'area1\']) / 2\\n\\nbin_stats[\'diff_pred\'] = bin_stats[\'final_mean\']", "print(area_per_class)\\nprint(area_per_class1)", "bin_stats", "bin_stats[\'amb\'] = (880 * bin_stats[\'diff_pred\'] * bin_stats[\'area_average\'])\\nbin_stats", "\\nif snd1 is not None and os.path.exists(snd1):\\n    snd11.head(7)\\n    \\n    snd11.sort_values(by = \'Elevation\')\\nelse:\\n    print(\\"snd1 not provided or file missing\\")\\n\\nif snd2 is not None and os.path.exists(snd2):\\n    snd22.head(7)\\n    \\n    snd22.sort_values(by = \'Elevation\')\\nelse:\\n    print(\\"snd2 not provided or file missing\\")\\n\\nif snd1 is not None:\\n    print(snd11.head(3))\\n\\nif snd2 is not None:\\n    print(snd22.head(3))", "from sklearn.linear_model import LinearRegression\\nimport matplotlib.pyplot as plt\\n\\nif snd1 is not None and os.path.exists(snd1):\\n    # Assuming snd11 is defined somewhere above this snippet if needed\\n    # For this snippet to run, you likely need a definition:\\n    # snd11 = pd.read_csv(snd1) \\n\\n    x_snd1 = snd11[\'Elevation\'].astype(float).values.reshape(-1, 1)\\n    y_snd1 = snd11[\'Snow_depth\'].values\\n\\n    # --- Fit normal linear regression ---\\n    lin_reg = LinearRegression().fit(x_snd1, y_snd1)\\n\\n    # --- Scatter plot of data points ---\\n    plt.figure()\\n    plt.scatter(\\n        x_snd1, \\n        y_snd1,\\n        color=\'royalblue\', \\n        edgecolor=\'black\', \\n        alpha=0.7, \\n        label=\'Stake locations\'\\n    )\\n\\n    # --- Regression line ---\\n    plt.plot(\\n        x_snd1,  # or x_snd if defined elsewhere\\n        lin_reg.predict(x_snd1),\\n        color=\'darkred\', \\n        linewidth=2, \\n        linestyle=\'--\', \\n        label=\'Linear regression line\'\\n    )\\n\\n    plt.grid(linestyle=\'--\', alpha=0.6)\\n    plt.xlabel(\'Elevation (m)\')\\n    plt.ylabel(\'Snow depth (m)\')\\n    plt.legend()\\n    # Use plt.show() to display the plot window\\n    plt.show() \\n\\n    # --- Predict for mid-bin values ---\\n    mid_bin1 = bin_stats[\'mean_bin\'].astype(float).values.reshape(-1, 1)\\n    mid_bin_snd1 = lin_reg.predict(mid_bin1)\\n\\n    # Use print() to display these values in the console\\n    print(mid_bin1)\\n    print(mid_bin_snd1)\\n    # --- Prepare data ---\\n\\nelse:\\n    print(\\"no files\\")", "\\nif snd2 is not None and os.path.exists(snd2):\\n    # --- Prepare data ---\\n    x_snd2 = snd22[\'Elevation\'].astype(float).values.reshape(-1, 1)\\n    y_snd2 = snd22[\'Snow_depth\'].values\\n\\n    # --- Fit normal linear regression ---\\n    lin_reg = LinearRegression().fit(x_snd2, y_snd2)\\n\\n    # --- Scatter plot of data points ---\\n    plt.figure()\\n    plt.scatter(\\n        x_snd2, \\n        y_snd2,\\n        color=\'royalblue\', \\n        edgecolor=\'black\', \\n        alpha=0.7, \\n        label=\'Stake locations\'\\n    )\\n\\n    # --- Regression line ---\\n    plt.plot(\\n        x_snd2,  # or x_snd if defined elsewhere\\n        lin_reg.predict(x_snd2),\\n        color=\'darkred\', \\n        linewidth=2, \\n        linestyle=\'--\', \\n        label=\'Linear regression line\'\\n    )\\n\\n    plt.grid(linestyle=\'--\', alpha=0.6)\\n    plt.xlabel(\'Elevation (m)\')\\n    plt.ylabel(\'Snow depth (m)\')\\n    plt.legend()\\n    plt.show()\\n\\n    # --- Predict for mid-bin values ---\\n    mid_bin2 = bin_stats[\'mean_bin\'].astype(float).values.reshape(-1, 1)\\n    mid_bin_snd2 = lin_reg.predict(mid_bin2)\\n    mid_bin_snd2 = np.where(mid_bin_snd2 > 0, mid_bin_snd2, 0)\\n\\n\\n    print(mid_bin2)\\n    print(mid_bin_snd2)\\nelse:\\n   print(\\"no such files\\")", "bin_stats", "\\nif (\\n    snd1 is not None and os.path.exists(snd1) and\\n    snd2 is not None and os.path.exists(snd2)\\n):\\n    bin_stats[\'snow_depth_2024\'] = mid_bin_snd1\\n    bin_stats[\'snow_depth_2025\'] = mid_bin_snd2\\n    bin_stats[\'diff_snow_depth_2025\'] = mid_bin_snd2 - mid_bin_snd1\\nelse:\\n    print(\\"snow files not fully provided or missing\\")", "\\nif (\\n    snd1 is not None and os.path.exists(snd1) and\\n    snd2 is not None and os.path.exists(snd2)\\n):\\n    bin_stats[\'Annual_MB\'] = (\\n        880 * bin_stats[\'diff_pred\']\\n        + bin_stats[\'diff_snow_depth_2025\'] * (400 - 880)\\n    )\\nelse:\\n    bin_stats[\'Annual_MB_no_snow\'] = (880 * bin_stats[\'diff_pred\'])", "bin_stats", "\\nif \'Annual_MB\' in bin_stats.columns:\\n    amb = np.sum(bin_stats[\'Annual_MB\'] * bin_stats[\'area_average\']) / np.sum(bin_stats[\'area_average\'])\\n    print(amb)\\nelse:\\n    amb = np.sum(bin_stats[\'Annual_MB_no_snow\'] * bin_stats[\'area_average\']) / np.sum(bin_stats[\'area_average\'])\\n    print(f\\"Mass balance(no snow) is:\'{amb}\'\\")", "x_agg = bin_stats[\'mean_bin\'].astype(float).values.reshape(-1, 1)\\ny_agg = bin_stats[\'average_elev_diff\'].values\\narea = bin_stats[\'area\'].values\\nmask = ~np.isnan(y_agg)\\nx_agg_clean = x_agg[mask]\\ny_agg_clean = y_agg[mask]\\narea_clean = area[mask]\\n\\ntheil_sen_agg = TheilSenRegressor().fit(x_agg_clean, y_agg_clean)\\n\\nfig, ax1 = plt.subplots(figsize=(10,6))\\nax1.scatter(x_agg_clean, y_agg_clean, color=\'blue\', label=\'Elevation difference\')\\nax1.plot(x_agg_clean, theil_sen_agg.predict(x_agg_clean), color=\'blue\', label=\'Theil-Sen regression line\')\\nax1.set_xlabel(\'Elevation (mean_bin)\',fontsize=14)\\nax1.set_ylabel(\'Elevation difference (m)\', color=\'blue\',fontsize=14)\\nax1.tick_params(axis=\'y\', labelcolor=\'blue\')\\nax1.legend(loc=\'upper left\')\\nax1.grid(True, linestyle=\'--\', alpha=0.6)\\n\\nax2 = ax1.twinx()\\nax2.scatter(x_agg_clean, area_clean, color=\'red\', marker=\'o\', alpha=0.7,label=\'Glacier area(m$^2$)\')\\nax2.set_ylabel(\'Glacier area (m$^2$)\', color=\'red\',fontsize=14)\\nax2.tick_params(axis=\'y\', labelcolor=\'red\')\\nplt.legend(loc=\'upper left\', bbox_to_anchor=(0.004, 0.86))\\nplt.savefig(os.path.join(output_dir, \\"elevation.png\\"),dpi=450)\\nplt.show()", "bin_stats[\'diff_pred2\'] = theil_sen_agg.predict(x_agg)\\n\\nif snd1 is not None and os.path.exists(snd1):\\n    bin_stats[\'Annual_MB_Aggregated\'] = (880 * bin_stats[\'diff_pred2\']+ bin_stats[\'diff_snow_depth_2025\'] * (400-880))\\nelse:\\n    bin_stats[\'Annual_MB_Aggregated\'] = (880 * bin_stats[\'diff_pred2\'])\\n    \\nbin_stats", "amb2 = np.sum(bin_stats[\'Annual_MB_Aggregated\']* bin_stats[\'area_average\'])/np.sum(bin_stats[\'area_average\'])\\nprint(amb2)", "amb_agg_data = np.sum(bin_stats[\'Annual_MB_Aggregated\']* bin_stats[\'area_average\'])/np.sum(bin_stats[\'area_average\'])\\namb_agg_data\\nnp.sum(bin_stats[\'area\'])/1000000\\n\\namb_array = [amb, amb_agg_data]\\nprint(amb_array)\\n\\nlabels = [\'Non-aggregated data\', \'Aggregated data\']\\n\\nplt.figure()\\nbars = plt.bar(labels, amb_array, color=[\'steelblue\', \'orange\'], alpha=0.8, edgecolor=\'black\')\\n\\nfor bar in bars:\\n    height = bar.get_height()\\n    plt.text(\\n        bar.get_x() + bar.get_width() / 2,\\n        height, \\n        f\\"{height:.2f}\\", \\n        ha=\'center\', \\n        va=\'bottom\' if height > 0 else \'top\',\\n        fontsize=12,\\n        color=\'black\'\\n    )\\nplt.ylabel(\'Annual mass balance (mm w.e.a)\', fontsize=12)\\nplt.grid(axis=\'y\', linestyle=\'--\', alpha=0.6)\\nplt.xticks(fontsize=12)\\nplt.yticks(fontsize=12)\\nplt.axhline(0, color=\'black\', linewidth=1)\\nplt.tight_layout()\\nplt.show()", "\\n\\n# --------------------------------------------------------------------\\n# 1. Get glacier boundary segments\\n# --------------------------------------------------------------------\\n\\nfrom shapely.geometry import LineString, MultiLineString\\ndef get_boundary_segments(glacier_shp_path):\\n    gdf = gpd.read_file(glacier_shp_path)\\n    boundary = gdf.geometry.boundary.unary_union\\n\\n    if boundary.geom_type == \\"MultiLineString\\":\\n        lines = list(boundary.geoms)\\n    else:\\n        lines = [boundary]\\n\\n    segments = []\\n    for line in lines:\\n        coords = list(line.coords)\\n        for i in range(len(coords) - 1):\\n            segments.append((coords[i], coords[i + 1]))\\n\\n    return segments, gdf.crs\\n\\n# --------------------------------------------------------------------\\n# 2. Sample DEM elevation at coordinate points\\n# --------------------------------------------------------------------\\ndef get_elevation_for_coords(dem_path, coords):\\n    \\"\\"\\"\\n    Samples elevation from DEM at given (x, y) coordinates.\\n    Returns a numpy array of elevation values.\\n    \\"\\"\\"\\n    with rasterio.open(dem_path) as src:\\n        band = src.read(1)\\n        values = []\\n        for x, y in coords:\\n            row, col = src.index(x, y)\\n            elev = band[row, col]\\n            values.append(elev)\\n    return np.array(values)\\n\\n# --------------------------------------------------------------------\\n# 3. Compute boundary length in fixed elevation bands (5101\\u20135501)\\n# --------------------------------------------------------------------\\ndef compute_segment_band_lengths_fixed(segments, start_elev, end_elev, interval=50):\\n    \\"\\"\\"\\n    Computes total boundary length in each elevation band, using\\n    a fixed elevation range from 5101 m to 5501 m with given interval.\\n    \\"\\"\\"\\n    avg_elevations = (start_elev + end_elev) / 2.0\\n\\n    # --- FIXED BIN RANGE HERE ---\\n    min_elev = elev_bins[0]\\n    max_elev = elev_bins[-1]\\n    bins = np.arange(min_elev, max_elev + interval, interval)\\n    # ----------------------------\\n\\n    labels = [f\\"{int(bins[i])}-{int(bins[i+1])} m\\" for i in range(len(bins) - 1)]\\n\\n    # Digitize avg elevations into these fixed bins\\n    band_indices = np.digitize(avg_elevations, bins) - 1  # shift to 0-based\\n\\n    band_lengths = {}\\n    for (p1, p2), band_idx in zip(segments, band_indices):\\n        if 0 <= band_idx < len(labels):\\n            band = labels[band_idx]\\n            length = np.hypot(p2[0] - p1[0], p2[1] - p1[1])  # length in CRS units (e.g. meters)\\n            band_lengths[band] = band_lengths.get(band, 0) + length\\n\\n    df = pd.DataFrame(\\n        list(band_lengths.items()),\\n        columns=[\\"Elevation Band\\", \\"Boundary Length (m)\\"]\\n    ).sort_values(\\"Elevation Band\\")\\n\\n    return df, bins\\n\\n# --------------------------------------------------------------------\\n# 4. Create segment GeoDataFrame using same fixed bins\\n# --------------------------------------------------------------------\\ndef create_segment_gdf_fixed(segments, start_elev, end_elev, crs, interval=50):\\n    \\"\\"\\"\\n    Creates a GeoDataFrame of boundary segments, each labeled with an\\n    elevation band using the fixed 5101\\u20135501 m range.\\n    \\"\\"\\"\\n    avg_elevations = (start_elev + end_elev) / 2.0\\n\\n    # --- FIXED BIN RANGE HERE ---\\n    min_elev = elev_bins[0]\\n    max_elev = elev_bins[-1]\\n    bins = np.arange(min_elev, max_elev + interval, interval)\\n    # ----------------------------\\n\\n    labels = [f\\"{int(bins[i])}-{int(bins[i+1])} m\\" for i in range(len(bins) - 1)]\\n    band_indices = np.digitize(avg_elevations, bins) - 1\\n\\n    bands = [labels[i] if 0 <= i < len(labels) else None for i in band_indices]\\n    lines = [LineString([p1, p2]) for (p1, p2) in segments]\\n\\n    gdf = gpd.GeoDataFrame(\\n        {\\n            \\"geometry\\": lines,\\n            \\"Elevation Band\\": bands\\n        },\\n        crs=crs\\n    )\\n\\n    return gdf\\n\\n# --------------------------------------------------------------------\\n# 5. Plot segments colored by elevation band\\n# --------------------------------------------------------------------\\ndef plot_segments_by_band(segment_gdf):\\n    \\"\\"\\"\\n    Plots glacier boundary segments colored by elevation band.\\n    \\"\\"\\"\\n    fig, ax = plt.subplots(figsize=(10, 10))\\n    segment_gdf.plot(\\n        ax=ax,\\n        column=\\"Elevation Band\\",\\n        cmap=\\"viridis\\",\\n        linewidth=2,\\n        legend=True\\n    )\\n    ax.set_title(\\"Glacier Boundary Segments by Elevation Band\\", fontsize=14)\\n    ax.set_axis_off()\\n    plt.tight_layout()\\n    plt.show()\\n\\n# --------------------------------------------------------------------\\n# 6. USAGE EXAMPLE\\n# --------------------------------------------------------------------\\n# Make sure these paths are defined before running:\\n# glacier_shp_path = r\\"path\\\\to\\\\your\\\\glacier.shp\\"\\n# corrected_dem    = r\\"path\\\\to\\\\your\\\\corrected_dem.tif\\"\\n\\n# Get boundary segments and CRS\\nsegments, crs = get_boundary_segments(glacier_shp_path)\\n\\n# Build list of coords (start and end of each segment)\\nstart_coords = [seg[0] for seg in segments]\\nend_coords   = [seg[1] for seg in segments]\\nall_coords   = start_coords + end_coords\\n\\n# Sample DEM elevations at all these coords\\nelevations_raw = get_elevation_for_coords(corrected_dem, all_coords)\\n\\n# Split into start and end elevation arrays\\nstart_elev = elevations_raw[:len(segments)]\\nend_elev   = elevations_raw[len(segments):]\\n\\n# Compute boundary lengths in fixed bands 5101\\u20135501 m\\ndf_result, used_bins = compute_segment_band_lengths_fixed(\\n    segments, start_elev, end_elev, interval=50\\n)\\n\\nprint(\\"Boundary length per elevation band:\\")\\nprint(df_result)\\nprint(\\"\\\\nBins used:\\", used_bins)\\n\\n\\n# Create GeoDataFrame of segments with band labels and plot\\nsegment_gdf = create_segment_gdf_fixed(\\n    segments, start_elev, end_elev, crs, interval=50\\n)\\n\\nplot_segments_by_band(segment_gdf)\\ndf_result", "df_result", "bin_stats[\'Perimeter\'] = df_result[\'Boundary Length (m)\'].values", "bin_stats", "if snd1 is not None and os.path.exists(snd1) and snd2 is not None and os.path.exists(snd2):\\n    mb_col = \'Annual_MB\'\\nelse:\\n    mb_col = \'Annual_MB_no_snow\'\\n\\nbin_stats[\'Area_Average_MB\'] = (\\n    bin_stats[mb_col] * bin_stats[\'area_average\']\\n) / np.sum(bin_stats[\'area_average\'])", "bin_stats", "\\n#for you to use this code you should have csv file with column name bg(area average mass balance),Absolute bg,Average Area and Per\\n# Constants\\nPIXEL_CONSTANT = 10\\nUNCERTAINTY_ICE_DENSITY = 30\\nUNCERTAINTY_SNOW_DENSITY = 100\\n\\n# Load CSV\\n\\n\\n# Clean column names\\nbin_stats.columns = bin_stats.columns.str.strip().str.replace(\'\\\\xa0\', \' \', regex=True)\\nbin_stats[\'Absolute bg\']=abs(bin_stats[\'Area_Average_MB\'])\\n# ---- STEP 1: Average of bg ----\\navg_bg = bin_stats[\'Area_Average_MB\'].mean()\\n\\n# ---- STEP 2: Total Area Average ----\\ntotal_area_avg = bin_stats[\'area\'].sum()\\n\\n# ---- STEP 3: (x - X)^2 ----\\nbin_stats[\'(x - X)^2\'] = (bin_stats[\'Area_Average_MB\'] - avg_bg) ** 2\\n\\n# ---- STEP 4: Total Summation of (x - X)^2 ----\\ntotal_summation = bin_stats[\'(x - X)^2\'].sum()\\n\\n# ---- STEP 5: dbz ----\\ndbz = np.sqrt(total_summation / len(bin_stats))\\n\\n# ---- STEP 6: dAz = 0.5 * pixel * Perimeter ----\\nbin_stats[\'dAz\'] = 0.5 * PIXEL_CONSTANT * bin_stats[\'Perimeter\']\\n\\n# ---- STEP 7: Uncertainty for Ice ----\\nbin_stats[\'Uncertainty Ice\'] = (\\n    (bin_stats[\'area\'] * dbz) +\\n    (bin_stats[\'dAz\'] * bin_stats[\'Absolute bg\']) +\\n    (bin_stats[\'area\'] * UNCERTAINTY_ICE_DENSITY)\\n) / total_area_avg\\n\\n# ---- STEP 8: Uncertainty for Snow ----\\nbin_stats[\'Uncertainty Snow\'] = (\\n    (bin_stats[\'area\'] * dbz) +\\n    (bin_stats[\'dAz\'] * bin_stats[\'Absolute bg\']) +\\n    (bin_stats[\'area\'] * UNCERTAINTY_SNOW_DENSITY)\\n) / total_area_avg\\n\\n# ---- STEP 9: Total Sum of Each ----\\ntotal_uncertainty_ice = bin_stats[\'Uncertainty Ice\'].sum()\\ntotal_uncertainty_snow = bin_stats[\'Uncertainty Snow\'].sum()\\n\\n# ---- STEP 10: Overall Uncertainty Average ----\\nuncertainty_overall = (total_uncertainty_ice + total_uncertainty_snow) / 2\\n\\n# ---- Round and Output ----\\nbin_stats = bin_stats.round(3)\\n\\nprint(bin_stats)\\nprint(\\"\\\\nAverage bg:\\", round(avg_bg, 3))\\nprint(\\"Total Area Average:\\", round(total_area_avg, 3))\\nprint(\\"Total Summation (x - X)^2:\\", round(total_summation, 3))\\nprint(\\"dbz:\\", round(dbz, 3))\\nprint(\\"Total Uncertainty Ice:\\", round(total_uncertainty_ice, 3))\\nprint(\\"Total Uncertainty Snow:\\", round(total_uncertainty_snow, 3))\\nprint(\\"Overall Uncertainty Average:\\", round(uncertainty_overall, 3))\\n\\n# Optional: Save output\\nbin_stats.to_csv(os.path.join(output_dir, \\"uncertainty_results.csv\\"), index=False)"]')

def save_uploaded_file(uploaded_file, dest_path):
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(dest_path)

def extract_shapefile_zip(uploaded_zip, dest_dir):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / uploaded_zip.name
    with open(zip_path, "wb") as f:
        f.write(uploaded_zip.getbuffer())
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)
    shp_files = list(dest_dir.rglob("*.shp"))
    if not shp_files:
        raise FileNotFoundError("No .shp file found in the uploaded ZIP.")
    return str(shp_files[0])

def find_output_files(output_dir):
    out = []
    for p in sorted(Path(output_dir).glob("*")):
        if p.is_file():
            out.append(p)
    return out

def render_namespace_outputs(ns):
    if "geo_gdf1" in ns:
        st.subheader("geo_gdf1")
        st.dataframe(ns["geo_gdf1"].head(10))
    if "geo_gdf2" in ns:
        st.subheader("geo_gdf2")
        st.dataframe(ns["geo_gdf2"].head(10))
    if "merged_gdf" in ns:
        st.subheader("merged_gdf")
        st.write(f"Shape: {ns['merged_gdf'].shape}")
        st.dataframe(ns["merged_gdf"].head(10))
    if "gdf_threshold" in ns:
        st.subheader("gdf_threshold")
        st.write(f"Shape: {ns['gdf_threshold'].shape}")
        st.dataframe(ns["gdf_threshold"].head(10))
    if "bin_stats" in ns:
        st.subheader("bin_stats")
        st.dataframe(ns["bin_stats"])
    if "df_result" in ns:
        st.subheader("Boundary-segment result")
        st.dataframe(ns["df_result"])
    summary = {}
    for key in ["amb", "amb2", "amb_agg_data"]:
        if key in ns:
            summary[key] = ns[key]
    if summary:
        st.subheader("Key summary values")
        st.json(summary)

def main():
    import streamlit as st
    user_epsg = st.sidebar.text_input("Projected CRS (EPSG)", value="32646")
    with st.sidebar:
        st.header("Inputs")

        dgps_2025 = st.file_uploader("2025 dGPS CSV (raw input for csv_path_1)", type=["csv"])
        dgps_2024 = st.file_uploader("2024 dGPS CSV (raw input for csv_path_2)", type=["csv"])
        raster_tif = st.file_uploader("DEM raster (.tif)", type=["tif", "tiff"])
        glacier_zip = st.file_uploader("Glacier shapefile ZIP (.zip)", type=["zip"])
        snow_2024 = st.file_uploader("Previous year Snow depth CSV  (optional)", type=["csv"])
        snow_2025 = st.file_uploader("Current year Snow depth CSV  (optional)", type=["csv"])

        st.header("Parameters from notebook")
        cell_size = st.number_input("cell_size", value=1.0, step=0.1)
        search_radius = st.number_input("search_radius", value=0.7, step=0.1)
        power = st.number_input("power", value=2, step=1)
        distance_threshold = st.number_input("distance_threshold", value=3.0, step=0.5)

        corrected_dem_name = st.text_input("corrected_dem_name", value="dem_corr1.tif")
        output_clipped_dem_name = st.text_input("output_clipped_dem_name", value="dem_sub_corr1.tif")
        corrected_dem_name_old = st.text_input("corrected_dem_name_old", value="dem_corr2.tif")
        output_clipped_dem_name_old = st.text_input("output_clipped_dem_name_old", value="dem_sub_corr2.tif")

        run_btn = st.button("Run notebook workflow", type="primary", use_container_width=True)

    st.info("Required files: both dGPS CSVs, raster TIFF, and glacier shapefile ZIP. Snow depth files are optional.")

    if not run_btn:
        return

    missing = []
    if dgps_2025 is None:
        missing.append("2025 dGPS CSV")
    if dgps_2024 is None:
        missing.append("2024 dGPS CSV")
    if raster_tif is None:
        missing.append("DEM raster")
    if glacier_zip is None:
        missing.append("Glacier shapefile ZIP")
    if missing:
        st.error("Missing required inputs: " + ", ".join(missing))
        return

    workdir = tempfile.mkdtemp(prefix="thana_streamlit_")
    input_dir = Path(workdir) / "inputs"
    output_dir = Path(workdir) / "outputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        csv_path_1 = save_uploaded_file(dgps_2025, input_dir / "csv_path_1.csv")
        csv_path_2 = save_uploaded_file(dgps_2024, input_dir / "csv_path_2.csv")
        raster_file = save_uploaded_file(raster_tif, input_dir / raster_tif.name)
        glacier_shp_path = extract_shapefile_zip(glacier_zip, input_dir / "glacier_shapefile")

        snd1 = save_uploaded_file(snow_2024, input_dir / "snow_1.csv") if snow_2024 is not None else None
        snd2 = save_uploaded_file(snow_2025, input_dir / "snow_2.csv") if snow_2025 is not None else None

        gdf_1 = str(output_dir / "Thana_idw_interpolated_1m_utm.csv")
        gdf_2 = str(output_dir / "Thana_idw_interpolated_1m_utm_old.csv")

        ns = {
            "__name__": "__main__",
            "csv_path_1": csv_path_1,
            "csv_path_2": csv_path_2,
            "gdf_1": gdf_1,
            "gdf_2": gdf_2,
            "gdf11": gdf_1,
            "gdf22": gdf_2,
            "raster_file": raster_file,
            "glacier_shp_path": glacier_shp_path,
            "snd1": snd1,
            "snd2": snd2,
            "cell_size": cell_size,
            "search_radius": search_radius,
            "power": power,
            "distance_threshold": distance_threshold,
            "corrected_dem_name": corrected_dem_name,
            "output_clipped_dem_name": output_clipped_dem_name,
            "corrected_dem_name_old": corrected_dem_name_old,
            "output_clipped_dem_name_old": output_clipped_dem_name_old,
            "output_dir": str(output_dir),
            "user_epsg": user_epsg,
        }

                progress = st.progress(0.0)
        status = st.empty()
        log_box = st.expander("Execution log", expanded=True)

        import matplotlib.pyplot as plt  # noqa

        for idx, code in enumerate(NOTEBOOK_CELLS):
            status.write(f"Running cell {idx + 1} of {len(NOTEBOOK_CELLS)}")
            stdout_buf = io.StringIO()
            prev_figs = set(plt.get_fignums())

            try:
                with contextlib.redirect_stdout(stdout_buf):
                    exec(code, ns)

            except ValueError as e:
                st.error(str(e))
                st.code(code, language="python")
                st.stop()

            except Exception as e:
                st.error(f"Cell {idx + 1} failed.")
                st.code(code, language="python")
                st.exception(e)
                st.stop()

            out = stdout_buf.getvalue().strip()
            with log_box:
                if out:
                    st.text(out)

            new_figs = [n for n in plt.get_fignums() if n not in prev_figs]
            for fig_num in new_figs:
                fig = plt.figure(fig_num)
                st.pyplot(fig, clear_figure=False)
                plt.close(fig)

            progress.progress((idx + 1) / len(NOTEBOOK_CELLS))

        status.success("Notebook workflow completed.")

        render_namespace_outputs(ns)

        st.subheader("Generated files")
        out_files = find_output_files(output_dir)
        if not out_files:
            st.write("No output files detected.")
        else:
            for p in out_files:
                with open(p, "rb") as f:
                    st.download_button(
                        label=f"Download {p.name}",
                        data=f.read(),
                        file_name=p.name,
                        mime="application/octet-stream",
                        key=f"download_{p.name}",
                    )
    finally:
        pass

if __name__ == "__main__":
    main()
        if not out_files:
            st.write("No output files detected.")
        else:
            for p in out_files:
                with open(p, "rb") as f:
                    st.download_button(
                        label=f"Download {p.name}",
                        data=f.read(),
                        file_name=p.name,
                        mime="application/octet-stream",
                        key=f"download_{p.name}",
                    )
    finally:
        pass

if __name__ == "__main__":
    main()
