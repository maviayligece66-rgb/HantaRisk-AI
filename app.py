from flask import Flask, render_template, request, jsonify
import folium
import os
import json
import pandas as pd
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

base = os.path.dirname(os.path.abspath(__file__))

geojson_yolu = os.path.join(base, "datasets", "world.geojson")
risk_csv_yolu = os.path.join(base, "datasets", "hanta_risk.csv")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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
    return render_template("gorsel.html")


def ai_gorsel_analiz(file):
    image_bytes = file.read()
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    mime_type = file.mimetype or "image/jpeg"
    image_data_url = f"data:{mime_type};base64,{encoded_image}"

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

Sadece geçerli JSON döndür. Açıklama yazma.

JSON formatı:
{
  "status": "success",
  "meta": {
    "detected_object": "",
    "category": "",
    "confidence_score": 0.0
  },
  "hantavirus_risk": {
    "has_risk": true,
    "risk_level": "Düşük Risk / Orta Risk / Yüksek Risk",
    "description": ""
  },
  "other_health_risks": [
    {
      "disease_name": "",
      "risk_factor": "",
      "note": ""
    }
  ],
  "recommendations": []
}
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_data_url}
                ]
            }
        ]
    )

    text = response.output_text.strip()

    try:
        return json.loads(text)
    except Exception:
        return {
            "status": "success",
            "meta": {
                "detected_object": "Görsel analiz edildi",
                "category": "AI Görsel Yorumu",
                "confidence_score": 0.70
            },
            "hantavirus_risk": {
                "has_risk": False,
                "risk_level": "Düşük Risk",
                "description": text
            },
            "other_health_risks": [],
            "recommendations": [
                "Görselde riskli bir canlı veya ortam varsa doğrudan temas etmeyin.",
                "Kemirgen izi görülen alanlarda maske ve eldiven kullanın.",
                "Şüpheli temas durumunda sağlık kuruluşuna başvurun."
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

    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({
            "status": "error",
            "message": "OPENAI_API_KEY bulunamadı. Lütfen .env dosyasına API anahtarını ekleyin."
        }), 500

    try:
        sonuc = ai_gorsel_analiz(file)
        return jsonify(sonuc)

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Görsel analiz sırasında hata oluştu: {str(e)}"
        }), 500


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
            props.get("ADMIN")
            or props.get("NAME")
            or props.get("name")
            or props.get("Country")
            or props.get("country")
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
        <div style="font-family: Arial; width: 250px;">
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
            tooltip=folium.Tooltip(
                f"{country_name} - {risk_adi(risk)}"
            ),
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

        <span style="background:#e74c3c;width:15px;height:15px;display:inline-block;"></span>
        Yüksek Risk<br>

        <span style="background:#f39c12;width:15px;height:15px;display:inline-block;"></span>
        Orta Risk<br>

        <span style="background:#2ecc71;width:15px;height:15px;display:inline-block;"></span>
        Düşük Risk<br>

        <span style="background:#3498db;width:15px;height:15px;display:inline-block;"></span>
        Risk Taşımıyor<br>

        <span style="background:#95a5a6;width:15px;height:15px;display:inline-block;"></span>
        Veri Yok
    </div>
    """

    dunya_haritasi.get_root().html.add_child(folium.Element(legend_html))

    harita_html = dunya_haritasi._repr_html_()

    return render_template("harita.html", harita=harita_html, hata=None)


if __name__ == "__main__":
    app.run(debug=True)
