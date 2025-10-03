
"""
Streamlit Mapping Pelanggan – AMR / P2TL
----------------------------------------
Fitur:
- Upload CSV/XLSX (kolom minimal: LOCATION_CODE, LAT, LON).
- Pewarnaan pin berdasarkan "Status Periksa": 
  Periksa - Sesuai (green), Temuan - K2 (red), Temuan - P1 (orange),
  Temuan - P2 (darkorange), Temuan - P3 (blue), Temuan - P4 (purple).
- Filter: tarif, jenis pelanggan, status periksa, status TO, range daya, skor anomali, tanggal last read.
- Peta Folium + MarkerCluster + Heatmap (opsional) + MeasureControl + LayerControl.
- Tabel data terfilter dan ekspor ke Excel.
"""

import io
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

import folium
from folium.plugins import MarkerCluster, HeatMap, MeasureControl
from streamlit_folium import st_folium

st.set_page_config(page_title="Mapping Pelanggan", layout="wide")
st.title("🗺️ Mapping Pelanggan – AMR / P2TL")
st.caption("Deploy-ready • GitHub + Streamlit Cloud")

with st.sidebar:
    st.header("📥 Upload Data")
    uploaded = st.file_uploader("Unggah file pelanggan (CSV/XLSX)", type=["csv", "xlsx"])
    st.markdown(
        "**Kolom minimal:** `LOCATION_CODE`, `LAT`, `LON`.\n"
        "**Direkomendasikan:** `TARIFF`, `POWER`, `LOCATION_TYPE`, `STATUS_TO`, "
        "`ANOMALY_SCORE`, `LAST_READ_TIME`, **`UPDATE_STATUS`/`STATUS_PERIKSA`**."
    )

    st.divider()
    st.header("🧭 Opsi Peta")
    basemap = st.selectbox(
        "Basemap",
        ["OpenStreetMap", "CartoDB positron", "CartoDB dark_matter", "Stamen Terrain", "Stamen Toner"],
        index=1
    )
    enable_heatmap = st.checkbox("Tampilkan Heatmap (berdasarkan ANOMALY_SCORE)", value=False)
    cluster_enabled = st.checkbox("Aktifkan MarkerCluster", value=True)

    st.divider()
    st.header("🎯 Logika Warna (fallback)")
    high_threshold = st.number_input("Ambang skor anomali tinggi", min_value=0.0, max_value=100.0, value=70.0, step=1.0)
    mid_threshold  = st.number_input("Ambang skor anomali menengah", min_value=0.0, max_value=100.0, value=40.0, step=1.0)

# ---------- Helpers ----------
def read_data(file) -> pd.DataFrame:
    if file is None:
        return pd.DataFrame()
    name = file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    df.columns = [c.strip().upper() for c in df.columns]

    # Aliases
    rename_map = {
        "IDPEL": "LOCATION_CODE",
        "LATITUDE": "LAT",
        "LONGITUDE": "LON",
        "LONG": "LON",
        "NAMA": "NAMA_PELANGGAN",
    }
    for k, v in rename_map.items():
        if k in df.columns and v not in df.columns:
            df[v] = df[k]

    # Types
    if "LAST_READ_TIME" in df.columns:
        df["LAST_READ_TIME"] = pd.to_datetime(df["LAST_READ_TIME"], errors="coerce")
    for num_col in ["POWER", "ANOMALY_SCORE", "LAT", "LON"]:
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")
    return df

def resolve_status_column(df: pd.DataFrame):
    candidates = [
        "UPDATE_STATUS", "UPDATE-STATUS", "STATUS_PERIKSA", "STATUS PERIKSA",
        "STATUS_P2TL", "HASIL_PERIKSA"
    ]
    for c in candidates:
        if c in df.columns:
            return c
    return None

STATUS_COLOR_MAP = {
    "Periksa - Sesuai": "green",
    "Temuan - K2": "red",
    "Temuan - P1": "orange",
    "Temuan - P2": "darkorange",
    "Temuan - P3": "blue",
    "Temuan - P4": "purple",
}

STATUS_ORDER = [
    "Periksa - Sesuai",
    "Temuan - K2",
    "Temuan - P1",
    "Temuan - P2",
    "Temuan - P3",
    "Temuan - P4",
]

def color_for_row(row, status_col: str | None, high_thr: float, mid_thr: float) -> str:
    if status_col and status_col in row:
        val = str(row.get(status_col, "")).strip()
        if val in STATUS_COLOR_MAP:
            return STATUS_COLOR_MAP[val]
    status_to = str(row.get("STATUS_TO", "")).strip().lower()
    score = row.get("ANOMALY_SCORE", np.nan)
    if status_to in {"target", "to", "suspect"}:
        return "red"
    if not (pd.isna(score)):
        if score >= high_thr: return "red"
        if score >= mid_thr:  return "orange"
    return "green"

