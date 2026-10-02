import json
import os
import random
import logging
import difflib
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InputMediaPhoto
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
    ContextTypes,
)

from database import db
import config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def load_drugs():
    try:
        with open('drugs_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return []

DRUGS = load_drugs()
USER_STATES = {}

ACCESS_DENIED_MESSAGE = (
    "⛔ У вас пока нет доступа к этому боту.\n\n"
    "Свяжитесь с администратором, чтобы он добавил вас в список доступа."
)

WELCOME_MESSAGE = (
    "👋 Добро пожаловать в бот по гистологии!\n\n"
    "🎧 Микронаушники в аренду от 350 рублей\n"
    "https://vk.ru/1ainurka1"
)

# Константы для управления отображением кнопок
ITEMS_PER_PAGE = 6  # Количество препаратов на одной странице
BUTTONS_PER_ROW = 3  # Количество кнопок в одной строке

# Группировка занятий по курсам
COURSE_GROUPS = {
    "1 курс": {
        "1 занятие": (1, 3),
        "2 занятие": (4, 12),
        "3 занятие": (13, 18),
        "5 занятие": (19, 24),
        "7 занятие": (25, 32),
        "8 занятие": (33, 35),
        "9 занятие": (36, 36),
        "10 занятие": (37, 44),
        "11 занятие": (45, 47),
        "12 занятие": (48, 51),
        "14 занятие": (52, 55),
        "15 занятие": (56, 61)
    },
    "2 курс": {
        "17 занятие": (62, 66),
        "18 занятие": (67, 68),
        "19 занятие": (69, 70),
        "21 занятие": (71, 73),
        "22 занятие": (74, 78),
        "23 занятие": (79, 83),
        "25 занятие": (84, 89),
        "26 занятие": (90, 95),
        "27 занятие": (96, 100),
        "28 занятие": (101, 104),
        "30 занятие": (105, 108),
        "31 занятие": (109, 111),
        "32 занятие": (112, 114),
        "33 занятие": (115, 119)
    }
}

def get_course_lessons(course_name):
    """Получить список занятий для курса"""
    return COURSE_GROUPS.get(course_name, {})

def get_drugs_by_lesson(course_name, lesson_name):
    """Получить препараты для конкретного занятия"""
    course_lessons = COURSE_GROUPS.get(course_name, {})
    if lesson_name not in course_lessons:
        return []
    
    start_id, end_id = course_lessons[lesson_name]
    return [drug for drug in DRUGS if start_id <= drug['id'] <= end_id]

def get_drug_by_id(drug_id):
    """Получить препарат по ID"""
    return next((d for d in DRUGS if d['id'] == drug_id), None)

def get_drug_by_name(drug_name, lesson_drugs=None):
    """Получить препарат по названию"""
    if lesson_drugs:
        # Ищем среди препаратов занятия
        for drug in lesson_drugs:
            if extract_short_name(drug['name']) == drug_name:
                return drug
    # Ищем среди всех препаратов
    for drug in DRUGS:
        if extract_short_name(drug['name']) == drug_name:
            return drug
    return None

def extract_short_name(full_name):
    """Извлечь короткое название до скобок"""
    if '(' in full_name:
        return full_name.split('(')[0].strip()
    return full_name.strip()


async def access_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверить доступ до обработки любого действия пользователя."""
    user = update.effective_user

    # Служебные обновления без пользователя не должны ломать обработку.
    if user is None:
        return

    if not db.is_allowed(user.id):
        message = update.effective_message
        if message:
            await message.reply_text(ACCESS_DENIED_MESSAGE)
        # Не передаём запрещённое действие остальным обработчикам.
        raise ApplicationHandlerStop


def parse_user_id_argument(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить Telegram ID из аргументов админ-команды."""
    if not context.args:
        return None

    try:
        user_id = int(context.args[0])
    except (TypeError, ValueError):
        return None

    return user_id if user_id > 0 else None


async def add_access_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-команда: /add_access <user_id>."""
    if not db.is_admin(update.effective_user.id):
        return

    user_id = parse_user_id_argument(update, context)
    if user_id is None:
        await update.message.reply_text(
            "Использование: /add_access <telegram_id>\n"
            "Пример: /add_access 123456789"
        )
        return

    added = db.add_to_access_list(user_id, update.effective_user.id)
    if added:
        await update.message.reply_text(
            f"✅ Пользователь {user_id} добавлен в список доступа."
        )
    else:
        await update.message.reply_text(
            f"ℹ️ Пользователь {user_id} уже есть в списке доступа."
        )


async def remove_access_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-команда: /remove_access <user_id>."""
    if not db.is_admin(update.effective_user.id):
        return

    user_id = parse_user_id_argument(update, context)
    if user_id is None:
        await update.message.reply_text(
            "Использование: /remove_access <telegram_id>\n"
            "Пример: /remove_access 123456789"
        )
        return

    if db.is_admin(user_id):
        await update.message.reply_text("⚠️ Нельзя удалить администратора из списка доступа.")
        return

    removed = db.remove_from_access_list(user_id)
    if removed:
        await update.message.reply_text(
            f"✅ Пользователь {user_id} удалён из списка доступа."
        )
    else:
        await update.message.reply_text(
            f"ℹ️ Пользователь {user_id} не найден в списке доступа."
        )


async def access_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-команда: показать список доступа."""
    if not db.is_admin(update.effective_user.id):
        return

    users = db.get_access_list()
    database_user_ids = {user["user_id"] for user in users}
    lines = ["🔐 Список доступа:", ""]
    for index, user in enumerate(users, start=1):
        display_name = " ".join(
            part for part in (user.get("first_name"), user.get("last_name"))
            if part
        )
        username = f"@{user['username']}" if user.get("username") else "без username"
        extra = f" — {display_name}" if display_name else ""
        lines.append(f"{index}. {user['user_id']} ({username}{extra})")

    # Показываем также ID из Render Environment Variable, даже если они
    # ещё не записаны в локальную SQLite-базу.
    env_only_ids = sorted(config.ALLOWED_USER_IDS - database_user_ids)
    for user_id in env_only_ids:
        lines.append(f"{user_id} (из ALLOWED_USER_IDS)")

    await update.message.reply_text("\n".join(lines))

# Функции проверки ответов (оставляем без изменений)
def normalize_string(text):
    if not text:
        return ""
    text = text.lower()
    text = text.replace('–', '-').replace('—', '-')
    text = ' '.join(text.split())
    text = re.sub(r'[^\w\s\-\(\)]', '', text)
    return text

def check_name_similarity(user_name, correct_name, drug_id=None):
    user_name_norm = normalize_string(user_name)
    correct_name_norm = normalize_string(correct_name)
    
    # Полное совпадение
    if user_name_norm == correct_name_norm:
        return True
    
    # Проверка с использованием difflib
    similarity = difflib.SequenceMatcher(None, user_name_norm, correct_name_norm).ratio()
    
    # Снижаем порог для длинных названий
    min_ratio = 0.75 if len(correct_name_norm) > 20 else 0.8
    
    if similarity >= min_ratio:
        return True
    
    # Проверка частичного совпадения (если введена часть названия)
    if user_name_norm in correct_name_norm and len(user_name_norm) >= len(correct_name_norm) * 0.6:
        return True
    
    # Дополнительные проверки для конкретных препаратов (если нужно)
    if drug_id:
        # Здесь можно добавить альтернативные названия для конкретных препаратов
        pass
    
    return False

def check_staining_similarity(user_staining, correct_staining):
    user_staining_norm = normalize_string(user_staining)
    correct_staining_norm = normalize_string(correct_staining)
    
    # Полное совпадение
    if user_staining_norm == correct_staining_norm:
        return True
    
    # Разделение на компоненты окраски
    user_parts = [part.strip() for part in user_staining_norm.split('-') if part.strip()]
    correct_parts = [part.strip() for part in correct_staining_norm.split('-') if part.strip()]
    
    # Проверка всех компонентов
    if len(user_parts) == len(correct_parts):
        all_match = True
        for user_part, correct_part in zip(user_parts, correct_parts):
            if not check_name_similarity(user_part, correct_part):
                all_match = False
                break
        if all_match:
            return True
    
    # Проверка вхождения (например, "гематоксилин-эозин" и "гематоксилин и эозин")
    user_joined = user_staining_norm.replace('-', ' ')
    correct_joined = correct_staining_norm.replace('-', ' ')
    
    if user_joined in correct_joined or correct_joined in user_joined:
        return True
    
    # Строгая проверка с учетом возможных опечаток
    similarity = difflib.SequenceMatcher(None, user_staining_norm, correct_staining_norm).ratio()
    return similarity >= 0.85

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать главное меню с reply-клавиатуря"""
    keyboard = [
        [KeyboardButton("📚 Список препаратов")],
        [KeyboardButton("🧪 Мне повезет!")],  # ← ПЕРЕИМЕНОВАНО
        [KeyboardButton("🏃 Прогон всех препаратов")],
        [KeyboardButton("❓ Помощь")]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🏠 Главное меню\n\n"
        "Выберите действие ниже 👇",
        reply_markup=reply_markup
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    db.register_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    await update.message.reply_text(WELCOME_MESSAGE)
    
    await show_main_menu(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 Помощь по боту\n\n"
        "Основные функции:\n"
        "• 📚 Список препаратов - просмотр всех препаратов с группировкой по курсам и занятиям\n"
        "• 🧪 Мне повезет! - случайный вопрос для самопроверки\n"
        "• 🏃 Прогон всех препаратов - последовательная проверка всех препаратов\n\n"
        "📝 Как использовать:\n"
        "1. Для тестирования вводите ответ в формате:\n"
        "   Название препарата (Окраска)\n"
        "2. Используйте кнопки для навигации\n"
        "3. Для просмотра деталей нажмите на название препарата\n\n"
        "✅ Улучшенная система проверки:\n"
        "• Принимаются альтернативные названия препаратов\n"
        "• Учитываются опечатки в названиях\n"
        "• Строгая проверка окрасок\n\n"
        "💬 По всем вопросам обращайтесь: @NurikAbyi"
    )

    if db.is_admin(update.effective_user.id):
        help_text += (
            "\n\n🔐 Команды администратора:\n"
            "• /add_access <telegram_id> — добавить пользователя\n"
            "• /remove_access <telegram_id> — удалить пользователя\n"
            "• /access_list — показать список доступа"
        )
    
    await update.message.reply_text(help_text)
    await show_main_menu(update, context)

async def show_courses_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню курсов"""
    keyboard = []
    for course_name in COURSE_GROUPS.keys():
        keyboard.append([KeyboardButton(f"🎓 {course_name}")])
    
    keyboard.append([KeyboardButton("🏠 Главное меню")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    text = "🎓 Выберите курс:\n\n"
    text += "• 1 курс - занятия с 1 по 15\n"
    text += "• 2 курс - занятия с 17 по 33\n"
    
    await update.message.reply_text(text, reply_markup=reply_markup)

async def show_lessons_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, course_name, page=0):
    """Показать меню занятий для выбранного курса с пагинацией"""
    course_lessons = list(COURSE_GROUPS.get(course_name, {}).keys())
    
    if not course_lessons:
        await update.message.reply_text("Для этого курса пока нет занятий.")
        return
    
    # Разделяем на страницы
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_lessons = course_lessons[start_idx:end_idx]
    
    # Сохраняем информацию о текущем курсе
    context.user_data['current_course'] = course_name
    context.user_data['lessons_page'] = page
    
    # Создаем кнопки для занятий текущей страницы
    keyboard = []
    for i in range(0, len(page_lessons), BUTTONS_PER_ROW):
        row = []
        for j in range(BUTTONS_PER_ROW):
            if i + j < len(page_lessons):
                row.append(KeyboardButton(page_lessons[i + j]))
        keyboard.append(row)
    
    # Добавляем кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(KeyboardButton("⬅️ Назад"))
    if end_idx < len(course_lessons):
        nav_buttons.append(KeyboardButton("Далее ➡️"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопки управления - ВМЕСТЕ на одном уровне
    keyboard.append([KeyboardButton("🎓 К выбору курса"), KeyboardButton("🏠 Главное меню")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    total_pages = (len(course_lessons) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    text = f"📚 {course_name}\n\n"
    text += f"Страница {page + 1}/{total_pages}\n\n"
    text += "Выберите занятие:"
    
    await update.message.reply_text(text, reply_markup=reply_markup)

async def show_drugs_for_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE, course_name, lesson_name, page=0):
    """Показать препараты для конкретного занятия с пагинацией"""
    lesson_drugs = get_drugs_by_lesson(course_name, lesson_name)
    
    if not lesson_drugs:
        await update.message.reply_text(f"В занятии '{lesson_name}' пока нет препаратов.")
        return
    
    # Получаем все занятия текущего курса для навигации
    course_lessons = list(COURSE_GROUPS.get(course_name, {}).keys())
    current_lesson_index = course_lessons.index(lesson_name)
    
    # Сохраняем информацию о текущем занятии
    context.user_data['current_course'] = course_name
    context.user_data['current_lesson'] = lesson_name
    context.user_data['current_lesson_index'] = current_lesson_index
    context.user_data['lesson_drugs'] = lesson_drugs
    context.user_data['drugs_page'] = page
    
    # Разделяем препараты на страницы
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_drugs = lesson_drugs[start_idx:end_idx]
    
    # Создаем кнопки для препаратов с короткими названиями
    keyboard = []
    for i in range(0, len(page_drugs), BUTTONS_PER_ROW):
        row = []
        for j in range(BUTTONS_PER_ROW):
            if i + j < len(page_drugs):
                drug = page_drugs[i + j]
                short_name = extract_short_name(drug['name'])
                # Обрезаем слишком длинные названия
                if len(short_name) > 30:
                    short_name = short_name[:27] + "..."
                button_text = f"{short_name}"
                row.append(KeyboardButton(button_text))
        keyboard.append(row)
    
    # Добавляем кнопки навигации по препаратам
    nav_buttons = []
    if page > 0:
        nav_buttons.append(KeyboardButton("⬅️ Назад"))
    if end_idx < len(lesson_drugs):
        nav_buttons.append(KeyboardButton("Далее ➡️"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопки навигации по занятиям
    lesson_nav_buttons = []
    if current_lesson_index > 0:
        prev_lesson = course_lessons[current_lesson_index - 1]
        lesson_nav_buttons.append(KeyboardButton(f"◀️ {prev_lesson}"))
    
    if current_lesson_index < len(course_lessons) - 1:
        next_lesson = course_lessons[current_lesson_index + 1]
        lesson_nav_buttons.append(KeyboardButton(f"{next_lesson} ▶️"))
    
    if lesson_nav_buttons:
        keyboard.append(lesson_nav_buttons)
    
    # Кнопки управления - ВМЕСТЕ на одном уровне
    keyboard.append([KeyboardButton("📚 К списку занятий"), KeyboardButton("🎓 К выбору курса")])
    keyboard.append([KeyboardButton("🏠 Главное меню")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    text = f"📚 {course_name} - {lesson_name}\n\n"
    text += f"Препараты {start_idx + 1}-{min(end_idx, len(lesson_drugs))} из {len(lesson_drugs)}\n\n"
    text += "Выберите препарат:"
    
    await update.message.reply_text(text, reply_markup=reply_markup)

async def show_drug_details(update: Update, context: ContextTypes.DEFAULT_TYPE, drug, from_test=False):
    """Показать детали препарата с фото и рисунком в одном сообщении"""
    # Формируем текст препарата
    text = f"🔬 <b>{drug['name']}</b>\n\n"
    
    if drug.get('staining'):
        text += f"🎨 <b>Окраска:</b> {drug['staining']}\n\n"
    
    if drug.get('description'):
        text += f"📋 <b>Описание:</b>\n{drug['description']}\n\n"
    
    # Записываем просмотр
    if not from_test:
        db.record_drug_view(update.effective_user.id, drug['id'], 'view')
    
    # Сохраняем текущий препарат в контексте
    context.user_data['current_drug'] = drug
    
    # Получаем препараты текущего занятия
    lesson_drugs = context.user_data.get('lesson_drugs', [])
    
    # Создаем кнопки для ВСЕХ препаратов занятия
    keyboard = []
    
    # Разбиваем препараты на строки по 2 кнопки
    for i in range(0, len(lesson_drugs), BUTTONS_PER_ROW):
        row = []
        for j in range(BUTTONS_PER_ROW):
            if i + j < len(lesson_drugs):
                current_drug_item = lesson_drugs[i + j]
                short_name = extract_short_name(current_drug_item['name'])
                # Обрезаем слишком длинные названия
                if len(short_name) > 30:
                    short_name = short_name[:27] + "..."
                
                # Добавляем 📋 к текущему просматриваемому препарату
                if current_drug_item['id'] == drug['id']:
                    button_text = f"📋 {short_name}"
                else:
                    button_text = f"{short_name}"
                
                row.append(KeyboardButton(button_text))
        if row:  # Добавляем только непустые строки
            keyboard.append(row)
    
    # Кнопки управления - ВМЕСТЕ на одном уровне
    keyboard.append([KeyboardButton("📚 К списку занятий"), KeyboardButton("🎓 К выбору курса")])
    keyboard.append([KeyboardButton("🏠 Главное меню")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    try:
        media_items = []
        
        # Добавляем фото препарата (если есть корректный File ID)
        if drug.get('photo') and isinstance(drug['photo'], str):
            # Проверяем, что это похоже на File ID (начинается с AgA или BQAC)
            if drug['photo'].startswith(('AgA', 'BQAC')):
                media_items.append(InputMediaPhoto(
                    media=drug['photo'],
                    caption=text,
                    parse_mode='HTML'
                ))
            else:
                logger.warning(f"Некорректный photo File ID для препарата {drug['id']}: {drug['photo'][:50]}...")
        
        # Добавляем рисунок препарата (если есть корректный File ID)
        if drug.get('drawing') and isinstance(drug['drawing'], str):
            # Проверяем, что это похоже на File ID
            if drug['drawing'].startswith(('AgA', 'BQAC')):
                if media_items:  # Если уже есть фото, добавляем без caption
                    media_items.append(InputMediaPhoto(
                        media=drug['drawing']
                    ))
                else:  # Если фото нет, добавляем рисунок с caption
                    media_items.append(InputMediaPhoto(
                        media=drug['drawing'],
                        caption=text,
                        parse_mode='HTML'
                    ))
            elif drug['drawing'].startswith('images/'):
                logger.warning(f"Рисунок для препарата {drug['id']} - путь к файлу, а не File ID")
            else:
                logger.warning(f"Некорректный drawing File ID для препарата {drug['id']}: {drug['drawing'][:50]}...")
        
        # Отправляем альбом или отдельное сообщение
        if media_items:
            try:
                await update.message.reply_media_group(
                    media=media_items
                )
                
                # Отправляем кнопки управления
                await update.message.reply_text(
                    "Выберите препарат:",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка отправки альбома: {e}")
                # Резервный вариант - отправляем текст с кнопками
                await update.message.reply_text(
                    text + "\n\n⚠️ Ошибка загрузки изображений",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
        else:
            # Если нет фото, отправляем только текст
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Критическая ошибка в show_drug_details: {e}")
        # Резервный вариант
        short_name = extract_short_name(drug['name'])
        await update.message.reply_text(
            f"🔬 {short_name}\n\n" +
            (f"🎨 {drug.get('staining', '')}\n\n" if drug.get('staining') else "") +
            "Выберите препарат:",
            reply_markup=reply_markup
        )

async def start_test_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать одиночный тест"""
    if not DRUGS:
        await update.message.reply_text("Нет препаратов для тестирования.")
        return
    
    random_drug = random.choice(DRUGS)
    
    USER_STATES[update.effective_user.id] = {
        'mode': 'test_single',
        'current_drug': random_drug,
        'awaiting_answer': True,
        'was_wrong': False  # Флаг для отслеживания неправильного ответа
    }
    
    drug = random_drug
    
    # Только при показе вопроса - кнопки для вопроса
    keyboard = [
        [KeyboardButton("🤷‍♂️ Не знаю")],
        [KeyboardButton("🏠 Главное меню")]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    caption = "🧪 Угадайте препарат\n\nВведите в формате:\nНазвание (Окраска)"
    
    if drug.get('photo') and isinstance(drug['photo'], str) and drug['photo'].startswith(('AgA', 'BQAC')):
        try:
            await update.message.reply_photo(
                photo=drug['photo'],
                caption=caption,
                reply_markup=reply_markup
            )
        except Exception as e:
            await update.message.reply_text(
                f"{caption}\n\n(Ошибка загрузки изображения)",
                reply_markup=reply_markup
            )
    else:
        await update.message.reply_text(caption, reply_markup=reply_markup)

async def start_run_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать прогон всех препаратов"""
    if not DRUGS:
        await update.message.reply_text("Нет препаратов для тестирования.")
        return
    
    shuffled_drugs = DRUGS.copy()
    random.shuffle(shuffled_drugs)
    
    USER_STATES[update.effective_user.id] = {
        'mode': 'run_all',
        'remaining_drugs': shuffled_drugs,
        'correct_answers': 0,
        'total_questions': 0,
        'awaiting_answer': True,
        'current_index': 0,
        'was_wrong': False  # Флаг для отслеживания неправильного ответа
    }
    
    await send_next_question(update, context)

async def send_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить следующий вопрос"""
    user_id = update.effective_user.id
    state = USER_STATES.get(user_id)
    
    if not state:
        return
    
    if state['mode'] == 'run_all' and not state['remaining_drugs']:
        # Прогон завершен
        result_text = (
            f"🏁 Прогон завершен!\n\n"
            f"📊 Результаты:\n"
            f"• Всего вопросов: {state['total_questions']}\n"
            f"• Правильных ответов: {state['correct_answers']}\n"
            f"• Процент правильных: {state['correct_answers']/state['total_questions']*100:.1f}%\n\n"
        )
        
        keyboard = [
            [KeyboardButton("🔄 Еще раз")],
            [KeyboardButton("🏠 Главное меню")]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(result_text, reply_markup=reply_markup)
        
        del USER_STATES[user_id]
        return
    
    if state['mode'] == 'run_all':
        drug = state['remaining_drugs'].pop(0)
        state['current_drug'] = drug
        state['current_index'] += 1
        state['was_wrong'] = False  # Сбрасываем флаг неправильного ответа
        
        progress = f" ({state['current_index']}/{len(DRUGS)})"
    else:
        drug = state['current_drug']
        state['was_wrong'] = False  # Сбрасываем флаг неправильного ответа
        progress = ""
    
    # Только при показе вопроса - кнопки для вопроса
    keyboard = [
        [KeyboardButton("🤷‍♂️ Не знаю")],
        [KeyboardButton("🏠 Главное меню")]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    caption = f"🧪 Угадайте препарат{progress}\n\nВведите в формате:\nНазвание (Окраска)"
    
    if drug.get('photo') and isinstance(drug['photo'], str) and drug['photo'].startswith(('AgA', 'BQAC')):
        try:
            await update.message.reply_photo(
                photo=drug['photo'],
                caption=caption,
                reply_markup=reply_markup
            )
        except Exception as e:
            await update.message.reply_text(
                f"{caption}\n\n(Ошибка загрузки изображения)",
                reply_markup=reply_markup
            )
    else:
        await update.message.reply_text(caption, reply_markup=reply_markup)

async def handle_test_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответов на тестовые вопросы"""
    user_id = update.effective_user.id
    state = USER_STATES.get(user_id)
    
    if not state or not state.get('awaiting_answer'):
        # Если это не ответ на тест, проверяем обычные команды
        await handle_button(update, context)
        return
    
    user_answer = update.message.text.strip()
    
    # Если это кнопка "🏠 Главное меню", выходим
    if user_answer == "🏠 Главное меню":
        del USER_STATES[user_id]
        await show_main_menu(update, context)
        return
    
    drug = state['current_drug']
    
    # Проверка ответа
    user_name = ""
    user_staining = ""
    
    if '(' in user_answer and ')' in user_answer:
        name_end = user_answer.find('(')
        user_name = user_answer[:name_end].strip()
        
        staining_start = user_answer.find('(') + 1
        staining_end = user_answer.find(')')
        if staining_start < staining_end:
            user_staining = user_answer[staining_start:staining_end].strip()
    else:
        user_name = user_answer
        user_staining = ""
    
    correct_name = drug['name']
    correct_staining = drug.get('staining', '')
    
    name_correct = check_name_similarity(user_name, correct_name, drug['id'])
    staining_correct = True
    
    if correct_staining:
        if user_staining:
            staining_correct = check_staining_similarity(user_staining, correct_staining)
        else:
            staining_correct = False
    
    all_correct = name_correct and staining_correct
    
    correct_answer = correct_name
    if correct_staining:
        correct_answer += f" ({correct_staining})"
    
    result_text = f"Правильный ответ: {correct_answer}\n\n"
    
    if all_correct:
        result_text += "✅ Все верно! Отличная работа!\n\n"
        if state['mode'] == 'run_all':
            state['correct_answers'] += 1
            db.record_test_result(user_id, drug['id'], True)
    else:
        result_text += "❌ Есть ошибки:\n"
        if not name_correct:
            result_text += f"• Название неверно\n"
        if not staining_correct and correct_staining:
            result_text += f"• Окраска неверна\n"
        
        if state['mode'] == 'run_all':
            db.record_test_result(user_id, drug['id'], False)
        
        # Устанавливаем флаг, что ответ был неправильный
        state['was_wrong'] = True
    
    if state['mode'] == 'run_all':
        state['total_questions'] += 1
    
    # Формируем кнопки ПОСЛЕ ответа
    keyboard = []
    
    # Кнопку "✅ Засчитать" показываем ТОЛЬКО если ответ был неправильный
    if state.get('was_wrong') or not all_correct:
        if state['mode'] == 'run_all':
            keyboard.append([KeyboardButton("✅ Засчитать"), KeyboardButton("➡️ Следующий вопрос")])
        else:
            keyboard.append([KeyboardButton("✅ Засчитать"), KeyboardButton("🔄 Новый вопрос")])
    else:
        # Если ответ правильный - показываем только кнопки продолжения
        if state['mode'] == 'run_all':
            keyboard.append([KeyboardButton("➡️ Следующий вопрос")])
        else:
            keyboard.append([KeyboardButton("🔄 Новый вопрос")])
    
    # Кнопку "🔍 Подробнее о препарате" показываем всегда
    keyboard.append([KeyboardButton("🔍 Подробнее о препарате")])
    keyboard.append([KeyboardButton("🏠 Главное меню")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(result_text, reply_markup=reply_markup)
    
    if state['mode'] == 'test_single':
        state['awaiting_answer'] = False  # Не удаляем сразу, ждем действий пользователя
    else:
        state['awaiting_answer'] = False

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий кнопок"""
    text = update.message.text
    user_id = update.effective_user.id
    
    # Сначала проверяем, если это кнопка "🏠 Главное меню" - сразу выходим в меню
    if text == "🏠 Главное меню":
        # Очищаем состояние теста, если оно было
        if user_id in USER_STATES:
            del USER_STATES[user_id]
        await show_main_menu(update, context)
        return
    
    # Проверяем, не ожидаем ли мы ответ на тест
    state = USER_STATES.get(user_id)
    if state and state.get('awaiting_answer'):
        await handle_test_answer(update, context)
        return
    
    # Главное меню (уже обработано выше)
    
    # Список препаратов
    elif text == "📚 Список препаратов":
        await show_courses_menu(update, context)
    
    # Проверить себя (переименовано)
    elif text == "🧪 Мне повезет!":
        await start_test_single(update, context)
    
    # Прогон всех препаратов
    elif text == "🏃 Прогон всех препаратов":
        await start_run_all(update, context)
    
    # Помощь
    elif text == "❓ Помощь":
        await help_command(update, context)
    
    # Выбор курса
    elif text in ["🎓 1 курс", "🎓 2 курс"]:
        course_name = text.replace("🎓 ", "")
        await show_lessons_menu(update, context, course_name, page=0)
    
    # К выбору курса
    elif text == "🎓 К выбору курса":
        await show_courses_menu(update, context)
    
    # К списку занятий
    elif text == "📚 К списку занятий":
        course_name = context.user_data.get('current_course')
        if course_name:
            await show_lessons_menu(update, context, course_name, page=0)
        else:
            await show_courses_menu(update, context)
    
    # Навигация по страницам занятий
    elif text in ["⬅️ Назад", "Далее ➡️"]:
        course_name = context.user_data.get('current_course')
        current_page = context.user_data.get('lessons_page', 0)
        
        if text == "⬅️ Назад":
            current_page = max(0, current_page - 1)
        else:
            current_page += 1
        
        context.user_data['lessons_page'] = current_page
        await show_lessons_menu(update, context, course_name, current_page)
    
    # Навигация по занятиям (предыдущее/следующее)
    elif text.endswith(" ▶️") or text.startswith("◀️ "):
        course_name = context.user_data.get('current_course')
        if not course_name:
            await update.message.reply_text("Сначала выберите курс")
            return
        
        course_lessons = list(COURSE_GROUPS.get(course_name, {}).keys())
        
        if text.endswith(" ▶️"):  # Следующее занятие
            next_lesson = text.replace(" ▶️", "")
            if next_lesson in course_lessons:
                await show_drugs_for_lesson(update, context, course_name, next_lesson, page=0)
        
        elif text.startswith("◀️ "):  # Предыдущее занятие
            prev_lesson = text.replace("◀️ ", "")
            if prev_lesson in course_lessons:
                await show_drugs_for_lesson(update, context, course_name, prev_lesson, page=0)
    
    # Выбор занятия
    elif text in [lesson for course in COURSE_GROUPS.values() for lesson in course.keys()]:
        course_name = context.user_data.get('current_course')
        if course_name:
            await show_drugs_for_lesson(update, context, course_name, text, page=0)
        else:
            # Если курс не определен, ищем в каком курсе находится это занятие
            for c_name, lessons in COURSE_GROUPS.items():
                if text in lessons:
                    context.user_data['current_course'] = c_name
                    await show_drugs_for_lesson(update, context, c_name, text, page=0)
                    break
    
    # Команды тестирования
    elif text == "🤷‍♂️ Не знаю":
        state = USER_STATES.get(user_id)
        if state and state.get('awaiting_answer'):
            drug = state['current_drug']
            correct_answer = drug['name']
            if drug.get('staining'):
                correct_answer += f" ({drug['staining']})"
            
            result_text = f"Правильный ответ: {correct_answer}\n\n❌ Вы не знали ответ\n\nПопробуйте еще раз!"
            
            # Устанавливаем флаг неправильного ответа
            state['was_wrong'] = True
            
            # Формируем кнопки - показываем "✅ Засчитать" так как ответ был неправильный
            keyboard = []
            if state['mode'] == 'run_all':
                keyboard.append([KeyboardButton("✅ Засчитать"), KeyboardButton("➡️ Следующий вопрос")])
            else:
                keyboard.append([KeyboardButton("✅ Засчитать"), KeyboardButton("🔄 Новый вопрос")])
            
            keyboard.append([KeyboardButton("🔍 Подробнее о препарате")])
            keyboard.append([KeyboardButton("🏠 Главное меню")])
            
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(result_text, reply_markup=reply_markup)
            
            if state['mode'] == 'run_all':
                state['total_questions'] += 1
                state['awaiting_answer'] = False
                db.record_test_result(user_id, drug['id'], False)
            else:
                state['awaiting_answer'] = False  # Не удаляем состояние, ждем действий
    
    elif text == "✅ Засчитать":
        state = USER_STATES.get(user_id)
        if state:
            drug = state.get('current_drug')
            if drug:
                # Записываем результат как правильный
                if state['mode'] == 'run_all':
                    state['correct_answers'] += 1
                    # Если уже записали как неправильный, нужно обновить запись
                    db.record_test_result(user_id, drug['id'], True)
                else:
                    # Для одиночного теста тоже записываем результат
                    db.record_test_result(user_id, drug['id'], True)
                
                correct_answer = drug['name']
                if drug.get('staining'):
                    correct_answer += f" ({drug['staining']})"
                
                await update.message.reply_text(
                    f"✅ Ответ засчитан как правильный!\n\nПравильный ответ: {correct_answer}"
                )
                
                # Продолжаем тест
                if state['mode'] == 'run_all':
                    state['awaiting_answer'] = True
                    await send_next_question(update, context)
                else:
                    # Для одиночного теста предлагаем новый вопрос
                    await start_test_single(update, context)
    
    elif text == "➡️ Следующий вопрос":
        state = USER_STATES.get(user_id)
        if state and state['mode'] == 'run_all':
            state['awaiting_answer'] = True
            await send_next_question(update, context)
    
    elif text == "🔄 Новый вопрос":
        await start_test_single(update, context)
    
    elif text == "🔍 Подробнее о препарате":
        state = USER_STATES.get(user_id)
        if state and 'current_drug' in state:
            drug = state['current_drug']
            
            # Формируем текст препарата
            text_drug = f"🔬 <b>{drug['name']}</b>\n\n"
            
            if drug.get('staining'):
                text_drug += f"🎨 <b>Окраска:</b> {drug['staining']}\n\n"
            
            if drug.get('description'):
                text_drug += f"📋 <b>Описание:</b>\n{drug['description']}\n\n"
            
            # Создаем специальные кнопки для режима теста
            keyboard = []
            
            # Показываем "✅ Засчитать" только если был неправильный ответ
            if state.get('was_wrong', False):
                if state['mode'] == 'run_all':
                    keyboard.append([KeyboardButton("✅ Засчитать"), KeyboardButton("➡️ Следующий вопрос")])
                else:
                    keyboard.append([KeyboardButton("✅ Засчитать"), KeyboardButton("🔄 Новый вопрос")])
            else:
                # Если ответ был правильный
                if state['mode'] == 'run_all':
                    keyboard.append([KeyboardButton("➡️ Следующий вопрос")])
                else:
                    keyboard.append([KeyboardButton("🔄 Новый вопрос")])
            
            keyboard.append([KeyboardButton("🏠 Главное меню")])
            
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            try:
                media_items = []
                
                # Добавляем фото препарата
                if drug.get('photo') and isinstance(drug['photo'], str) and drug['photo'].startswith(('AgA', 'BQAC')):
                    media_items.append(InputMediaPhoto(
                        media=drug['photo'],
                        caption=text_drug,
                        parse_mode='HTML'
                    ))
                
                # Добавляем рисунок препарата
                if drug.get('drawing') and isinstance(drug['drawing'], str) and drug['drawing'].startswith(('AgA', 'BQAC')):
                    if media_items:
                        media_items.append(InputMediaPhoto(media=drug['drawing']))
                    else:
                        media_items.append(InputMediaPhoto(
                            media=drug['drawing'],
                            caption=text_drug,
                            parse_mode='HTML'
                        ))
                
                if media_items:
                    try:
                        await update.message.reply_media_group(media=media_items)
                        await update.message.reply_text("Что дальше?", reply_markup=reply_markup)
                    except Exception as e:
                        await update.message.reply_text(
                            text_drug + "\n\n⚠️ Ошибка загрузки изображений",
                            reply_markup=reply_markup,
                            parse_mode='HTML'
                        )
                else:
                    await update.message.reply_text(text_drug, reply_markup=reply_markup, parse_mode='HTML')
                    
            except Exception as e:
                logger.error(f"Ошибка в деталях препарата: {e}")
                await update.message.reply_text(
                    f"🔬 {drug['name']}\n\n" +
                    (f"🎨 {drug.get('staining', '')}\n\n" if drug.get('staining') else "") +
                    "Что дальше?",
                    reply_markup=reply_markup
                )
    
    elif text == "🔄 Еще раз":
        await start_run_all(update, context)
    
    else:
        # Проверяем, не является ли это названием препарата
        # Получаем препараты текущего занятия
        lesson_drugs = context.user_data.get('lesson_drugs', [])
        
        # Чистим текст от эмодзи 📋
        clean_text = text.replace("📋 ", "").strip()
        
        # Ищем препарат по точному совпадению короткого названия
        for drug in lesson_drugs:
            short_name = extract_short_name(drug['name'])
            
            # Проверяем точное совпадение
            if clean_text == short_name:
                # Нашли препарат - показываем его
                await show_drug_details(update, context, drug)
                return
            
            # Проверяем частичное совпадение (если название обрезано)
            if len(short_name) > 30 and clean_text == short_name[:27] + "...":
                await show_drug_details(update, context, drug)
                return
        
        # Если не нашли, проверяем среди всех препаратов (для тестового режима)
        for drug in DRUGS:
            short_name = extract_short_name(drug['name'])
            if clean_text == short_name or (len(short_name) > 30 and clean_text == short_name[:27] + "..."):
                await show_drug_details(update, context, drug, from_test=True)
                return
        
        await update.message.reply_text(
            "Я не понял команду. Используйте кнопки меню 👇",
            reply_markup=ReplyKeyboardMarkup([["🏠 Главное меню"]], resize_keyboard=True)
        )

def main():
    TOKEN = config.BOT_TOKEN
    
    application = Application.builder().token(TOKEN).build()

    # Проверка доступа выполняется первой для каждого обновления, включая
    # команды, обычные сообщения и другие действия пользователя.
    application.add_handler(TypeHandler(Update, access_guard), group=-1)
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", show_main_menu))
    application.add_handler(CommandHandler("add_access", add_access_command))
    application.add_handler(CommandHandler("remove_access", remove_access_command))
    application.add_handler(CommandHandler("access_list", access_list_command))
    
    # Обработчик всех текстовых сообщений
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_button
    ))
    
    print("🤖 Бот запущен! Нажмите Ctrl+C для остановки.")
    print("✨ Основные исправления:")
    print("   1. Исправлена логика кнопок в тестах:")
    print("      - На этапе вопроса: только '🤷‍♂️ Не знаю' и '🏠 Главное меню'")
    print("      - После ответа: '✅ Засчитать' показывается только при неправильном ответе")
    print("   2. Удалена админ-панель")
    print("   3. Переименовано '🧪 Проверить себя' на '🧪 Мне повезет!'")
    print("   4. Кнопка '🔍 Подробнее о препарате' корректно работает")
    print("   5. Улучшена навигация в режимах тестирования")
    
    # Локально используем polling. На Render Web Service переключаемся на
    # webhook и слушаем обязательный HTTP-порт Render.
    if os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_URL"):
        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        if not render_url:
            raise RuntimeError("Для Render Web Service не задан RENDER_EXTERNAL_URL")

        port = int(os.environ.get("PORT", "10000"))
        webhook_url = f"{render_url.rstrip('/')}/{config.WEBHOOK_PATH}"
        print(f"🌐 Запуск webhook на 0.0.0.0:{port}")
        print(f"🔗 Webhook URL: {webhook_url}")

        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=config.WEBHOOK_PATH,
            webhook_url=webhook_url,
            secret_token=config.WEBHOOK_SECRET,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    if not os.path.exists('drugs_data.json'):
        print("❌ Файл drugs_data.json не найден!")
        exit(1)
    
    print("✅ Все проверки пройдены. Запускаю бота...")
    print(f"📊 Загружено препаратов: {len(DRUGS)}")
    main()
