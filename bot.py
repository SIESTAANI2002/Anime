import os
import subprocess
import requests
from bs4 import BeautifulSoup
from telegram import Bot
import time
import json

# === CONFIG ===
DOWNLOAD_FOLDER = "downloads"
ENCODED_FOLDER = "encoded"
TRACK_FILE = "downloaded.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(ENCODED_FOLDER, exist_ok=True)

bot = Bot(token=TELEGRAM_TOKEN)
BASE_URL = "https://subsplease.org/"

# === Load tracked episodes ===
if os.path.exists(TRACK_FILE):
    with open(TRACK_FILE, "r") as f:
        downloaded_episodes = set(json.load(f))
else:
    downloaded_episodes = set()

def save_tracked():
    with open(TRACK_FILE, "w") as f:
        json.dump(list(downloaded_episodes), f)

# === Get all recent releases from SubsPlease ===
def get_recent_releases():
    releases = []
    try:
        res = requests.get(BASE_URL, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        for link in soup.find_all("a"):
            href = link.get("href", "")
            if "magnet:" in href:
                releases.append(href)
    except Exception as e:
        print("Error fetching recent releases:", e)
    return releases

# === Download via aria2c ===
def download_magnet(magnet_link):
    command = ["aria2c", "-d", DOWNLOAD_FOLDER, magnet_link, "--max-connection-per-server=4"]
    subprocess.run(command)

# === Encode video to 720p ===
def encode_video(input_path):
    filename = os.path.basename(input_path)
    output_path = os.path.join(ENCODED_FOLDER, filename)
    command = [
        "ffmpeg",
        "-i", input_path,
        "-vf", "scale=-1:720",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-y",
        output_path
    ]
    subprocess.run(command)
    return output_path

# === Send video to Telegram ===
def send_to_telegram(video_path):
    with open(video_path, "rb") as f:
        bot.send_video(chat_id=CHAT_ID, video=f)

# === Delete local files ===
def cleanup(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)

# === MAIN LOOP ===
while True:
    try:
        recent_magnets = get_recent_releases()
        for magnet in recent_magnets:
            if magnet not in downloaded_episodes:
                print("New episode found! Downloading...")
                download_magnet(magnet)

                files = os.listdir(DOWNLOAD_FOLDER)
                files.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_FOLDER, x)))
                latest_file = os.path.join(DOWNLOAD_FOLDER, files[-1])

                print(f"Encoding {latest_file} to 720p...")
                encoded_file = encode_video(latest_file)

                print(f"Uploading {encoded_file} to Telegram...")
                send_to_telegram(encoded_file)

                cleanup(latest_file)
                cleanup(encoded_file)

                downloaded_episodes.add(magnet)
                save_tracked()
                print("Episode processed successfully ✅\n")

        print("Waiting 1 hour before next check...\n")
        time.sleep(3600)

    except Exception as e:
        print("Error:", e)
        time.sleep(600)
