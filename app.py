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
    
    # DİKKAT: Excel dosyanın adı tam olarak bu olmalı
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
st.info("Hemogram ve Biyokimya sonuçlarını yükleyin. Sistem ikisini birleştirip tek satır yapacaktır.")

col1, col2 = st.columns(2)

with col1:
    hemo_file = st.file_uploader("1. Hemogram (Mor Tüp)", type=["jpg", "png", "jpeg"], key="hemo")

with col2:
    bio_file = st.file_uploader("2. Biyokimya (Sarı Tüp)", type=["jpg", "png", "jpeg"], key="bio")

# Analiz Butonu
if st.button("Analiz Et ve Tabloya Yaz", type="primary"):
    
    if not hemo_file and not bio_file:
        st.warning("Lütfen en az bir sonuç kağıdı yükleyin.")
        st.stop()

    with st.spinner('Yapay zeka sonuçları okuyor ve hasta ismini arıyor...'):
        try:
            # --- GÖRÜNTÜLERİ HAZIRLA ---
            content_parts = []
            
            # Asıl Komut (Prompt) - Excel Sütunlarına Göre Ayarlı
            prompt_text = """
            Sen uzman bir tıbbi asistansın. Yüklenen laboratuvar sonuçlarını incele.
            
            GÖREVLER:
            1. Resmin sol üst köşesindeki Hasta Adı Soyadı veya Protokol numarasını bul ve 'ID' olarak kaydet.
            2. Aşağıdaki spesifik değerleri bul. Hemogram ve Biyokimya kağıtlarını ayırt et.
            3. Sonucu SADECE JSON formatında ver. Başka kelime etme.
            
            İSTENEN JSON FORMATI (Excel sütunlarına karşılık gelen):
            {
                "ID": "Hasta Adı veya TC",
                "HGB": "Sayısal değer",
                "PLT": "Sayısal değer",
                "RDW": "Sayısal değer",
                "NEUT_HASH": "Nötrofil Mutlak Sayısı (Neu# veya Neu)",
                "LYMPH_HASH": "Lenfosit Mutlak Sayısı (Lym# veya Lym)",
                "IG_HASH": "İmmatür Granülosit (IG# veya IG). Yoksa null yaz.",
                "CRP": "C-Reaktif Protein",
                "Prokalsitonin": "Prokalsitonin değeri"
            }
            
            Eğer bir değer kağıtta yoksa "null" yaz. Ondalıklı sayıları nokta (.) ile ayır.
            """
            
            content_parts.append({"text": prompt_text})

            # Hemogram varsa ekle
            if hemo_file:
                img_hemo = Image.open(hemo_file)
                content_parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": image_to_base64(img_hemo)
                    }
                })

            # Biyokimya varsa ekle
            if bio_file:
                img_bio = Image.open(bio_file)
                content_parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": image_to_base64(img_bio)
                    }
                })

            # --- API İSTEĞİ (Gemini 2.5 Flash) ---
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
            headers = {'Content-Type': 'application/json'}
            payload = {"contents": [{"parts": content_parts}]}
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                # --- SONUCU İŞLE ---
                result = response.json()
                text_content = result['candidates'][0]['content']['parts'][0]['text']
                
                # JSON Temizliği
                text_content = text_content.replace("```json", "").replace("```", "").strip()
                data = json.loads(text_content)
                
                # Ekrana Göster
                st.subheader(f"Hasta: {data.get('ID', 'Bulunamadı')}")
                st.json(data)
                
                # --- GOOGLE SHEETS KAYDI ---
                # Excel'deki sütun sırasına göre diziyoruz:
                # A:ID, B:HGB, C:PLT, D:RDW, E:NEUT#, F:LYMPH#, G:IG#, H:CRP, I:Prokalsitonin
                
                sheet = client.open(SHEET_NAME).sheet1
                
                row = [
                    data.get("ID"),
                    data.get("HGB"),
                    data.get("PLT"),
                    data.get("RDW"),
                    data.get("NEUT_HASH"),   # Excel'deki NEUT#
                    data.get("LYMPH_HASH"),  # Excel'deki LYMPH#
                    data.get("IG_HASH"),     # Excel'deki IG#
                    data.get("CRP"),
                    data.get("Prokalsitonin")
                ]
                
                sheet.append_row(row)
                st.balloons()
                st.success(f"✅ {data.get('ID')} için veriler 'Hasta Takip' dosyasına eklendi!")
                
            else:
                st.error(f"Sunucu Hatası: {response.status_code}")
                st.write(response.text)

        except Exception as e:
            st.error(f"Hata oluştu: {e}")
