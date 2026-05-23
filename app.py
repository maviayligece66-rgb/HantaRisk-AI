from flask import Flask, render_template, request, jsonify
import folium
import os
import json
import pandas as pd

app = Flask(__name__)

base = os.path.dirname(os.path.abspath(__file__))

geojson_yolu = os.path.join(base, "datasets", "world.geojson")
risk_csv_yolu = os.path.join(base, "datasets", "hanta_risk.csv")


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


# Çok yönlü görsel analiz sistemi için API Rotası
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

    mock_response = {
        "status": "success",
        "meta": {
            "detected_object": "Geyik Faresi (Peromyscus maniculatus)",
            "category": "Canlı / Kemirgen",
            "confidence_score": 0.94
        },
        "hantavirus_risk": {
            "has_risk": True,
            "risk_level": "Yüksek Risk",
            "description": "Analiz edilen görselde hantavirüs taşıma potansiyeli olan kemirgen türü tespit edilmiştir."
        },
        "other_health_risks": [
            {
                "disease_name": "Lyme Hastalığı",
                "risk_factor": "Orta Risk",
                "note": "Bu kemirgen türü, bazı keneler için konak olabilir."
            },
            {
                "disease_name": "Leptospiroz",
                "risk_factor": "Yüksek Risk",
                "note": "Kemirgen idrarı ile temas edilen yüzeylerden bulaşma riski bulunabilir."
            }
        ],
        "recommendations": [
            "Görseldeki canlıyla veya bulunduğu ortamla doğrudan temas kurmayın.",
            "Şüpheli alanı temizlerken maske ve eldiven kullanın.",
            "Kuru süpürme yerine ıslak dezenfeksiyon yöntemi tercih edin.",
            "Olası temas, ısırık veya belirti durumunda sağlık kuruluşuna başvurun."
        ]
    }

    return jsonify(mock_response)


def risk_rengi(risk):
    risk = str(risk).lower().strip()

    if risk == "high":
        return "#e74c3c"      # kırmızı
    elif risk == "medium":
        return "#f39c12"      # turuncu
    elif risk == "low":
        return "#2ecc71"      # yeşil
    elif risk == "no_risk":
        return "#3498db"      # mavi
    else:
        return "#95a5a6"      # gri


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
    dunya_haritasi = folium.Map(
        location=[20, 0],
        zoom_start=2,
        tiles="cartodbpositron"
    )

    if not os.path.exists(geojson_yolu):
        return "world.geojson dosyası bulunamadı. Lütfen datasets klasörüne ekleyin."

    if not os.path.exists(risk_csv_yolu):
        return "hanta_risk.csv dosyası bulunamadı. Lütfen datasets klasörüne ekleyin."

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

    return render_template("harita.html", harita=harita_html)


if __name__ == "__main__":
    app.run(debug=True)