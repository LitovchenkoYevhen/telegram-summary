# Добавьте эти строки в самое начало файла, сразу после импортов
print("====== Начало выполнения программы ======")

# Проверка загрузки переменных окружения
try:
    from dotenv import dotenv_values
    print("Загрузка конфигурации из .env...")
    config = dotenv_values(".env")
    print("Найденные переменные окружения:")
    for key in config:
        if key in ['TELEGRAM_API_HASH', 'OPENAI_API_KEY', 'BOT_TOKEN']:
            print(f"{key}: {'[УСТАНОВЛЕН]' if config[key] else '[ОТСУТСТВУЕТ]'}")
        else:
            print(f"{key}: {config[key]}")
except Exception as e:
    print(f"❌ Ошибка при загрузке .env: {e}")
    exit(1)

# Проверка импортов
try:
    print("\nПроверка необходимых импортов...")
    import telethon
    print("✓ telethon импортирован успешно")
    import telegram
    print("✓ python-telegram-bot импортирован успешно")
    import openai
    print("✓ openai импортирован успешно")
    import schedule
    print("✓ schedule импортирован успешно")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Выполните: pip install -r requirements.txt")
    exit(1)

from telethon import TelegramClient
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from telegram import Update
from datetime import datetime, timedelta
import os
from openai import OpenAI
import time
import threading
import json
import getpass
import asyncio
import logging
import nest_asyncio
from telethon.tl.functions.channels import GetForumTopicsRequest

# Включаем поддержку вложенных event loops
nest_asyncio.apply()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
print("====== Начало выполнения программы ======")
print("Загрузка конфигурации из .env...")
config = dotenv_values(".env")

# Конфигурация
API_ID = int(config['TELEGRAM_API_ID'])
API_HASH = config['TELEGRAM_API_HASH']
OPENAI_API_KEY = config['OPENAI_API_KEY']
BOT_TOKEN = config['BOT_TOKEN']
TARGET_GROUP_LINK = config['TARGET_GROUP_LINK']

# Структура чатов для анализа
CHATS_CONFIG = {
    2278307897: {'topic_ids': [1, 2]},
    2295058026: {'topic_ids': [1, 272, 2, 8, 294, 4]}
}

# Глобальный клиент Telethon
telethon_client = None

async def init_telethon():
    """Асинхронная инициализация Telethon клиента"""
    global telethon_client
    telethon_client = TelegramClient('analyzer_session', API_ID, API_HASH)
    await telethon_client.start()
    return telethon_client

async def analyze_messages(messages, chat_title, topic_name, is_full_analysis=False):
    logger.info(f"Analyzing {'full history' if is_full_analysis else 'daily'} for {chat_title} - {topic_name}")
    
    summary_type = "полная история" if is_full_analysis else "последние 24 часа"
    header = f"📊 {chat_title}\n💬 {topic_name}\n📅 {summary_type}\n\n"
    
    if not messages:
        return None
        
    messages_text = []
    for message in messages:
        if message.message:
            messages_text.append(message.message)
        if message.media:
            messages_text.append("[медиа-файл]")
    
    if not messages_text:
        return None
        
    combined_text = "\n".join(messages_text)
    
    client = OpenAI(api_key=config['OPENAI_API_KEY'])
    
    prompt = f"""
    Read these chat messages and tell me what happened there.
    Focus on events, decisions, and key points of discussions.
    Keep all topics but explain them briefly.
    Write in Russian, in a clear narrative style.
    
    Messages:
    {combined_text}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that explains chat discussions in Russian"},
                {"role": "user", "content": prompt}
            ]
        )
        summary = response.choices[0].message.content
        return f"{header}{summary}"
        
    except Exception as e:
        logger.error(f"Error during OpenAI API call: {e}")
        return None

async def run_analysis(is_full_analysis=False):
    """Асинхронный анализ чатов"""
    global telethon_client
    logger.info(f"Starting {'full' if is_full_analysis else 'daily'} analysis")
    
    try:
        target_group = await telethon_client.get_entity(TARGET_GROUP_LINK)
        logger.info(f"Target group obtained: {target_group.title}")
        
        for chat_id, config in CHATS_CONFIG.items():
            try:
                chat = await telethon_client.get_entity(chat_id)
                logger.info(f"Analyzing chat: {chat.title}")
                
                forum_topics = await telethon_client(GetForumTopicsRequest(
                    channel=chat,
                    offset_date=0,
                    offset_id=0,
                    offset_topic=0,
                    limit=100
                ))
                
                topics_dict = {topic.id: topic.title for topic in forum_topics.topics}
                logger.info(f"Found topics: {topics_dict}")
                
                for topic_id in config['topic_ids']:
                    try:
                        topic_name = topics_dict.get(topic_id, f"Topic {topic_id}")
                        logger.info(f"Analyzing topic: {topic_name}")
                        
                        messages = await telethon_client.get_messages(
                            chat,
                            limit=100 if not is_full_analysis else None,
                            reply_to=topic_id
                        )
                        
                        if messages:
                            summary = await analyze_messages(messages, chat.title, topic_name, is_full_analysis)
                            if summary:
                                await telethon_client.send_message(target_group, summary)
                                logger.info(f"Analysis sent for topic: {topic_name}")
                                
                    except Exception as e:
                        error_msg = f"Error analyzing topic {topic_id}: {str(e)}"
                        logger.error(error_msg)
                        
            except Exception as e:
                error_msg = f"Error analyzing chat {chat_id}: {str(e)}"
                logger.error(error_msg)
                
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise

async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логирование всех входящих сообщений"""
    user = update.effective_user
    message = update.message.text
    print(f"\n====== Новое сообщение ======")
    print(f"От пользователя: {user.id} ({user.username})")
    print(f"Текст сообщения: {message}")
    print("============================\n")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    logger.info(f"Start command from user: {update.effective_user.id} ({update.effective_user.username})")
    await update.message.reply_text("Starting daily chat analysis...")
    try:
        await run_analysis(is_full_analysis=False)
        await update.message.reply_text("Analysis completed successfully!")
    except Exception as e:
        await update.message.reply_text(f"Analysis error: {str(e)}")

async def full_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /full_analyze"""
    logger.info(f"Full analyze command from user: {update.effective_user.id} ({update.effective_user.username})")
    await update.message.reply_text("Starting full history analysis...")
    try:
        await run_analysis(is_full_analysis=True)
        await update.message.reply_text("Full analysis completed successfully!")
    except Exception as e:
        await update.message.reply_text(f"Analysis error: {str(e)}")

def run_scheduler():
    """Функция для запуска планировщика"""
    schedule.every().day.at("09:00").do(run_analysis, False)
    while True:
        schedule.run_pending()
        time.sleep(60)

async def check_auth():
    """Проверка авторизации"""
    try:
        client = TelegramClient('analyzer_session', API_ID, API_HASH)
        await client.connect()
        is_authorized = await client.is_user_authorized()
        await client.disconnect()
        return is_authorized
    except Exception as e:
        print(f"Ошибка при проверке авторизации: {e}")
        return False

def main():
    """Основная функция"""
    logger.info("Initializing application")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_telethon())
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Добавляем обраотчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("full_analyze", full_analyze))
    
    logger.info("Bot started and ready")
    print("\n====== Бот запущен и готов к работе! ======")
    print("Доступные команды:")
    print("/start - запуск ежедневного анализа")
    print("/full_analyze - запуск полного анализа")
    print("=========================================\n")
    
    application.run_polling()

if __name__ == '__main__':
    main() 