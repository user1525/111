import sqlite3
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from config import BOT_TOKEN, ADMINS

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# База данных
DB_NAME = 'cinema_collab.db'

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME)
        self.cursor = self.conn.cursor()
        self._create_tables()
    
    def _create_tables(self):
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            department TEXT,
            profession TEXT,
            experience TEXT,
            portfolio TEXT,
            location TEXT
        )''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            favorite_user_id INTEGER,
            PRIMARY KEY (user_id, favorite_user_id),
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (favorite_user_id) REFERENCES users (user_id)
        )''')
        self.conn.commit()
    
    def add_user(self, user_id, username, full_name):
        self.cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, full_name) 
        VALUES (?, ?, ?)''', (user_id, username, full_name))
        self.conn.commit()
    
    def update_profile(self, user_id, **kwargs):
        set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        self.cursor.execute(f'''
        UPDATE users SET {set_clause} WHERE user_id = ?''', values)
        self.conn.commit()
    
    def delete_user(self, user_id):
        self.cursor.execute('DELETE FROM favorites WHERE user_id = ? OR favorite_user_id = ?', (user_id, user_id))
        self.cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone()
    
    def search_users(self, **filters):
        where_clause = ' AND '.join([f"{key} = ?" for key in filters.keys()]) if filters else '1'
        query = f'SELECT * FROM users WHERE {where_clause}'
        self.cursor.execute(query, list(filters.values()))
        return self.cursor.fetchall()
    
    def add_favorite(self, user_id, favorite_user_id):
        self.cursor.execute('''
        INSERT OR IGNORE INTO favorites (user_id, favorite_user_id) 
        VALUES (?, ?)''', (user_id, favorite_user_id))
        self.conn.commit()
    
    def remove_favorite(self, user_id, favorite_user_id):
        self.cursor.execute('''
        DELETE FROM favorites WHERE user_id = ? AND favorite_user_id = ?''', 
        (user_id, favorite_user_id))
        self.conn.commit()
    
    def get_favorites(self, user_id):
        self.cursor.execute('''
        SELECT u.* FROM users u
        JOIN favorites f ON u.user_id = f.favorite_user_id
        WHERE f.user_id = ?''', (user_id,))
        return self.cursor.fetchall()
    
    def is_favorite(self, user_id, favorite_user_id):
        self.cursor.execute('''
        SELECT 1 FROM favorites WHERE user_id = ? AND favorite_user_id = ?''', 
        (user_id, favorite_user_id))
        return bool(self.cursor.fetchone())

db = Database()

# Классы состояний
class ProfileStates(StatesGroup):
    department = State()
    profession = State()
    experience = State()
    portfolio = State()
    location = State()

class SearchStates(StatesGroup):
    department = State()
    profession = State()

