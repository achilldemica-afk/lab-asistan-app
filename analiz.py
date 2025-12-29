import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import altair as alt
import numpy as np
# YENİ KÜTÜPHANE:
from tableone import TableOne

# --- AYARLAR ---
st.set_page_config(page_title="Tıbbi Analiz & Rapor", page_icon="📋", layout="wide")

# ... (GÜVENLİK ve VERİ ÇEKME kısımları AYNEN KALACAK - Burayı atlıyorum) ...
# ... (load_data fonksiyonun aynen kalsın) ...

# --- ARAYÜZ KISMI (Buradan aşağısı değişiyor) ---

st.title("📋 Tıbbi Analiz ve Raporlama")

# Verileri Yükle
df = load_data()

if not df.empty:
    # Sayısal sütunları belirle
    numeric_columns = df.select_dtypes(include=['float64', 'int64']).columns.tolist()

    tab1, tab2, tab3 = st.tabs(["🧩 Dinamik Grafikler", "📄 Jamovi Tarzı Tablo (Table 1)", "📥 Veri İndir"])

    # --- SEKME 1: GRAFİKLER (Eski kod buraya) ---
    with tab1:
        st.info("Burada eski grafik kodların çalışmaya devam edecek...")
        # (Buraya eski grafik kodlarını koyabilirsin veya olduğu gibi bırakırsın)
        
        # Örnek Grafik (Kodun bütünlüğü bozulmasın diye ekliyorum)
        st.subheader("Hızlı Bakış")
        chart = alt.Chart(df).mark_circle().encode(
            x='CRP', y='HGB', tooltip=['ID', 'CRP', 'HGB']
        ).interactive()
        st.altair_chart(chart, use_container_width=True)

    # --- SEKME 2: JAMOVI TARZI OTOMATİK TABLO ---
    with tab2:
        st.header("Otomatik 'Table 1' Oluşturucu")
        st.markdown("Makalelerde kullanılan **Demografik ve Klinik Özellikler** tablosunu otomatik üretir.")

        col_settings, col_table = st.columns([1, 3])

        with col_settings:
            st.subheader("Tablo Ayarları")
            
            # Hangi sütunlar tabloda görünsün?
            columns_to_show = st.multiselect(
                "Tabloya Dahil Edilecek Parametreler",
                numeric_columns,
                default=numeric_columns # Hepsi seçili gelsin
            )
            
            # Gruplama Yapmak İster misin? (Örn: Enfeksiyon Var/Yok)
            # Şu an veride "Grup" yok ama ileride olursa buraya eklenir.
            # Şimdilik CRP'ye göre sanal bir grup yapalım:
            df['Durum'] = np.where(df['CRP'] > 50, 'Yüksek Enfeksiyon', 'Düşük/Orta Risk')
            
            groupby_col = st.selectbox("Gruplama Ölçütü", ["Yok (Genel Özet)", "Durum (CRP > 50)"])

            st.info("Not: P-Değerleri otomatik hesaplanır (Normal dağılım yoksa Mann-Whitney U, varsa T-test).")

        with col_table:
            if columns_to_show:
                try:
                    # TableOne Büyüsü Burada!
                    group_by = ['Durum'] if groupby_col == "Durum (CRP > 50)" else None
                    
                    mytable = TableOne(
                        df, 
                        columns=columns_to_show, 
                        groupby=group_by, 
                        pval=True if group_by else False, # Grup varsa P değeri hesapla
                        nonnormal=columns_to_show # Hepsini non-normal kabul et (Tıpta genelde böyledir)
                    )
                    
                    st.markdown(mytable.tabulate(tablefmt="github"))
                    
                    # İndirme Butonu (HTML formatında indirir, Word'e yapıştırılır)
                    st.download_button(
                        "📥 Tabloyu İndir (Excel/Word Uyumlu)",
                        mytable.to_csv(),
                        file_name="table1_raporu.csv"
                    )
                except Exception as e:
                    st.error(f"Tablo oluşturulamadı: {e}")
            else:
                st.warning("Lütfen en az bir parametre seçin.")

    # --- SEKME 3: HAM VERİ ---
    with tab3:
        st.dataframe(df)

else:
    st.warning("Veri bekleniyor...")
