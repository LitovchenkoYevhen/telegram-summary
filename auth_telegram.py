from telethon.sync import TelegramClient
from telethon.errors import SessionPasswordNeededError
from dotenv import dotenv_values
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
config = dotenv_values(".env")
API_ID = int(config['TELEGRAM_API_ID'])
API_HASH = config['TELEGRAM_API_HASH']

def auth_telegram():
    """Скрипт для первичной аутентификации в Telegram"""
    with TelegramClient('analyzer_session', API_ID, API_HASH) as client:
        if not client.is_user_authorized():
            logger.info("Authentication required")
            phone = input("Enter phone number (+375XXXXXXXXX): ").strip()
            
            try:
                logger.info("Sending confirmation code")
                client.send_code_request(phone)
                code = input("Enter Telegram code: ").strip()
                
                try:
                    client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    password = input("Enter 2FA password: ")
                    client.sign_in(password=password)
                    
                logger.info("Authentication successful")
            except Exception as e:
                logger.error(f"Authentication error: {e}")
                return False
        else:
            logger.info("Already authorized")
        return True

if __name__ == "__main__":
    auth_telegram() 