import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import pandas as pd
from datetime import datetime

# --- AYARLAR ---
# Bu kısımları Streamlit Secrets'tan çekeceğiz, buraya dokunma.
try:
    GOOGLE_API_KEY = st.secrets["GEMINI_API_KEY"]
    # Google Sheets credentials işlemleri (Secrets içindeki JSON verisini kullanacağız)
    sheets_secrets = st.secrets["gcp_service_account"]
except:
    st.error("Anahtarlar bulunamadı! Lütfen Streamlit Secrets ayarlarını yapın.")
    st.stop()

# --- GEMINI AI MODELİNİ BAŞLAT ---
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-latest')

# --- GOOGLE SHEETS BAĞLANTISI ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(sheets_secrets, scope)
client = gspread.authorize(creds)

# Tablo adını buraya yaz (Sheet'in sol üstündeki isimle AYNI olmalı)
SHEET_NAME = "LabSonuclari" 

st.title("🩺 Asistan Lab Veri Girişi")
st.write("Laboratuvar sonucunun ekran görüntüsünü yükleyin.")

uploaded_file = st.file_uploader("Resim Yükle", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    st.image(uploaded_file, caption='Yüklenen Resim', width=300)
    
    if st.button("Verileri Analiz Et ve Tabloya Yaz"):
        with st.spinner('Yapay zeka verileri okuyor...'):
            try:
                # 1. AI'ya Talimat Ver (Prompt)
                prompt = """
                Bu tıbbi laboratuvar sonucunu incele. Aşağıdaki değerleri bul ve bana SADECE geçerli bir JSON formatında ver.
                Başka hiçbir kelime yazma. Eğer değer yoksa "null" yaz.
                Sayısal değerleri sayı (float/int) olarak ver.

                İstediğim Alanlar:
                - WBC (Lökosit)
                - Neu (Nötrofil, bazen Neu% veya #Neu olabilir, mutlak değeri tercih et)
                - Hgb (Hemoglobin)
                - Plt (Trombosit)
                - CRP (C-Reaktif Protein)
                """
                
                # 2. Resmi Gönder
                # Streamlit uploaded file'ı byte'a çevirip gönderiyoruz
                image_bytes = uploaded_file.getvalue()
                image_parts = [{"mime_type": uploaded_file.type, "data": image_bytes}]
                
                response = model.generate_content([prompt, image_parts[0]])
                
                # 3. Gelen Yanıtı Temizle ve JSON'a Çevir
                cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(cleaned_text)
                
                st.subheader("Bulunan Değerler:")
                st.json(data) # Kullanıcıya göster

                # 4. Google Sheets'e Kaydet
                sheet = client.open(SHEET_NAME).sheet1
                
                # Satır sırası: Tarih, WBC, Neu, Hgb, Plt, CRP
                yeni_satir = [
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    data.get("WBC", "-"),
                    data.get("Neu", "-"),
                    data.get("Hgb", "-"),
                    data.get("Plt", "-"),
                    data.get("CRP", "-")
                ]
                
                sheet.append_row(yeni_satir)
                st.success(f"✅ Başarılı! Veriler '{SHEET_NAME}' tablosuna eklendi.")
                
            except Exception as e:
                st.error(f"Bir hata oluştu: {e}")
                st.error("Lütfen resmin net olduğundan emin olun veya tekrar deneyin.")
