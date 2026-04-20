# %% [cell 1]
# Import necessary modules

import os
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from sklearn.linear_model import TheilSenRegressor
from shapely.geometry import Point, LineString, MultiLineString
t1 = int(t1) if 't1' in globals() else 2024
t2 = int(t2) if 't2' in globals() else 2025

if t1 >= t2:
    raise ValueError("t1 must be less than t2")
def normalize_crs_to_epsg(crs_obj):
    if crs_obj is None:
        return None
    try:
        return crs_obj.to_epsg()
    except Exception:
        return None
Time_period = t2 - t1
elevation_interval = int(elevation_interval) if 'elevation_interval' in globals() else 50

def validate_crs_or_stop(glacier_shp_path, raster_file, user_epsg):
    glacier_gdf = gpd.read_file(glacier_shp_path)

    if glacier_gdf.crs is None:
        raise ValueError("Glacier boundary file has no CRS defined.")

    with rasterio.open(raster_file) as src:
        dem_crs = src.crs
        if dem_crs is None:
            raise ValueError("DEM raster has no CRS defined.")

    boundary_epsg = normalize_crs_to_epsg(glacier_gdf.crs)
    dem_epsg = normalize_crs_to_epsg(dem_crs)

    if boundary_epsg is None:
        raise ValueError(f"Could not determine EPSG for glacier boundary CRS: {glacier_gdf.crs}")

    if dem_epsg is None:
        raise ValueError(f"Could not determine EPSG for DEM CRS: {dem_crs}")

    try:
        user_epsg_int = int(str(user_epsg).replace("EPSG:", "").strip())
    except Exception:
        raise ValueError(f"Invalid selected CRS: {user_epsg}")

    errors = []

    if boundary_epsg != dem_epsg:
        errors.append(f"Boundary CRS is EPSG:{boundary_epsg}, but DEM CRS is EPSG:{dem_epsg}.")

    if user_epsg_int != dem_epsg:
        errors.append(f"Selected CRS is EPSG:{user_epsg_int}, but DEM CRS is EPSG:{dem_epsg}.")

    if user_epsg_int != boundary_epsg:
        errors.append(f"Selected CRS is EPSG:{user_epsg_int}, but boundary CRS is EPSG:{boundary_epsg}.")

    if errors:
        raise ValueError("CRS validation failed: " + " | ".join(errors))

    return f"EPSG:{user_epsg_int}"
# %% [cell 2]
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

# -----------------------------
# 1. Paths & parameters
# -----------------------------
# csv_path_1 provided by Streamlit
# gdf_1 provided by Streamlit

# Column names in your CSV (edit if needed)
x_col = "Longitude"      # UTM Easting in your file
y_col = "Latitude"       # UTM Northing in your file
z_col = "Elevation"      # Elevation

cell_size = float(cell_size) if 'cell_size' in globals() else 1.0
search_radius = float(search_radius) if 'search_radius' in globals() else 0.7
power = float(power) if 'power' in globals() else 2          # IDW power

# -----------------------------
# 2. Read CSV
# -----------------------------
df = pd.read_csv(csv_path_1)

if not set([x_col, y_col, z_col]).issubset(df.columns):
    raise ValueError(f"CSV must contain {x_col}, {y_col}, {z_col} columns. "
                     f"Found: {list(df.columns)}")

x = df[x_col].to_numpy(dtype=float)
y = df[y_col].to_numpy(dtype=float)
z = df[z_col].to_numpy(dtype=float)

# Drop NaNs if any
valid_mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
x = x[valid_mask]
y = y[valid_mask]
z = z[valid_mask]

if x.size == 0:
    raise ValueError("No valid points after removing NaNs. Check your CSV.")

# -----------------------------
# 3. Build 1 m grid (UTM)
# -----------------------------
minx, maxx = x.min(), x.max()
miny, maxy = y.min(), y.max()

pad = cell_size * 0.5
minx -= pad
miny -= pad
maxx += pad
maxy += pad

if maxx <= minx or maxy <= miny:
    raise ValueError(
        f"Invalid bounds: minx={minx}, maxx={maxx}, miny={miny}, maxy={maxy}"
    )

grid_x = np.arange(minx, maxx, cell_size)
grid_y = np.arange(miny, maxy, cell_size)

grid_xx, grid_yy = np.meshgrid(grid_x, grid_y)
grid_points = np.vstack((grid_xx.ravel(), grid_yy.ravel())).T

# -----------------------------
# 4. IDW interpolation (in UTM)
# -----------------------------
tree = cKDTree(np.vstack((x, y)).T)
neighbors_idx = tree.query_ball_point(grid_points, r=search_radius)

interp_z = np.full(grid_points.shape[0], np.nan, dtype=float)

for i, idx_list in enumerate(neighbors_idx):
    if len(idx_list) == 0:
        continue  # no neighbors within radius

    x_neighbors = x[idx_list]
    y_neighbors = y[idx_list]
    z_neighbors = z[idx_list]

    dx = x_neighbors - grid_points[i, 0]
    dy = y_neighbors - grid_points[i, 1]
    d = np.sqrt(dx**2 + dy**2)

    # Exact sample point -> copy value
    zero_mask = d == 0
    if np.any(zero_mask):
        interp_z[i] = z_neighbors[zero_mask][0]
        continue

    w = 1.0 / (d**power)
    interp_z[i] = np.sum(w * z_neighbors) / np.sum(w)

# -----------------------------
# 5. Build output table (UTM 45N)
# -----------------------------
valid = ~np.isnan(interp_z)
grid_valid = grid_points[valid]
z_valid = interp_z[valid]

utm_x = grid_valid[:, 0]
utm_y = grid_valid[:, 1]

out_df = pd.DataFrame({
    "Point_id": np.arange(1, len(z_valid) + 1),
    "Latitude": utm_y,      # UTM 45N Easting
    "Longitude": utm_x ,    # UTM 45N Northing
    "Elevation": z_valid
})
final_df = out_df.sort_values('Elevation', ascending = False)
final_df['sorted_order'] = np.arange(1, len(final_df) + 1)
final_df.to_csv(gdf_1, index=False)
print(f"Saved interpolated UTM points to: {gdf_1}")
print(final_df.head())

# %% [cell 3]


# %% [cell 4]
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

# -----------------------------
# 1. Paths & parameters
# -----------------------------
# csv_path_2 provided by Streamlit
# gdf_2 provided by Streamlit

# Column names in your CSV (edit if needed)
x_col = "Longitude"      # UTM Easting in your file
y_col = "Latitude"       # UTM Northing in your file
z_col = "Elevation"      # Elevation

cell_size = float(cell_size) if 'cell_size' in globals() else 1.0
search_radius = float(search_radius) if 'search_radius' in globals() else 0.7
power = float(power) if 'power' in globals() else 2       # IDW power

# -----------------------------
# 2. Read CSV
# -----------------------------
df = pd.read_csv(csv_path_2)

