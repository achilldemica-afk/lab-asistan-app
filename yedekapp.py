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

# --- 1. AYARLAR ---
st.set_page_config(page_title="Makale Kulübü Lab Asistanı", page_icon="🩸", layout="wide")

try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
    else:
        st.error("API Key eksik! Secrets ayarlarını kontrol et.")
        st.stop()
        
    if "gcp_service_account" in st.secrets:
        sheets_secrets = st.secrets["gcp_service_account"]
    else:
        st.error("Google Sheets yetkisi eksik! Secrets ayarlarını kontrol et.")
        st.stop()
except Exception as e:
    st.error(f"Ayar hatası: {e}")
    st.stop()

# --- 2. GOOGLE SHEETS BAĞLANTISI ---
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(sheets_secrets, scope)
    client = gspread.authorize(creds)
    SHEET_NAME = "Hasta Takip" 
except Exception as e:
    st.error(f"Google Sheets Bağlantı Hatası: {e}")
    st.stop()

# --- 3. YARDIMCI FONKSİYON ---
def image_to_base64(image):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# --- 4. ARAYÜZ ---
st.title("🩸 Makale Kulübü Lab Asistanı")
st.info("ℹ️ Telefondan giriyorsanız **'Browse files'** butonuna basınca **'Fotoğraf Çek'** veya **'Kamera'** seçeneğini seçin.")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 1. Hemogram")
    hemo_file = st.file_uploader("Hemogram Yükle / Çek", type=["jpg", "png", "jpeg"], key="hemo")

with col2:
    st.markdown("### 2. Biyokimya")
    bio_file = st.file_uploader("Biyokimya Yükle / Çek", type=["jpg", "png", "jpeg"], key="bio")


if st.button("Analizi Başlat", type="primary"):
    
    if not hemo_file and not bio_file:
        st.warning("Lütfen dosya yükleyin veya fotoğraf çekin.")
        st.stop()

    with st.spinner('Hmm...'):
        try:
            content_parts = []
            
            # --- PROMPT: SATIR VE SÜTUN TAKİP MANTIĞI ---
            prompt_text = """
            GÖREV: Sen titiz bir veri giriş operatörüsün. Önündeki kağıtta yazanları satır satır okuyup sisteme gireceksin.
            
            YÖNTEMİN ŞU OLACAK (ADIM ADIM):
            1. Önce sol sütunda "Parametre Adını" (Test İsmi) bul.
            2. Bulduğun satırda parmağını sağa kaydır ve ilk karşına çıkan "SONUÇ" (Result) rakamını al.
            3. Yan taraftaki "Referans Aralığı" (Örn: 11-15) sütununa SAKIN bakma. Orayı görmezden gel.
            
            AŞAĞIDAKİLERİ TEK TEK BUL:
            - "HGB" veya "Hemoglobin" yazısını bul -> Yanındaki Sonucu al.
            - "PLT" veya "Trombosit" yazısını bul -> Yanındaki Sonucu al.
            - "RDW" yazısını bul -> Yanındaki Sonucu al.
            - "NEU#" veya "Nötrofil#" (Mutlak değer) yazısını bul -> Yanındaki Sonucu al.
            - "LYM#" veya "Lenfosit#" (Mutlak değer) yazısını bul -> Yanındaki Sonucu al.
            - "IG#" veya "İmmatür Granülosit" yazısını bul -> Yanındaki Sonucu al.
            - "CRP" yazısını bul -> Yanındaki Sonucu al. (Referansla aynı olsa bile al!)
            - "Prokalsitonin" yazısını bul -> Yanındaki Sonucu al.
            
            KİMLİK:
            - Sol üstteki İsim veya Protokol numarasını 'ID' olarak al.
            
            ÇIKTI FORMATI (SADECE JSON):
            {
                "ID": "...",
                "HGB": 0.0,
                "PLT": 0,
                "RDW": 0.0,
                "NEUT_HASH": 0.0,
                "LYMPH_HASH": 0.0,
                "IG_HASH": 0.0,
                "CRP": 0.0,
                "Prokalsitonin": 0.0
            }
            Rakam yoksa null yaz. Ondalık için nokta kullan.
            """
            
            content_parts.append({"text": prompt_text})

            if hemo_file:
                content_parts.append({"inline_data": {"mime_type": "image/png", "data": image_to_base64(Image.open(hemo_file))}})
            if bio_file:
                content_parts.append({"inline_data": {"mime_type": "image/png", "data": image_to_base64(Image.open(bio_file))}})

            # --- MODEL: Gemini 3.0 Pro Preview (En Akıllısı) ---
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-preview:generateContent?key={API_KEY}"
            
            headers = {'Content-Type': 'application/json'}
            payload = {"contents": [{"parts": content_parts}]}
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                try:
                    text_content = result['candidates'][0]['content']['parts'][0]['text']
                    text_content = text_content.replace("```json", "").replace("```", "").strip()
                    
                    start = text_content.find('{')
                    end = text_content.rfind('}') + 1
                    if start != -1 and end != -1:
                         data = json.loads(text_content[start:end])
                    else:
                         data = json.loads(text_content)

                    st.subheader(f"Hasta: {data.get('ID', 'Bilinmiyor')}")
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("HGB", data.get("HGB"))
                    c2.metric("PLT", data.get("PLT"))
                    c3.metric("CRP", data.get("CRP"))
                    c4.metric("Prokalsitonin", data.get("Prokalsitonin"))

                    with st.expander("Tüm Veriyi Gör"):
                        st.json(data)

                    # Kayıt
                    sheet = client.open(SHEET_NAME).sheet1
                    row = [
                        data.get("ID"),
                        data.get("HGB"),
                        data.get("PLT"),
                        data.get("RDW"),
                        data.get("NEUT_HASH"),
                        data.get("LYMPH_HASH"),
                        data.get("IG_HASH"),
                        data.get("CRP"),
                        data.get("Prokalsitonin")
                    ]
                    sheet.append_row(row)
                    st.success("✅ Başarıyla Kaydedildi!")
                    
                except Exception as parse_error:
                    st.error("Veri okunamadı. Lütfen fotoğrafın net olduğundan emin olun.")
                    st.text(text_content)
            else:
                st.error(f"Sunucu Hatası: {response.status_code}")
                st.write(response.text)

        except Exception as e:
            st.error(f"Hata: {e}")
