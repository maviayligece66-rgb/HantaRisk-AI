
import os
import json
import base64
import sqlite3
from datetime import datetime
import pandas as pd
import folium
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from PIL import Image
import io

# 1. Çevresel değişkenleri yükle (.env dosyasını okur)
load_dotenv()

app = Flask(__name__)

# 2. Güvenlik Anahtarı ve Klasör Yapılandırması
app.secret_key = os.getenv("SECRET_KEY", "hantarisk_ai_ozel_sifresi_123")
base = os.path.dirname(os.path.abspath(__file__))

geojson_yolu = os.path.join(base, "datasets", "world.geojson")
risk_csv_yolu = os.path.join(base, "datasets", "hanta_risk.csv")
db_yolu = os.path.join(base, "datasets", "hantarisk_analiz.db")

# 3. Genel Yapay Zekâ (Google Gemini) Bağlantısı
# .env dosyanızda GEMINI_API_KEY anahtarı tanımlı olmalıdır.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = None

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)



# ----------------- SQLITE VERİTABANI -----------------

def veritabani_olustur():
    """Görsel analiz kayıtları için SQLite veritabanını ve tabloyu oluşturur."""
    try:
        os.makedirs(os.path.join(base, "datasets"), exist_ok=True)

        conn = sqlite3.connect(db_yolu)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gorsel_analiz_kayitlari (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dosya_adi TEXT,
                tespit_edilen TEXT,
                kategori TEXT,
                guven_skoru REAL,
                risk_var_mi TEXT,
                risk_seviyesi TEXT,
                risk_aciklamasi TEXT,
                tarih TEXT
            )
        """)

        conn.commit()
        conn.close()

        print("SQLite veritabanı hazır.")

    except Exception as e:
        print("Veritabanı oluşturma hatası:", e)


def son_gorsel_analiz_kayitlari(limit=8):
    """Görsel analiz sayfasında gösterilecek son kayıtları getirir."""
    try:
        conn = sqlite3.connect(db_yolu)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM gorsel_analiz_kayitlari
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        kayitlar = cursor.fetchall()
        conn.close()

        return kayitlar

    except Exception as e:
        print("Görsel analiz kayıtları okuma hatası:", e)
        return []


def analiz_kaydini_veritabanina_ekle(dosya_adi, sonuc):
    """AI görsel analiz sonucunu SQLite veritabanına kaydeder."""
    try:
        meta = sonuc.get("meta", {})
        risk = sonuc.get("hantavirus_risk", {})

        conn = sqlite3.connect(db_yolu)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO gorsel_analiz_kayitlari (
                dosya_adi,
                tespit_edilen,
                kategori,
                guven_skoru,
                risk_var_mi,
                risk_seviyesi,
                risk_aciklamasi,
                tarih
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dosya_adi,
            meta.get("detected_object", "Belirlenemedi"),
            meta.get("category", "Belirlenemedi"),
            meta.get("confidence_score", 0),
            str(risk.get("has_risk", False)),
            risk.get("risk_level", "Belirlenemedi"),
            risk.get("description", ""),
            datetime.now().strftime("%d.%m.%Y %H:%M")
        ))

        conn.commit()
        conn.close()

        print("Görsel analiz sonucu veritabanına kaydedildi.")

    except Exception as e:
        print("Görsel analiz veritabanı kayıt hatası:", e)


veritabani_olustur()


# ----------------- ROUTE TANIMLAMALARI -----------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/bilgi")
def bilgi():
    return render_template("bilgi.html")


@app.route("/analiz")
def analiz():
    return render_template("analiz.html")


@app.route("/grafikler")
def grafikler():
    return render_template("grafikler.html")


@app.route("/gorsel")
def gorsel():
    kayitlar = son_gorsel_analiz_kayitlari(limit=8)
    return render_template("gorsel.html", kayitlar=kayitlar)


# ----------------- YAPAY ZEKÂ GÖRSEL ANALİZ MOTORU -----------------
def ai_gorsel_analiz(file):
    if not client:
        raise ValueError("Yayay zekâ istemcisi başlatılamadı. GEMINI_API_KEY eksik.")

    # Dosyayı hafızaya alıp Pillow (Image) nesnesine dönüştürüyoruz
    image_bytes = file.read()
    img = Image.open(io.BytesIO(image_bytes))

    prompt = """
