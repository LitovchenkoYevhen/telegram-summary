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

async def analyze_messages(messages, chat_title, topic_title=None, is_full_analysis=False):
    """Анализ сообщений"""
    if not messages:
        return None
        
    messages_text = "\n".join([
        f"[{msg.date}] {msg.sender.first_name if msg.sender else 'Unknown'}: {msg.text}"
        for msg in messages if msg.text
    ])
    
    if not messages_text.strip():
        return None
    
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    
    system_prompt = f"""Создайте краткую сводку обсуждения из топика '{topic_title}'. 
    {'Это полный анализ истории обсуждения.' if is_full_analysis else 'Это анализ за последние 24 часа.'}
    Включите: основные темы, принятые решения, важные моменты."""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": system_prompt
            }, {
                "role": "user",
                "content": f"Проанализируйте следующую беседу:\n{messages_text}"
            }]
        )
        
        summary = response.choices[0].message.content
        report = f"""
📊 {'Полный анализ' if is_full_analysis else 'Ежедневная сводка'}
📅 Дата: {datetime.now().strftime('%Y-%m-%d')}
💬 Группа: {chat_title}
📌 Топик: {topic_title}

{summary}
{'=' * 50}
"""
        return report
    except Exception as e:
        print(f"Ошибка при анализе сообщений: {e}")
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
                # Пробуем получить чат через get_input_entity
                try:
                    chat = await telethon_client.get_input_entity(chat_id)
                except ValueError:
                    # Если не получилось, пробуем через диалоги
                    async for dialog in telethon_client.iter_dialogs():
                        if dialog.id == chat_id:
                            chat = dialog.entity
                            break
                    else:
                        raise ValueError(f"Chat {chat_id} not found in dialogs")
                
                logger.info(f"Analyzing chat: {chat_id}")
                chat_title = chat.title
                print(f"Анализ группы: {chat_title}")
                
                for topic_id in config['topic_ids']:
                    try:
                        print(f"Анализ топика {topic_id}")
                        if is_full_analysis:
                            messages = await telethon_client.get_messages(chat, limit=None, reply_to=topic_id)
                        else:
                            messages = await telethon_client.get_messages(
                                chat,
                                limit=100,
                                reply_to=topic_id,
                                offset_date=datetime.now() - timedelta(days=1)
                            )
                        
                        if messages:
                            summary = await analyze_messages(messages, chat_title, f"Топик {topic_id}", is_full_analysis)
                            if summary:
                                await telethon_client.send_message(target_group, summary)
                                print(f"Отправлен анализ топика {topic_id}")
                    
                    except Exception as e:
                        error_msg = f"Ошибка при анализе топика {topic_id}: {str(e)}"
                        print(error_msg)
                        await telethon_client.send_message(target_group, error_msg)
                        
            except Exception as e:
                error_msg = f"Ошибка при анализе чата {chat_id}: {str(e)}"
                print(error_msg)
                await telethon_client.send_message(target_group, error_msg)
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
    
    # Инициализируем Telethon клиент в отдельном event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_telethon())
    
    # Настройка бота
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("full_analyze", full_analyze))
    
    logger.info("Bot started and ready")
    print("\n====== Бот запущен и готов к работе! ======")
    print("Доступные команды:")
    print("/start - запуск ежедневного анализа")
    print("/full_analyze - запуск полного анализа")
    print("=========================================\n")
    
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main() 