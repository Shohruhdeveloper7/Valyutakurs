import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from decimal import Decimal, InvalidOperation
from cachetools import TTLCache
import aiohttp
import asyncio

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Конфигурация бота
TOKEN = "8198907146:AAHyB4w-HhVNQsed9PxHSNLFSZHximUj_0U"
API_BASE = "https://v6.exchangerate-api.com/v6/075da83e108bde274389c814/latest/"
CACHE_TTL = 300  # Кеширование на 5 минут

# Кеш для курсов валют
rates_cache = TTLCache(maxsize=100, ttl=CACHE_TTL)


# Состояния FSM
class CurrencyStates(StatesGroup):
    GET_AMOUNT = State()


# Направления обмена
EXCHANGE_DIRECTIONS = {
    'USD_RUB': '🇺🇸 USD → RUB 🇷🇺',
    'RUB_USD': '🇷🇺 RUB → USD 🇺🇸',
    'EUR_RUB': '🇪🇺 EUR → RUB 🇷🇺',
    'USD_EUR': '🇺🇸 USD → EUR 🇪🇺',
    'EUR_USD': '🇪🇺 EUR → USD 🇺🇸',
}

# Инициализация бота
bot = Bot(token=TOKEN)
dp = Dispatcher()


async def get_exchange_rate(base: str, target: str) -> Decimal | None:
    """Получение курса валюты с кешированием"""
    cache_key = f"{base}_{target}"
    if cache_key in rates_cache:
        return rates_cache[cache_key]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}{base}", timeout=10) as response:
                data = await response.json()

                if data.get('result') == 'success':
                    rate = Decimal(str(data['conversion_rates'][target]))
                    rates_cache[cache_key] = rate
                    return rate
    except Exception as e:
        logger.error(f"Ошибка получения курса: {e}")
    return None


async def convert_currency(amount: Decimal, direction: str) -> str:
    """Конвертация валюты"""
    base, target = direction.split("_")
    rate = await get_exchange_rate(base, target)

    if rate is None:
        return "❌ Ошибка получения курса. Пожалуйста, попробуйте позже."

    result = (amount * rate).quantize(Decimal('0.01'))
    return (f"🔹 Результат: {amount} {base} ≈ {result} {target}\n"
            f"🔸 Курс: 1 {base} = {rate} {target}\n"
            f"⏳ Обновляется каждые {CACHE_TTL // 60} минут")


def get_exchange_keyboard():
    """Создание клавиатуры"""
    buttons = [
        [KeyboardButton(text=name)]
        for name in EXCHANGE_DIRECTIONS.values()
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


async def show_main_menu(message: types.Message):
    """Показать главное меню"""
    await message.answer(
        "Выберите направление конвертации:",
        reply_markup=get_exchange_keyboard()
    )


# ========== ОБРАБОТЧИКИ ========== #

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    await show_main_menu(message)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Обработка команды /help"""
    help_text = (
        "💰 *Конвертер валют*\n\n"
        "✅ /start - Начать работу с ботом\n"
        "✅ /help - Получить справку\n\n"
        "Бот позволяет быстро конвертировать основные валюты!"
    )
    await message.answer(help_text, parse_mode='Markdown')


@dp.message(F.text.in_(EXCHANGE_DIRECTIONS.values()))
async def direction_selected(message: types.Message, state: FSMContext):
    """Выбор направления конвертации"""
    direction_code = next(k for k, v in EXCHANGE_DIRECTIONS.items() if v == message.text)
    await state.update_data(direction=direction_code)
    await message.answer(
        "Введите сумму для конвертации:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(CurrencyStates.GET_AMOUNT)


@dp.message(CurrencyStates.GET_AMOUNT)
async def amount_entered(message: types.Message, state: FSMContext):
    """Ввод суммы для конвертации"""
    try:
        amount = Decimal(message.text.replace(',', '.').strip())
        if amount <= 0:
            raise ValueError
    except (ValueError, InvalidOperation):
        await message.answer("⚠️ Неверный формат суммы. Введите число (например: 100 или 150.50)")
        return

    data = await state.get_data()
    try:
        result = await convert_currency(amount, data['direction'])
        await message.answer(result)
    except Exception as e:
        logger.error(f"Ошибка конвертации: {e}")
        await message.answer("❌ Произошла ошибка. Пожалуйста, попробуйте позже.")

    await state.clear()
    await show_main_menu(message)


@dp.message()
async def unknown_message(message: types.Message):
    """Обработка неизвестных сообщений"""
    await message.answer("Пожалуйста, выберите направление конвертации из меню!")
    await show_main_menu(message)


# ========== ЗАПУСК БОТА ========== #

async def main():
    """Запуск бота"""
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())