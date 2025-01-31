import asyncio
import requests
import os
import time
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
import logging
from deep_translator import GoogleTranslator, exceptions

# 🔹 Токен бота та ID каналів
BOT_TOKEN = "5367470824:AAHQtKIOCVnq7a74UnNwiMqIQQ6jXL-Evuc"
CHANNEL_UA = "-1002080353500"
CHANNEL_RU = "-1002080353500"  # Вставити ID російського каналу

# 🔹 Ініціалізація бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot=bot)

# 🔹 URL сайту ТСН
MAIN_NEWS_URL = "https://tsn.ua/"

# 🔹 Логування
logging.basicConfig(filename="bot.log", level=logging.INFO,
                    format="%(asctime)s - %(message)s")

# 🔹 Файл для збереження вже відправлених новин
SENT_NEWS_FILE = "sent_news.txt"

# 🔹 Ініціалізація перекладача
translator = GoogleTranslator(source="uk", target="ru")

# Завантаження вже відправлених заголовків


def load_sent_news():
    if not os.path.exists(SENT_NEWS_FILE):
        return set()
    with open(SENT_NEWS_FILE, "r", encoding="utf-8") as file:
        return set(line.strip() for line in file.readlines())

# Збереження нових заголовків у файл


def save_sent_news(title):
    with open(SENT_NEWS_FILE, "a", encoding="utf-8") as file:
        file.write(title + "\n")

# 🔹 Отримання ОСТАННІХ ПОСИЛАНЬ НА НОВИНИ


def get_latest_news_links():
    response = requests.get(MAIN_NEWS_URL)
    soup = BeautifulSoup(response.content, "html.parser")

    news_links = []
    seen_titles = set()
    for article in soup.find_all("article"):
        title_tag = article.find("a", class_="c-card__link")
        if title_tag:
            title = title_tag.get_text(strip=True)
            link = title_tag["href"]
            if not link.startswith("http"):
                link = "https://tsn.ua" + link

            if title not in seen_titles:
                seen_titles.add(title)
                news_links.append({"title": title, "link": link})

    return news_links[:5]

# 🔹 Очищення та форматування тексту новини


def clean_text(text):
    # Видаляємо зайві фрази
    remove_phrases = [
        "Реклама", "доповнюється", "Про це повідомили", "Нагадаємо",
        "Як повідомляє", "За даними", "Зазначається", "Як зазначили в",
        "Також", "Водночас", "ТСН.ua", "Читайте також", "Що відомо?",
        "Підписуйтесь на наші канали у Telegram та Viber.", "Підписуйтесь на наші канали уTelegramтаViber."
    ]
    for phrase in remove_phrases:
        text = text.replace(phrase, "")

    # Видаляємо зайві пробіли
    text = text.replace("  ", " ").strip()

    # Видаляємо порожні абзаци та дублікати
    paragraphs = text.split("\n\n")
    cleaned_paragraphs = []
    seen_sentences = set()

    for para in paragraphs:
        para = para.strip()

        # Прибираємо коми на початку речення
        if para.startswith(", "):
            para = para[2:]

        # Прибираємо незавершені речення типу ": "
        if para.endswith(":"):
            continue

        # Видаляємо дублікати абзаців
        if para not in seen_sentences:
            seen_sentences.add(para)
            cleaned_paragraphs.append(para)

    return "\n\n".join(cleaned_paragraphs)
# 🔹 Отримання ПОВНОГО ТЕКСТУ НОВИНИ + ГОЛОВНОГО ФОТО


def get_news_content(news_url):
    response = requests.get(news_url)
    soup = BeautifulSoup(response.content, "html.parser")

    content_tag = soup.find("div", class_="c-article__body")
    if content_tag:
        content_paragraphs = [p.get_text(strip=True) for p in content_tag.find_all(
            "p") if p.get_text(strip=True)]
        content = "\n\n".join(content_paragraphs)
    else:
        content = "Опис новини відсутній."

    # Очищуємо текст
    content = clean_text(content)

    # Обрізаємо текст, якщо він занадто довгий
    if len(content) > 4090:
        content = content[:4090] + "..."

    # Отримуємо головне фото новини (meta og:image)
    image_url = None
    meta_image = soup.find("meta", property="og:image")
    if meta_image:
        image_url = meta_image["content"]

    return content, image_url

# 🔹 Переклад тексту на російську


def translate_to_russian(text, attempts=3):
    paragraphs = text.split("\n\n")
    translated_paragraphs = []

    for para in paragraphs:
        for _ in range(attempts):
            try:
                translation = translator.translate(para)
                if translation is None:
                    raise ValueError("Переклад повернув None")
                translated_paragraphs.append(translation)
                break
            except (exceptions.RequestError, ValueError):
                time.sleep(2)
        else:
            # Якщо не вдалося перекласти, залишаємо оригінал
            translated_paragraphs.append(para)

    return "\n\n".join(translated_paragraphs)

# 🔹 Відправка новин у Telegram-канали


async def send_news_to_channels():
    sent_news = load_sent_news()
    news_list = get_latest_news_links()
    seen_titles = set()

    for news in news_list:
        title, link = news["title"], news["link"]

        if title in sent_news or title in seen_titles:
            continue

        seen_titles.add(title)

        # Отримуємо повний опис новини та фото
        description, image_url = get_news_content(link)

        # 🔹 Форматований текст українською
        message_text_ua = f"📰 <b>{
            title}</b>\n\n{description}\n\n🔗 <a href='{link}'>Читати далі</a>"

        # 🔹 Переклад російською
        title_ru = translate_to_russian(title)
        description_ru = translate_to_russian(description)
        message_text_ru = f"📰 <b>{
            title_ru}</b>\n\n{description_ru}\n\n🔗 <a href='{link}'>Подробнее</a>"

        async def send_news(channel, text, img):
            try:
                if img:
                    await bot.send_photo(channel, photo=img)
                await bot.send_message(channel, text[:4096], parse_mode="HTML", disable_web_page_preview=True)
            except Exception as e:
                logging.error(f"⚠️ Помилка відправки у {channel}: {str(e)}")

        await send_news(CHANNEL_UA, message_text_ua, image_url)
        await send_news(CHANNEL_RU, message_text_ru, image_url)

        logging.info(f"✅ Опубліковано: {title} (UA) та {title_ru} (RU)")
        save_sent_news(title)

# 🔹 Автоматичний запуск перевірки новин кожні 10 хвилин


async def auto_news_scheduler():
    while True:
        await send_news_to_channels()
        await asyncio.sleep(1)

# 🔹 Головна функція запуску


async def main():
    asyncio.create_task(auto_news_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
