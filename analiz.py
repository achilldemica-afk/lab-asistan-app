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

# --- 1. AYARLAR ---
st.set_page_config(page_title="İmmün Topoloji & Analiz", page_icon="🧬", layout="wide")

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

# --- 3. VERİ ÇEKME FONKSİYONU ---
@st.cache_data(ttl=60)
def load_data():
    try:
        # Bağlantı
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(sheets_secrets, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Hasta Takip").sheet1
        
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Sayısal Temizlik
        # Olası sütun isimlerini buraya ekledik
        target_cols = ["HGB", "PLT", "RDW", "NEUT_HASH", "LYMPH_HASH", "IG_HASH", "CRP", "Prokalsitonin", "NEU#", "LYM#", "IG#"]
        
        for col in target_cols:
            if col in df.columns:
                # Stringe çevir -> Virgülleri nokta yap -> Sayıya çevir
                df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # --- İndeks Hesaplamaları (Varsa Hesapla) ---
        # 1. NLR (Neutrophil / Lymphocyte)
        # Sütun adı NEUT_HASH mi yoksa NEU# mi kontrol et
        neu_col = "NEUT_HASH" if "NEUT_HASH" in df.columns else ("NEU#" if "NEU#" in df.columns else None)
        lym_col = "LYMPH_HASH" if "LYMPH_HASH" in df.columns else ("LYM#" if "LYM#" in df.columns else None)
        
        if neu_col and lym_col:
            df["NLR"] = df[neu_col] / df[lym_col]

        # 2. PLR (Platelet / Lymphocyte)
        if "PLT" in df.columns and lym_col:
            df["PLR"] = df["PLT"] / df[lym_col]

        # 3. SII (Systemic Immune-Inflammation Index)
        if "PLT" in df.columns and neu_col and lym_col:
             df["SII"] = (df["PLT"] * df[neu_col]) / df[lym_col]

        return df
    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")
        return pd.DataFrame()

# --- 4. ARAYÜZ ---
st.title("🧬 İmmün Sistemin Geometrisi ve Analizi")

df = load_data()

if not df.empty:
    # Sadece sayısal olan sütunları al (İsim, ID hariç)
    numeric_columns = df.select_dtypes(include=['float64', 'int64']).columns.tolist()
    
    # Veri Temizliği (Boşlukları at, yoksa UMAP ve Radar çalışmaz)
    df_clean = df.dropna(subset=[c for c in numeric_columns if c in df.columns])

    # Sekmeler
    tab1, tab2, tab3 = st.tabs(["🗺️ UMAP (Harita)", "🕸️ Radar (Şekil)", "📋 Tablolar & Jamovi"])

    # ==========================================
    # SEKME 1: UMAP & FENOTİP HARİTASI
    # ==========================================
    with tab1:
        st.markdown("### Hipotez Kontrolü")
        st.info("Benzer hastalar bir arada mı duruyor? NLR renk geçişi düzenli mi?")

        if len(df_clean) > 5:
            try:
                # UMAP için veriyi hazırla
                # Sadece mevcut sayısal sütunları kullan
                features = [c for c in numeric_columns if c in df_clean.columns and c not in ['UMAP_X', 'UMAP_Y']]
                
                if len(features) > 2:
                    scaler = MinMaxScaler()
                    scaled_data = scaler.fit_transform(df_clean[features])
                    
                    reducer = umap.UMAP(n_neighbors=5, min_dist=0.3, random_state=42)
                    embedding = reducer.fit_transform(scaled_data)
                    
                    df_clean['UMAP_X'] = embedding[:, 0]
                    df_clean['UMAP_Y'] = embedding[:, 1]
                    
                    # Renklendirme seçeneği
                    valid_colors = [c for c in ["NLR", "CRP", "PLT", "SII"] if c in df_clean.columns]
                    color_by = st.selectbox("Renklendirme Kriteri", valid_colors, index=0 if valid_colors else None)
                    
                    if color_by:
                        fig_umap = px.scatter(
                            df_clean, x='UMAP_X', y='UMAP_Y',
                            color=color_by,
                            hover_data=['ID'],
                            color_continuous_scale='Turbo',
                            title=f"Hasta Evreni ({color_by} Dağılımı)"
                        )
                        st.plotly_chart(fig_umap, use_container_width=True)
                    else:
                        st.warning("Renklendirme için uygun sütun bulunamadı (NLR hesaplanamamış olabilir).")
                else:
                    st.warning("Yeterli parametre yok.")
            except Exception as e:
                st.error(f"UMAP Hatası: {e}")
        else:
            st.warning("UMAP analizi için en az 5-10 hasta verisi gerekiyor.")

    # ==========================================
    # SEKME 2: RADAR (ŞEKİL) ANALİZİ
    # ==========================================
    with tab2:
        st.markdown("### 🕸️ Şekil Değişimi (Shape Deformation)")
        
        # --- HATA ÖNLEYİCİ AKILLI SEÇİM ---
        # 1. Kodun çökmesini önlemek için varsayılan listeyi kontrol et
        desired_defaults = ["HGB", "PLT", "NEUT_HASH", "LYMPH_HASH", "CRP", "RDW", "NEU#", "LYM#"]
        valid_defaults = [col for col in desired_defaults if col in numeric_columns]
        
        # Eğer varsayılanlar boşsa, rastgele ilk 3 taneyi seç (Yeter ki çökmesin)
        if not valid_defaults and len(numeric_columns) >= 3:
            valid_defaults = numeric_columns[:3]

        if len(numeric_columns) >= 3:
            radar_cols = st.multiselect(
                "Radarda Olacak Parametreler",
                numeric_columns,
                default=valid_defaults 
            )

            if len(radar_cols) >= 3:
                # Veriyi Radar için 0-1 arasına sıkıştır
                scaler_radar = MinMaxScaler()
                df_radar_scaled = pd.DataFrame(scaler_radar.fit_transform(df_clean[radar_cols]), columns=radar_cols)
                
                # ID ve Sıralama Kriterini (NLR) ekle
                df_radar_scaled['ID'] = df_clean['ID'].values
                
                sort_col = "NLR" if "NLR" in df_clean.columns else numeric_columns[0]
                df_radar_scaled['Sort_Val'] = df_clean[sort_col].values
                
                # Sırala
                df_sorted = df_radar_scaled.sort_values(by='Sort_Val').reset_index(drop=True)
                
                # Slider
                total_patients = len(df_sorted)
                if total_patients > 0:
                    selected_index = st.slider(f"Hastaları Tara ({sort_col} Artışına Göre)", 0, total_patients-1, 0)
                    
                    patient = df_sorted.iloc[selected_index]
                    
                    # Radar Çizimi
                    values = patient[radar_cols].values.tolist()
                    values += values[:1] # Kapatmak için
                    categories = radar_cols + [radar_cols[0]]
                    
                    fig_radar = go.Figure()
                    fig_radar.add_trace(go.Scatterpolar(
                        r=values, theta=categories, fill='toself',
                        name=f"Hasta {patient['ID']}",
                        line_color='#FF5733'
                    ))
                    fig_radar.update_layout(
                        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
                        showlegend=False,
                        title=f"Hasta: {patient['ID']} | {sort_col}: {patient['Sort_Val']:.2f}",
                        height=500
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)
                else:
                    st.warning("Gösterilecek hasta yok.")
            else:
                st.warning("Lütfen en az 3 parametre seçin.")
        else:
            st.error("Yeterli sayısal veri sütunu bulunamadı.")

    # ==========================================
    # SEKME 3: JAMOVI TABLOSU
    # ==========================================
    with tab3:
        st.header("Tablo 1: Klinik Özellikler")
        
        c1, c2 = st.columns([1, 3])
        with c1:
            # Akıllı Seçim Burası İçin de Geçerli
            default_table_cols = [c for c in ["HGB", "PLT", "CRP", "NLR", "SII"] if c in numeric_columns]
            cols_to_show = st.multiselect("Tablo Parametreleri", numeric_columns, default=default_table_cols)
            
            # Otomatik Gruplama
            if "CRP" in df_clean.columns:
                df_clean['Grup'] = np.where(df_clean['CRP'] > 50, 'Yüksek Enfeksiyon', 'Düşük/Orta')
                use_group = st.checkbox("Gruplandır (CRP > 50)")
            else:
                use_group = False

        with c2:
            if cols_to_show:
                try:
                    groupby_list = ['Grup'] if use_group else None
                    
                    mytable = TableOne(
                        df_clean, 
                        columns=cols_to_show, 
                        groupby=groupby_list, 
                        pval=True if use_group else False,
                        nonnormal=cols_to_show 
                    )
                    st.markdown(mytable.tabulate(tablefmt="github"))
                except Exception as e:
                    st.error(f"Tablo oluşturulamadı: {e}")
            
        st.markdown("---")
        st.subheader("Ham Veri")
        st.dataframe(df)

else:
    st.info("Veri bekleniyor... Lütfen 'lab-asistan-app' üzerinden veri girişi yapın.")