def get_center(df: pd.DataFrame):
    if df.empty or ("LAT" not in df or "LON" not in df):
        return -2.5, 118.0, 5  # Indonesia centroid approx
    lat = df["LAT"].dropna(); lon = df["LON"].dropna()
    if lat.empty or lon.empty: return -2.5, 118.0, 5
    return float(lat.median()), float(lon.median()), 11

# ---------- Load ----------
df = read_data(uploaded)
if df.empty:
    st.info("Unggah data untuk mulai memetakan pelanggan. Atau gunakan template di folder `data/` pada repo.")
    st.stop()

required = {"LOCATION_CODE", "LAT", "LON"}
missing = required - set(df.columns)
if missing:
    st.error(f"Kolom wajib hilang: {', '.join(sorted(missing))}. Minimal butuh LAT & LON.")
    st.dataframe(df.head(20))
    st.stop()

# Drop rows missing coords
before = len(df)
df = df.dropna(subset=["LAT", "LON"]).copy()
after = len(df)
if after < before:
    st.warning(f"Mengabaikan {before - after} baris tanpa koordinat valid.")

# ---------- Filters ----------
colA, colB, colC, colD = st.columns([1,1,1,1])
with colA:
    q_idpel = st.text_input("Cari IDPEL (LOCATION_CODE) mengandung…", "")
    q_nama  = st.text_input("Cari Nama Pelanggan mengandung…", "")
with colB:
    tariffs = sorted([t for t in df.get("TARIFF", pd.Series(dtype=str)).dropna().unique()])
    sel_tariff = st.multiselect("Filter Tarif", tariffs, default=[])
with colC:
    types = sorted([t for t in df.get("LOCATION_TYPE", pd.Series(dtype=str)).dropna().unique()])
    sel_types = st.multiselect("Filter Jenis Pelanggan", types, default=(["Customer"] if "Customer" in types else []))
with colD:
    status_to_list = sorted([t for t in df.get("STATUS_TO", pd.Series(dtype=str)).dropna().unique()])
    sel_status_to = st.multiselect("Filter Status TO", status_to_list, default=[])

col1, col2, col3 = st.columns([1,1,1])
with col1:
    if "POWER" in df.columns and df["POWER"].notna().any():
        pmin, pmax = float(np.nanmin(df["POWER"])), float(np.nanmax(df["POWER"]))
        power_rng = st.slider("Range Daya (VA)", min_value=0.0, max_value=max(1000.0, pmax), value=(pmin, pmax))
    else: power_rng = None
with col2:
    if "ANOMALY_SCORE" in df.columns and df["ANOMALY_SCORE"].notna().any():
        smin, smax = float(np.nanmin(df["ANOMALY_SCORE"])), float(np.nanmax(df["ANOMALY_SCORE"]))
        score_rng = st.slider("Range Skor Anomali", min_value=0.0, max_value=max(100.0, smax), value=(smin, smax))
    else: score_rng = None
with col3:
    if "LAST_READ_TIME" in df.columns and df["LAST_READ_TIME"].notna().any():
        dmin = pd.to_datetime(df["LAST_READ_TIME"].min()); dmax = pd.to_datetime(df["LAST_READ_TIME"].max())
        date_rng = st.date_input("Rentang Tanggal Baca Terakhir", value=(dmin.date(), dmax.date()))
    else: date_rng = None

# Status Periksa
status_col = resolve_status_column(df)
if status_col and status_col in df.columns:
    st.info(f"Kolom status periksa terdeteksi: **{status_col}**. Warna pin mengikuti kategori.")
    existing_status = df[status_col].dropna().astype(str).unique().tolist()
    ordered = [s for s in STATUS_ORDER if s in existing_status]
    others  = [s for s in sorted(existing_status) if s not in ordered]
    default_status = ordered if ordered else existing_status
    sel_status_periksa = st.multiselect("Filter Status Periksa", ordered + others, default=default_status)
else:
    sel_status_periksa = None

# Apply filters
filt = pd.Series(True, index=df.index)
if q_idpel: filt &= df["LOCATION_CODE"].astype(str).str.contains(q_idpel, case=False, na=False)
if q_nama and "NAMA_PELANGGAN" in df.columns:
    filt &= df["NAMA_PELANGGAN"].astype(str).str.contains(q_nama, case=False, na=False)
if sel_tariff:   filt &= df.get("TARIFF", pd.Series(index=df.index, dtype=str)).isin(sel_tariff)
if sel_types:    filt &= df.get("LOCATION_TYPE", pd.Series(index=df.index, dtype=str)).isin(sel_types)
if sel_status_to:filt &= df.get("STATUS_TO", pd.Series(index=df.index, dtype=str)).isin(sel_status_to)
if power_rng is not None and "POWER" in df.columns:
    pmin, pmax = power_rng; filt &= df["POWER"].between(pmin, pmax)
if score_rng is not None and "ANOMALY_SCORE" in df.columns:
    smin, smax = score_rng; filt &= df["ANOMALY_SCORE"].between(smin, smax)
