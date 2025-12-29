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
st.set_page_config(page_title="Hasta Takip Asistanı", page_icon="🩸")

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
st.title("🩸 Hasta Takip (Tablo Modu)")
st.info("Yöntem: Sütun Eşleştirme (Parametre -> Sonuç)")

col1, col2 = st.columns(2)
with col1:
    hemo_file = st.file_uploader("1. Hemogram Yükle", type=["jpg", "png", "jpeg"], key="hemo")
with col2:
    bio_file = st.file_uploader("2. Biyokimya Yükle", type=["jpg", "png", "jpeg"], key="bio")

if st.button("Analiz Et", type="primary"):
    
    if not hemo_file and not bio_file:
        st.warning("Dosya seçilmedi.")
        st.stop()

    with st.spinner('Tablo sütunları taranıyor...'):
        try:
            content_parts = []
            
            # --- TABLO ODAKLI YENİ PROMPT ---
            prompt_text = """
            Sen sadece görüntü işleyen bir robotsun. Resmi bir Excel tablosu gibi düşün.
            
            GÖREV: Aşağıdaki adımları sırayla uygula:
            
            ADIM 1: SÜTUNLARI TESPİT ET
            - Resimde parametre isimlerinin yazdığı sütunu bul (Genelde "Test Adı" veya "Parametre" yazar).
            - Resimde ölçüm değerlerinin yazdığı sütunu bul (Genelde "Sonuç" veya "Result" yazar).
            - Resimde "Referans Aralığı" veya "Normal Değerler" sütununu bul ve bu sütunu TAMAMEN UNUT. Buradan asla veri alma.
            
            ADIM 2: SATIRLARI BUL VE EŞLEŞTİR
            Aşağıdaki anahtar kelimeleri "Parametre" sütununda ara, bulduğun satırın hizasındaki "Sonuç" sütunundaki sayıyı al.
            
            ARANACAKLAR:
            1. Parametre Sütununda: "HGB" veya "Hemoglobin" -> Sonuç Sütunundaki değeri al -> JSON'da "HGB"ye yaz.
            2. Parametre Sütununda: "PLT" veya "Trombosit" -> Sonuç Sütunundaki değeri al -> JSON'da "PLT"ye yaz.
            3. Parametre Sütununda: "RDW" -> Sonuç Sütunundaki değeri al -> JSON'da "RDW"ye yaz.
            4. Parametre Sütununda: "NEU#" veya "Nötrofil#" (Mutlak değer) -> JSON'da "NEUT_HASH"a yaz.
            5. Parametre Sütununda: "LYM#" veya "Lenfosit#" (Mutlak değer) -> JSON'da "LYMPH_HASH"a yaz.
            6. Parametre Sütununda: "IG#" veya "İmmatür Granülosit" -> JSON'da "IG_HASH"a yaz (Yoksa null).
            7. Parametre Sütununda: "CRP" veya "C-Reaktif Protein" -> Sonuç Sütunundaki değeri al -> JSON'da "CRP"ye yaz.
            8. Parametre Sütununda: "Prokalsitonin" -> Sonuç Sütunundaki değeri al -> JSON'da "Prokalsitonin"e yaz.
            
            ÖZEL NOT (CRP İÇİN): 
            - CRP satırını bulduğunda, referans aralığına bakma. Sadece Sonuç sütununda ne yazıyorsa (Örn: 5, 3.2, <5) onu olduğu gibi al.
            - Eğer hücre boş değilse "null" yazma.
            
            KİMLİK:
            - Sol üstteki İsim/Protokol bilgisini "ID" olarak al.
            
            ÇIKTI FORMATI (JSON):
            { "ID": "...", "HGB": "...", "PLT": "...", "RDW": "...", "NEUT_HASH": "...", "LYMPH_HASH": "...", "IG_HASH": "...", "CRP": "...", "Prokalsitonin": "..." }
            """
            
            content_parts.append({"text": prompt_text})

            if hemo_file:
                content_parts.append({"inline_data": {"mime_type": "image/png", "data": image_to_base64(Image.open(hemo_file))}})
            if bio_file:
                content_parts.append({"inline_data": {"mime_type": "image/png", "data": image_to_base64(Image.open(bio_file))}})

            # Model: 2.5 Pro (En iyisi)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={API_KEY}"
            headers = {'Content-Type': 'application/json'}
            payload = {"contents": [{"parts": content_parts}]}
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                try:
                    text_content = result['candidates'][0]['content']['parts'][0]['text']
                    text_content = text_content.replace("```json", "").replace("```", "").strip()
                    
                    # JSON ayıklama
                    start = text_content.find('{')
                    end = text_content.rfind('}') + 1
                    data = json.loads(text_content[start:end])
                except:
                    st.error("Veri okunamadı. Ham yanıt:")
                    st.write(text_content)
                    st.stop()
                
                st.subheader(f"Hasta: {data.get('ID')}")
                
                cols = st.columns(4)
                cols[0].metric("HGB", data.get("HGB"))
                cols[1].metric("PLT", data.get("PLT"))
                cols[2].metric("CRP", data.get("CRP"))
                cols[3].metric("Prokalsitonin", data.get("Prokalsitonin"))
                
                with st.expander("Detaylı JSON Verisi"):
                    st.json(data)

                # Google Sheets
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
                st.success("✅ Tabloya Eklendi!")
                
            else:
                st.error(f"Sunucu Hatası: {response.status_code}")
                st.write(response.text)

        except Exception as e:
            st.error(f"Hata: {e}")