if not set([x_col, y_col, z_col]).issubset(df.columns):
    raise ValueError(f"CSV must contain {x_col}, {y_col}, {z_col} columns. "
                     f"Found: {list(df.columns)}")

x = df[x_col].to_numpy(dtype=float)
y = df[y_col].to_numpy(dtype=float)
z = df[z_col].to_numpy(dtype=float)

# Drop NaNs if any
valid_mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
x = x[valid_mask]
y = y[valid_mask]
z = z[valid_mask]

if x.size == 0:
    raise ValueError("No valid points after removing NaNs. Check your CSV.")

# -----------------------------
# 3. Build 1 m grid (UTM)
# -----------------------------
minx, maxx = x.min(), x.max()
miny, maxy = y.min(), y.max()

pad = cell_size * 0.5
minx -= pad
miny -= pad
maxx += pad
maxy += pad

if maxx <= minx or maxy <= miny:
    raise ValueError(
        f"Invalid bounds: minx={minx}, maxx={maxx}, miny={miny}, maxy={maxy}"
    )

grid_x = np.arange(minx, maxx, cell_size)
grid_y = np.arange(miny, maxy, cell_size)

grid_xx, grid_yy = np.meshgrid(grid_x, grid_y)
grid_points = np.vstack((grid_xx.ravel(), grid_yy.ravel())).T

# -----------------------------
# 4. IDW interpolation (in UTM)
# -----------------------------
tree = cKDTree(np.vstack((x, y)).T)
neighbors_idx = tree.query_ball_point(grid_points, r=search_radius)

interp_z = np.full(grid_points.shape[0], np.nan, dtype=float)

for i, idx_list in enumerate(neighbors_idx):
    if len(idx_list) == 0:
        continue  # no neighbors within radius

    x_neighbors = x[idx_list]
    y_neighbors = y[idx_list]
    z_neighbors = z[idx_list]

    dx = x_neighbors - grid_points[i, 0]
    dy = y_neighbors - grid_points[i, 1]
    d = np.sqrt(dx**2 + dy**2)

    # Exact sample point -> copy value
    zero_mask = d == 0
    if np.any(zero_mask):
        interp_z[i] = z_neighbors[zero_mask][0]
        continue

    w = 1.0 / (d**power)
    interp_z[i] = np.sum(w * z_neighbors) / np.sum(w)

# -----------------------------
# 5. Build output table (UTM 45N)
# -----------------------------
valid = ~np.isnan(interp_z)
grid_valid = grid_points[valid]
z_valid = interp_z[valid]

utm_x = grid_valid[:, 0]
utm_y = grid_valid[:, 1]

out_df = pd.DataFrame({
    "Point_id": np.arange(1, len(z_valid) + 1),
    "Latitude": utm_y,      # UTM 45N Easting
    "Longitude": utm_x ,    # UTM 45N Northing
    "Elevation": z_valid
})
final_df_1 = out_df.sort_values('Elevation', ascending = False)

final_df_1['sorted_order'] = np.arange(1, len(final_df_1) + 1)

final_df_1.to_csv(gdf_2, index=False)
print(f"Saved interpolated UTM points to: {gdf_2}")
print(final_df_1.head())

# %% [cell 5]
"""Only this section needs u"""
# gdf1 = "/mnt/d/NCHM_Data/tracks/Gangju la_2024_01.csv" # New csv file (e.g., 2024) path
# gdf2 = "/mnt/d/NCHM_Data/tracks/Gangju_La_rawdata_2023.csv" # Old csv file (e.g., 2023) path

# merged_gdf['elev_diff'] = merged_gdf['Elevation_left'] - merged_gdf['Elevation_right'] # e.g., 5m (2023)  2m in (2024): 2m - 5m

gdf11 = gdf_1
gdf22 = gdf_2

# raster_file provided by Streamlit
# glacier_shp_path provided by Streamlit


"""Snow depth data at stakes"""

# snd1 provided by Streamlit
# snd2 provided by Streamlit

"""Change if necessary"""

# distance_threshold provided by Streamlit
# corrected_dem_name provided by Streamlit
# output_clipped_dem_name provided by Streamlit
# corrected_dem_name_old provided by Streamlit
# output_clipped_dem_name_old provided by Streamlit

# %% [cell 6]


if snd1 is not None and os.path.exists(snd1):
    snd11 = pd.read_csv(snd1)
else:
    print("snd1 not provided or file missing")

if snd2 is not None and os.path.exists(snd2):
    snd22 = pd.read_csv(snd2)
else:
    print("snd2 not provided or file missing")

if snd1 is not None:
    print(snd11.head(3))

if snd2 is not None:
    print(snd22.head(3))

# %% [cell 7]
master_path = os.path.split(raster_file)[0]
corrected_dem = os.path.join(master_path, corrected_dem_name)  
output_clipped_dem = os.path.join(master_path, output_clipped_dem_name)  
corrected_dem1 = os.path.join(master_path, corrected_dem_name_old)  
output_clipped_dem1 = os.path.join(master_path, output_clipped_dem_name_old)
gdf1 = pd.read_csv(gdf11) # current year(t2)# Left
gdf2 = pd.read_csv(gdf22) # previous year(t1) # Right
gdf2.head(3)

# %% [cell 8]
gdf1['geometry'] = gdf1.apply(lambda row: Point(row.iloc[2], row.iloc[1]), axis=1)
gdf2['geometry'] = gdf2.apply(lambda row: Point(row.iloc[2], row.iloc[1]), axis=1)

crs_proj = validate_crs_or_stop(glacier_shp_path, raster_file, user_epsg)

geo_gdf1 = gpd.GeoDataFrame(gdf1, geometry='geometry', crs=crs_proj) # current year
geo_gdf2 = gpd.GeoDataFrame(gdf2, geometry='geometry', crs=crs_proj) # previous year
# %% [cell 9]
geo_gdf1

# %% [cell 10]
glacier_gdf_01 = gpd.read_file(glacier_shp_path)
fig, ax = plt.subplots(figsize=(10, 12))  # Adjust figure size for higher resolution
glacier_gdf_01.plot(ax=ax,facecolor='none',edgecolor='black',linewidth=1.5,label="Glacier boundary")

geo_gdf2.plot(ax=ax, color='red', alpha=0.6, markersize=30, label= f"{t1} dGPS survey track")  # Customize style for geo_gdf2
geo_gdf1.plot(ax=ax, color='blue', alpha=0.6, markersize=30, label=f"{t2} dGPS survey track")  # Customize style for geo_gdf1

# Add labels and legend
ax.set_xlabel("Easting (m)", fontsize=12)
ax.set_ylabel("Northing (m)", fontsize=12)
ax.legend(fontsize=12, loc="upper left")

ax.grid(visible=True, linestyle='--', alpha=0.5)

# Improve axis style
ax.tick_params(axis='both', labelsize=10)
plt.tight_layout()
plt.show()