# Полная структура цехов и профессий
DEPARTMENTS = {
    "Режиссерский цех": [
        "Режиссеры-постановщики",
        "Режиссеры анимации",
        "Вторые режиссеры",
        "Ассистенты второго режиссера",
        "Ассистенты режиссера по актерам",
        "Помощники режиссера",
        "Бригадиры АМС",
        "Кастинг-директора"
    ],
    "Звуковой цех": [
        "Звукорежиссеры",
        "Ассистенты звукорежиссера"
    ],
    "Операторский цех": [
        "Вторые операторы",
        "Камермены",
        "Фокус-пуллеры",
        "Операторы и пилоты коптеров",
        "Осветители",
        "Грип",
        "Gaffer"
    ],
    "Художественно-постановочный цех": [
        "Художники-постановщики",
        "Ассистенты художника-постановщика",
        "Декораторы",
        "Постановщики кадра"
    ],
    "Художники по реквизиту": [
        "Художники по реквизиту(ассистент режиссера по реквизиту)",
        "Ассистенты художника по реквизиту",
        "Реквизиторы"
    ],
    "Художники по гриму": [
        "Художники по гриму",
        "Ассистенты художника по гриму",
        "Гримеры",
        "Постижеры"
    ],
    "Художники по костюмам": [
        "Художники по костюмам",
        "Ассистенты художника по костюмам",
        "Художники-фактуровщики",
        "Костюмеры"
    ],
    "Актерский цех": [
        "Исполнители ролей первого плана",
        "Исполнители линейных ролей",
        "Эпизодники",
        "Дублеры",
        "Статисты",
        "Групповка",
        "Актеры массовых сцен"
    ],
    "Продюсерский департамент": [
        "Продюсеры кино и телевидения",
        "Продюсеры анимации",
        "Исполнительные продюсеры",
        "Линейные продюсеры",
        "Ассистенты продюсеров",
        "Менеджеры подготовки кинообъектов (Локейшен-менеджеры)"
    ],
    "Административный цех": [
        "Директора фильма",
        "Заместители директора фильма (по подготовке, транспорту, объектам)",
        "Инженер по охране труда",
        "Администраторы съемочных групп и площадки",
        "Координаторы",
        "Рабочие",
        "Буфет"
    ],
    "Транспортный цех": [
        "Водители"
    ],
    "Каскадерско-пиротехнический департамент": [
        "Постановщики трюков",
        "Каскадеры",
        "Пиротехники"
    ],
    "Цех скрипт-супервайзеров": [
        "Скрипт-супервайзеры"
    ],
    "Монтажный цех": [
        "Режиссеры монтажа",
        "Ассистенты режиссера монтажа",
        "Монтажеры",
        "Логгеры"
    ],
    "Анимация": [
        "Художники-постановщики анимационных фильмов",
        "Концепт-художники",
        "Художники персонажей",
        "Художники по фонам",
        "Режиссеры аниматика",
        "Аниматикеры",
        "Лейаут-художники",
        "Художники-аниматоры",
        "Прорисовщики",
        "Заливщики",
        "2D аниматоры (перекладка/гибридная анимация/костная)",
        "2D риггинг",
        "3D аниматоры",
        "Stop-motion аниматоры",
        "3D риггинг",
        "Моделлеры",
        "3D Лейаут",
        "Компоузеры",
        "Специалисты по свету",
        "Рендер"
    ]
}

EXPERIENCE_LEVELS = ["Без опыта", "До 1 года", "1-3 года", "3-5 лет", "5+ лет"]

# Клавиатуры
def get_main_menu():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🔍 Поиск коллег", "👤 Мой профиль")
    keyboard.add("⭐ Избранное")
    return keyboard

def get_departments_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(*DEPARTMENTS.keys())
    keyboard.add("🔙 Назад")
    return keyboard

def get_professions_keyboard(department):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    professions = DEPARTMENTS.get(department, [])
    for profession in professions:
        keyboard.add(profession)
    keyboard.add("🔙 Назад")
    return keyboard

def get_profile_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("✏️ Редактировать", callback_data="edit_profile"),
        types.InlineKeyboardButton("🗑️ Удалить анкету", callback_data="delete_profile")
    )
    return keyboard

# Хранилище для ID сообщений бота
user_message_ids = {}

async def cleanup_chat(chat_id):
    """Удаляем только сообщения бота"""
    try:
        if chat_id in user_message_ids:
            for msg_id in user_message_ids[chat_id]:
                try:
                    await bot.delete_message(chat_id, msg_id)
                except:
                    continue
            user_message_ids[chat_id] = []
    except Exception as e:
        logger.error(f"Ошибка при очистке чата: {e}")

async def track_message(chat_id, message_id):
    """Отслеживаем сообщения бота"""
    if chat_id not in user_message_ids:
        user_message_ids[chat_id] = []
    user_message_ids[chat_id].append(message_id)

# Обработчики команд
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message):
    await cleanup_chat(message.chat.id)
    db.add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    msg = await message.answer(
        "👋 Добро пожаловать в бот для поиска коллег в киноиндустрии!\n"
        "Вы можете создать профиль и найти специалистов для совместной работы.\n\n"
        "Доступные команды:\n"
        "/start - начать работу с ботом\n"
        "/help - помощь\n"
        "Используйте кнопки меню для навигации",
        reply_markup=get_main_menu()
    )
    await track_message(message.chat.id, msg.message_id)

