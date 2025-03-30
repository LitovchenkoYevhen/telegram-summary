"""
Скрипт для проверки окружения и настроек
"""
import sys
import os
from dotenv import load_dotenv
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info("Checking environment and settings")
logger.info(f"Python version: {sys.version}")

logger.info("Checking required packages:")
packages = ['telethon', 'telegram', 'openai', 'python-dotenv', 'schedule']
for package in packages:
    try:
        __import__(package)
        logger.info(f"✓ {package} installed")
    except ImportError:
        logger.error(f"✗ {package} NOT installed")

logger.info("Checking .env file:")
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    logger.info(f"✓ .env file found: {env_path}")
    load_dotenv(env_path)
    
    required_vars = [
        'TELEGRAM_API_ID',
        'TELEGRAM_API_HASH',
        'OPENAI_API_KEY',
        'BOT_TOKEN',
        'TARGET_GROUP_LINK'
    ]
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            logger.info(f"✓ {var}: set")
        else:
            logger.error(f"✗ {var}: missing")
else:
    logger.error(f"✗ .env file not found")

logger.info("Check completed") 