# %% [cell 11]
import matplotlib.patches as mpatches

glacier_gdf_01 = gpd.read_file(glacier_shp_path)
fig, ax = plt.subplots(figsize=(8, 12))  # Adjust figure size

# Plot glacier boundary (transparent fill)
glacier_gdf_01.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.5)

# Plot dGPS tracks
geo_gdf2.plot(ax=ax, color='red', alpha=0.6, markersize=30, label=f"{t1} dGPS survey track")
geo_gdf1.plot(ax=ax, color='blue', alpha=0.6, markersize=30, label=f"{t2} dGPS survey track")


# Create manual legend patch for glacier boundary
boundary_patch = mpatches.Patch(facecolor='none', edgecolor='black', linewidth=1.5, label='Glacier boundary')

# Get existing legend handles (from tracks) and add boundary patch
handles, labels = ax.get_legend_handles_labels()
handles.append(boundary_patch)

# Add legend
ax.legend(handles=handles, loc="upper left")

# Labels, grid, ticks
ax.set_xlabel("Easting (m)")
ax.set_ylabel("Northing (m)")
ax.grid(visible=True, linestyle='--', alpha=0.5)
ax.tick_params(axis='both', labelsize=10)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "dGPS_with_boundary.png"), dpi=300)
plt.show()

# %% [cell 12]
with rasterio.open(raster_file) as src:
    if geo_gdf1.crs != src.crs:
        raise ValueError(
            f"geo_gdf1 CRS {geo_gdf1.crs} does not match raster CRS {src.crs}. "
            "Stopping to avoid wrong raster sampling."
        )

    coordinates = [(point.x, point.y) for point in geo_gdf1.geometry]
    raster_values = list(src.sample(coordinates))
    geo_gdf1['raster_raw_value'] = [val[0] for val in raster_values]

    geo_gdf1['dgps_dem_diff'] = np.abs(geo_gdf1['raster_raw_value'] - geo_gdf1['Elevation'])
    dgps_dem_diff_avg = np.mean(geo_gdf1['dgps_dem_diff'])

    from rasterio.plot import show
    fig, ax = plt.subplots()
    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]
    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap="pink")
    geo_gdf1.plot(ax=ax)
    ax.set_title('Raw Dem')
    profile = src.profile
    data = src.read(1)

    corrected_dem_arr = data - dgps_dem_diff_avg
    profile.update(dtype='float32')

with rasterio.open(corrected_dem, "w", **profile) as dst:
    dst.write(corrected_dem_arr.astype('float32'), 1)

with rasterio.open(corrected_dem) as src:
    if geo_gdf1.crs != src.crs:
        raise ValueError(
            f"geo_gdf1 CRS {geo_gdf1.crs} does not match corrected DEM CRS {src.crs}. "
            "Stopping to avoid wrong raster sampling."
        )

    coordinates = [(point.x, point.y) for point in geo_gdf1.geometry]
    raster_values = list(src.sample(coordinates))
    geo_gdf1['raster_corr_value'] = [val[0] for val in raster_values]

    from rasterio.plot import show
    fig, ax = plt.subplots()
    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]
    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap="pink")
    ax.set_title('Corr Dem')
    geo_gdf1.plot(ax=ax)
# %% [cell 13]
geo_gdf2.head(3)

# %% [cell 14]
fig, ax = plt.subplots()
plt.plot( geo_gdf1['sorted_order'],geo_gdf1['Elevation'], label='dGPS')
plt.plot( geo_gdf1['sorted_order'],geo_gdf1['raster_raw_value'], label='DEM-Sat-Raw')
plt.legend()
plt.tight_layout
plt.savefig(os.path.join(output_dir, "difference_dem.png"),dpi=300)
plt.show()

# %% [cell 15]
geo_gdf1['dem_corr'] = geo_gdf1['raster_raw_value'] - dgps_dem_diff_avg

fig, ax = plt.subplots()
plt.plot(geo_gdf1['sorted_order'],geo_gdf1['dgps_dem_diff'])
plt.show()

fig, ax = plt.subplots()
plt.plot(geo_gdf1['sorted_order'],geo_gdf1['Elevation'], label='dGPS')
plt.plot(geo_gdf1['sorted_order'],geo_gdf1['raster_corr_value'], label='DEM-Sat-Correct')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "corrected_Dem.png"),dpi=300)
plt.show()

fig, ax = plt.subplots()
plt.hist(geo_gdf1['dgps_dem_diff'], bins=elevation_interval)
plt.axvline(dgps_dem_diff_avg, color='red', ls='--', lw=2)
plt.show()

# %% [cell 16]
# Step 1: Clip the Corrected DEM with the glacier outline
from rasterio.mask import mask
def clip_dem(dem_path, glacier_shp_path, output_clipped_dem):
    # Load glacier shapefile
    glacier_gdf = gpd.read_file(glacier_shp_path)
    # Open the DEM
    with rasterio.open(dem_path) as dem_src:
        # Mask DEM with glacier geometry
        glacier_geometry = glacier_gdf.geometry
        clipped_dem, clipped_transform = mask(dem_src, glacier_geometry, crop=True)
        clipped_meta = dem_src.meta.copy()

        # Update metadata for the clipped DEM
        clipped_meta.update({
            "driver": "GTiff",
            "height": clipped_dem.shape[1],
            "width": clipped_dem.shape[2],
            "transform": clipped_transform
        })

        # Save the clipped DEM
        with rasterio.open(output_clipped_dem, "w", **clipped_meta) as dest:
            dest.write(clipped_dem)
    return output_clipped_dem

# Step 2: Classify elevations and calculate area in each class
def classify_and_calculate_area(path, elevation_interval=elevation_interval):
    with rasterio.open(path) as src:
        dem_data = src.read(1)
        dem_data = dem_data[dem_data > 0]  # Filter out no-data values
        pixel_area = abs(src.transform[0] * src.transform[4])  # Calculate pixel area

    # Classify elevations
    min_elevation = int(np.floor(dem_data.min()))
    max_elevation = int(np.ceil(dem_data.max()))
    
    bins = np.arange(min_elevation, max_elevation + elevation_interval, elevation_interval)
    elevation_classes = np.digitize(dem_data, bins)

    # Calculate area for each elevation class
    area_per_class = []
    for i in range(1, len(bins)):
        area = (elevation_classes == i).sum() * pixel_area
        area_per_class.append(area)

    return bins, area_per_class

def plot_elevation_vs_area(bins, area_per_class):
    mid_bins = (bins[:-1] + bins[1:]) / 2
    plt.figure()
    plt.barh(
        mid_bins, 
        area_per_class, 
        height=30,
        color="skyblue",  
        edgecolor="black", 
        alpha=0.9
    )
    plt.xlabel("Area (m²)", fontsize=12)
    plt.ylabel("Elevation (m)", fontsize=12)
    plt.grid(axis='x', linestyle='--', alpha=0.6)
    plt.xticks(fontsize=12)
    plt.yticks(mid_bins,fontsize=12)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "hypsometry.png"),dpi=450)
    plt.show()
    return mid_bins

