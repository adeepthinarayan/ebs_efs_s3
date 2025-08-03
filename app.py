from flask import Flask, render_template, request
import boto3
import os
from werkzeug.utils import secure_filename
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import socket

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp'

# ---------- Load config from ENV ----------
S3_BUCKET = os.getenv('S3_BUCKET_NAME')
S3_REGION = os.getenv('S3_REGION')
EC2_PUBLIC_IP = os.getenv('EC2_PUBLIC_IP', 'localhost')  # fallback if not set
LOG_FILE_PATH = '/efs/upload_log.txt'

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'babycontest')
}

# ---------- Initialize S3 Client ----------
s3 = boto3.client('s3', region_name=S3_REGION)

def insert_to_db(baby_name, baby_age, parent_name, contact, image_url):
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO entries (baby_name, baby_age, parent_name, contact, s3_image_url)
            VALUES (%s, %s, %s, %s, %s)
        """, (baby_name, baby_age, parent_name, contact, image_url))
        connection.commit()
        cursor.close()
        connection.close()
    except Error as e:
        print("Database error:", e)

def log_upload(filename):
    timestamp = datetime.now()
    hostname = socket.gethostname()

    # Count existing entries
    if os.path.exists(LOG_FILE_PATH):
        with open(LOG_FILE_PATH, 'r') as f:
            count = sum(1 for _ in f) + 1
    else:
        count = 1

    # Construct local app URL
    local_url = f"http://{EC2_PUBLIC_IP}:5000/static/uploads/{filename}"
    log_line = f"{timestamp} - Uploaded: {count}, Image URL: {local_url}, DNS: {hostname}\n"

    with open(LOG_FILE_PATH, 'a') as log_file:
        log_file.write(log_line)

@app.route('/', methods=['GET', 'POST'])
def upload_form():
    if request.method == 'POST':
        # Get form fields
        baby_name = request.form['baby_name']
        baby_age = request.form['baby_age']
        parent_name = request.form['parent_name']
        contact = request.form['contact']
        file = request.files['baby_image']

        if file and file.filename != '':
            filename = secure_filename(file.filename)
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(local_path)

            # Upload to S3
            try:
                s3.upload_file(local_path, S3_BUCKET, filename)
                image_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{filename}"
                log_upload(filename)  # <-- Add this line
            except Exception as e:
                return f"Upload failed: {str(e)}"

            # Insert into DB
            insert_to_db(baby_name, baby_age, parent_name, contact, image_url)

            return render_template('form.html',
                                   submitted=True,
                                   baby_name=baby_name,
                                   baby_age=baby_age,
                                   parent_name=parent_name,
                                   contact=contact,
                                   image_url=image_url)

    return render_template('form.html', submitted=False)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
