
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
import pandas as pd
import numpy as np
import re
from pathlib import Path

import streamlit as st
NOTEBOOK_FILE = Path(__file__).parent / "NOTEBOOK_CELLS_editable.py"

notebook_text = NOTEBOOK_FILE.read_text(encoding="utf-8")

NOTEBOOK_CELLS = re.split(
    r'^\s*# %% \[cell \d+\]\s*$',
    notebook_text,
    flags=re.MULTILINE
)

NOTEBOOK_CELLS = [cell.strip() for cell in NOTEBOOK_CELLS if cell.strip()]

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
    This user interface is script based glacier mass balance workflow:
    IDW interpolation → DEM bias correction → glacier-clipped hypsometry
    → nearest-point differencing → optional snow correction
    → amb and uncertainty summary.
</div>
""")

st.markdown(banner_html, unsafe_allow_html=True)

with st.expander("Show Scientific Equations Used", expanded=False):

    st.markdown("### Geodetic Mass Balance")
    st.latex(r"b_g=\frac{\Delta h_g \rho_i + (s_{t2}-s_{t1})(\rho_s-\rho_i)}{t_2-t_1}")
    st.markdown(
        "Where $b_g$ is the annual geodetic mass balance, "
        "$\Delta h_g$ is glacier surface elevation change (negative when the glacier surface lowers), "
        "*ρᵢ* is ice density, *ρₛ* is snow density, and "
        "$s_{t1}, s_{t2}$ are snow thicknesses at times $t_1$ and $t_2$. "
        "$t_2-t_1$ is the time interval between observations."
    )

    st.markdown("### Area-Averaged Geodetic Mass Balance")
    st.latex(r"\overline{b_g}=\frac{\sum_z A_z\, b_{gz}}{A_T}")
    st.markdown(
        "Where $\overline{b_g}$ is the glacier-wide average annual mass balance, "
        "$A_z$ is the area of each 50 m elevation band, "
        "$b_{gz}$ is the average geodetic mass balance of elevation band $z$, "
        "and $A_T$ is the total glacier area."
    )

    st.markdown("### Direct / Stake-Based Mass Balance")
    st.latex(r"b_d=\frac{\Delta h_d \rho_i + (s_{t2}-s_{t1})(\rho_s-\rho_i)}{t_2-t_1}")
    st.markdown(
        "Where $b_d$ is the annual mass balance from stake measurements, "
        "$\Delta h_d$ is the change in stake height between $t_1$ and $t_2$, "
        "*ρᵢ* is ice density, *ρₛ* is snow density, and "
        "$s_{t1}, s_{t2}$ are snow thicknesses measured at the two observation times."
    )

    st.markdown("### Uncertainty Equation")
    st.latex(
    r"\sigma=\frac{\sum A_z\, \mathrm{d}b_z+\sum \mathrm{d}A_z |b_z|+\sum A_z\, \mathrm{d}b_{\rho}}{A_T}"
)
    st.markdown(
        "Where $\sigma$ is the uncertainty of glacier-wide annual mass balance, "
        "$\mathrm{d} b_z$ is uncertainty in mass balance for each elevation band, "
        "$\mathrm{d} A_z$ is uncertainty in the delineated area of each band, "
        "$|b_z|$ is the absolute value of band mass balance, "
        "d*bρ* is uncertainty due to density assumptions, "
        "and $A_T$ is the total glacier area."
    )

    st.markdown("### Constants Used in This Workflow")
    st.markdown(
        "- Ice density: **880 ± 30 kg m⁻³**\n"
        "- Snow density: **400 ± 100 kg m⁻³**\n"
        "- Elevation band interval: **50 m**\n"
        "- Regression used: **Theil-Sen** for elevation-difference estimation and **linear regression** for snow-thickness estimation"
    )

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
        st.subheader("Time Settings")

        t1 = int(st.text_input("t1 (Previous Year)", value="2024"))
        t2 = int(st.text_input("t2 (Current Year)", value="2025"))

        if t1 >= t2:
            st.error("t1 must be less than t2")
            return

    with st.sidebar:
        st.header("Inputs")

        with st.expander("Show Sample CSV Format", expanded=False):

            st.markdown("### Sample dGPS CSV")
            st.markdown(
                "Expected columns (recommended order): "
                "**Point_id, Elevation, Northing, Easting**"
            )

            dgps_sample = pd.DataFrame({
                "Point_id": [1, 2, 3],
                "Elevation": [5123.45, 5124.10, 5122.88],
                "Northing": [3098765.12, 3098766.55, 3098768.20],
                "Easting": [456789.33, 456790.12, 456792.01]
            })

            st.dataframe(dgps_sample, use_container_width=True)

            st.download_button(
                "Download dGPS Sample CSV",
                dgps_sample.to_csv(index=False),
                file_name="dgps_sample.csv",
                mime="text/csv"
            )

            st.markdown("---")

            st.markdown("### Sample Snow Depth CSV")
            st.markdown(
                "Expected columns: **ID, Elevation, Snow_Depth**"
            )

            snow_sample = pd.DataFrame({
                "ID": ["Stake 1", "Stake 2", "Stake 3"],
                "Elevation": [5000, 5050, 5100],
                "Snow_Depth": [0.25, 0.18, 0.10]
            })

            st.dataframe(snow_sample, use_container_width=True)

            st.download_button(
                "Download Snow Sample CSV",
                snow_sample.to_csv(index=False),
                file_name="snow_sample.csv",
                mime="text/csv"
            )

            st.info(
                "Ensure numeric values only where required, correct column names, "
                "and matching projected CRS units for dGPS coordinates."
            )

        dgps_2025 = st.file_uploader("Current year dGPS CSV (raw input for csv_path)", type=["csv"])
        dgps_2024 = st.file_uploader("Previous year dGPS CSV (raw input for csv_path)", type=["csv"])
        raster_tif = st.file_uploader("DEM raster (.tif)", type=["tif", "tiff"])
        glacier_zip = st.file_uploader("Glacier shapefile ZIP (.zip)", type=["zip"])
        snow_2024 = st.file_uploader("Previous year Snow depth CSV  (optional)", type=["csv"])
        snow_2025 = st.file_uploader("Current year Snow depth CSV  (optional)", type=["csv"])

        st.header("Parameters")
        cell_size = st.number_input("cell_size", value=1.0, step=0.1)
        search_radius = st.number_input("search_radius", value=0.7, step=0.1)
        power = st.number_input("power", value=2, step=1)
        distance_threshold = st.number_input("distance_threshold", value=3.0, step=0.5)
        elevation_interval = st.number_input("elevation_interval", value=50, step=10)

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
        missing.append("Current dGPS CSV")
    if dgps_2024 is None:
        missing.append("Previous dGPS CSV")
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
            "t1":t1,
            "t2":t2,
            "elevation_interval":elevation_interval,
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