clipped_dem = clip_dem(corrected_dem, glacier_shp_path, output_clipped_dem)
elev_bins, area_per_class = classify_and_calculate_area(output_clipped_dem, elevation_interval=elevation_interval)
mid_bins = plot_elevation_vs_area(elev_bins, area_per_class)

# %% [cell 17]
with rasterio.open(raster_file) as src:
    if geo_gdf2.crs != src.crs:
        raise ValueError(
            f"geo_gdf2 CRS {geo_gdf2.crs} does not match raster CRS {src.crs}. "
            "Stopping to avoid wrong raster sampling."
        )

    coordinates = [(point.x, point.y) for point in geo_gdf2.geometry]
    raster_values = list(src.sample(coordinates))
    geo_gdf2['raster_raw_value'] = [val[0] for val in raster_values]

    geo_gdf2['dgps_dem_diff'] = np.abs(geo_gdf2['raster_raw_value'] - geo_gdf2['Elevation'])
    dgps_dem_diff_avg1 = np.mean(geo_gdf2['dgps_dem_diff'])

    from rasterio.plot import show
    fig, ax = plt.subplots()
    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]
    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap="pink")
    geo_gdf2.plot(ax=ax)
    ax.set_title('Raw Dem')
    profile = src.profile
    data = src.read(1)

    corrected_dem_arr1 = data - dgps_dem_diff_avg1
    profile.update(dtype='float32')

with rasterio.open(corrected_dem1, "w", **profile) as dst:
    dst.write(corrected_dem_arr1.astype('float32'), 1)

with rasterio.open(corrected_dem1) as src:
    if geo_gdf2.crs != src.crs:
        raise ValueError(
            f"geo_gdf2 CRS {geo_gdf2.crs} does not match corrected DEM CRS {src.crs}. "
            "Stopping to avoid wrong raster sampling."
        )

    coordinates = [(point.x, point.y) for point in geo_gdf2.geometry]
    raster_values = list(src.sample(coordinates))
    geo_gdf2['raster_corr_value'] = [val[0] for val in raster_values]

    from rasterio.plot import show
    fig, ax = plt.subplots()
    extent = [src.bounds[0], src.bounds[2], src.bounds[1], src.bounds[3]]
    ax = rasterio.plot.show(src, extent=extent, ax=ax, cmap="pink")
    ax.set_title('Corr Dem')
    geo_gdf2.plot(ax=ax)

# %% [cell 18]
geo_gdf2['dem_corr'] = geo_gdf2['raster_raw_value'] - dgps_dem_diff_avg1

fig, ax = plt.subplots()
plt.plot(geo_gdf2['sorted_order'],geo_gdf2['dgps_dem_diff'])
plt.show()

fig, ax = plt.subplots()
plt.plot(geo_gdf2['Elevation'], label='dGPS')
plt.plot(geo_gdf2['raster_corr_value'], label='DEM-Sat-Correct')
plt.legend()
plt.show()

fig, ax = plt.subplots()
plt.hist(geo_gdf2['dgps_dem_diff'], bins=elevation_interval)
plt.axvline(dgps_dem_diff_avg1, color='red', ls='--', lw=2)

# %% [cell 19]
# Step 1: Clip the Corrected DEM with the glacier outline
from rasterio.mask import mask
def clip_dem(dem_path, glacier_shp_path, output_clipped_dem1):
    # Load glacier shapefile
    glacier_gdf2 = gpd.read_file(glacier_shp_path)
    # Open the DEM
    with rasterio.open(dem_path) as dem_src:
        # Mask DEM with glacier geometry
        glacier_geometry2 = glacier_gdf2.geometry
        clipped_dem1, clipped_transform = mask(dem_src, glacier_geometry2, crop=True)
        clipped_meta1 = dem_src.meta.copy()

        # Update metadata for the clipped DEM
        clipped_meta1.update({
            "driver": "GTiff",
            "height": clipped_dem1.shape[1],
            "width": clipped_dem1.shape[2],
            "transform": clipped_transform
        })

        # Save the clipped DEM
        with rasterio.open(output_clipped_dem1, "w", **clipped_meta1) as dest:
            dest.write(clipped_dem1)
    return output_clipped_dem1

# Step 2: Classify elevations and calculate area in each class
def classify_and_calculate_area(path, elevation_interval=elevation_interval):
    with rasterio.open(path) as src:
        dem_data = src.read(1)
        dem_data = dem_data[dem_data > 0]  # Filter out no-data values
        pixel_area = abs(src.transform[0] * src.transform[4])  # Calculate pixel area

    # Classify elevations
    min_elevation = elev_bins[0]
    max_elevation = elev_bins[-1]
    
    bins = np.arange(min_elevation, max_elevation + elevation_interval, elevation_interval)
    elevation_classes = np.digitize(dem_data, bins)

    # Calculate area for each elevation class
    area_per_class1 = []
    for i in range(1, len(bins)):
        area1 = (elevation_classes == i).sum() * pixel_area
        area_per_class1.append(area1)

    return bins, area_per_class1

def plot_elevation_vs_area(bins, area_per_class1):
    mid_bins = (bins[:-1] + bins[1:]) / 2
    plt.figure()
    plt.barh(
        mid_bins, 
        area_per_class1, 
        height=30,
        color="skyblue",  
        edgecolor="black", 
        alpha=0.9
    )
    plt.xlabel("Area (m²)", fontsize=12)
    plt.ylabel("Elevation (m)", fontsize=12)
    plt.grid(axis='x', linestyle='--', alpha=0.6)
    plt.xticks(fontsize=12)
    plt.yticks(mid_bins,fontsize=12)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "hypsometry.png"),dpi=450)
    plt.show()
    return mid_bins

clipped_dem1 = clip_dem(corrected_dem1, glacier_shp_path, output_clipped_dem1)
elev_bins, area_per_class1 = classify_and_calculate_area(output_clipped_dem1, elevation_interval=elevation_interval)
mid_bins = plot_elevation_vs_area(elev_bins, area_per_class1)

