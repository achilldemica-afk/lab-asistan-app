import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import pandas as pd
from datetime import datetime
from PIL import Image
import requests
import base64
import io

# --- AYARLAR ---
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
    else:
        st.error("API Key eksik! Secrets ayarlarını kontrol edin.")
        st.stop()
        
    if "gcp_service_account" in st.secrets:
        sheets_secrets = st.secrets["gcp_service_account"]
    else:
        st.error("Google Sheets yetkisi eksik! Secrets ayarlarını kontrol edin.")
        st.stop()
except Exception as e:
    st.error(f"Ayar hatası: {e}")
    st.stop()

# --- GOOGLE SHEETS BAĞLANTISI ---
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(sheets_secrets, scope)
    client = gspread.authorize(creds)
    SHEET_NAME = "LabSonuclari" # Tablo adınızın aynısı olmalı
except Exception as e:
    st.error(f"Google Sheets Bağlantı Hatası: {e}")
    st.stop()

# --- YARDIMCI FONKSİYON: RESMİ BASE64 YAPMA ---
def image_to_base64(image):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# --- ANA EKRAN ---
st.title("🩺 Asistan Veri Giriş Paneli")
st.info("Sistem Durumu: Manuel Bağlantı Modu (v3)")

uploaded_file = st.file_uploader("Lab Sonucu Yükle", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption='Yüklenen Resim', width=300)
    
    if st.button("Analiz Et ve Kaydet"):
        with st.spinner('Google Gemini sunucusuna bağlanılıyor...'):
            try:
                # 1. Resmi Hazırla
                base64_image = image_to_base64(image)
                
                # 2. DOĞRUDAN API İSTEĞİ (Kütüphanesiz)
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
                
                headers = {'Content-Type': 'application/json'}
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": "Bu resimdeki laboratuvar sonuçlarını oku. Şu değerleri JSON olarak ver: WBC, Neu, Hgb, Plt, CRP. Değer yoksa null yaz. Sadece saf JSON döndür, markdown kullanma."},
                            {"inline_data": {
                                "mime_type": "image/png",
                                "data": base64_image
                            }}
                        ]
                    }]
                }
                
                # İsteği Gönder
                response = requests.post(url, headers=headers, json=payload)
                
                if response.status_code != 200:
                    st.error(f"Sunucu Hatası ({response.status_code}): {response.text}")
                else:
                    # 3. Yanıtı İşle
                    result = response.json()
                    try:
                        text_content = result['candidates'][0]['content']['parts'][0]['text']
                        # JSON temizliği
                        text_content = text_content.replace("```json", "").replace("```", "").strip()
                        data = json.loads(text_content)
                        
                        st.success("Veriler Çekildi:")
                        st.json(data)
                        
                        # 4. Sheets'e Yaz
                        sheet = client.open(SHEET_NAME).sheet1
                        row = [
                            str(datetime.now())[:19],
                            data.get("WBC"), data.get("Neu"), 
                            data.get("Hgb"), data.get("Plt"), data.get("CRP")
                        ]
                        sheet.append_row(row)
                        st.balloons()
                        st.success("✅ Tabloya başarıyla eklendi!")
                        
                    except Exception as parse_error:
                        st.error(f"Veri çözümleme hatası: {parse_error}")
                        st.write("Ham yanıt:", result)

            except Exception as e:
                st.error(f"Beklenmeyen hata: {e}")
