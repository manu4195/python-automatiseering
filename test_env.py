import os
from dotenv import load_dotenv

# Volledig pad naar jouw .env
dotenv_path = r"C:\Users\darle\Desktop\coding\pythonScrape\.env"
load_dotenv(dotenv_path=dotenv_path)

print("OSIRIS_USER:", os.getenv("OSIRIS_USER"))
print("OSIRIS_PASS:", os.getenv("OSIRIS_PASS"))
print("DISCORD_WEBHOOK:", os.getenv("DISCORD_WEBHOOK"))
