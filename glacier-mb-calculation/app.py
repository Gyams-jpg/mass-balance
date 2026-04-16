
import os, io, json, re, zipfile, shutil, tempfile, traceback, contextlib, base64, textwrap
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Thana Notebook Streamlit Wrapper", layout="wide")

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"

def image_to_data_uri(path):
    path = Path(path)
    if not path.exists():
        return ""
    suffix = path.suffix.lower().replace(".", "")
    mime = "jpeg" if suffix in ("jpg","jpeg") else suffix
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/{mime};base64,{data}"

logo_b64 = image_to_data_uri(ASSETS_DIR / "logo.jpg")
bg_b64 = image_to_data_uri(ASSETS_DIR / "glacier_background.png")

st.markdown(textwrap.dedent(f"""
<style>
.hero-wrap {{border-radius:28px;overflow:hidden;margin-bottom:1rem;border:1px solid rgba(255,255,255,.08);}}
.hero-top {{background:white;padding:18px 30px;display:flex;justify-content:space-between;align-items:center;gap:20px;}}
.hero-top img {{height:88px;object-fit:contain;}}
.hero-org {{flex:1;text-align:center;color:black;}}
.hero-main {{min-height:430px;background-image:linear-gradient(rgba(8,20,45,.45),rgba(8,20,45,.70)),url('{bg_b64}');background-size:cover;background-position:center;display:flex;align-items:center;justify-content:center;padding:40px;}}
.hero-card {{width:min(1100px,88%);background:rgba(20,30,45,.35);border:1px solid rgba(255,255,255,.12);border-radius:26px;padding:48px 36px;text-align:center;}}
.hero-card h1 {{margin:0;font-size:3rem;color:white;font-weight:800;}}
.hero-card p {{margin-top:18px;font-size:1.2rem;color:rgba(255,255,255,.92);}}
.hero-note {{margin-top:16px;background:rgba(49,99,190,.18);color:#79b0ff;border-radius:14px;padding:18px 20px;font-size:1rem;}}
</style>
<div class="hero-wrap">
  <div class="hero-top">
    <img src="{logo_b64}">
    <div class="hero-org">
      <h2>National Center for Hydrology and Meteorology</h2>
      <p>Royal Government of Bhutan</p>
    </div>
    <img src="{logo_b64}">
  </div>
  <div class="hero-main">
    <div class="hero-card">
      <h1>Thana Glacier Mass Balance Calculation</h1>
      <p>Cryosphere Services Division - Thana notebook workflow.</p>
    </div>
  </div>
</div>
<div class="hero-note">
This app follows the uploaded Thana notebook workflow: IDW interpolation → DEM bias correction → glacier-clipped hypsometry → nearest-point differencing → optional snow correction → SMB and uncertainty summary.
</div>
"""), unsafe_allow_html=True)

st.info("Replace this top section into your existing app.py. Keep the rest of your original workflow code below this line.")
