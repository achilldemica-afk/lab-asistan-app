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
st.set_page_config(page_title="Makale Kulübü Lab Asistanı", page_icon="👶", layout="wide")

# Session State Başlatma (Hafıza)
if 'okunan_veri' not in st.session_state:
    st.session_state.okunan_veri = None

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
st.title("👶 Makale Kulübü Lab Asistanı")

# --- YAŞ BİLGİSİ ---
st.markdown("### 1. Hasta Bilgileri")
st.info("Lütfen ekranda yazan yaşı giriniz. Sadece ay varsa 'Yıl' kısmını 0 bırakın.")

col_yas1, col_yas2 = st.columns(2)
with col_yas1:
    yas_yil = st.number_input("Yaş (YIL)", min_value=0, value=0, step=1)
with col_yas2:
    yas_ay = st.number_input("Yaş (AY)", min_value=0, max_value=11, value=0, step=1)

st.markdown("---")

# --- DOSYA YÜKLEME ---
st.markdown("### 2. Laboratuvar Sonuçları")
st.caption("Telefondan giriyorsanız 'Browse files' -> 'Fotoğraf Çek' seçeneğini kullanın.")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Hemogram")
    hemo_file = st.file_uploader("Hemogram Yükle / Çek", type=["jpg", "png", "jpeg"], key="hemo")

with col2:
    st.markdown("#### Biyokimya")
    bio_file = st.file_uploader("Biyokimya Yükle / Çek", type=["jpg", "png", "jpeg"], key="bio")

# --- ADIM 1: ANALİZ BUTONU (KAYDETMEZ) ---
if st.button("🔍 1. Fotoğrafları Oku (Kaydetmez)", type="primary"):
    
    if not hemo_file and not bio_file:
        st.warning("Lütfen dosya yükleyin veya fotoğraf çekin.")
        st.stop()

    with st.spinner('Hmm...'):
        try:
            content_parts = []
            
            # --- PROMPT ---
            prompt_text = """
            GÖREV: Sen titiz bir veri giriş operatörüsün.
            
            YÖNTEM (SATIR TAKİP):
            1. Sol sütunda Parametre Adını bul.
            2. Parmağını sağa kaydır, REFERANS ARALIĞINI ATLA, SONUÇ (Result) değerini al.
            
            BULUNACAKLAR:
            - HGB (Hemoglobin)
            - PLT (Trombosit)
            - RDW
            - NEU# (Nötrofil Mutlak) -> Yoksa 'null'
            - LYM# (Lenfosit Mutlak) -> Yoksa 'null'
            - IG# (İmmatür Granülosit) -> Yoksa 'null'
            - CRP -> Yoksa 'null'
            - Prokalsitonin -> Yoksa 'null'
            
            KİMLİK:
            - Sol üstteki İsim/Protokol -> 'ID'
            
            ÇIKTI (JSON):
            { "ID": "...", "HGB": 0.0, "PLT": 0, "RDW": 0.0, "NEUT_HASH": 0.0, "LYMPH_HASH": 0.0, "IG_HASH": 0.0, "CRP": 0.0, "Prokalsitonin": 0.0 }
            """
            
            content_parts.append({"text": prompt_text})

            if hemo_file:
                content_parts.append({"inline_data": {"mime_type": "image/png", "data": image_to_base64(Image.open(hemo_file))}})
            if bio_file:
                content_parts.append({"inline_data": {"mime_type": "image/png", "data": image_to_base64(Image.open(bio_file))}})

            # MODEL: Gemini 3.0 Pro Preview
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
                    data = json.loads(text_content[start:end] if start != -1 else text_content)

                    # --- YAŞ HESAPLAMA VE VERİ BİRLEŞTİRME ---
                    # Veriyi DataFrame'e çevirip yaş bilgilerini ekliyoruz
                    data["YAS_YIL"] = yas_yil
                    data["YAS_AY"] = yas_ay
                    data["TOPLAM_AY"] = (yas_yil * 12) + yas_ay
                    
                    # Session State'e kaydet (Hafızaya al)
                    st.session_state.okunan_veri = pd.DataFrame([data])
                    
                    # Sayfayı yenile ki editör açılsın
                    st.rerun()

                except Exception as parse_error:
                    st.error("Veri okunamadı. Resim net olmayabilir.")
                    st.text(text_content)
            else:
                st.error(f"Sunucu Hatası: {response.status_code}")
                st.write(response.text)

        except Exception as e:
            st.error(f"Hata: {e}")

# --- ADIM 2: KONTROL VE DÜZELTME EKRANI ---
if st.session_state.okunan_veri is not None:
    st.markdown("---")
    st.info("⚠️ Lütfen aşağıdaki değerleri kontrol edin. Hatalı bir yer varsa **üzerine tıklayıp düzeltebilirsiniz.**")
    
    # EDİTÖR: Excel gibi düzenlenebilir tablo
    # Sütun sırasını kullanıcı dostu yapalım
    column_order = ["ID", "YAS_YIL", "YAS_AY", "TOPLAM_AY", "HGB", "PLT", "RDW", "NEUT_HASH", "LYMPH_HASH", "IG_HASH", "CRP", "Prokalsitonin"]
    
    # Sadece veride var olan sütunları seç (Hata önlemek için)
    existing_cols = [col for col in column_order if col in st.session_state.okunan_veri.columns]
    
    duzenlenmis_df = st.data_editor(
        st.session_state.okunan_veri, 
        column_order=existing_cols,
        num_rows="fixed", 
        hide_index=True,
        use_container_width=True
    )
    
    col_save, col_cancel = st.columns([1, 4])
    
    # --- ADIM 3: KAYDET BUTONU ---
    with col_save:
        if st.button("✅ Onayla ve Kaydet", type="primary"):
            try:
                # Düzenlenmiş veriyi al
                final_data = duzenlenmis_df.iloc[0]
                
                # Google Sheets'e Kayıt (Sıraya dikkat)
                sheet = client.open(SHEET_NAME).sheet1
                row = [
                    final_data.get("ID"),
                    final_data.get("YAS_YIL"),
                    final_data.get("YAS_AY"),
                    final_data.get("TOPLAM_AY"),
                    final_data.get("HGB"),
                    final_data.get("PLT"),
                    final_data.get("RDW"),
                    final_data.get("NEUT_HASH"),
                    final_data.get("LYMPH_HASH"),
                    final_data.get("IG_HASH"),
                    final_data.get("CRP"),
                    final_data.get("Prokalsitonin")
                ]
                
                # NaN (Boş) değerleri temizle (Google Sheets hatasını önler)
                row = [str(x) if pd.notna(x) else "" for x in row]
                
                sheet.append_row(row)
                
                st.success(f"Başarıyla Kaydedildi! (ID: {final_data.get('ID')})")
                
                # Hafızayı temizle (Yeni hasta için)
                st.session_state.okunan_veri = None
                # st.rerun() # Otomatik sıfırlamak istersen bu satırı aç
                
            except Exception as e:
                st.error(f"Kayıt Hatası: {e}")

    with col_cancel:
        if st.button("❌ İptal / Temizle"):
            st.session_state.okunan_veri = None
            st.rerun()
