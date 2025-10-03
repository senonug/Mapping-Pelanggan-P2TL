# Mapping Pelanggan – AMR / P2TL

Streamlit app untuk memetakan pelanggan (AMR/P2TL) dengan pewarnaan pin berdasarkan **Status Periksa**:
- Periksa - Sesuai (green)
- Temuan - K2 (red)
- Temuan - P1 (orange)
- Temuan - P2 (darkorange)
- Temuan - P3 (blue)
- Temuan - P4 (purple)

## 🚀 Jalankan Lokal
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## ☁️ Deploy ke Streamlit Cloud
1. Fork / push repo ini ke GitHub.
2. Di Streamlit Cloud, pilih repo dan file utama `streamlit_app.py`.
3. Python version akan mengikuti `runtime.txt`.

## 📄 Format Data
Minimal kolom:
- `LOCATION_CODE` (IDPEL), `LAT`, `LON`

Opsional (disarankan):
- `TARIFF`, `POWER`, `LOCATION_TYPE`, `STATUS_TO`, `ANOMALY_SCORE`, `LAST_READ_TIME`, `NAMA_PELANGGAN`, `ALAMAT`, dan salah satu kolom status periksa:
  - `UPDATE_STATUS`, `UPDATE-STATUS`, `STATUS_PERIKSA`, `STATUS PERIKSA`, `STATUS_P2TL`, `HASIL_PERIKSA`

## 🧪 Sample
Lihat `data/sample_mapping.csv` untuk contoh skema kolom.
