import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import altair as alt
import numpy as np

# --- AYARLAR ---
st.set_page_config(page_title="Non-Lineer Dinamikler", page_icon="🧬", layout="wide")

# --- GÜVENLİK ---
try:
    if "gcp_service_account" in st.secrets:
        sheets_secrets = st.secrets["gcp_service_account"]
    else:
        st.error("Google Sheets yetkisi eksik!")
        st.stop()
except Exception as e:
    st.error(f"Hata: {e}")
    st.stop()

# --- VERİ ÇEKME ---
@st.cache_data(ttl=60)
def load_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(sheets_secrets, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Hasta Takip").sheet1 
        
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Sayısal Temizlik
        numeric_cols = ["HGB", "PLT", "RDW", "NEUT_HASH", "LYMPH_HASH", "IG_HASH", "CRP", "Prokalsitonin"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # --- TÜRETİLMİŞ İNDEKSLER ---
        if "NEUT_HASH" in df.columns and "LYMPH_HASH" in df.columns:
            df["NLR"] = df["NEUT_HASH"] / df["LYMPH_HASH"]
            
        if "PLT" in df.columns and "LYMPH_HASH" in df.columns:
            df["PLR"] = df["PLT"] / df["LYMPH_HASH"]

        if "PLT" in df.columns and "NEUT_HASH" in df.columns and "LYMPH_HASH" in df.columns:
             df["SII"] = (df["PLT"] * df["NEUT_HASH"]) / df["LYMPH_HASH"]

        return df
    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")
        return pd.DataFrame()

# --- ARAYÜZ ---
st.title("🧬 Biyolojik Eğriler ve Eşikler")
st.markdown("""
Burada **doğrusal olmayan (non-lineer)** ilişkileri arıyoruz. 
Biyolojik sistemlerdeki **doygunluk noktalarını**, **U-dönüşlerini** ve **kırılma anlarını** tespit etmek için tasarlandı.
""")

if st.button("🔄 Verileri Tazele"):
    st.cache_data.clear()
    st.rerun()

df = load_data()

if not df.empty:
    numeric_columns = df.select_dtypes(include=['float64', 'int64']).columns.tolist()

    # --- KONTROL PANELİ ---
    st.sidebar.header("Eksen Ayarları")
    x_axis = st.sidebar.selectbox("X Ekseni (Bağımsız)", numeric_columns, index=numeric_columns.index("CRP") if "CRP" in numeric_columns else 0)
    y_axis = st.sidebar.selectbox("Y Ekseni (Bağımlı)", numeric_columns, index=numeric_columns.index("HGB") if "HGB" in numeric_columns else 0)
    color_code = st.sidebar.selectbox("Renklendirme", numeric_columns, index=numeric_columns.index("NLR") if "NLR" in numeric_columns else 0)
    
    st.sidebar.markdown("---")
    st.sidebar.header("Model Seçimi")
    trend_type = st.sidebar.radio(
        "Eğri Tipi Seç:",
        ("LOESS (Organik)", "Polinom (U-Şekli / Parabol)", "Lineer (Referans İçin)")
    )

    # --- GRAFİK ALANI ---
    col_main, col_info = st.columns([3, 1])

    with col_main:
        st.subheader(f"{x_axis} vs {y_axis}")
        
        # 1. Ana Noktalar (Scatter)
        base = alt.Chart(df).mark_circle(size=80, opacity=0.6).encode(
            x=alt.X(x_axis, title=f"{x_axis}"),
            y=alt.Y(y_axis, title=f"{y_axis}"),
            color=alt.Color(color_code, scale=alt.Scale(scheme='turbo'), title=color_code),
            tooltip=['ID', x_axis, y_axis, color_code]
        )

        # 2. Eğri Çizimi (Seçime Göre)
        if trend_type == "LOESS (Organik)":
            # LOESS: Veriye en iyi uyan yumuşak eğri (Bandwidth ayarlı)
            trend = base.transform_loess(
                x_axis, y_axis, bandwidth=0.5
            ).mark_line(color='red', size=4)
            st.caption("ℹ️ LOESS: Verinin doğal akışını takip eder. Eşik değerleri ve kırılmaları görmek için idealdir.")

        elif trend_type == "Polinom (U-Şekli / Parabol)":
            # 2. Derece Polinom: U veya Ters-U şekli arar
            trend = base.transform_regression(
                x_axis, y_axis, method="poly", order=2
            ).mark_line(color='red', size=4)
            st.caption("ℹ️ Polinom (2. Derece): Sistemin bir 'U dönüşü' yapıp yapmadığını test eder.")

        else: # Lineer
            trend = base.transform_regression(
                x_axis, y_axis, method="linear"
            ).mark_line(color='gray', strokeDash=[5,5], size=3)
            st.caption("ℹ️ Lineer: Sadece referans amaçlıdır.")

        # Grafiği Çiz
        chart = (base + trend).properties(height=500).interactive()
        st.altair_chart(chart, use_container_width=True)

    # --- İSTATİSTİK BİLGİSİ ---
    with col_info:
        st.markdown("### 🔍 İlişki Gücü")
        
        # Spearman Korelasyonu (Non-lineer, sıra tabanlı ilişki)
        # Pearson yerine Spearman kullanıyoruz çünkü verinin normal dağılmadığını varsayıyoruz.
        corr_spearman = df[x_axis].corr(df[y_axis], method='spearman')
        
        st.metric("Spearman Korelasyonu (Rho)", f"{corr_spearman:.2f}")
        
        if abs(corr_spearman) > 0.7:
            st.success("Güçlü İlişki!")
        elif abs(corr_spearman) > 0.4:
            st.warning("Orta Düzey İlişki")
        else:
            st.info("Zayıf veya Karmaşık İlişki")

        st.markdown("---")
        st.write("**Not:** Eğer Spearman düşük çıkmasına rağmen grafikte net bir 'U' şekli görüyorsan, istatistiğe değil gözüne inan. Çünkü korelasyon formülleri U-dönüşlerini 'sıfır ilişki' sanabilir.")

else:
    st.info("Veri bekleniyor...")