if date_rng is not None and "LAST_READ_TIME" in df.columns:
    dstart, dend = date_rng
    filt &= (df["LAST_READ_TIME"].dt.date >= dstart) & (df["LAST_READ_TIME"].dt.date <= dend)
if sel_status_periksa is not None and status_col and status_col in df.columns:
    filt &= df[status_col].astype(str).isin(sel_status_periksa)

view = df[filt].copy()
st.success(f"Menampilkan {len(view):,} dari {len(df):,} pelanggan.")

# ---------- Map ----------
def map_basetiles(name):
    return {
        "OpenStreetMap": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "CartoDB positron": "https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}{r}.png",
        "CartoDB dark_matter": "https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}{r}.png",
        "Stamen Terrain": "https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.jpg",
        "Stamen Toner": "https://stamen-tiles.a.ssl.fastly.net/toner/{z}/{x}/{y}.png",
    }[name]

center_lat, center_lon, zoom = get_center(view)
m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, control_scale=True)
folium.TileLayer(tiles=map_basetiles(basemap), attr=basemap, name=basemap, control=True).add_to(m)
m.add_child(MeasureControl(position='topleft', primary_length_unit='kilometers'))

container = MarkerCluster(name="Pelanggan").add_to(m) if cluster_enabled else m

if enable_heatmap and "ANOMALY_SCORE" in view.columns and view["ANOMALY_SCORE"].notna().any():
    heat_data = view[["LAT", "LON", "ANOMALY_SCORE"]].dropna().values.tolist()
    HeatMap(heat_data, name="Heatmap Anomali", radius=16, blur=24, max_zoom=14).add_to(m)

for _, r in view.iterrows():
    lat, lon = r["LAT"], r["LON"]
    if pd.isna(lat) or pd.isna(lon): 
        continue
    color = color_for_row(r, status_col, high_threshold, mid_threshold)
    popup_html = f"""
        <b>IDPEL</b>: {r.get('LOCATION_CODE', '-') }<br>
        <b>Nama</b>: {r.get('NAMA_PELANGGAN', '-') }<br>
        <b>Tarif</b>: {r.get('TARIFF', '-') } | <b>Daya</b>: {r.get('POWER', '-') }<br>
        <b>Status Periksa</b>: {r.get(status_col, '-') if status_col else '-'}<br>
        <b>Status TO</b>: {r.get('STATUS_TO', '-') } | <b>Skor</b>: {r.get('ANOMALY_SCORE', '-') }<br>
        <b>Last Read</b>: {r.get('LAST_READ_TIME', '-') }<br>
        <b>Alamat</b>: {r.get('ALAMAT', '-') }
    """
    folium.CircleMarker(
        location=[lat, lon],
        radius=6, color=color, fill=True, fill_color=color, fill_opacity=0.9,
        popup=folium.Popup(popup_html, max_width=350),
        tooltip=f"{r.get('LOCATION_CODE','-')} – {r.get('NAMA_PELANGGAN','-')}"
    ).add_to(container)

folium.LayerControl(collapsed=False).add_to(m)

# Legend
if status_col and status_col in view.columns:
    legend_html = """
    <div style='position: fixed; bottom: 30px; left: 30px; z-index: 9999; background: white; padding: 10px 12px; border: 1px solid #999; border-radius: 8px; font-size: 12px;'>
      <b>Status Periksa</b><br>
      <span style='display:inline-block;width:10px;height:10px;background:green;border-radius:50%;margin-right:6px;'></span>Periksa - Sesuai<br>
      <span style='display:inline-block;width:10px;height:10px;background:red;border-radius:50%;margin-right:6px;'></span>Temuan - K2<br>
      <span style='display:inline-block;width:10px;height:10px;background:orange;border-radius:50%;margin-right:6px;'></span>Temuan - P1<br>
      <span style='display:inline-block;width:10px;height:10px;background:darkorange;border-radius:50%;margin-right:6px;'></span>Temuan - P2<br>
      <span style='display:inline-block;width:10px;height:10px;background:blue;border-radius:50%;margin-right:6px;'></span>Temuan - P3<br>
      <span style='display:inline-block;width:10px;height:10px;background:purple;border-radius:50%;margin-right:6px;'></span>Temuan - P4
    </div>
    """
    from branca.element import Element
    m.get_root().html.add_child(Element(legend_html))

map_state = st_folium(m, width=None, height=650)

# ---------- Table & Export ----------
with st.expander("🔎 Lihat Tabel Data Terfilter", expanded=False):
    st.dataframe(view.reset_index(drop=True))

buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
    view.to_excel(writer, index=False, sheet_name="Data")
st.download_button(
    label="💾 Unduh Excel (Data Terfilter)",
    data=buffer.getvalue(),
    file_name=f"mapping_pelanggan_filtered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.caption("© 2025 – Mapping Pelanggan (AMR/P2TL). Siap untuk GitHub & Streamlit Cloud.")
