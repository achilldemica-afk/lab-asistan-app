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

# --- 1. GÜVENLİK VE AYARLAR ---
st.set_page_config(page_title="Lab Asistanı 2.0", page_icon="🧬", layout="wide")

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
    SHEET_NAME = "Hasta Takip"  # Excel dosya adın
except Exception as e:
    st.error(f"Google Sheets Bağlantı Hatası: {e}")
    st.stop()

# --- 3. YARDIMCI FONKSİYONLAR ---
def image_to_base64(image):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# --- 4. ARAYÜZ TASARIMI ---
st.title("🧬 Lab Asistanı 2.0 (Gemini 2.0 Motoru)")
st.markdown("Bu sürüm, **Gemini 2.0 Flash** motorunu kullanarak tabloyu önce okur, sonra veriyi çeker. Rakam uydurma riskini en aza indirir.")

col1, col2 = st.columns(2)
with col1:
    hemo_file = st.file_uploader("1. Hemogram Yükle", type=["jpg", "png", "jpeg"], key="hemo")
with col2:
    bio_file = st.file_uploader("2. Biyokimya Yükle", type=["jpg", "png", "jpeg"], key="bio")

# --- 5. ANALİZ MOTORU ---
if st.button("Analizi Başlat", type="primary"):
    
    if not hemo_file and not bio_file:
        st.warning("Lütfen dosya yükleyin.")
        st.stop()

    status_text = st.empty()
    status_text.info("Gemini 2.0 Flash motoru çalıştırılıyor...")

    try:
        content_parts = []
        
        # --- YENİ PROMPT STRATEJİSİ: "OCR FIRST" ---
        # Modele önce tabloyu dökmesini, sonra JSON yapmasını söylüyoruz.
        prompt_text = """
        Sen gelişmiş bir OCR (Optik Karakter Tanıma) motorusun.
        
        GÖREV 1: KİMLİK TESPİTİ
        Resmin sol üst veya üst orta kısmındaki Hasta Adı/Soyadı veya Protokol numarasını bul.
        
        GÖREV 2: TABLO OKUMA VE EŞLEŞTİRME
        Resimdeki tabloyu satır satır incele. Şu mantığı kullan:
        1. "Parametre Adı" sütununu bul (Örn: WBC, HGB, PLT, CRP yazar).
        2. "Sonuç" (Result) sütununu bul.
        3. "Referans Aralığı" sütununu bul ve GÖRMEZDEN GEL.
        
        Aşağıdaki parametrelerin tam karşısındaki "SONUÇ" değerini al:
        - HGB (Hemoglobin)
        - PLT (Trombosit)
        - RDW (veya RDW-CV/SD)
        - NEU# (Nötrofil Mutlak Değeri - % olanı değil, # olanı al)
        - LYM# (Lenfosit Mutlak Değeri - % olanı değil, # olanı al)
        - IG# (İmmatür Granülosit Mutlak Değeri - Yoksa 'null' yaz)
        - CRP (C-Reaktif Protein - Referans ile aynı olsa bile sonucu al)
        - Prokalsitonin
        
        GÖREV 3: ÇIKTI ÜRETME
        Sadece ve sadece aşağıdaki JSON formatını üret. Başka hiçbir metin yazma.
        
        {
            "ID": "Bulunan İsim",
            "HGB": 0.0,
            "PLT": 0,
            "RDW": 0.0,
            "NEUT_HASH": 0.0,
            "LYMPH_HASH": 0.0,
            "IG_HASH": 0.0,
            "CRP": 0.0,
            "Prokalsitonin": 0.0
        }
        
        Eğer bir değer yoksa rakam yerine null yaz. Sayılarda nokta (.) kullan.
        """
        
        content_parts.append({"text": prompt_text})

        # Resimleri Base64 yapıp ekle
        if hemo_file:
            content_parts.append({"inline_data": {"mime_type": "image/png", "data": image_to_base64(Image.open(hemo_file))}})
        if bio_file:
            content_parts.append({"inline_data": {"mime_type": "image/png", "data": image_to_base64(Image.open(bio_file))}})

        # --- MOTOR SEÇİMİ: Gemini 2.0 Flash ---
        # Listende vardı: 'models/gemini-2.0-flash'
        # Bu model OCR konusunda çok daha keskindir.
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
        
        headers = {'Content-Type': 'application/json'}
        payload = {"contents": [{"parts": content_parts}]}
        
        # İsteği Gönder
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            try:
                # Metni temizle
                raw_text = result['candidates'][0]['content']['parts'][0]['text']
                clean_json = raw_text.replace("```json", "").replace("```", "").strip()
                
                # Bazen JSON'ın dışına açıklama yazar, sadece { } arasını alalım
                start = clean_json.find('{')
                end = clean_json.rfind('}') + 1
                if start != -1 and end != -1:
                    clean_json = clean_json[start:end]
                
                data = json.loads(clean_json)
                
                status_text.success("Analiz Tamamlandı!")
                
                # --- SONUÇLARI GÖSTER (Kontrol Paneli) ---
                st.subheader(f"👤 Hasta: {data.get('ID', 'Belirsiz')}")
                
                # Grid Görünümü
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("HGB", data.get("HGB"))
                c2.metric("PLT", data.get("PLT"))
                c3.metric("RDW", data.get("RDW"))
                c4.metric("CRP", data.get("CRP"))
                c5.metric("Prokalsitonin", data.get("Prokalsitonin"))
                
                c6, c7, c8 = st.columns(3)
                c6.metric("NEU#", data.get("NEUT_HASH"))
                c7.metric("LYM#", data.get("LYMPH_HASH"))
                c8.metric("IG#", data.get("IG_HASH"))

                # Detaylı JSON (Debug için gizli)
                with st.expander("Ham Veriyi Gör (Hata Varsa Buraya Bak)"):
                    st.json(data)
                    st.text("Modelin Ham Yanıtı:")
                    st.code(raw_text)

                # --- EXCEL KAYDI ---
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
                st.toast("✅ Excel'e Kaydedildi!", icon="💾")
                
            except Exception as parse_error:
                status_text.error("Veri okunamadı! Modelin yanıtı bozuk olabilir.")
                st.error(f"Hata Detayı: {parse_error}")
                st.write("Gelen Ham Veri:", result)
        else:
            status_text.error(f"Sunucu Hatası: {response.status_code}")
            st.write(response.text)

    except Exception as e:
        st.error(f"Kritik Hata: {e}")
