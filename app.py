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
import re

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

# --- 3. YARDIMCI FONKSİYONLAR ---
def image_to_base64(image):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# --- 4. ARAYÜZ ---
st.title("🩸 Hasta Takip (Gemini 2.5 Pro)")
st.info("Model: Gemini 2.5 Pro (Listenizdeki En Zeki Model Seçildi)")

col1, col2 = st.columns(2)
with col1:
    hemo_file = st.file_uploader("1. Hemogram Yükle", type=["jpg", "png", "jpeg"], key="hemo")
with col2:
    bio_file = st.file_uploader("2. Biyokimya Yükle", type=["jpg", "png", "jpeg"], key="bio")

if st.button("Analiz Et", type="primary"):
    if not hemo_file and not bio_file:
        st.warning("Dosya seçilmedi.")
        st.stop()

    with st.spinner('Gemini 2.5 Pro, referans aralıklarını eliyor...'):
        try:
            content_parts = []
            
            # --- GELİŞTİRİLMİŞ 'DEDEKTİF' EMRİ (PROMPT) ---
            # Bu prompt, modele önce satırı analiz ettirir, sonra karar verdirir.
            prompt_text = """
            Sen laboratuvar sonuçlarını okuyan bir uzmansın.
            
            GÖREV: Aşağıdaki parametrelerin SADECE 'SONUÇ' (RESULT) değerlerini bul.
            
            KRİTİK HATA ÖNLEME KURALLARI:
            1. Laboratuvar kağıtlarında genelde 3 sayı yan yana yazar: "Sonuç", "Ünite", "Referans Aralığı".
            2. "Referans Aralığı" sütununda genelde tire (-) işareti olur (Örn: 11.5 - 15.5). BU SAYIYI ASLA ALMA.
            3. Eğer bir satırda "5.1" ve "13.5" görüyorsan; hangisinin "Normal Değer" (Referans) olduğuna bak ve onu at. Diğerini (Hastanın değerini) al.
            4. HGB (Hemoglobin) için: Eğer değer 5.1 ise ve referans 13.0 ise, 5.1'i al.
            
            ÇIKTI FORMATI (SADECE JSON):
            {
                "ID": "Hasta Adı veya Protokol No (Sol üstten)",
                "HGB": "Sayı",
                "PLT": "Sayı",
                "RDW": "Sayı",
                "NEUT_HASH": "Nötrofil Mutlak (#) Değeri (% değil)",
                "LYMPH_HASH": "Lenfosit Mutlak (#) Değeri",
                "IG_HASH": "IG Mutlak (#) Değeri (yoksa null)",
                "CRP": "Sayı",
                "Prokalsitonin": "Sayı"
            }
            """
            content_parts.append({"text": prompt_text})

            if hemo_file:
                content_parts.append({"inline_data": {"mime_type": "image/png", "data": image_to_base64(Image.open(hemo_file))}})
            if bio_file:
                content_parts.append({"inline_data": {"mime_type": "image/png", "data": image_to_base64(Image.open(bio_file))}})

            # --- MODEL SEÇİMİ: Listenizdeki 'gemini-2.5-pro' ---
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={API_KEY}"
            headers = {'Content-Type': 'application/json'}
            payload = {"contents": [{"parts": content_parts}]}
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                # Yanıtı çözümle
                text_content = result['candidates'][0]['content']['parts'][0]['text']
                text_content = text_content.replace("```json", "").replace("```", "").strip()
                
                # Bazen model açıklama yapar, sadece süslü parantez arasını alalım
                try:
                    start = text_content.find('{')
                    end = text_content.rfind('}') + 1
                    json_str = text_content[start:end]
                    data = json.loads(json_str)
                except:
                    st.error("AI yanıtı JSON formatına uymadı. Ham yanıt:")
                    st.write(text_content)
                    st.stop()
                
                # --- VERİ KONTROL VE TEMİZLİK ---
                # Burada Python ile son bir filtre yapabiliriz (opsiyonel)
                
                st.subheader(f"Hasta: {data.get('ID')}")
                
                # Ekrana basarak kontrol etmeni sağlayalım
                cols = st.columns(4)
                cols[0].metric("HGB", data.get("HGB"))
                cols[1].metric("PLT", data.get("PLT"))
                cols[2].metric("CRP", data.get("CRP"))
                cols[3].metric("Prokalsitonin", data.get("Prokalsitonin"))
                
                st.json(data)

                # Google Sheets'e Yaz
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
            st.error(f"Bir hata oluştu: {e}")