# %% [cell 20]
def plot_hypsometry_comparison(bins_a, area_a, bins_b, area_b,
                              label_a="DEM A", label_b="DEM B"):
    # --- If bins differ, restrict to their common range ---
    if not np.array_equal(bins_a, bins_b):
        raise ValueError("Elevation bins differ between the two datasets. "
                        "Re-bin them to a common set before plotting.")

    # Mid-points for elevation bands
    mid_bins = (bins_a[:-1] + bins_a[1:]) / 2
    bar_height = int(bins_a[1] - bins_a[0])  # should be 50 m

    plt.figure(figsize=(8, 6))

    # Calculate bar dimensions for perfect stacking
    bar_height_half = bar_height * 0.4
    offset = bar_height_half  # Offset for the second bar

    # First dataset - top half
    plt.barh(
        mid_bins + offset/2,  # Position in the top half
        area_a,
        height=bar_height_half,  # Half the total height
        color="skyblue",
        edgecolor="black",
        alpha=0.8,
        label=label_a,
    )

    # Second dataset - bottom half
    plt.barh(
        mid_bins - offset/2,  # Position in the bottom half
        area_b,
        height=bar_height_half,  # Half the total height
        color="blue",
        edgecolor="black",
        alpha=0.5,
        label=label_b,
        linewidth=1
    )

    plt.xlabel("Area (m²)", fontsize=12)
    plt.ylabel("Elevation (m)", fontsize=12)

    # y-axis ticks exactly at the centre of the combined bars
    plt.yticks(mid_bins, labels=mid_bins.astype(int), fontsize=12)


    # Grid only in x direction, alpha 0.5
    plt.grid(axis="x", linestyle="--", alpha=0.5)

    plt.xticks(np.round(plt.xticks()[0]).astype(int))
    plt.legend(fontsize=11)
    plt.tight_layout()

    plt.show()

# %% [cell 21]
# Old / auto-binned
elev_bins, area_per_class = classify_and_calculate_area(output_clipped_dem, elevation_interval=elevation_interval)

# New / fixed 4873–5173
elev_bins1, area_per_class1 = classify_and_calculate_area(output_clipped_dem1, elevation_interval=elevation_interval)

# Plot comparison
plot_hypsometry_comparison(
    elev_bins,
    area_per_class,
    elev_bins1,
    area_per_class1,
    label_a=f"{t2}",
    label_b=f"{t1}"
)

# %% [cell 22]
# Perform the nearest spatial join with a max distance of 50 meters
merged_gdf = gpd.sjoin_nearest(
    geo_gdf1, 
    geo_gdf2, 
    how="inner", 
    distance_col="nearest_distance", 
    max_distance=50
)
merged_gdf.head(3)

# %% [cell 23]
merged_gdf.shape

# %% [cell 24]
fig, ax = plt.subplots()
ax.scatter(
    merged_gdf['nearest_distance'], 
    merged_gdf['Elevation_right'], 
    color='darkblue', 
    # edgecolor='black', 
    alpha=0.8, 
    s=20,
)
ax.set_xlabel('Merged distance (m)', fontsize=12)
ax.set_ylabel('Elevation (m)', fontsize=12)
ax.grid(linestyle='--', alpha=0.6)
ax.tick_params(axis='both', labelsize=12)
plt.tight_layout()
plt.show()

# %% [cell 25]
fig, ax = plt.subplots()
ax.plot(
    range(merged_gdf['raster_corr_value_left'].shape[0]), 
    merged_gdf['raster_corr_value_left'], 
    label='DEM-Sat', 
    color='blue', 
    linewidth=2, 
    linestyle='-'
)
ax.plot(
    range(merged_gdf['Elevation_left'].shape[0]), 
    merged_gdf['Elevation_left'], 
    label=f'dGPS {t2}', 
    color='green', 
    linewidth=2, 
    linestyle='--'
)
ax.plot(
    range(merged_gdf['Elevation_right'].shape[0]), 
    merged_gdf['Elevation_right'], 
    label=f'dGPS {t1}', 
    color='red', 
    linewidth=2, 
    linestyle=':'
)
ax.legend(
    fontsize=12, 
    loc='best', 
    frameon=True, 
    framealpha=0.8, 
    edgecolor='black'
)
ax.set_xlabel('Samples', fontsize=12)
ax.set_ylabel('Elevation Values (m)', fontsize=12)
ax.grid(linestyle='--', alpha=0.6)
ax.tick_params(axis='both', labelsize=12)
plt.tight_layout()
plt.show()

# %% [cell 26]
merged_gdf['elev_diff'] = merged_gdf['Elevation_left'] - merged_gdf['Elevation_right'] # e.g., 5m (2023)  2m in (2024): 2m - 5m
gdf_threshold = merged_gdf[(merged_gdf['nearest_distance'] <= distance_threshold) & (merged_gdf['elev_diff'] != 0)]
gdf_threshold.head(3)

# %% [cell 27]
x_elev = gdf_threshold['Elevation_left'].astype(float).values.reshape(-1, 1)
y_diff = gdf_threshold['elev_diff'].values
theil_sen_non_agg = TheilSenRegressor(random_state=42).fit(x_elev, y_diff)
pred_diff_values = theil_sen_non_agg.predict(x_elev)

plt.figure()
plt.scatter(
    gdf_threshold['Elevation_left'],
    y_diff,
    color='royalblue', 
    edgecolor='black', 
    alpha=0.7, 
    label='Data points'
)
plt.plot(
    gdf_threshold['Elevation_left'],
    pred_diff_values,
    color='darkred', 
    linewidth=2, 
    linestyle='--', 
    label='Theil-Sen regression line'
)

plt.ylabel('Elevation difference (m)', fontsize=12)
plt.xlabel('Elevation (m)', fontsize=12)
plt.legend(fontsize=12, loc='best')

plt.grid(linestyle='--', alpha=0.6)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "elevation.png"),dpi=300)
plt.show()

# %% [cell 28]
fig, ax = plt.subplots()
n, bin, patches = plt.hist(
    gdf_threshold['elev_diff'], 
    bins=20, 
    color='skyblue', 
    edgecolor='black', 
    alpha=0.7
)
mean_value = gdf_threshold['elev_diff'].mean()
plt.axvline(mean_value, color='red', linestyle='--', linewidth=2, label=f'Mean = {mean_value:.2f}')

for i in range(len(n)):
    plt.text(bin[i] + (bin[i+1] - bin[i]) / 2, n[i] + 0.5, f"{int(n[i])}", 
             ha='center', va='bottom', fontsize=10, color='black')

plt.xlabel('Elevation difference (m)', fontsize=14)
plt.ylabel('Frequency', fontsize=14)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.legend(fontsize=12)
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "Frequency.png"),dpi=300)
plt.show()

# %% [cell 29]
xx_elev = gdf_threshold['elev_diff'].astype(float).values.reshape(-1, 1)
yy_diff = gdf_threshold['Elevation_left'].values
theil_sen_lg = TheilSenRegressor(random_state=42).fit(xx_elev, yy_diff)
predicted_values = theil_sen_lg.predict(xx_elev)

plt.figure()
plt.scatter(
    gdf_threshold['elev_diff'], 
    gdf_threshold['Elevation_left'], 
    color='royalblue', 
    edgecolor='black', 
    alpha=0.7, 
    label='Data points'
)
plt.plot(
    gdf_threshold['elev_diff'], 
    predicted_values, 
    color='darkred', 
    linewidth=2, 
    linestyle='--', 
    label='Theil-Sen regression line'
)

