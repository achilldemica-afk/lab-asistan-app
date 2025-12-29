import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import pandas as pd
from datetime import datetime
from PIL import Image

# --- AYARLAR ---
try:
    GOOGLE_API_KEY = st.secrets["GEMINI_API_KEY"]
    sheets_secrets = st.secrets["gcp_service_account"]
except:
    st.error("Anahtarlar bulunamadı! Lütfen Streamlit Secrets ayarlarını kontrol edin.")
    st.stop()

# --- GEMINI MODELİNİ BAŞLAT ---
genai.configure(api_key=GOOGLE_API_KEY)

# BURAYI DEĞİŞTİRDİK: Flash yerine garanti çalışan 'gemini-pro-vision' kullanıyoruz.
model = genai.GenerativeModel('gemini-pro-vision')

# --- GOOGLE SHEETS BAĞLANTISI ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(sheets_secrets, scope)
client = gspread.authorize(creds)

# Tablo adını buraya yaz
SHEET_NAME = "LabSonuclari" 

st.title("🩺 Asistan Lab Veri Girişi")
st.warning("Not: Sadece resim dosyası yükleyin (PNG, JPG).")

uploaded_file = st.file_uploader("Lab Sonucunu Yükle", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # Resmi PIL formatında açıyoruz (Daha güvenli yöntem)
    image = Image.open(uploaded_file)
    st.image(image, caption='Yüklenen Resim', width=300)
    
    if st.button("Verileri Analiz Et ve Tabloya Yaz"):
        with st.spinner('Yapay zeka verileri okuyor...'):
            try:
                # 1. Prompt Hazırla
                prompt = """
                Sen bir tıbbi asistan yapay zekasın. Bu resimdeki laboratuvar sonuçlarını oku.
                Aşağıdaki değerleri bul ve sadece saf JSON formatında çıktı ver.
                Markdown (```json) kullanma, sadece süslü parantez ile başla ve bitir.
                Değer bulamazsan "null" yaz.

                İstenenler:
                - WBC
                - Neu
                - Hgb
                - Plt
                - CRP
                """
                
                # 2. Modeli Çalıştır (Eski yöntem - Pro Vision uyumlu)
                response = model.generate_content([prompt, image])
                
                # 3. Yanıtı Temizle
                text_response = response.text
                # Bazen AI ```json ile başlar, temizleyelim
                if "```" in text_response:
                    text_response = text_response.replace("```json", "").replace("```", "")
                
                data = json.loads(text_response)
                
                st.subheader("Bulunan Değerler:")
                st.json(data) 

                # 4. Sheets'e Kaydet
                sheet = client.open(SHEET_NAME).sheet1
                yeni_satir = [
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    data.get("WBC", "-"),
                    data.get("Neu", "-"),
                    data.get("Hgb", "-"),
                    data.get("Plt", "-"),
                    data.get("CRP", "-")
                ]
                
                sheet.append_row(yeni_satir)
                st.success(f"✅ Başarılı! Veriler kaydedildi.")
                
            except Exception as e:
                st.error(f"Hata oluştu: {e}")
