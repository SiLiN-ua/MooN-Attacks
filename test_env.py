import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')
phone = os.getenv('TELEGRAM_PHONE')

print(f"API_ID: {api_id}")
print(f"API_HASH: {api_hash[:6]}..." if api_hash else "API_HASH: None")
print(f"PHONE: {phone}")