plt.xlabel('Elevation difference (m)', fontsize=12)
plt.ylabel('Elevation (m)', fontsize=12)
plt.legend(fontsize=12, loc='best')

plt.grid(linestyle='--', alpha=0.6)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.tight_layout()
plt.show()

# %% [cell 30]
# Use pandas `cut` function to categorize 'raster_value' into bins
gdf_threshold = gdf_threshold.copy()
gdf_threshold['elevation_bin'] = pd.cut(gdf_threshold['Elevation_left'], bins=elev_bins, right=False)

# %% [cell 31]
gdf_threshold.tail(3) # Check the output

# %% [cell 32]
# Group by the elevation bins and calculate count and average
bin_stats = gdf_threshold.groupby('elevation_bin', observed=False)['elev_diff'].agg(
    count='count', 
    average_elev_diff='mean'
).reset_index()

# Print the result
bin_stats.shape

# %% [cell 33]
bin_stats

# %% [cell 34]
import numpy as np
import pandas as pd
from sklearn.linear_model import TheilSenRegressor

# --- 1) Build bin stats (raw means) ---
bin_stats = (
    gdf_threshold
    .groupby('elevation_bin', observed=False)['elev_diff']
    .agg(count='count', average_elev_diff='mean')
    .reset_index()
)

# midpoint elevation for each bin
bin_stats['mean_bin'] = bin_stats['elevation_bin'].apply(
    lambda itv: (itv.left + itv.right) / 2
)

# --- 2) Fit regression ONLY on bins that have raw data ---
train = bin_stats.dropna(subset=['average_elev_diff']).copy()

X_train = train['mean_bin'].to_numpy().reshape(-1, 1)
y_train = train['average_elev_diff'].to_numpy()

theil_sen = TheilSenRegressor(random_state=42)
theil_sen.fit(X_train, y_train)

# --- 3) Predict for ALL bins (including empty ones) ---
X_all = bin_stats['mean_bin'].to_numpy().reshape(-1, 1)
bin_stats['pred_mean'] = theil_sen.predict(X_all)

# --- 4) Hybrid: use raw where available, else predicted ---
bin_stats['final_mean'] = bin_stats['average_elev_diff'].fillna(bin_stats['pred_mean'])

# Optional: flag which values were filled
bin_stats['source'] = np.where(bin_stats['average_elev_diff'].isna(), 'predicted', 'raw')

# Result you want:
# mean_bin = mid-bin elevation
# final_mean = raw mean if exists else predicted

# %% [cell 35]
# Calculate the mean of each interval in the elevation_bin column
bin_stats['mean_bin'] = bin_stats['elevation_bin'].apply(lambda interval: (interval.left + interval.right) / 2)


bin_stats['area'] = area_per_class 
bin_stats['area1'] = area_per_class1
bin_stats['area_average'] = (bin_stats['area']+bin_stats['area1']) / 2

bin_stats['diff_pred'] = bin_stats['final_mean']

# %% [cell 36]

# %% [cell 37]
bin_stats

# %% [cell 38]
bin_stats['amb'] = (880 * bin_stats['diff_pred'] * bin_stats['area_average'])
bin_stats

# %% [cell 39]

if snd1 is not None and os.path.exists(snd1):
    snd11.head(7)
    
    snd11.sort_values(by = 'Elevation')
else:
    print("snd1 not provided or file missing")

if snd2 is not None and os.path.exists(snd2):
    snd22.head(7)
    
    snd22.sort_values(by = 'Elevation')
else:
    print("snd2 not provided or file missing")

if snd1 is not None:
    print(snd11.head(3))

if snd2 is not None:
    print(snd22.head(3))

# %% [cell 40]
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt

if snd1 is not None and os.path.exists(snd1):
    # Assuming snd11 is defined somewhere above this snippet if needed
    # For this snippet to run, you likely need a definition:
    # snd11 = pd.read_csv(snd1) 

    x_snd1 = snd11['Elevation'].astype(float).values.reshape(-1, 1)
    y_snd1 = snd11['Snow_depth'].values

    # --- Fit normal linear regression ---
    lin_reg = LinearRegression().fit(x_snd1, y_snd1)

    # --- Scatter plot of data points ---
    plt.figure()
    plt.scatter(
        x_snd1, 
        y_snd1,
        color='royalblue', 
        edgecolor='black', 
        alpha=0.7, 
        label='Stake locations'
    )

    # --- Regression line ---
    plt.plot(
        x_snd1,  # or x_snd if defined elsewhere
        lin_reg.predict(x_snd1),
        color='darkred', 
        linewidth=2, 
        linestyle='--', 
        label='Linear regression line'
    )

    plt.grid(linestyle='--', alpha=0.6)
    plt.xlabel('Elevation (m)')
    plt.ylabel('Snow depth (m)')
    plt.legend()
    # Use plt.show() to display the plot window
    plt.show() 

    # --- Predict for mid-bin values ---
    mid_bin1 = bin_stats['mean_bin'].astype(float).values.reshape(-1, 1)
    mid_bin_snd1 = lin_reg.predict(mid_bin1)

    # Use print() to display these values in the console
  
    # --- Prepare data ---

else:
    print("no files")

# %% [cell 41]

if snd2 is not None and os.path.exists(snd2):
    # --- Prepare data ---
    x_snd2 = snd22['Elevation'].astype(float).values.reshape(-1, 1)
    y_snd2 = snd22['Snow_depth'].values

    # --- Fit normal linear regression ---
    lin_reg = LinearRegression().fit(x_snd2, y_snd2)

    # --- Scatter plot of data points ---
    plt.figure()
    plt.scatter(
        x_snd2, 
        y_snd2,
        color='royalblue', 
        edgecolor='black', 
        alpha=0.7, 
        label='Stake locations'
    )

    # --- Regression line ---
    plt.plot(
        x_snd2,  # or x_snd if defined elsewhere
        lin_reg.predict(x_snd2),
        color='darkred', 
        linewidth=2, 
        linestyle='--', 
        label='Linear regression line'
    )

    plt.grid(linestyle='--', alpha=0.6)
    plt.xlabel('Elevation (m)')
    plt.ylabel('Snow depth (m)')
    plt.legend()
    plt.show()

    # --- Predict for mid-bin values ---
    mid_bin2 = bin_stats['mean_bin'].astype(float).values.reshape(-1, 1)
    mid_bin_snd2 = lin_reg.predict(mid_bin2)
    mid_bin_snd2 = np.where(mid_bin_snd2 > 0, mid_bin_snd2, 0)


    
else:
   print("no such files")

# %% [cell 42]
bin_stats

# %% [cell 43]

if (
    snd1 is not None and os.path.exists(snd1) and
    snd2 is not None and os.path.exists(snd2)
):
    bin_stats[f'snow_depth_{t1}'] = mid_bin_snd1
    bin_stats[f'snow_depth_{t2}'] = mid_bin_snd2
    bin_stats[f'diff_snow_depth_{t2}'] = mid_bin_snd2 - mid_bin_snd1
