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

from telethon import TelegramClient, functions, types
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

async def analyze_messages(messages, chat_title, topic_name, is_full_analysis=False, mode="retell", user_id=None):
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
    Make a brief summary of the following chat messages.
    Include all important information but make it concise.
    Don't skip any topics or decisions, just make them shorter.
    Don't evaluate or prioritize information - include everything in a brief form.
    
    Format the response in clear sections:
    1. Start with key points and decisions if any
    2. Group related topics together
    3. Use bullet points for listing items
    4. Add line breaks between different topics
    5. Use markdown formatting:
       - **bold** for important terms
       - • for bullet points
       - Add empty line between paragraphs
    
    The response should be in Russian.
    
    Messages:
    {combined_text}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that formats summaries in clear, structured text with markdown"},
                {"role": "user", "content": prompt}
            ]
        )
        summary = response.choices[0].message.content
        
        # Добавляем разделитель после заголовка
        formatted_summary = f"{header}{'─' * 30}\n\n{summary}\n\n{'─' * 30}"
        return formatted_summary
        
    except Exception as e:
        logger.error(f"Error during OpenAI API call: {e}")
        return None

async def run_analysis(*, is_full_analysis=False, mode="retell", user_id=None, context=None, update=None):
    global telethon_client
    logger.info(f"Starting {'full' if is_full_analysis else 'daily'} analysis")
    
    try:
        for chat_id, config in CHATS_CONFIG.items():
            try:
                chat = await telethon_client.get_entity(chat_id)
                logger.info(f"Analyzing chat: {chat.title}")
                
                forum_topics = await telethon_client(functions.channels.GetForumTopicsRequest(
                    channel=chat,
                    offset_date=0,
                    offset_id=0,
                    offset_topic=0,
                    limit=100
                ))
                
                topics_dict = {topic.id: topic.title for topic in forum_topics.topics}
                
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
                            summary = await analyze_messages(messages, chat.title, topic_name, is_full_analysis, mode, user_id)
                            if summary and context and update:
                                await context.bot.send_message(
                                    chat_id=update.effective_chat.id,
                                    text=summary
                                )
                                logger.info(f"Analysis sent to user chat: {topic_name}")
                                
                    except Exception as e:
                        error_msg = f"Error analyzing topic {topic_id}: {str(e)}"
                        logger.error(error_msg)
                        if context and update:
                            await context.bot.send_message(
                                chat_id=update.effective_chat.id,
                                text=error_msg
                            )
                        
            except Exception as e:
                error_msg = f"Error analyzing chat {chat_id}: {str(e)}"
                logger.error(error_msg)
                if context and update:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=error_msg
                    )
                
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
    user_id = update.effective_user.id
    logger.info(f"Start command from user: {user_id} ({update.effective_user.username})")
    
    mode = "describe"
    if context.args and context.args[0] in ["retell", "describe"]:
        mode = context.args[0]
    
    await update.message.reply_text("Starting daily chat analysis...")
    try:
        await run_analysis(
            is_full_analysis=False,
            mode=mode,
            user_id=user_id,
            context=context,
            update=update
        )
        await update.message.reply_text("Analysis completed successfully!")
    except Exception as e:
        await update.message.reply_text(f"Analysis error: {str(e)}")

async def full_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Full analyze command from user: {user_id} ({update.effective_user.username})")
    
    mode = "describe"
    if context.args and context.args[0] in ["retell", "describe"]:
        mode = context.args[0]
    
    await update.message.reply_text("Starting full history analysis...")
    try:
        await run_analysis(
            is_full_analysis=True,
            mode=mode,
            user_id=user_id,
            context=context,
            update=update
        )
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
    logger.info("Initializing application")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_telethon())
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("full_analyze", full_analyze))
    
    logger.info("\n" + "="*40)
    logger.info("Бот запущен и готов к работе!")
    logger.info("Доступные команды:")
    logger.info("/start - запуск ежедневного анализа")
    logger.info("/start describe - ежедневный анализ в формате описания")
    logger.info("/start retell - ежедневный анализ в формате пересказа")
    logger.info("/full_analyze - запуск полного анализа истории")
    logger.info("/full_analyze describe - полный анализ в формате описания")
    logger.info("/full_analyze retell - полный анализ в формате пересказа")
    logger.info("Цитирование - отправьте сообщение с текстом в кавычках для уточнения деталей")
    logger.info("Пример: Что имелось в виду под \"проблема с Docker\"?")
    logger.info("="*40 + "\n")
    
    application.run_polling()

if __name__ == '__main__':
    main() 