Sen HantaRisk AI adlı sağlık ve çevresel risk analiz sistemisin.

Görev:
Kullanıcının yüklediği görseli analiz et.
Görseldeki canlıyı, nesneyi veya ortamı tanımla.
Hantavirüs açısından risk taşıyıp taşımadığını değerlendir.

Kurallar:
- Hantavirüs doğrudan fotoğraftan tespit edilemez.
- Bu yüzden risk değerlendirmesi; kemirgen varlığı, depo/bodrum/kırsal ortam, dışkı/idrar izi, hijyen durumu ve temas ihtimaline göre yapılmalıdır.
- Fare, sıçan, kemirgen, geyik faresi gibi canlılar yüksek risk kabul edilir.
- Depo, bodrum, ahır, eski kulübe, kirli kapalı alan orta/yüksek risk kabul edilir.
- İnsan, masa, kitap, evcil hayvan, temiz açık alan gibi görseller düşük risk kabul edilir.
- Bilinmeyen görsellerde temkinli yorum yap.

Sadece geçerli bir JSON objesi döndür. Markdown etiketleri (```json ... ``` gibi) KULLANMA, kod blokları ekleme.

JSON formatı birebir şu şekilde olmalıdır:
{
  "status": "success",
  "meta": {
    "detected_object": "Tespit edilen nesne/canlı",
    "category": "Kategori",
    "confidence_score": 0.95
  },
  "hantavirus_risk": {
    "has_risk": true,
    "risk_level": "Yüksek Risk / Orta Risk / Düşük Risk",
    "description": "Risk durumu açıklaması"
  },
  "other_health_risks": [
    {
      "disease_name": "Hastalık adı",
      "risk_factor": "Risk faktörü",
      "note": "Not"
    }
  ],
  "recommendations": ["Tavsiye 1", "Tavsiye 2"]
}
"""

    # Gemini Çoklu Ortam (Multimodal) API çağrısı
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[img, prompt]
    )

    text = response.text.strip()

    try:
        # JSON yapısını doğrula ve Python sözlüğüne çevir
        return json.loads(text)
    except Exception:
        # Fallback yapısı: Eğer model JSON dışında bir metin üretirse hata vermemesi için koruma
        return {
            "status": "success",
            "meta": {
                "detected_object": "Görsel yapay zekâ tarafından incelendi",
                "category": "Genel Multimodal Analiz",
                "confidence_score": 0.85
            },
            "hantavirus_risk": {
                "has_risk": True,
                "risk_level": "Orta Risk",
                "description": text
            },
            "other_health_risks": [],
            "recommendations": [
                "Görselde riskli bir canlı veya ortam varsa doğrudan temas etmeyin.",
                "Kemirgen izi görülen alanlarda temizlik yaparken maske ve eldiven kullanın.",
                "Şüpheli bir kemirgen teması durumunda en yakın sağlık kuruluşuna başvurun."
            ]
        }


@app.route("/api/analiz-et", methods=["POST"])
def analiz_et():
    if "file" not in request.files:
        return jsonify({
            "status": "error",
            "message": "Herhangi bir görsel yüklenmedi."
        }), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({
            "status": "error",
            "message": "Geçersiz veya boş dosya ismi."
        }), 400

    if not os.getenv("GEMINI_API_KEY"):
        return jsonify({
            "status": "error",
            "message": "GEMINI_API_KEY bulunamadı. Lütfen Render panelinden veya .env dosyasından API anahtarını tanımlayın."
        }), 500

    try:
        sonuc = ai_gorsel_analiz(file)
        analiz_kaydini_veritabanina_ekle(file.filename, sonuc)
        return jsonify(sonuc)

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Görsel analiz sırasında sistem hatası oluştu: {str(e)}"
        }), 500



@app.route("/gecmis")
def gecmis():
    kayitlar = son_gorsel_analiz_kayitlari(limit=50)
    return render_template("gecmis.html", kayitlar=kayitlar)



# ----------------- HARİTA YARDIMCI FONKSİYONLARI -----------------

def risk_rengi(risk):
    risk = str(risk).lower().strip()
    if risk == "high":
        return "#e74c3c"
    elif risk == "medium":
        return "#f39c12"
    elif risk == "low":
        return "#2ecc71"
    elif risk == "no_risk":
        return "#3498db"
    else:
        return "#95a5a6"


def risk_adi(risk):
    risk = str(risk).lower().strip()
    if risk == "high":
        return "Yüksek Risk"
    elif risk == "medium":
        return "Orta Risk"
    elif risk == "low":
        return "Düşük Risk"
    elif risk == "no_risk":
        return "Risk Taşımıyor"
    else:
        return "Veri Yok / Bilinmiyor"


@app.route("/harita")
def harita():
    if not os.path.exists(geojson_yolu):
        return render_template(
            "harita.html",
            harita=None,
            hata="world.geojson dosyası bulunamadı. Lütfen datasets klasörüne ekleyin."
        )

    if not os.path.exists(risk_csv_yolu):
        return render_template(
            "harita.html",
            harita=None,
            hata="hanta_risk.csv dosyası bulunamadı. Lütfen datasets klasörüne ekleyin."
        )

    dunya_haritasi = folium.Map(
        location=[20, 0],
        zoom_start=2,
        tiles="cartodbpositron"
    )

    with open(geojson_yolu, "r", encoding="utf-8") as f:
        world_data = json.load(f)

    df = pd.read_csv(risk_csv_yolu)
    risk_dict = {}

    for _, row in df.iterrows():
        country = str(row["country"]).strip()
        risk_dict[country] = {
            "risk_level": row.get("risk_level", "unknown"),
            "cases": row.get("cases", 0),
            "deaths": row.get("deaths", 0),
            "description": row.get("description", "")
        }

    for feature in world_data["features"]:
        props = feature["properties"]
        country_name = (
            props.get("ADMIN") or props.get("NAME") or props.get("name") or 
            props.get("Country") or props.get("country")
        )

        if country_name is None:
            country_name = "Bilinmeyen Ülke"

        bilgi = risk_dict.get(country_name, {
            "risk_level": "unknown",
            "cases": 0,
            "deaths": 0,
            "description": "Bu ülke için yeterli hantavirüs risk verisi bulunmamaktadır."
        })

        risk = bilgi["risk_level"]
        renk = risk_rengi(risk)

        popup_html = f"""
        <div style="font-family: Arial; width: 250px; color: black;">
            <h4>{country_name}</h4>
            <b>Risk Durumu:</b> {risk_adi(risk)}<br>
            <b>Vaka Sayısı:</b> {bilgi["cases"]}<br>
            <b>Ölüm Sayısı:</b> {bilgi["deaths"]}<br><br>
            <b>Açıklama:</b><br>
            {bilgi["description"]}
        </div>
        """

        folium.GeoJson(
            feature,
            style_function=lambda x, renk=renk: {
                "fillColor": renk,
                "color": "white",
                "weight": 0.5,
                "fillOpacity": 0.75
            },
            highlight_function=lambda x: {
                "fillOpacity": 0.95,
                "weight": 2,
                "color": "black"
            },
            tooltip=folium.Tooltip(f"{country_name} - {risk_adi(risk)}"),
            popup=folium.Popup(popup_html, max_width=300)
        ).add_to(dunya_haritasi)

    legend_html = """
    <div style="
        position: fixed;
        bottom: 30px;
        left: 30px;
        width: 240px;
        background-color: white;
        border: 2px solid #333;
        z-index: 9999;
        font-size: 14px;
        padding: 12px;
        border-radius: 10px;
        color: black;
    ">
        <b>Hantavirüs Risk Haritası</b><br><br>
        <span style="background:#e74c3c;width:15px;height:15px;display:inline-block;"></span> Yüksek Risk<br>
        <span style="background:#f39c12;width:15px;height:15px;display:inline-block;"></span> Orta Risk<br>
        <span style="background:#2ecc71;width:15px;height:15px;display:inline-block;"></span> Düşük Risk<br>
        <span style="background:#3498db;width:15px;height:15px;display:inline-block;"></span> Risk Taşımıyor<br>
        <span style="background:#95a5a6;width:15px;height:15px;display:inline-block;"></span> Veri Yok
    </div>
    """

    dunya_haritasi.get_root().html.add_child(folium.Element(legend_html))
    harita_html = dunya_haritasi._repr_html_()

    return render_template("harita.html", harita=harita_html, hata=None)


if __name__ == "__main__":
    app.run(debug=True)
    
