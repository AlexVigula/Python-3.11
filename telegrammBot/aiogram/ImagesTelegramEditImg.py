import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram import F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
########################################################
#                                                       #
#    Отправка и изменения изображения в телеграмм боте  #
#    dev Alex Vigula      tg @gunsxp                    #
#                                                       #
#########################################################
API_TOKEN = 'Ваш Токен'  # Замените на ваш токен

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Папка для хранения изображений
if not os.path.exists('images'):
    os.makedirs('images')

# Переменная для хранения текущего изображения
current_image_path = None

# Создаем клавиатуру с кнопками "Профиль" и "Изменить изображение"
def create_main_kb() -> ReplyKeyboardMarkup:
    profile_button = KeyboardButton(text="👤 Профиль")
    edit_button = KeyboardButton(text="🖼 Изменить изображение")
    keyboard = ReplyKeyboardMarkup(keyboard=[[profile_button, edit_button]], resize_keyboard=True)
    return keyboard

@dp.message(Command("start"))
async def send_welcome(message: Message):
    await message.answer("Привет! Отправь мне изображение, и я его сохраню.", reply_markup=create_main_kb())

@dp.message(F.photo)
async def handle_photo(message: Message):
    global current_image_path  # Используем глобальную переменную # Получаем файл изображения
    file_id = message.photo[-1].file_id  # Получаем файл самого высокого разрешения 
    file = await bot.get_file(file_id)

    # Сохраняем изображение
    current_image_path = f'images/{file_id}.jpg'
    await bot.download_file(file.file_path, current_image_path)
    await message.answer("Изображение сохранено!", reply_markup=create_main_kb())

@dp.message(F.text)
async def handle_text(message: Message):
    global current_image_path 
    if message.text == "👤 Профиль":
        if current_image_path and os.path.exists(current_image_path):
            with open(current_image_path, 'rb') as photo:
                await message.answer_photo(photo, caption="Вот ваше текущее изображение.")
        else:
            await message.answer("У вас еще нет сохраненного изображения.")
    elif message.text == "🖼 Изменить изображение":
        await message.answer("Пожалуйста, отправь новое изображение.", reply_markup=types.ReplyKeyboardRemove())
    else:
        await message.answer("Я не понимаю эту команду. Пожалуйста, выбери действие.")

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
