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

# --- 1. AYARLAR VE GÜVENLİK ---
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
    else:
        st.error("API Key eksik! Lütfen Secrets ayarlarını kontrol et.")
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
    # DİKKAT: Buradaki isim Google Sheet dosyanın adıyla BİREBİR aynı olmalı
    SHEET_NAME = "LabSonuclari" 
except Exception as e:
    st.error(f"Google Sheets Bağlantı Hatası: {e}")
    st.stop()

# --- 3. YARDIMCI FONKSİYONLAR ---
def image_to_base64(image):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# --- 4. ARAYÜZ (FRONTEND) ---
st.set_page_config(page_title="Lab Asistanı", page_icon="🩺")
st.title("🩺 Asistan Lab Veri Girişi")
st.success(f"Sistem Hazır - Model: Gemini 2.5 Flash")

uploaded_file = st.file_uploader("Lütfen Lab Sonucunun Ekran Görüntüsünü Yükleyin", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # Resmi göster
    image = Image.open(uploaded_file)
    st.image(image, caption='Yüklenen Resim', width=400)
    
    if st.button("Analiz Et ve Tabloya İşle", type="primary"):
        with st.spinner('Yapay zeka (Gemini 2.5) verileri okuyor...'):
            try:
                # A) Resmi Hazırla
                base64_image = image_to_base64(image)
                
                # B) API İSTEĞİ (Senin listendeki MODEL buraya yazıldı)
                # Listende 'models/gemini-2.5-flash' vardı.
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
                
                headers = {'Content-Type': 'application/json'}
                
                # C) AI'ya Verilen Emir (Prompt)
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": """
                            Sen uzman bir hematolog asistanısın. Bu resimdeki laboratuvar sonuçlarını incele.
                            Sadece aşağıdaki parametreleri bul ve JSON formatında çıkar.
                            Başka hiçbir metin yazma, sadece JSON.
                            Değer bulamazsan "null" yaz.
                            
                            İstenenler:
                            - WBC (Lökosit)
                            - Neu (Nötrofil - Mutlak değer tercih edilir, yoksa %)
                            - Hgb (Hemoglobin)
                            - Plt (Trombosit)
                            - CRP (C-Reaktif Protein)
                            """},
                            {"inline_data": {
                                "mime_type": "image/png",
                                "data": base64_image
                            }}
                        ]
                    }]
                }
                
                # D) İsteği Gönder
                response = requests.post(url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    # E) Sonucu İşle
                    result = response.json()
                    try:
                        # AI cevabının içindeki metni cımbızla çekiyoruz
                        text_content = result['candidates'][0]['content']['parts'][0]['text']
                        
                        # Temizlik (Markdown işaretlerini kaldır)
                        text_content = text_content.replace("```json", "").replace("```", "").strip()
                        data = json.loads(text_content)
                        
                        # Ekrana Yazdır
                        st.subheader("✅ Okunan Değerler:")
                        col1, col2, col3, col4, col5 = st.columns(5)
                        col1.metric("WBC", data.get("WBC"))
                        col2.metric("Neu", data.get("Neu"))
                        col3.metric("Hgb", data.get("Hgb"))
                        col4.metric("Plt", data.get("Plt"))
                        col5.metric("CRP", data.get("CRP"))
                        
                        st.json(data)
                        
                        # F) Google Sheets'e Kaydet
                        sheet = client.open(SHEET_NAME).sheet1
                        row = [
                            str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                            data.get("WBC"), 
                            data.get("Neu"), 
                            data.get("Hgb"), 
                            data.get("Plt"), 
                            data.get("CRP")
                        ]
                        sheet.append_row(row)
                        st.balloons()
                        st.success("Tabloya başarıyla kaydedildi!")
                        
                    except Exception as parse_error:
                        st.error("AI yanıtı anlaşılamadı. JSON formatı bozuk olabilir.")
                        st.write("Gelen Ham Veri:", text_content)
                else:
                    st.error(f"Sunucu Hatası: {response.status_code}")
                    st.write(response.text)

            except Exception as e:
                st.error(f"Beklenmeyen bir hata oluştu: {e}")
