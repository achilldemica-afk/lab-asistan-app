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

# --- 1. AYARLAR VE GÜVENLİK ---
st.set_page_config(page_title="Hasta Takip Asistanı", page_icon="🩸")

try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
    else:
        st.error("HATA: API Key bulunamadı! Secrets ayarlarını kontrol edin.")
        st.stop()
        
    if "gcp_service_account" in st.secrets:
        sheets_secrets = st.secrets["gcp_service_account"]
    else:
        st.error("HATA: Google Sheets yetkisi eksik! Secrets ayarlarını kontrol edin.")
        st.stop()
except Exception as e:
    st.error(f"Ayar hatası: {e}")
    st.stop()

# --- 2. GOOGLE SHEETS BAĞLANTISI ---
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(sheets_secrets, scope)
    client = gspread.authorize(creds)
    # Excel dosyasının adı tam olarak bu olmalı
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
st.info("CRP ve Referans Ayrımı Güçlendirilmiş Mod")

col1, col2 = st.columns(2)

with col1:
    hemo_file = st.file_uploader("1. Hemogram Yükle", type=["jpg", "png", "jpeg"], key="hemo")

with col2:
    bio_file = st.file_uploader("2. Biyokimya Yükle", type=["jpg", "png", "jpeg"], key="bio")

# --- 5. ANALİZ VE İŞLEME ---
if st.button("Analiz Et ve Tabloya Yaz", type="primary"):
    
    if not hemo_file and not bio_file:
        st.warning("Lütfen en az bir dosya yükleyin.")
        st.stop()

    with st.spinner('Yapay zeka (Gemini 2.5 Pro) analiz ediyor...'):
        try:
            content_parts = []
            
            # --- GELİŞTİRİLMİŞ PROMPT (EMİR) ---
            prompt_text = """
            Sen uzman bir laboratuvar asistanısın. Görevin resimdeki değerleri okumak.
            
            HEDEF: Aşağıdaki parametrelerin 'SONUÇ' (RESULT) değerlerini bul ve JSON yap.
            
            KRİTİK KURALLAR (Referans vs Sonuç Ayrımı):
            1. Laboratuvar kağıtlarında "Sonuç" ve "Referans Aralığı" yanyana yazar.
            2. Referans aralıkları genelde tire (-) içerir (Örn: 11.5 - 15.5). BU SAYILARI ASLA ALMA.
            3. Senin alacağın sayı "Sonuç" sütunundadır ve genelde TEK bir sayıdır (Örn: 13.2).
            
            ÖZEL DURUM (CRP ve Prokalsitonin):
            - Bazen sonuç değeri, referans limitiyle aynı olabilir veya çok yakın olabilir.
            - Örn: Sonuç "5" ve Referans "<5". Bu durumda "5" değerini SONUÇ olarak al. "null" yazma!
            - Değer var olduğu sürece, referansa benzese bile onu al.
            
            KİMLİK TESPİTİ:
            - Sol üst köşedeki Hasta Adı Soyadı veya Protokol Numarasını 'ID' hanesine yaz.
            
            İSTENEN JSON FORMATI:
            {
                "ID": "Hasta Adı",
                "HGB": "Sayı (Hemoglobin)",
                "PLT": "Sayı (Trombosit)",
                "RDW": "Sayı",
                "NEUT_HASH": "Sayı (Nötrofil Mutlak/#)",
                "LYMPH_HASH": "Sayı (Lenfosit Mutlak/#)",
                "IG_HASH": "Sayı (İmmatür Granülosit/# - Yoksa null)",
                "CRP": "Sayı (CRP Sonucu)",
                "Prokalsitonin": "Sayı"
            }
            """
            
            content_parts.append({"text": prompt_text})

            # Resimleri Ekle
            if hemo_file:
                content_parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": image_to_base64(Image.open(hemo_file))
                    }
                })

            if bio_file:
                content_parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": image_to_base64(Image.open(bio_file))
                    }
                })

            # --- API İSTEĞİ (Gemini 2.5 Pro) ---
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={API_KEY}"
            
            headers = {'Content-Type': 'application/json'}
            payload = {"contents": [{"parts": content_parts}]}
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                
                # Yanıtı çözümle
                try:
                    text_content = result['candidates'][0]['content']['parts'][0]['text']
                    # Markdown temizliği
                    text_content = text_content.replace("```json", "").replace("```", "").strip()
                    # JSON'ı bul (Bazen AI gevezelik edip başına sonuna yazı ekleyebilir)
                    start_index = text_content.find('{')
                    end_index = text_content.rfind('}') + 1
                    json_str = text_content[start_index:end_index]
                    
                    data = json.loads(json_str)
                except Exception as parse_err:
                    st.error("AI yanıtı okunamadı. Ham yanıt aşağıda:")
                    st.text(text_content)
                    st.stop()
                
                # --- EKRAN KONTROLÜ ---
                st.subheader(f"Bulunan Hasta: {data.get('ID', '---')}")
                
                # Sonuçları göster (Gözle kontrol için)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("HGB", data.get("HGB"))
                c2.metric("PLT", data.get("PLT"))
                c3.metric("CRP", data.get("CRP"))
                c4.metric("Prokalsitonin", data.get("Prokalsitonin"))
                
                with st.expander("Tüm Veriyi Gör"):
                    st.json(data)
                
                # --- GOOGLE SHEETS KAYDI ---
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
                st.success("✅ Veriler Google E-Tablosuna başarıyla işlendi!")
                
            else:
                st.error(f"Sunucu Hatası: {response.status_code}")
                st.write(response.text)

        except Exception as e:
            st.error(f"Beklenmeyen bir hata oluştu: {e}")