else:
    print("snow files not fully provided or missing")

# %% [cell 44]

if (
    snd1 is not None and os.path.exists(snd1) and
    snd2 is not None and os.path.exists(snd2)
):
    bin_stats['Annual_MB'] = ((
        880 * bin_stats['diff_pred']
        + bin_stats[f'diff_snow_depth_{t2}'] * (400 - 880))/(Time_period)
    )
else:
    bin_stats['Annual_MB_no_snow'] = ((880 * bin_stats['diff_pred']))/(Time_period)

# %% [cell 45]
bin_stats

# %% [cell 46]

if snd1 is not None and os.path.exists(snd1):
    amb = np.sum(bin_stats['Annual_MB']* bin_stats['area_average'])/np.sum(bin_stats['area_average'])
    print(f"Mass balance(presence of snow) is:{amb} mm w.e. a⁻¹")
else:
    amb = np.sum(bin_stats['Annual_MB_no_snow']* bin_stats['area_average'])/np.sum(bin_stats['area_average'])
    print(f"Mass balance(no snow) is:{amb} mm w.e. a⁻¹")

# %% [cell 47]
x_agg = bin_stats['mean_bin'].astype(float).values.reshape(-1, 1)
y_agg = bin_stats['average_elev_diff'].values
area = bin_stats['area'].values
mask = ~np.isnan(y_agg)
x_agg_clean = x_agg[mask]
y_agg_clean = y_agg[mask]
area_clean = area[mask]

theil_sen_agg = TheilSenRegressor().fit(x_agg_clean, y_agg_clean)

fig, ax1 = plt.subplots(figsize=(10,6))
ax1.scatter(x_agg_clean, y_agg_clean, color='blue', label='Elevation difference')
ax1.plot(x_agg_clean, theil_sen_agg.predict(x_agg_clean), color='blue', label='Theil-Sen regression line')
ax1.set_xlabel('Elevation (mean_bin)',fontsize=14)
ax1.set_ylabel('Elevation difference (m)', color='blue',fontsize=14)
ax1.tick_params(axis='y', labelcolor='blue')
ax1.legend(loc='upper left')
ax1.grid(True, linestyle='--', alpha=0.6)

ax2 = ax1.twinx()
ax2.scatter(x_agg_clean, area_clean, color='red', marker='o', alpha=0.7,label='Glacier area(m$^2$)')
ax2.set_ylabel('Glacier area (m$^2$)', color='red',fontsize=14)
ax2.tick_params(axis='y', labelcolor='red')
plt.legend(loc='upper left', bbox_to_anchor=(0.004, 0.86))
plt.savefig(os.path.join(output_dir, "elevation.png"),dpi=450)
plt.show()

# %% [cell 48]
bin_stats['diff_pred2'] = theil_sen_agg.predict(x_agg)

if snd1 is not None and os.path.exists(snd1):
    bin_stats['Annual_MB_Aggregated'] = ((880 * bin_stats['diff_pred2']+ bin_stats[f'diff_snow_depth_{t2}'] * (400-880)))/(Time_period)
else:
    bin_stats['Annual_MB_Aggregated'] = ((880 * bin_stats['diff_pred2']))/(Time_period)
    
bin_stats

# %% [cell 49]
amb2 = np.sum(bin_stats['Annual_MB_Aggregated']* bin_stats['area_average'])/np.sum(bin_stats['area_average'])
print(f"Annual Mass balance Aggregated(presence of snow):{amb2} mm w.e. a⁻¹")

# %% [cell 50]
amb_agg_data = np.sum(bin_stats['Annual_MB_Aggregated']* bin_stats['area_average'])/np.sum(bin_stats['area_average'])
amb_agg_data
np.sum(bin_stats['area'])/1000000

amb_array = [amb, amb_agg_data]
print(amb_array)

labels = ['Non-aggregated data', 'Aggregated data']

plt.figure()
bars = plt.bar(labels, amb_array, color=['steelblue', 'orange'], alpha=0.8, edgecolor='black')

for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        height, 
        f"{height:.2f}", 
        ha='center', 
        va='bottom' if height > 0 else 'top',
        fontsize=12,
        color='black'
    )
plt.ylabel('Annual mass balance (mm w.e.a)', fontsize=12)
plt.grid(axis='y', linestyle='--', alpha=0.6)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.axhline(0, color='black', linewidth=1)
plt.tight_layout()
plt.show()

# %% [cell 51]


# --------------------------------------------------------------------
# 1. Get glacier boundary segments
# --------------------------------------------------------------------

from shapely.geometry import LineString, MultiLineString
def get_boundary_segments(glacier_shp_path):
    gdf = gpd.read_file(glacier_shp_path)
    boundary = gdf.geometry.boundary.unary_union

    if boundary.geom_type == "MultiLineString":
        lines = list(boundary.geoms)
    else:
        lines = [boundary]

    segments = []
    for line in lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            segments.append((coords[i], coords[i + 1]))

    return segments, gdf.crs

# --------------------------------------------------------------------
# 2. Sample DEM elevation at coordinate points
# --------------------------------------------------------------------
def get_elevation_for_coords(dem_path, coords):
    """
    Samples elevation from DEM at given (x, y) coordinates.
    Returns a numpy array of elevation values.
    """
    with rasterio.open(dem_path) as src:
        band = src.read(1)
        values = []
        for x, y in coords:
            row, col = src.index(x, y)
            elev = band[row, col]
            values.append(elev)
    return np.array(values)

# --------------------------------------------------------------------
# 3. Compute boundary length in fixed elevation bands (5101–5501)
# --------------------------------------------------------------------
def compute_segment_band_lengths_fixed(segments, start_elev, end_elev, interval=elevation_interval):
    """
    Computes total boundary length in each elevation band, using
    a fixed elevation range from 5101 m to 5501 m with given interval.
    """
    avg_elevations = (start_elev + end_elev) / 2.0

    # --- FIXED BIN RANGE HERE ---
    min_elev = elev_bins[0]
    max_elev = elev_bins[-1]
    bins = np.arange(min_elev, max_elev + interval, interval)
    # ----------------------------

    labels = [f"{int(bins[i])}-{int(bins[i+1])} m" for i in range(len(bins) - 1)]

    # Digitize avg elevations into these fixed bins
    band_indices = np.digitize(avg_elevations, bins) - 1  # shift to 0-based

    band_lengths = {}
    for (p1, p2), band_idx in zip(segments, band_indices):
        if 0 <= band_idx < len(labels):
            band = labels[band_idx]
            length = np.hypot(p2[0] - p1[0], p2[1] - p1[1])  # length in CRS units (e.g. meters)
            band_lengths[band] = band_lengths.get(band, 0) + length

    df = pd.DataFrame(
        list(band_lengths.items()),
        columns=["Elevation Band", "Boundary Length (m)"]
    ).sort_values("Elevation Band")

    return df, bins

