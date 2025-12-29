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
st.title("🩸 Hasta Takip & Veri Girişi (V3 - Sütun Korumalı)")
st.info("Akıllı Sütun Tespiti Aktif: Referans aralıkları filtreleniyor.")

col1, col2 = st.columns(2)

with col1:
    hemo_file = st.file_uploader("1. Hemogram (Mor Tüp)", type=["jpg", "png", "jpeg"], key="hemo")

with col2:
    bio_file = st.file_uploader("2. Biyokimya (Sarı Tüp)", type=["jpg", "png", "jpeg"], key="bio")

if st.button("Analiz Et ve Tabloya Yaz", type="primary"):
    
    if not hemo_file and not bio_file:
        st.warning("Lütfen en az bir sonuç kağıdı yükleyin.")
        st.stop()

    with st.spinner('Tablo sütunları ayrıştırılıyor...'):
        try:
            content_parts = []
            
            # --- KRİTİK DEĞİŞİKLİK: PROMPT (EMİR) GÜNCELLENDİ ---
            prompt_text = """
            Sen laboratuvar sonuçlarını okuyan dikkatli bir uzmansın.
            
            ÖNEMLİ UYARI:
            Bu kağıtlarda birden fazla sayı sütunu vardır (Sonuç, Ünite, Referans Aralığı).
            Senin görevin SADECE 'Sonuç' (Result) sütununu okumaktır.
            
            KURALLAR:
            1. **Sütun Ayrımı:** 'Referans Aralığı' (Reference Range / Normal Değerler) sütunundaki sayıları ASLA okuma. Bu sütunda genelde tire (-) işareti olur (örn: 11.5 - 15.5). Bunları görmezden gel.
            2. **Doğru Değer:** Sadece hastanın o anki ölçüm değerini al.
            3. **HGB Örneği:** Eğer HGB satırında "5.1" ve yanında "11.5-15.5" yazıyorsa, bana "5.1" değerini ver. "11.5" veya "13.5" gibi referans sayılarını verme.
            4. **Kimlik:** Sol üstteki Hasta Adını 'ID' olarak al.
            
            ÇIKARILACAK JSON VERİSİ:
            {
                "ID": "Hasta Adı",
                "HGB": "Sadece SONUÇ değeri (Referans değil!)",
                "PLT": "Sadece SONUÇ değeri",
                "RDW": "Sadece SONUÇ değeri",
                "NEUT_HASH": "Nötrofil Mutlak (#) Değeri",
                "LYMPH_HASH": "Lenfosit Mutlak (#) Değeri",
                "IG_HASH": "IG Mutlak (#) Değeri (yoksa null)",
                "CRP": "CRP Sonucu",
                "Prokalsitonin": "Prokalsitonin Sonucu"
            }
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

            # Modeli 1.5 PRO'ya çekiyoruz (Bazen 2.5 fazla 'yaratıcı' olup hata yapabiliyor, 1.5 talimatlara daha sadık)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={API_KEY}"
            
            headers = {'Content-Type': 'application/json'}
            payload = {"contents": [{"parts": content_parts}]}
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                text_content = result['candidates'][0]['content']['parts'][0]['text']
                text_content = text_content.replace("```json", "").replace("```", "").strip()
                data = json.loads(text_content)
                
                st.subheader(f"Bulunan Hasta: {data.get('ID', '---')}")
                
                # Kontrol amaçlı ekrana da basalım
                c1, c2, c3 = st.columns(3)
                c1.metric("HGB (Kontrol Et)", data.get("HGB"))
                c2.metric("PLT", data.get("PLT"))
                c3.metric("CRP", data.get("CRP"))
                
                st.json(data)
                
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
                st.success(f"✅ Kaydedildi!")
                
            else:
                st.error(f"Sunucu Hatası: {response.status_code}")
                st.write(response.text)

        except Exception as e:
            st.error(f"Hata oluştu: {e}")