@dp.message_handler(text="👤 Мой профиль")
async def my_profile(message: types.Message):
    await cleanup_chat(message.chat.id)
    user = db.get_user(message.from_user.id)
    if not user:
        msg = await message.answer("Профиль не найден. Начните с команды /start", reply_markup=get_main_menu())
        await track_message(message.chat.id, msg.message_id)
        return
    
    profile_text = (
        f"👤 <b>Ваш профиль:</b>\n\n"
        f"<b>Цех:</b> {user[3] or 'Не указано'}\n"
        f"<b>Профессия:</b> {user[4] or 'Не указано'}\n"
        f"<b>Опыт:</b> {user[5] or 'Не указано'}\n"
        f"<b>Портфолио:</b> {user[6] or 'Не указано'}\n"
        f"<b>Локация:</b> {user[7] or 'Не указано'}\n\n"
        "Используйте кнопки ниже для управления профилем."
    )
    
    msg = await message.answer(profile_text, reply_markup=get_profile_keyboard(), parse_mode="HTML")
    await track_message(message.chat.id, msg.message_id)

@dp.callback_query_handler(text="edit_profile")
async def edit_profile(callback: types.CallbackQuery):
    await cleanup_chat(callback.message.chat.id)
    msg = await callback.message.answer("Выберите цех:", reply_markup=get_departments_keyboard())
    await track_message(callback.message.chat.id, msg.message_id)
    await ProfileStates.department.set()
    await callback.answer()

@dp.callback_query_handler(text="delete_profile")
async def delete_profile(callback: types.CallbackQuery):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("✅ Да, удалить", callback_data="confirm_delete"),
        types.InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_delete")
    )
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите удалить свой профиль?\n"
        "Это действие нельзя отменить! Все ваши данные будут безвозвратно удалены.",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query_handler(text="confirm_delete")
async def confirm_delete(callback: types.CallbackQuery):
    db.delete_user(callback.from_user.id)
    msg = await callback.message.answer("🗑️ Ваш профиль успешно удален!", reply_markup=get_main_menu())
    await track_message(callback.message.chat.id, msg.message_id)
    await callback.answer()

@dp.callback_query_handler(text="cancel_delete")
async def cancel_delete(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if user:
        profile_text = (
            f"👤 <b>Ваш профиль:</b>\n\n"
            f"<b>Цех:</b> {user[3] or 'Не указано'}\n"
            f"<b>Профессия:</b> {user[4] or 'Не указано'}\n"
            f"<b>Опыт:</b> {user[5] or 'Не указано'}\n"
            f"<b>Портфолио:</b> {user[6] or 'Не указано'}\n"
            f"<b>Локация:</b> {user[7] or 'Не указано'}\n\n"
            "Удаление профиля отменено."
        )
        await callback.message.edit_text(profile_text, reply_markup=get_profile_keyboard(), parse_mode="HTML")
    else:
        await callback.message.edit_text("Удаление профиля отменено.", reply_markup=get_main_menu())
    await callback.answer()

@dp.message_handler(text="🔍 Поиск коллег")
async def search_colleagues(message: types.Message):
    await cleanup_chat(message.chat.id)
    msg = await message.answer("Выберите цех для поиска:", reply_markup=get_departments_keyboard())
    await track_message(message.chat.id, msg.message_id)
    await SearchStates.department.set()

@dp.message_handler(text="⭐ Избранное")
async def show_favorites(message: types.Message):
    await cleanup_chat(message.chat.id)
    favorites = db.get_favorites(message.from_user.id)
    if not favorites:
        msg = await message.answer("У вас пока нет избранных профилей.", reply_markup=get_main_menu())
        await track_message(message.chat.id, msg.message_id)
        return
    
    main_msg = await message.answer("Ваши избранные профили:", reply_markup=get_main_menu())
    await track_message(message.chat.id, main_msg.message_id)
    
    for user in favorites:
        profile_text = (
            f"👤 <b>Профиль:</b>\n\n"
            f"<b>Имя:</b> {user[2]}\n"
            f"<b>Цех:</b> {user[3]}\n"
            f"<b>Профессия:</b> {user[4]}\n"
            f"<b>Опыт:</b> {user[5]}\n"
            f"<b>Локация:</b> {user[7]}\n\n"
            f"<a href='tg://user?id={user[0]}'>Написать</a>"
        )
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(
            "❌ Удалить из избранного", 
            callback_data=f"remove_favorite_{user[0]}"
        ))
        
        msg = await message.answer(profile_text, reply_markup=keyboard, parse_mode="HTML")
        await track_message(message.chat.id, msg.message_id)

