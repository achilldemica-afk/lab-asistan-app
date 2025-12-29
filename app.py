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
st.title("🩸 Hasta Takip & Veri Girişi")
st.success("Aktif Model: Gemini 2.5 PRO (Yüksek Hassasiyet Modu)")

col1, col2 = st.columns(2)

with col1:
    hemo_file = st.file_uploader("1. Hemogram (Mor Tüp)", type=["jpg", "png", "jpeg"], key="hemo")

with col2:
    bio_file = st.file_uploader("2. Biyokimya (Sarı Tüp)", type=["jpg", "png", "jpeg"], key="bio")

if st.button("Analiz Et ve Tabloya Yaz", type="primary"):
    
    if not hemo_file and not bio_file:
        st.warning("Lütfen en az bir sonuç kağıdı yükleyin.")
        st.stop()

    with st.spinner('Yapay zeka (Pro) dikkatlice inceliyor...'):
        try:
            content_parts = []
            
            # --- GELİŞTİRİLMİŞ EMRİNİZ (PROMPT) ---
            prompt_text = """
            Sen son derece titiz bir tıbbi veri uzmanısın. Yüklenen laboratuvar sonuçlarını incele.
            
            GÖREVLER VE KURALLAR:
            1. **Sayısal Hassasiyet:** Rakamları okurken OCR hatalarına düşme. Nokta (.) ve Virgül (,) ayrımına çok dikkat et.
            2. **Kimlik:** Resmin sol üst köşesindeki Hasta Adı Soyadı veya Protokol numarasını bul ve 'ID' olarak al.
            3. **Format:** Sonucu sadece JSON formatında ver.
            
            İSTENEN JSON ALANLARI:
            {
                "ID": "Hasta Adı veya TC",
                "HGB": "Hemoglobin değeri (Sayı)",
                "PLT": "Trombosit değeri (Sayı)",
                "RDW": "RDW değeri (Sayı)",
                "NEUT_HASH": "Nötrofil MUTLAK sayısı (Genelde NEU# veya #NEU yazar, % değil)",
                "LYMPH_HASH": "Lenfosit MUTLAK sayısı (LYM#)",
                "IG_HASH": "İmmatür Granülosit (IG#). Yoksa null.",
                "CRP": "CRP değeri",
                "Prokalsitonin": "Prokalsitonin değeri"
            }
            Değer kağıtta yoksa "null" yaz.
            """
            
            content_parts.append({"text": prompt_text})

            if hemo_file:
                img_hemo = Image.open(hemo_file)
                content_parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": image_to_base64(img_hemo)
                    }
                })

            if bio_file:
                img_bio = Image.open(bio_file)
                content_parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": image_to_base64(img_bio)
                    }
                })

            # --- MODEL DEĞİŞİKLİĞİ BURADA YAPILDI ---
            # Eski: gemini-2.5-flash -> Yeni: gemini-2.5-pro
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={API_KEY}"
            
            headers = {'Content-Type': 'application/json'}
            payload = {"contents": [{"parts": content_parts}]}
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                text_content = result['candidates'][0]['content']['parts'][0]['text']
                text_content = text_content.replace("```json", "").replace("```", "").strip()
                data = json.loads(text_content)
                
                st.subheader(f"Hasta: {data.get('ID', 'Bulunamadı')}")
                st.json(data)
                
                # Excel Kaydı
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
                st.balloons()
                st.success(f"✅ Kayıt Başarılı! (Kullanılan Model: Gemini 2.5 PRO)")
                
            else:
                st.error(f"Sunucu Hatası: {response.status_code}")
                st.write(response.text)

        except Exception as e:
            st.error(f"Hata oluştu: {e}")
