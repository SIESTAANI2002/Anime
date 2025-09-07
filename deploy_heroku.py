import requests
import time

# === CONFIG ===
HEROKU_API_KEY = "your_heroku_api_key"
HEROKU_EMAIL = "your_email@example.com"
APP_NAME = "anime-bot"  # Heroku app name (must be unique)
GITHUB_REPO = "yourusername/anime_bot"  # GitHub repo: username/repo
TELEGRAM_TOKEN = "your_telegram_token"
CHAT_ID = "@your_channel_username"

HEADERS = {
    "Accept": "application/vnd.heroku+json; version=3",
    "Authorization": f"Bearer {HEROKU_API_KEY}"
}

# === 1️⃣ Create Heroku App ===
print("Creating Heroku app...")
data = {"name": APP_NAME, "region": "us"}
res = requests.post("https://api.heroku.com/apps", headers=HEADERS, json=data)
if res.status_code == 201:
    print("App created successfully ✅")
else:
    print(res.json())

time.sleep(2)

# === 2️⃣ Set Config Vars ===
print("Setting config vars...")
config_vars = {"TELEGRAM_TOKEN": TELEGRAM_TOKEN, "CHAT_ID": CHAT_ID}
res = requests.patch(f"https://api.heroku.com/apps/{APP_NAME}/config-vars", headers=HEADERS, json=config_vars)
print("Config vars set:", res.json())

time.sleep(2)

# === 3️⃣ Deploy GitHub Repo ===
print("Starting deployment from GitHub...")
deploy_data = {
    "source_blob": {
        "url": f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip"
    }
}
res = requests.post(f"https://api.heroku.com/apps/{APP_NAME}/builds", headers=HEADERS, json=deploy_data)
if res.status_code in [201, 202]:
    print("Deployment started ✅")
else:
    print(res.json())

time.sleep(5)

# === 4️⃣ Scale Worker Dyno ===
print("Scaling worker dyno...")
scale_data = {"updates": [{"type": "worker", "quantity": 1}]}
res = requests.patch(f"https://api.heroku.com/apps/{APP_NAME}/formation", headers=HEADERS, json=scale_data)
if res.status_code == 200:
    print("Worker scaled successfully ✅")
else:
    print(res.json())

print("\nDeployment complete! Your bot should be live on Heroku.")
