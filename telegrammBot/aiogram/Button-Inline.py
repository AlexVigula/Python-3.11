from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
import asyncio

API_TOKEN = 'Свой токе сюда'
# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    button1 = InlineKeyboardButton(text="Кнопка 1", callback_data='button1')
    button2 = InlineKeyboardButton(text="Кнопка 2", callback_data='button2')
 # Создаем клавиатуру с кнопками
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[button1, button2]])
    
    await message.answer("Привет! Нажми на кнопку:", reply_markup=keyboard)

@dp.callback_query(F.data.in_(['button1', 'button2']))
async def process_callback(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    if callback_query.data == 'button1':
        await bot.send_message(callback_query.from_user.id, "Вы нажали кнопку 1")
    elif callback_query.data == 'button2':
        await bot.send_message(callback_query.from_user.id, "Вы нажали кнопку 2")

if __name__ == '__main__':
    # Запускаем бота 
    asyncio.run(dp.start_polling(bot))