# Обработчики состояний для профиля
@dp.message_handler(state=ProfileStates.department)
async def process_department(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.finish()
        msg = await message.answer("Главное меню:", reply_markup=get_main_menu())
        await track_message(message.chat.id, msg.message_id)
        return
    
    if message.text not in DEPARTMENTS:
        msg = await message.answer("Пожалуйста, выберите цех из списка:", reply_markup=get_departments_keyboard())
        await track_message(message.chat.id, msg.message_id)
        return
    
    await state.update_data(department=message.text)
    msg = await message.answer("Выберите профессию:", reply_markup=get_professions_keyboard(message.text))
    await track_message(message.chat.id, msg.message_id)
    await ProfileStates.profession.set()

@dp.message_handler(state=ProfileStates.profession)
async def process_profession(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await ProfileStates.department.set()
        data = await state.get_data()
        msg = await message.answer("Выберите цех:", reply_markup=get_departments_keyboard())
        await track_message(message.chat.id, msg.message_id)
        return
    
    data = await state.get_data()
    department = data.get('department')
    
    if message.text not in DEPARTMENTS.get(department, []):
        msg = await message.answer("Пожалуйста, выберите профессию из списка:", reply_markup=get_professions_keyboard(department))
        await track_message(message.chat.id, msg.message_id)
        return
    
    await state.update_data(profession=message.text)
    msg = await message.answer("Укажите ваш опыт:", reply_markup=types.ReplyKeyboardMarkup(
        resize_keyboard=True, row_width=2
    ).add(*EXPERIENCE_LEVELS).add("🔙 Назад"))
    await track_message(message.chat.id, msg.message_id)
    await ProfileStates.experience.set()

@dp.message_handler(state=ProfileStates.experience)
async def process_experience(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        data = await state.get_data()
        await ProfileStates.profession.set()
        msg = await message.answer("Выберите профессию:", reply_markup=get_professions_keyboard(data.get('department')))
        await track_message(message.chat.id, msg.message_id)
        return
    
    if message.text not in EXPERIENCE_LEVELS:
        msg = await message.answer("Пожалуйста, выберите уровень опыта из списка:", reply_markup=types.ReplyKeyboardMarkup(
            resize_keyboard=True, row_width=2
        ).add(*EXPERIENCE_LEVELS).add("🔙 Назад"))
        await track_message(message.chat.id, msg.message_id)
        return
    
    await state.update_data(experience=message.text)
    msg = await message.answer("Пришлите ссылку на ваше портфолио (если есть):", reply_markup=types.ReplyKeyboardMarkup(
        resize_keyboard=True
    ).add("Пропустить").add("🔙 Назад"))
    await track_message(message.chat.id, msg.message_id)
    await ProfileStates.portfolio.set()

@dp.message_handler(state=ProfileStates.portfolio)
async def process_portfolio(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await ProfileStates.experience.set()
        msg = await message.answer("Укажите ваш опыт:", reply_markup=types.ReplyKeyboardMarkup(
            resize_keyboard=True, row_width=2
        ).add(*EXPERIENCE_LEVELS).add("🔙 Назад"))
        await track_message(message.chat.id, msg.message_id)
        return
    
    portfolio = message.text if message.text != "Пропустить" else ""
    await state.update_data(portfolio=portfolio)
    msg = await message.answer("Укажите вашу локацию (город):", reply_markup=types.ReplyKeyboardMarkup(
        resize_keyboard=True
    ).add("🔙 Назад"))
    await track_message(message.chat.id, msg.message_id)
    await ProfileStates.location.set()

@dp.message_handler(state=ProfileStates.location)
async def process_location(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await ProfileStates.portfolio.set()
        msg = await message.answer("Пришлите ссылку на ваше портфолио (если есть):", reply_markup=types.ReplyKeyboardMarkup(
            resize_keyboard=True
        ).add("Пропустить").add("🔙 Назад"))
        await track_message(message.chat.id, msg.message_id)
        return
    
    data = await state.get_data()
    
    db.update_profile(
        message.from_user.id,
        department=data.get('department'),
        profession=data.get('profession'),
        experience=data.get('experience'),
        portfolio=data.get('portfolio', ''),
        location=message.text
    )
    
    await state.finish()
    msg = await message.answer("✅ Ваш профиль успешно обновлен!", reply_markup=get_main_menu())
    await track_message(message.chat.id, msg.message_id)

# Обработчики состояний для поиска
@dp.message_handler(state=SearchStates.department)
async def search_department(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.finish()
        msg = await message.answer("Главное меню:", reply_markup=get_main_menu())
        await track_message(message.chat.id, msg.message_id)
        return
    
    if message.text not in DEPARTMENTS:
        msg = await message.answer("Пожалуйста, выберите цех из списка:", reply_markup=get_departments_keyboard())
        await track_message(message.chat.id, msg.message_id)
        return
    
    await state.update_data(department=message.text)
    msg = await message.answer("Выберите профессию:", reply_markup=get_professions_keyboard(message.text))
    await track_message(message.chat.id, msg.message_id)
    await SearchStates.profession.set()

@dp.message_handler(state=SearchStates.profession)
async def search_profession(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await SearchStates.department.set()
        msg = await message.answer("Выберите цех:", reply_markup=get_departments_keyboard())
        await track_message(message.chat.id, msg.message_id)
        return
    
    data = await state.get_data()
    department = data.get('department')
    
    if message.text not in DEPARTMENTS.get(department, []):
        msg = await message.answer("Пожалуйста, выберите профессию из списка:", reply_markup=get_professions_keyboard(department))
        await track_message(message.chat.id, msg.message_id)
        return
    
    results = db.search_users(
        department=department,
        profession=message.text
    )
    
    if not results:
        msg = await message.answer("Никого не найдено. Попробуйте изменить параметры поиска.", 
                           reply_markup=get_professions_keyboard(department))
        await track_message(message.chat.id, msg.message_id)
        return
    
    main_msg = await message.answer(f"🔍 Найдено {len(results)} специалистов:", reply_markup=get_main_menu())
    await track_message(message.chat.id, main_msg.message_id)
    
    for user in results:
        is_favorite = db.is_favorite(message.from_user.id, user[0])
        profile_text = (
            f"👤 <b>Найден специалист:</b>\n\n"
            f"<b>Имя:</b> {user[2]}\n"
            f"<b>Цех:</b> {user[3]}\n"
            f"<b>Профессия:</b> {user[4]}\n"
            f"<b>Опыт:</b> {user[5]}\n"
            f"<b>Локация:</b> {user[7]}\n\n"
            f"<a href='tg://user?id={user[0]}'>Написать</a>"
        )
        
        keyboard = types.InlineKeyboardMarkup()
        if is_favorite:
            keyboard.add(types.InlineKeyboardButton(
                "❌ Удалить из избранного", 
                callback_data=f"remove_favorite_{user[0]}"
            ))
        else:
            keyboard.add(types.InlineKeyboardButton(
                "⭐ Добавить в избранное", 
                callback_data=f"add_favorite_{user[0]}"
            ))
        
        msg = await message.answer(profile_text, reply_markup=keyboard, parse_mode="HTML")
        await track_message(message.chat.id, msg.message_id)
    
    await state.finish()

# Обработчики избранного
@dp.callback_query_handler(lambda c: c.data.startswith('add_favorite_'))
async def add_to_favorites(callback: types.CallbackQuery):
    favorite_user_id = int(callback.data.split('_')[2])
    db.add_favorite(callback.from_user.id, favorite_user_id)
    await callback.answer("✅ Добавлено в избранное")
    await callback.message.edit_reply_markup(reply_markup=types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("❌ Удалить из избранного", callback_data=f"remove_favorite_{favorite_user_id}")
    ))

@dp.callback_query_handler(lambda c: c.data.startswith('remove_favorite_'))
async def remove_from_favorites(callback: types.CallbackQuery):
    favorite_user_id = int(callback.data.split('_')[2])
    db.remove_favorite(callback.from_user.id, favorite_user_id)
    await callback.answer("❌ Удалено из избранного")
    await callback.message.edit_reply_markup(reply_markup=types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("⭐ Добавить в избранное", callback_data=f"add_favorite_{favorite_user_id}")
    ))

# Обработчик текстовых сообщений
@dp.message_handler()
async def handle_text(message: types.Message):
    if message.text == "🔙 Назад":
        msg = await message.answer("Главное меню:", reply_markup=get_main_menu())
        await track_message(message.chat.id, msg.message_id)
    else:
        msg = await message.answer("Используйте кнопки меню для навигации", reply_markup=get_main_menu())
        await track_message(message.chat.id, msg.message_id)

# Запуск бота
if __name__ == '__main__':
    logger.info("Бот запускается...")
    executor.start_polling(dp, skip_updates=True)
