from flask import Flask, render_template, request, redirect, url_for, send_file
import mysql.connector
from mysql.connector import errorcode
import pandas as pd
from docx import Document
from pptx import Presentation
from pptx.util import Inches
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime

app = Flask(__name__)

# Configuração do banco de dados
db_config = {
    'user': 'root',
    'password': '',
    'host': 'localhost',
    'database': 'tca'
}

try:
    db = mysql.connector.connect(**db_config)
except mysql.connector.Error as err:
    if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        print("Something is wrong with your user name or password")
    elif err.errno == errorcode.ER_BAD_DB_ERROR:
        print("Database does not exist")
    else:
        print(err)
    exit()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/shorten_url", methods=["POST"])
def shorten_url():
    original_url = request.form["original_url"]
    short_code = "WebEncurt_" + original_url[:4]  # Ajusta o código curto

    cursor = db.cursor()
    try:
        cursor.execute("INSERT INTO urls (original_url, short_code) VALUES (%s, %s)", (original_url, short_code))
        db.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        cursor.close()

    return redirect(url_for("index"))

@app.route("/urls")
def show_urls():
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM urls")
    urls = cursor.fetchall()
    cursor.close()
    return render_template("urls.html", urls=urls)

@app.route("/charts")
def charts():
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT short_code, original_url, click_count, created_at, last_click_at, last_click_ip FROM urls")
    urls = cursor.fetchall()
    cursor.close()

    # Prepare data for charts
    url_data = {
        'Short Codes': [url['short_code'] for url in urls],
        'Original URLs': [url['original_url'] for url in urls],
        'Clicks': [url['click_count'] for url in urls],
        'Created At': [url['created_at'].strftime('%Y-%m-%d') for url in urls],
        'Last Click At': [url['last_click_at'].strftime('%Y-%m-%d %H:%M:%S') if url['last_click_at'] else 'Never' for url in urls],
        'Last Click IP': [url['last_click_ip'] if url['last_click_ip'] else 'N/A' for url in urls]
    }

    # Generate chart
    fig, ax = plt.subplots()
    ax.bar(url_data['Short Codes'], url_data['Clicks'])
    ax.set_xlabel('Short Codes')
    ax.set_ylabel('Click Count')
    ax.set_title('URL Clicks')
    plt.xticks(rotation=45, ha='right')

    # Save the plot to a BytesIO object
    img_stream = io.BytesIO()
    plt.savefig(img_stream, format='png')
    img_stream.seek(0)
    plt.close(fig)

    # Convert image to base64
    img_base64 = base64.b64encode(img_stream.getvalue()).decode('utf-8')

    return render_template("charts.html", url_data=url_data, chart_img=img_base64)

@app.route("/download/<file_type>")
def download_report(file_type):
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT short_code, original_url, click_count, created_at, last_click_at, last_click_ip FROM urls")
    urls = cursor.fetchall()
    cursor.close()

    if file_type == 'docx':
        doc = Document()
        doc.add_heading('URL Report', 0)
        
        for url in urls:
            doc.add_heading(f"Short Code: {url['short_code']}", level=1)
            doc.add_paragraph(f"Original URL: {url['original_url']}")
            doc.add_paragraph(f"Clicks: {url['click_count']}")
            doc.add_paragraph(f"Created At: {url['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")
            doc.add_paragraph(f"Last Click At: {url['last_click_at'].strftime('%Y-%m-%d %H:%M:%S') if url['last_click_at'] else 'Never'}")
            doc.add_paragraph(f"Last Click IP: {url['last_click_ip'] if url['last_click_ip'] else 'N/A'}")
            doc.add_paragraph()  # Blank line between entries

        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        return send_file(file_stream, as_attachment=True, download_name="report.docx", mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    elif file_type == 'pptx':
        prs = Presentation()
        
        for url in urls:
            slide = prs.slides.add_slide(prs.slide_layouts[5])  # Layout with Title and Content
            title = slide.shapes.title
            title.text = f"Short Code: {url['short_code']}"
            
            content = slide.shapes.add_textbox(Inches(1), Inches(1.5), Inches(8), Inches(4))
            text_frame = content.text_frame
            p = text_frame.add_paragraph()
            p.text = (
                f"Original URL: {url['original_url']}\n"
                f"Clicks: {url['click_count']}\n"
                f"Created At: {url['created_at'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Last Click At: {url['last_click_at'].strftime('%Y-%m-%d %H:%M:%S') if url['last_click_at'] else 'Never'}\n"
                f"Last Click IP: {url['last_click_ip'] if url['last_click_ip'] else 'N/A'}"
            )

            # Add Chart
            fig, ax = plt.subplots()
            ax.bar([url['short_code']], [url['click_count']])
            ax.set_xlabel('URLs')
            ax.set_ylabel('Click Count')
            ax.set_title('URL Clicks')
            plt.xticks(rotation=45, ha='right')

            chart_stream = io.BytesIO()
            plt.savefig(chart_stream, format='png')
            chart_stream.seek(0)
            plt.close(fig)

            img_stream = io.BytesIO(chart_stream.read())
            chart_stream.close()
            
            slide.shapes.add_picture(img_stream, Inches(1), Inches(2.5), Inches(8), Inches(4))
        
        file_stream = io.BytesIO()
        prs.save(file_stream)
        file_stream.seek(0)
        return send_file(file_stream, as_attachment=True, download_name="report.pptx", mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation")

    elif file_type == 'xlsx':
        df = pd.DataFrame(urls)
        file_stream = io.BytesIO()
        with pd.ExcelWriter(file_stream, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='URLs', index=False)
        file_stream.seek(0)
        return send_file(file_stream, as_attachment=True, download_name="report.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return "Invalid file type", 400

if __name__ == "__main__":
    app.run(debug=True)
