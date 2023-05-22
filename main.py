import os
import base64
import email
import re
import time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from apiclient.discovery import build
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from google_auth_oauthlib.flow import InstalledAppFlow
import sqlite3

# Настройки Google API
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
creds = None
if os.path.exists('token.json'):
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as token:
        token.write(creds.to_json())

# Настройки Telegram бота
TELEGRAM_TOKEN = '6289852678:AAF491uAPXA1O97JG0UxDLNqzOoQ7k5Zppg'
telegram_bot = Updater(token=TELEGRAM_TOKEN, use_context=True)

# Создаем базу данных и таблицу для хранения адресатов
conn = sqlite3.connect('emails.db',check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS emails
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  email TEXT)''')

# Функция, которая ищет новые письма от указанного адресата
def check_email_updates(update, context):
    service = build('gmail', 'v1', credentials=creds)
    user_profile = service.users().getProfile(userId='me').execute()
    user_email = user_profile['emailAddress']
    for user_id, email in cursor.execute('SELECT user_id, email FROM emails'):
        result = service.users().messages().list(userId='me', q=f'from:{email} is:unread').execute()
        messages = result.get('messages', [])
        if not messages:
            continue
        for message in reversed(messages):  # Читаем сообщения в порядке, обратном их получению
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            snippet = msg['snippet']
            message_text = None
            payload = msg['payload']
            headers = payload['headers']
            for header in headers:
                if header['name'] == 'From':
                    sender = header['value']
                elif header['name'] == 'Subject':
                    subject = header['value']
                elif header['name'] == 'Date':
                    sent_at = header['value']
                elif header['name'] == 'Message-ID':
                    message_id = header['value']
            if 'parts' in payload:
                parts = payload['parts']
                for part in parts:
                    part_headers = part['headers']
                    part_type = part['mimeType']
                    if part_type == 'text/plain':
                        part_data = part['body']['data']
                        message_text = base64.urlsafe_b64decode(part_data).decode()
                    elif part_type == 'text/html':
                        continue
            elif 'data' in payload['body']:
                part_data = payload['body']['data']
                message_text = base64.urlsafe_b64decode(part_data).decode()
            if message_text:
                # Здесь можно проверить содержание сообщения на наличие ключевых слов, чтобы не уведомлять о ненужных письмах
                telegram_message = f'У вас новое сообщение от {sender}: {snippet}'
                context.bot.send_message(chat_id=update.message.chat_id, text=telegram_message)

# Команда для добавления адресата
def add_email_start(telegram_bot, update):
    telegram_bot.message.reply_text('Введите адрес электронной почты, от которого вы хотите получать уведомления:')
    # Добавляем хэндлер для обработки ответа пользователя
    return 'add-email'

def add_email(telegram_bot, update):
    user_id = telegram_bot.message.chat_id
    email = telegram_bot.message.text
    cursor.execute('INSERT INTO emails (user_id, email) VALUES (?, ?)', (user_id, email))
    conn.commit()
    telegram_bot.message.reply_text(f'Адрес {email} успешно добавлен.')

# Добавляем хэндлер для обработки ответа пользователя
telegram_bot.dispatcher.add_handler(MessageHandler(Filters.regex(r'[1]+@[\w.-]+.\w+'), add_email), group=1)

# Создаем клавиатуру для удаления обработчика
keyboard = ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True, one_time_keyboard=True)

# Добавляем хэндлер для отмены добавления адресата
def add_email_cancel(telegram_bot, update):
    telegram_bot.message.reply_text("Добавление адресата отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Создаем ConversationHandler для запуска процесса добавления адресата
add_email_handler = ConversationHandler(entry_points=[CommandHandler('add_email', add_email_start)],
                                        states={"add-email": [MessageHandler(Filters.regex(r'^[\w\.-]+@[\w\.-]+\.\w+'), add_email)]},
                                        fallbacks=[MessageHandler(Filters.text(['Отмена']), add_email_cancel)],allow_reentry=True)
telegram_bot.dispatcher.add_handler(add_email_handler)

# Команда для просмотра списка адресатов
def view_emails(telegram_bot, update):
    user_id = telegram_bot.message.chat_id
    emails = [row[0] for row in cursor.execute('SELECT email FROM emails WHERE user_id = ?', (user_id,))]
    if emails:
        message = 'Список адресатов:\n' + '\n'.join(emails)
    else:
        message = 'Список адресатов пуст.'
    telegram_bot.message.reply_text(message)

telegram_bot.dispatcher.add_handler(CommandHandler('add_email', add_email, pass_args=True))
telegram_bot.dispatcher.add_handler(CommandHandler('view_emails', view_emails))
telegram_bot.dispatcher.add_handler(MessageHandler(Filters.text, check_email_updates))
telegram_bot.start_polling()

# Запуск бесконечного цикла для проверки новых писем
#while True:
    #check_email_updates()
    #time.sleep(60)
