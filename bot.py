import os
import requests
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import time
import json
import threading
import subprocess

# === CONFIG ===
DOWNLOAD_FOLDER = "downloads"
ENCODED_FOLDER = "encoded"
TRACK_FILE = "downloaded.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(ENCODED_FOLDER, exist_ok=True)

bot = Bot(token=TELEGRAM_TOKEN)
API_URL = "https://subsplease.org/api/?f=latest&tz=UTC"

# === Load tracked episodes ===
if os.path.exists(TRACK_FILE):
    with open(TRACK_FILE, "r") as f:
        downloaded_episodes = set(json.load(f))
else:
    downloaded_episodes = set()

def save_tracked():
    with open(TRACK_FILE, "w") as f:
        json.dump(list(downloaded_episodes), f)

# === Get releases from SubsPlease API ===
def get_recent_releases():
    releases = []
    try:
        res = requests.get(API_URL, timeout=15).json()
        for ep in res.get("data", []):
            title = ep["release_title"]
            link = ep["link"]
            releases.append((title, link))
    except Exception as e:
        print("Error fetching releases:", e)
    return releases

def download_file(url, output_path):
    r = requests.get(url, stream=True)
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return output_path

# === Encoding Function ===
def encode_video(input_path, output_path, progress_callback=None):
    import json

    ext = os.path.splitext(input_path)[1].lower()
    output_path = os.path.splitext(output_path)[0] + ext

    # Detect audio streams
    probe_cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index,codec_name",
        "-of", "json", input_path
    ]
    result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    audio_info = json.loads(result.stdout).get("streams", [])

    command = [
        "ffmpeg", "-i", input_path,
        "-vf", "scale=-1:720",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:s", "copy"
    ]

    for stream in audio_info:
        idx = stream["index"]
        codec = stream["codec_name"].lower()
        if codec == "aac":
            command += [f"-c:a:{idx}", "aac", f"-b:a:{idx}", "128k"]
        elif codec == "opus":
            command += [f"-c:a:{idx}", "libopus", f"-b:a:{idx}", "128k"]
        elif codec == "mp3":
            command += [f"-c:a:{idx}", "libmp3lame", f"-b:a:{idx}", "128k"]
        elif codec == "flac":
            command += [f"-c:a:{idx}", "flac"]  # lossless, no bitrate limit
        else:
            command += [f"-c:a:{idx}", "aac", f"-b:a:{idx}", "128k"]

    command += ["-y", output_path]

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        if progress_callback and ("frame=" in line or "time=" in line):
            progress_callback(line.strip())
    process.wait()
    return output_path

def send_to_telegram(video_path):
    with open(video_path, "rb") as f:
        bot.send_document(chat_id=CHAT_ID, document=f)

def cleanup(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)

# === Auto Mode (background) ===
def auto_mode():
    while True:
        try:
            recent_releases = get_recent_releases()
            for title, url in recent_releases:
                if url not in downloaded_episodes:
                    print(f"⬇️ Downloading {title}")
                    file_path = os.path.join(DOWNLOAD_FOLDER, title + os.path.splitext(url)[1])
                    download_file(url, file_path)

                    print(f"⚙️ Encoding {title}...")
                    output_file = os.path.join(ENCODED_FOLDER, os.path.basename(file_path))
                    encode_video(file_path, output_file)

                    print(f"📤 Uploading {title}...")
                    send_to_telegram(output_file)

                    cleanup(file_path)
                    cleanup(output_file)

                    downloaded_episodes.add(url)
                    save_tracked()
                    print(f"✅ Done {title}\n")

            print("Sleeping 1 hour...\n")
            time.sleep(3600)

        except Exception as e:
            print("Error:", e)
            time.sleep(600)

# === Manual Mode ===
pending_videos = {}

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 I auto-download SubsPlease releases & also encode your uploaded videos.\nSend a video, then use /encode <filename>.")

def handle_video(update: Update, context: CallbackContext):
    video = update.message.video or update.message.document
    if not video:
        update.message.reply_text("Send a video file.")
        return

    file_id = video.file_id
    file_name = video.file_name if hasattr(video, "file_name") else f"{file_id}.mp4"
    file_path = os.path.join(DOWNLOAD_FOLDER, file_name)

    update.message.reply_text(f"⬇️ Downloading {file_name}...")
    new_file = bot.get_file(file_id)
    new_file.download(custom_path=file_path)

    pending_videos[file_name] = file_path
    update.message.reply_text(f"✅ {file_name} ready.\nUse /encode {file_name}")

def encode_command(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        update.message.reply_text("Usage: /encode <filename>")
        return

    filename = context.args[0]
    if filename not in pending_videos:
        update.message.reply_text("⚠️ File not found.")
        return

    input_path = pending_videos[filename]
    output_path = os.path.join(ENCODED_FOLDER, filename)
    update.message.reply_text(f"⚙️ Encoding {filename}...")

    def progress(line):
        try:
            update.message.reply_text(f"📊 {line}")
        except:
            pass

    encode_video(input_path, output_path, progress_callback=progress)
    update.message.reply_text(f"✅ Done {filename}")

    with open(output_path, "rb") as f:
        update.message.reply_document(f)

    cleanup(input_path)
    cleanup(output_path)
    pending_videos.pop(filename, None)

# === Main ===
def main():
    threading.Thread(target=auto_mode, daemon=True).start()

    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("encode", encode_command))
    dp.add_handler(MessageHandler(Filters.video | Filters.document, handle_video))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
