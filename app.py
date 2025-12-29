import streamlit as st
import requests
import json

# --- AYARLAR ---
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
    else:
        st.error("API Key yok! Secrets ayarlarını kontrol et.")
        st.stop()
except Exception as e:
    st.error(f"Ayar hatası: {e}")
    st.stop()

st.title("🕵️‍♀️ Google Model Dedektifi")
st.write("Şu an kullandığın API Anahtarı ile hangi modellere erişebildiğimizi sorguluyoruz.")
st.write(f"Kullanılan Anahtarın İlk 4 Hanesi: `{API_KEY[:4]}...`")

if st.button("Modelleri Listele (Google'a Sor)"):
    try:
        # Doğrudan Google'a "Elinizde ne var?" diye soruyoruz
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
        
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            st.success("✅ Bağlantı Başarılı! İşte senin kullanabileceğin modeller:")
            
            # Gelen listeyi temiz bir tablo gibi gösterelim
            if "models" in data:
                model_names = []
                for model in data["models"]:
                    # Sadece resim okuyabilen veya metin üretenleri filtreleyelim
                    isim = model.get("name", "İsimsiz")
                    versiyon = model.get("version", "-")
                    desteklenenler = model.get("supportedGenerationMethods", [])
                    
                    st.code(f"Model Adı: {isim}\nDesteklediği İşler: {desteklenenler}")
                    model_names.append(isim)
                
                st.write("---")
                st.info("Aşağıdaki satırı kopyalayıp bana ver, asıl koda onu yazacağız:")
                st.text_area("Kopyalanacak Liste", str(model_names))
            else:
                st.warning("Google cevap verdi ama liste boş döndü. Tuhaf.")
                st.json(data)
                
        else:
            st.error(f"❌ Bağlantı Hatası Oldu! Kod: {response.status_code}")
            st.write("Google'ın Hata Mesajı:")
            st.json(response.json())
            
    except Exception as e:
        st.error(f"Kod çalışırken hata oluştu: {e}")