# --------------------------------------------------------------------
# 4. Create segment GeoDataFrame using same fixed bins
# --------------------------------------------------------------------
def create_segment_gdf_fixed(segments, start_elev, end_elev, crs, interval=elevation_interval):
    """
    Creates a GeoDataFrame of boundary segments, each labeled with an
    elevation band using the fixed 5101–5501 m range.
    """
    avg_elevations = (start_elev + end_elev) / 2.0

    # --- FIXED BIN RANGE HERE ---
    min_elev = elev_bins[0]
    max_elev = elev_bins[-1]
    bins = np.arange(min_elev, max_elev + interval, interval)
    # ----------------------------

    labels = [f"{int(bins[i])}-{int(bins[i+1])} m" for i in range(len(bins) - 1)]
    band_indices = np.digitize(avg_elevations, bins) - 1

    bands = [labels[i] if 0 <= i < len(labels) else None for i in band_indices]
    lines = [LineString([p1, p2]) for (p1, p2) in segments]

    gdf = gpd.GeoDataFrame(
        {
            "geometry": lines,
            "Elevation Band": bands
        },
        crs=crs
    )

    return gdf

# --------------------------------------------------------------------
# 5. Plot segments colored by elevation band
# --------------------------------------------------------------------
def plot_segments_by_band(segment_gdf):
    """
    Plots glacier boundary segments colored by elevation band.
    """
    fig, ax = plt.subplots(figsize=(10, 10))
    segment_gdf.plot(
        ax=ax,
        column="Elevation Band",
        cmap="viridis",
        linewidth=2,
        legend=True
    )
    ax.set_title("Glacier Boundary Segments by Elevation Band", fontsize=14)
    ax.set_axis_off()
    plt.tight_layout()
    plt.show()

# --------------------------------------------------------------------
# 6. USAGE EXAMPLE
# --------------------------------------------------------------------
# Make sure these paths are defined before running:
# glacier_shp_path = r"path\to\your\glacier.shp"
# corrected_dem    = r"path\to\your\corrected_dem.tif"

# Get boundary segments and CRS
segments, crs = get_boundary_segments(glacier_shp_path)

# Build list of coords (start and end of each segment)
start_coords = [seg[0] for seg in segments]
end_coords   = [seg[1] for seg in segments]
all_coords   = start_coords + end_coords

# Sample DEM elevations at all these coords
elevations_raw = get_elevation_for_coords(corrected_dem, all_coords)

# Split into start and end elevation arrays
start_elev = elevations_raw[:len(segments)]
end_elev   = elevations_raw[len(segments):]

# Compute boundary lengths in fixed bands 5101–5501 m
df_result, used_bins = compute_segment_band_lengths_fixed(
    segments, start_elev, end_elev, interval=elevation_interval
)

print("Boundary length per elevation band:")
print(df_result)
print("\nBins used:", used_bins)


# Create GeoDataFrame of segments with band labels and plot
segment_gdf = create_segment_gdf_fixed(
    segments, start_elev, end_elev, crs, interval=elevation_interval
)

plot_segments_by_band(segment_gdf)
df_result

# %% [cell 52]
df_result

# %% [cell 53]
bin_stats['Perimeter'] = df_result['Boundary Length (m)'].values

# %% [cell 54]
bin_stats

# %% [cell 55]
# %% [cell 55]
if snd1 is not None and os.path.exists(snd1) and snd2 is not None and os.path.exists(snd2):
    mb_col = 'Annual_MB'
else:
    mb_col = 'Annual_MB_no_snow'

bin_stats['Area_Average_MB'] = (
    bin_stats[mb_col] * bin_stats['area_average']
) / np.sum(bin_stats['area_average'])

# %% [cell 56]
bin_stats

# %% [cell 57]

#for you to use this code you should have csv file with column name bg(area average mass balance),Absolute bg,Average Area and Per
# Constants
PIXEL_CONSTANT = 10
UNCERTAINTY_ICE_DENSITY = 30
UNCERTAINTY_SNOW_DENSITY = 100

# Load CSV


# Clean column names
bin_stats.columns = bin_stats.columns.str.strip().str.replace('\xa0', ' ', regex=True)
bin_stats['Absolute bg']=abs(bin_stats['Area_Average_MB'])
# ---- STEP 1: Average of bg ----
avg_bg = bin_stats['Area_Average_MB'].mean()

# ---- STEP 2: Total Area Average ----
total_area_avg = bin_stats['area'].sum()

# ---- STEP 3: (x - X)^2 ----
bin_stats['(x - X)^2'] = (bin_stats['Area_Average_MB'] - avg_bg) ** 2

# ---- STEP 4: Total Summation of (x - X)^2 ----
total_summation = bin_stats['(x - X)^2'].sum()

# ---- STEP 5: dbz ----
dbz = np.sqrt(total_summation / len(bin_stats))

# ---- STEP 6: dAz = 0.5 * pixel * Perimeter ----
bin_stats['dAz'] = 0.5 * PIXEL_CONSTANT * bin_stats['Perimeter']

# ---- STEP 7: Uncertainty for Ice ----
bin_stats['Uncertainty Ice'] = (
    (bin_stats['area'] * dbz) +
    (bin_stats['dAz'] * bin_stats['Absolute bg']) +
    (bin_stats['area'] * UNCERTAINTY_ICE_DENSITY)
) / total_area_avg

# ---- STEP 8: Uncertainty for Snow ----
bin_stats['Uncertainty Snow'] = (
    (bin_stats['area'] * dbz) +
    (bin_stats['dAz'] * bin_stats['Absolute bg']) +
    (bin_stats['area'] * UNCERTAINTY_SNOW_DENSITY)
) / total_area_avg

# ---- STEP 9: Total Sum of Each ----
total_uncertainty_ice = bin_stats['Uncertainty Ice'].sum()
total_uncertainty_snow = bin_stats['Uncertainty Snow'].sum()

# ---- STEP 10: Overall Uncertainty Average ----
uncertainty_overall = (total_uncertainty_ice + total_uncertainty_snow) / 2

# ---- Round and Output ----
bin_stats = bin_stats.round(3)

print(bin_stats)
print("\nAverage bg:", round(avg_bg, 3))
print("Total Area Average:", round(total_area_avg, 3))
print("Total Summation (x - X)^2:", round(total_summation, 3))
print("dbz:", round(dbz, 3))
print("Total Uncertainty Ice:", round(total_uncertainty_ice, 3))
print("Total Uncertainty Snow:", round(total_uncertainty_snow, 3))
print("Overall Uncertainty Average:", round(uncertainty_overall, 3))

# Optional: Save output
bin_stats.to_csv(os.path.join(output_dir, "uncertainty_results.csv"), index=False)

# %% [cell 58]


# %% [cell 59]

