import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import altair as alt
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from sklearn.preprocessing import MinMaxScaler
from tableone import TableOne
import umap.umap_ as umap

# --- AYARLAR ---
st.set_page_config(page_title="İmmün Topoloji", page_icon="🧬", layout="wide")

# --- GÜVENLİK VE BAĞLANTI ---
try:
    if "gcp_service_account" in st.secrets:
        sheets_secrets = st.secrets["gcp_service_account"]
    else:
        st.error("Google Sheets yetkisi eksik!")
        st.stop()
except Exception as e:
    st.error(f"Ayar hatası: {e}")
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
        
        numeric_cols = ["HGB", "PLT", "RDW", "NEUT_HASH", "LYMPH_HASH", "IG_HASH", "CRP", "Prokalsitonin"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # İndeksler
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
st.title("🧬 İmmün Sistemin Geometrisi")

df = load_data()

if not df.empty:
    # Sadece sayısal sütunlar (ID hariç)
    numeric_columns = df.select_dtypes(include=['float64', 'int64']).columns.tolist()
    
    # NaN temizliği (UMAP ve Radar için boşluk olmamalı)
    df_clean = df.dropna(subset=numeric_columns)

    tab1, tab2, tab3 = st.tabs(["🗺️ UMAP & Fenotip Haritası", "🕸️ Radar (Şekil) Analizi", "📋 Tablolar"])

    # ==========================================
    # SEKME 1: UMAP İLE DOĞRULAMA
    # ==========================================
    with tab1:
        st.markdown("### Hipotez Kontrolü: NLR gerçekten belirleyici mi?")
        st.info("UMAP algoritması, hastaları kan değerlerine göre gruplar. Eğer 'NLR'ye göre renklendirdiğimizde düzenli bir geçiş (gradient) görüyorsak, sıralama mantıklıdır.")

        if len(df_clean) > 5: # UMAP için en az 5-10 veri lazım
            # 1. Veriyi Normalize Et (0-1 arasına sıkıştır)
            scaler = MinMaxScaler()
            scaled_data = scaler.fit_transform(df_clean[numeric_columns])
            
            # 2. UMAP Çalıştır
            reducer = umap.UMAP(n_neighbors=5, min_dist=0.3, random_state=42)
            embedding = reducer.fit_transform(scaled_data)
            
            df_clean['UMAP_X'] = embedding[:, 0]
            df_clean['UMAP_Y'] = embedding[:, 1]
            
            # 3. Görselleştir
            color_by = st.selectbox("Renklendirme Kriteri", ["NLR", "CRP", "PLT", "HGB"], index=0)
            
            fig_umap = px.scatter(
                df_clean, x='UMAP_X', y='UMAP_Y',
                color=color_by,
                hover_data=['ID', 'NLR', 'CRP'],
                color_continuous_scale='Turbo',
                title=f"Hasta Evreni ({color_by} Dağılımı)"
            )
            st.plotly_chart(fig_umap, use_container_width=True)
            
            st.markdown("""
            **Nasıl Okunmalı?**
            * Noktalar birbirine yakınsa, o hastaların kan tabloları birbirine benziyor demektir.
            * Eğer renkler (NLR değerleri) harita üzerinde dağınık değil de bir uçtan bir uca düzenli değişiyorsa, **NLR dominant bir faktördür.**
            """)
        else:
            st.warning("UMAP analizi için en az 5-10 hasta verisi gerekiyor.")

    # ==========================================
    # SEKME 2: RADAR (ŞEKİL) ANALİZİ
    # ==========================================
    with tab2:
        st.markdown("### 🕸️ Şekil Değişimi (Shape Deformation)")
        st.markdown("Hastaları NLR oranına göre sıraya dizdik. Slider'ı kaydırarak immünitenin şekil değiştirmesini izle.")

        # 1. Parametre Seçimi (Radar'ın köşeleri)
        radar_cols = st.multiselect(
            "Radarda Olacak Parametreler (En az 3 tane seç)",
            numeric_columns,
            default=["HGB", "PLT", "NEUT_HASH", "LYMPH_HASH", "CRP", "RDW"]
        )

        if len(radar_cols) >= 3:
            # 2. Veriyi Hazırla ve Sırala
            # Radar grafiği için verilerin 0-1 arasında olması ŞARTTIR.
            # Yoksa 300.000 PLT yanında 5 CRP görünmez.
            scaler_radar = MinMaxScaler()
            df_radar_scaled = pd.DataFrame(scaler_radar.fit_transform(df_clean[numeric_cols]), columns=numeric_cols)
            
            # ID ve Orijinal NLR'yi geri ekle
            df_radar_scaled['ID'] = df_clean['ID'].values
            df_radar_scaled['Gercek_NLR'] = df_clean['NLR'].values
            
            # NLR'ye göre sırala (Küçükten Büyüğe)
            df_sorted = df_radar_scaled.sort_values(by="Gercek_NLR").reset_index(drop=True)
            
            # 3. Slider ile Hasta Seçimi
            total_patients = len(df_sorted)
            selected_index = st.slider("Hastaları Tara (NLR Artışına Göre)", 0, total_patients-1, 0)
            
            # Seçilen Hasta Verisi
            patient = df_sorted.iloc[selected_index]
            
            # 4. Radar Grafiğini Çiz
            values = patient[radar_cols].values.tolist()
            values += values[:1] # Şekli kapatmak için başa dön
            
            categories = radar_cols
            categories += categories[:1]
            
            fig_radar = go.Figure()

            fig_radar.add_trace(go.Scatterpolar(
                r=values,
                theta=categories,
                fill='toself',
                name=f"Hasta {patient['ID']}",
                line_color='#00ff00' if patient['Gercek_NLR'] < 3 else '#ff0000'
            ))

            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 1] # Veriyi normalize ettiğimiz için
                    )),
                showlegend=False,
                title=f"Hasta: {patient['ID']} | NLR: {patient['Gercek_NLR']:.2f}",
                height=500
            )
            
            col_r1, col_r2 = st.columns([2, 1])
            with col_r1:
                st.plotly_chart(fig_radar, use_container_width=True)
            
            with col_r2:
                st.info(f"**Sıralama:** {selected_index+1} / {total_patients}")
                st.metric("Bu Hastanın NLR Değeri", f"{patient['Gercek_NLR']:.2f}")
                
                st.write("---")
                st.markdown("**Şekil Yorumu:**")
                st.markdown("* **Dar Alan:** İmmün sistem baskılanmış veya sakin.")
                st.markdown("* **Geniş Alan:** Sistem genel alarma geçmiş.")
                st.markdown("* **Sivri Köşeler:** O parametrede (Örn: CRP) dengesiz bir patlama var.")

        else:
            st.warning("Lütfen radarda göstermek için en az 3 parametre seç.")

    # ==========================================
    # SEKME 3: KLASİK TABLOLAR
    # ==========================================
    with tab3:
        st.dataframe(df_clean)

else:
    st.info("Veri bekleniyor...")
