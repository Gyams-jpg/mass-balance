
import os
import io
import json
import re
import zipfile
import shutil
import tempfile
import traceback
import contextlib
import base64
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Thana Notebook Streamlit Wrapper", layout="wide")

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"

def img_to_base64(path):
    path = Path(path)
    if path.exists():
        return base64.b64encode(path.read_bytes()).decode()
    return ""

logo_b64 = img_to_base64(ASSETS_DIR / "logo.png")
bg_b64 = img_to_base64(ASSETS_DIR / "glacier_background.png")

st.markdown(
    f"""
    <style>
    .hero-wrap {{
        border-radius: 28px;
        overflow: hidden;
        margin-bottom: 1rem;
        border: 1px solid rgba(255,255,255,0.08);
    }}

    .hero-top {{
        background: white;
        padding: 18px 30px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}

    .hero-top img {{
        height: 88px;
        object-fit: contain;
    }}

    .hero-org {{
        flex: 1;
        text-align: center;
        color: black;
        line-height: 1.2;
    }}

    .hero-org h2 {{
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
    }}

    .hero-org p {{
        margin: 6px 0 0 0;
        font-size: 1.05rem;
    }}

    .hero-main {{
        min-height: 430px;
        background-image:
            linear-gradient(rgba(8,20,45,0.45), rgba(8,20,45,0.70)),
            url("data:image/png;base64,{bg_b64}");
        background-size: cover;
        background-position: center;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 40px;
    }}

    .hero-card {{
        width: min(1100px, 88%);
        background: rgba(20,30,45,0.35);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 26px;
        padding: 48px 36px;
        text-align: center;
        backdrop-filter: blur(10px);
    }}

    .hero-card h1 {{
        margin: 0;
        font-size: 3rem;
        color: white;
        font-weight: 800;
    }}

    .hero-card p {{
        margin-top: 18px;
        font-size: 1.2rem;
        color: rgba(255,255,255,0.92);
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

        <div class="hero-top">
            <img src="data:image/png;base64,{logo_b64}">
            <div class="hero-org">
                <h2>National Center for Hydrology and Meteorology</h2>
                <p>Royal Government of Bhutan</p>
            </div>
            <img src="data:image/png;base64,{logo_b64}">
        </div>

        <div class="hero-main">
            <div class="hero-card">
                <h1>Thana Glacier Mass Balance Calculation</h1>
                <p>Cryosphere Services Division - Thana notebook workflow.</p>
            </div>
        </div>

    </div>

    <div class="hero-note">
        This app follows the uploaded Thana notebook workflow:
        IDW interpolation → DEM bias correction → glacier-clipped hypsometry
        → nearest-point differencing → optional snow correction
        → SMB and uncertainty summary.
    </div>
    """,
    unsafe_allow_html=True
)
def load_notebook_cells_from_readable(py_path):
    text = Path(py_path).read_text(encoding="utf-8")
    parts = re.split(r"^# %% \[cell \d+\]\s*$", text, flags=re.M)
    cells = [p.strip("\n") for p in parts if p.strip()]
    return cells

EDITABLE_CELLS_FILE = Path(__file__).with_name("NOTEBOOK_CELLS_editable.py")
NOTEBOOK_CELLS = load_notebook_cells_from_readable(EDITABLE_CELLS_FILE)

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
    for key in ["smb", "smb2", "amb_agg_data"]:
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
        snow_2024 = st.file_uploader("Snow depth CSV 1 (optional)", type=["csv"])
        snow_2025 = st.file_uploader("Snow depth CSV 2 (optional)", type=["csv"])

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
