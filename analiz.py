import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import altair as alt
import numpy as np
from tableone import TableOne  # Jamovi tarzı tablo için

# --- 1. AYARLAR ---
st.set_page_config(page_title="Tıbbi Analiz & Rapor", page_icon="📋", layout="wide")

# --- 2. GÜVENLİK VE BAĞLANTI ---
try:
    if "gcp_service_account" in st.secrets:
        sheets_secrets = st.secrets["gcp_service_account"]
    else:
        st.error("Google Sheets yetkisi eksik! Secrets ayarlarını kontrol edin.")
        st.stop()
except Exception as e:
    st.error(f"Ayar hatası: {e}")
    st.stop()

# --- 3. VERİ ÇEKME FONKSİYONU (Eksik Olan Kısım Buydu) ---
@st.cache_data(ttl=60)
def load_data():
    try:
        # Google Sheets Bağlantısı
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(sheets_secrets, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Hasta Takip").sheet1  # Dosya adın
        
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Sayısal Temizlik
        numeric_cols = ["HGB", "PLT", "RDW", "NEUT_HASH", "LYMPH_HASH", "IG_HASH", "CRP", "Prokalsitonin"]
        for col in numeric_cols:
            if col in df.columns:
                # 1. Stringe çevir, virgülleri nokta yap
                df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
                # 2. Sayıya çevir (Hatalı veri varsa NaN yap)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # --- İndeks Hesaplamaları ---
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

# --- 4. ARAYÜZ ---
st.title("📋 Tıbbi Analiz ve Raporlama")

# Verileri Yükle
df = load_data()

if not df.empty:
    # Sayısal sütun listesi
    numeric_columns = df.select_dtypes(include=['float64', 'int64']).columns.tolist()

    # Sekmeler
    tab1, tab2, tab3 = st.tabs(["🧩 Dinamik Grafikler", "📄 Jamovi Tarzı Tablo (Table 1)", "📥 Veri İndir"])

    # --- SEKME 1: GRAFİKLER (LOESS / Polinom) ---
    with tab1:
        st.markdown("### Non-Lineer Biyolojik İlişkiler")
        
        col_main, col_settings = st.columns([3, 1])
        
        with col_settings:
            st.markdown("**Eksen Ayarları**")
            x_axis = st.selectbox("X Ekseni", numeric_columns, index=numeric_columns.index("CRP") if "CRP" in numeric_columns else 0)
            y_axis = st.selectbox("Y Ekseni", numeric_columns, index=numeric_columns.index("HGB") if "HGB" in numeric_columns else 0)
            color_code = st.selectbox("Renk", numeric_columns, index=numeric_columns.index("NLR") if "NLR" in numeric_columns else 0)
            
            trend_type = st.radio("Model Tipi", ("LOESS (Organik)", "Polinom (U-Şekli)", "Lineer"))

        with col_main:
            # Grafik Çizimi
            base = alt.Chart(df).mark_circle(size=80, opacity=0.6).encode(
                x=alt.X(x_axis, title=f"{x_axis}"),
                y=alt.Y(y_axis, title=f"{y_axis}"),
                color=alt.Color(color_code, scale=alt.Scale(scheme='turbo'), title=color_code),
                tooltip=['ID', x_axis, y_axis, color_code]
            )

            if trend_type == "LOESS (Organik)":
                trend = base.transform_loess(x_axis, y_axis, bandwidth=0.5).mark_line(color='red', size=4)
            elif trend_type == "Polinom (U-Şekli)":
                trend = base.transform_regression(x_axis, y_axis, method="poly", order=2).mark_line(color='red', size=4)
            else:
                trend = base.transform_regression(x_axis, y_axis, method="linear").mark_line(color='gray', strokeDash=[5,5])

            st.altair_chart((base + trend).properties(height=500).interactive(), use_container_width=True)
            
            # Spearman Korelasyonu
            if x_axis in df.columns and y_axis in df.columns:
                corr = df[x_axis].corr(df[y_axis], method='spearman')
                st.metric("Spearman Korelasyonu (Rho)", f"{corr:.2f}")

    # --- SEKME 2: JAMOVI TARZI TABLO ---
    with tab2:
        st.header("Otomatik 'Table 1' Oluşturucu")
        
        c1, c2 = st.columns([1, 3])
        with c1:
            st.subheader("Ayarlar")
            cols_to_show = st.multiselect("Tablo Parametreleri", numeric_columns, default=numeric_columns)
            
            # Otomatik Gruplama (Örnek: CRP > 50)
            df['Grup'] = np.where(df['CRP'] > 50, 'Yüksek Enfeksiyon', 'Düşük/Orta Risk')
            gruplama = st.checkbox("Gruplara Ayır (CRP > 50)")

        with c2:
            if cols_to_show:
                try:
                    groupby_list = ['Grup'] if gruplama else None
                    
                    mytable = TableOne(
                        df, 
                        columns=cols_to_show, 
                        groupby=groupby_list, 
                        pval=True if gruplama else False,
                        nonnormal=cols_to_show 
                    )
                    
                    st.markdown(mytable.tabulate(tablefmt="github"))
                    
                except Exception as e:
                    st.error(f"Tablo hatası: {e}")

    # --- SEKME 3: HAM VERİ ---
    with tab3:
        st.dataframe(df)

else:
    st.info("Veri bekleniyor... Lütfen önce veri girişi yapın.")
