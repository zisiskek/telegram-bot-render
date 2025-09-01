import asyncio
import json
import os
import datetime
import pytz
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

TOKEN = "8326284268:AAFsF3Xyc9_AfvxZiMiXc-rlLXsHb7OR7iY"
bot = Bot(token=TOKEN)
dp = Dispatcher()

# FSM для логина
class LoginStates(StatesGroup):
    waiting_username = State()
    waiting_password = State()

# FSM для добавления образца
class SampleStates(StatesGroup):
    waiting_number = State()
    waiting_department = State()
    waiting_tests = State()

# FSM для поиска
class SearchStates(StatesGroup):
    waiting_query = State()

# Пользователи с ролями (можно добавить больше логинов)
USERS = {
    "director": {"password": "dir123", "role": 1},
    "lab": {"password": "5678", "role": 2},
    "viewer": {"password": "0000", "role": 3},
}

# Файл для хранения образцов
SAMPLES_FILE = "samples.json"

# Часовой пояс Москвы
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Форматирование даты в дд.мм.гггг чч:мм
def format_datetime(dt_str):
    if not dt_str:
        return '-'
    dt = datetime.datetime.fromisoformat(dt_str.replace('+03:00', '+03:00'))
    dt = dt.astimezone(MOSCOW_TZ)
    return dt.strftime('%d.%m.%Y %H:%M')

# Загрузка образцов с миграцией старых данных
def load_samples():
    if os.path.exists(SAMPLES_FILE):
        with open(SAMPLES_FILE, 'r', encoding='utf-8') as f:
            samples = json.load(f)
        # Миграция: добавляем недостающие поля
        for sample in samples:
            if 'created_at' not in sample:
                sample['created_at'] = datetime.datetime.now().isoformat()
            for test in sample['tests']:
                if 'transferred_at' not in test:
                    test['transferred_at'] = None
                if 'completed_at' not in test:
                    test['completed_at'] = None
        return samples
    return []

# Сохранение образцов в файл
def save_samples(samples):
    with open(SAMPLES_FILE, 'w', encoding='utf-8') as f:
        json.dump(samples, f, ensure_ascii=False, indent=4)

SAMPLES = load_samples()

# ЗаLogged-in пользователи (user_id: {"role": role, "username": username})
logged_in = {}

# Чат-ид для уведомлений (роль: set(chat_ids))
notification_chats = {
    1: set(),  # директора
    2: set(),  # лаборанты
}

departments = ["3","5","7","10","кп","склад 271","склад 272","склад 274","склад 6002","псэт","пск","ПОПС","сварщики","метизы","ОгМет"]

mech_tests = ["рг","рх","уд","загиб","сварка","тверд"]
metal_tests = ["нем","мкк","макро"]
chem_tests = ["хим"]

def get_today_changes(samples, test_names):
    today = datetime.datetime.now(MOSCOW_TZ).date()
    changes_by_dept = {dept: [] for dept in departments}
    for sample in samples:
        dept = sample["department"]
        if dept not in changes_by_dept:
            continue
        changes = []
        for test in sample["tests"]:
            if test["name"] in test_names:
                completed_at = test.get("completed_at")
                if completed_at and datetime.datetime.fromisoformat(completed_at).astimezone(MOSCOW_TZ).date() == today:
                    changes.append(test['name'])
        if changes:
            changes_by_dept[dept].append(f"{sample['number']} ({', '.join(changes)})")
    return {dept: '; '.join(items) if items else '-' for dept, items in changes_by_dept.items()}

def get_in_work(samples):
    in_work_by_dept = {dept: [] for dept in departments}
    for sample in samples:
        dept = sample["department"]
        if dept not in in_work_by_dept:
            continue
        tests_in_work = [test["name"] for test in sample["tests"] if test["status"] == "в работе"]
        if tests_in_work:
            in_work_by_dept[dept].append(f"{sample['number']} ({', '.join(tests_in_work)})")
    return {dept: '; '.join(items) if items else '-' for dept, items in in_work_by_dept.items()}

def add_table_to_fig(ax, title, data, y_position, height):
    ax.text(0.5, y_position + 0.03, title, ha='center', va='center', fontsize=12)  # Заголовок над таблицей
    col_labels = ['Цех', 'Образцы']
    table_data = [[dept, data[dept]] for dept in departments]
    table = ax.table(cellText=table_data, colLabels=col_labels, loc='center', cellLoc='left',
                     bbox=[0.05, y_position - height, 0.9, height])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.2)  # Адаптация высоты строк под текст
    ax.axis('off')

def generate_report():
    today_str = datetime.datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y")
    report_file = "report.pdf"
    with PdfPages(report_file) as pdf:
        fig, ax = plt.subplots(figsize=(8, 11))
        ax.text(0.5, 0.95, today_str, ha='center', va='center', fontsize=12)

        # Механические испытания
        changes = get_today_changes(SAMPLES, mech_tests)
        add_table_to_fig(ax, "передано на мех испытания", changes, 0.85, 0.20)

        # Металлографические исследования
        changes = get_today_changes(SAMPLES, metal_tests)
        add_table_to_fig(ax, "передано на металлографические исследования", changes, 0.60, 0.20)

        # Химический анализ
        changes = get_today_changes(SAMPLES, chem_tests)
        add_table_to_fig(ax, "передано на хим анализ", changes, 0.35, 0.20)

        # В работе
        in_work = get_in_work(SAMPLES)
        add_table_to_fig(ax, "в работе", in_work, 0.10, 0.20)

        pdf.savefig(fig)
        plt.close()

# Главное меню
def get_main_menu(role):
    buttons = [[KeyboardButton(text="Поиск")]]
    if role == 1:
        buttons.append([KeyboardButton(text="Добавить образец")])
    if role in [1, 2]:
        buttons.append([KeyboardButton(text="Отчёт")])
    buttons.append([KeyboardButton(text="Выйти")])
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    return kb

# Команда /start
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await message.answer("Введите логин:")
    await state.set_state(LoginStates.waiting_username)

# Ввод логина
@dp.message(LoginStates.waiting_username)
async def process_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if username not in USERS:
        await message.answer("❌ Логин не найден. Попробуйте снова:")
        return
    await state.update_data(username=username)
    await message.answer("Введите пароль:")
    await state.set_state(LoginStates.waiting_password)

# Ввод пароля
@dp.message(LoginStates.waiting_password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = data["username"]
    if message.text.strip() != USERS[username]["password"]:
        await message.answer("❌ Неверный пароль. Попробуйте снова:")
        return
    role = USERS[username]["role"]
    user_id = message.from_user.id
    logged_in[user_id] = {"role": role, "username": username}
    notification_chats[role].add(message.chat.id)
    await message.answer(f"✅ Добро пожаловать, {username}!", reply_markup=get_main_menu(role))
    await state.clear()

# Выход из учётной записи
@dp.message(lambda m: m.text=="Выйти")
async def logout(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    role = logged_in.get(user_id, {}).get("role")
    if role:
        notification_chats[role].discard(message.chat.id)
    logged_in.pop(user_id, None)
    await message.answer("Вы вышли из учётной записи. Введите /start для входа снова.", reply_markup=types.ReplyKeyboardRemove())
    await state.clear()

# Начало добавления образца
@dp.message(lambda m: m.text=="Добавить образец")
async def add_sample_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    role = logged_in.get(user_id, {}).get("role", 0)
    if role != 1:
        await message.answer("❌ У вас нет доступа к добавлению образца.")
        return
    await message.answer("Введите номер образца:")
    await state.set_state(SampleStates.waiting_number)

# Ввод номера образца
@dp.message(SampleStates.waiting_number)
async def add_sample_number(message: types.Message, state: FSMContext):
    number = message.text.strip()
    await state.update_data(number=number)
    dept_buttons = [
        [InlineKeyboardButton(text=d, callback_data=f"dept_{d}")] for d in departments
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=dept_buttons)
    await message.answer("Выберите цех:", reply_markup=kb)
    await state.set_state(SampleStates.waiting_department)

# Выбор цеха
@dp.callback_query(lambda c: c.data and c.data.startswith("dept_"))
async def add_sample_department(callback: types.CallbackQuery, state: FSMContext):
    department = callback.data[5:]
    await state.update_data(department=department, tests=[])
    await show_tests_keyboard(callback.message, state)
    await callback.answer()
    await state.set_state(SampleStates.waiting_tests)

# Функция для показа клавиатуры тестов
async def show_tests_keyboard(message: types.Message, state: FSMContext):
    data = await state.get_data()
    current_tests = data.get("tests", [])
    test_buttons = [
        [InlineKeyboardButton(text=t, callback_data=f"test_{t}")] for t in
        ["рг","рх","уд","нем","мкк","тверд","сварка","макро","загиб","хим"]
    ]
    test_buttons.append([InlineKeyboardButton(text="Готово", callback_data="done")])
    kb = InlineKeyboardMarkup(inline_keyboard=test_buttons)
    await message.answer(f"Выберите виды испытаний (по одному, повторный клик удалит):\nТекущие: {', '.join(current_tests) or 'никаких'}", reply_markup=kb)

# Выбор видов испытаний
@dp.callback_query(lambda c: c.data and (c.data.startswith("test_") or c.data == "done"))
async def add_sample_tests(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if callback.data == "done":
        if not data.get("tests"):
            await callback.message.answer("❌ Выберите хотя бы одно испытание.")
            return
        tests_with_status = [{"name": t, "status": "в работе", "transferred_at": None, "completed_at": None} for t in data["tests"]]
        new_sample = {
            "number": data["number"],
            "department": data["department"],
            "tests": tests_with_status,
            "urgent": False,
            "created_at": datetime.datetime.now(MOSCOW_TZ).isoformat()
        }
        SAMPLES.append(new_sample)
        save_samples(SAMPLES)
        await callback.message.answer(f"✅ Образец {data['number']} добавлен! Цех: {data['department']}, испытания: {', '.join(data['tests'])}")
        await state.clear()
    else:
        test = callback.data[5:]
        tests = data.get("tests", [])
        if test in tests:
            tests.remove(test)
        else:
            tests.append(test)
        await state.update_data(tests=tests)
        await callback.message.edit_text(f"Выберите виды испытания (по одному, повторный клик удалит):\nТекущие: {', '.join(tests) or 'никаких'}", reply_markup=callback.message.reply_markup)
    await callback.answer()

# Поиск
@dp.message(lambda m: m.text=="Поиск")
async def search_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    role = logged_in.get(user_id, {}).get("role", 0)
    if role == 0:
        await message.answer("❌ Вы не авторизованы.")
        return
    await message.answer("Введите номер образца или его часть для поиска:")
    await state.set_state(SearchStates.waiting_query)

@dp.message(SearchStates.waiting_query)
async def process_search_query(message: types.Message, state: FSMContext):
    query = message.text.strip().lower()
    matching_samples = [(i, s) for i, s in enumerate(SAMPLES) if query in s["number"].lower()]
    if not matching_samples:
        await message.answer("❌ Нет совпадений.")
        await state.clear()
        return
    buttons = [
        [InlineKeyboardButton(text=f"{s['number']} ({s['department']})", callback_data=f"sample_{i}")]
        for i, s in matching_samples
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Выберите образец:", reply_markup=kb)
    await state.clear()

# Выбор образца из поиска
@dp.callback_query(lambda c: c.data and c.data.startswith("sample_"))
async def show_sample_details(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data[7:])
    sample = SAMPLES[index]
    user_id = callback.from_user.id
    role = logged_in.get(user_id, {}).get("role", 0)

    all_done = all(t["status"] == "испытано" for t in sample["tests"])
    any_transferred = any(t["status"] == "передано на испытания" for t in sample["tests"])
    general_status = "испытаны" if all_done else ("переданы на испытания" if any_transferred else "в работе")

    tests_info = "\n".join([f"- {t['name']}: {t['status']} (передан: {format_datetime(t.get('transferred_at'))}, испытан: {format_datetime(t.get('completed_at'))})" for t in sample["tests"]])
    urgent_info = " (срочный)" if sample["urgent"] else ""
    msg = f"Образец {sample['number']}{urgent_info}\nЦех: {sample['department']}\nСоздан: {format_datetime(sample['created_at'])}\nОбщий статус: {general_status}\nИспытания:\n{tests_info}"

    buttons = []
    if role == 1:
        buttons.append([InlineKeyboardButton(text="Удалить", callback_data=f"delete_{index}")])
        urgent_text = "Снять срочный" if sample["urgent"] else "Сделать срочным"
        buttons.append([InlineKeyboardButton(text=urgent_text, callback_data=f"urgent_{index}")])
    if role in [1, 2]:
        buttons.append([InlineKeyboardButton(text="Изменить статус испытания", callback_data=f"edit_test_{index}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await callback.message.answer(msg, reply_markup=kb)
    await callback.answer()

# Удаление образца (директор)
@dp.callback_query(lambda c: c.data and c.data.startswith("delete_"))
async def delete_sample(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    role = logged_in.get(user_id, {}).get("role", 0)
    if role != 1:
        await callback.answer("❌ Нет доступа.")
        return
    index = int(callback.data[7:])
    number = SAMPLES[index]["number"]
    del SAMPLES[index]
    save_samples(SAMPLES)
    await callback.message.answer(f"✅ Образец {number} удалён.")
    await callback.answer()

# Срочный статус (директор)
@dp.callback_query(lambda c: c.data and c.data.startswith("urgent_"))
async def toggle_urgent(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    role = logged_in.get(user_id, {}).get("role", 0)
    if role != 1:
        await callback.answer("❌ Нет доступа.")
        return
    index = int(callback.data[7:])
    sample = SAMPLES[index]
    sample["urgent"] = not sample["urgent"]
    save_samples(SAMPLES)
    status = "срочный" if sample["urgent"] else "не срочный"
    await callback.message.answer(f"✅ Образец {sample['number']} теперь {status}.")

    if sample["urgent"]:
        notification_msg = f"🚨 Срочный образец: {sample['number']}"
        for chat_id in notification_chats[1] | notification_chats[2]:
            try:
                await bot.send_message(chat_id, notification_msg)
            except:
                pass
    await callback.answer()

# Изменение статуса теста
@dp.callback_query(lambda c: c.data and c.data.startswith("edit_test_"))
async def edit_test_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    role = logged_in.get(user_id, {}).get("role", 0)
    if role not in [1, 2]:
        await callback.answer("❌ Нет доступа.")
        return
    index = int(callback.data[10:])
    sample = SAMPLES[index]
    buttons = [[InlineKeyboardButton(text=f"{t['name']} ({t['status']})", callback_data=f"select_test_{index}_{i}")] for i, t in enumerate(sample["tests"])]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.answer("Выберите испытание для изменения статуса:", reply_markup=kb)
    await callback.answer()

# Выбор теста для изменения
@dp.callback_query(lambda c: c.data and c.data.startswith("select_test_"))
async def select_test_for_status(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    sample_index = int(parts[2])
    test_index = int(parts[3])
    user_id = callback.from_user.id
    role = logged_in.get(user_id, {}).get("role", 0)
    sample = SAMPLES[sample_index]
    test = sample["tests"][test_index]
    current_status = test["status"]

    if role == 1:
        possible_statuses = ["в работе", "передано на испытания", "испытано"]
    else:  # role == 2
        possible_statuses = ["испытано"] if current_status != "испытано" else ["в работе"]

    if not possible_statuses:
        await callback.message.answer("❌ Нет доступных изменений для этого испытания.")
        await callback.answer()
        return

    buttons = [[InlineKeyboardButton(text=status, callback_data=f"set_status_{sample_index}_{test_index}_{status.replace(' ', '_')}")] for status in possible_statuses]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.answer(f"Выберите новый статус для {test['name']}:", reply_markup=kb)
    await callback.answer()

# Установка нового статуса
@dp.callback_query(lambda c: c.data and c.data.startswith("set_status_"))
async def set_test_status(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    sample_index = int(parts[2])
    test_index = int(parts[3])
    new_status = "_".join(parts[4:]).replace("_", " ")
    sample = SAMPLES[sample_index]
    test = sample["tests"][test_index]
    test["status"] = new_status
    if new_status == "передано на испытания" and not test.get("transferred_at"):
        test["transferred_at"] = datetime.datetime.now(MOSCOW_TZ).isoformat()
    if new_status == "испытано" and not test.get("completed_at"):
        test["completed_at"] = datetime.datetime.now(MOSCOW_TZ).isoformat()
    save_samples(SAMPLES)
    await callback.message.answer(f"✅ Статус {test['name']} изменён на {new_status}.")
    await callback.answer()

# Отправка отчёта
@dp.message(lambda m: m.text=="Отчёт")
async def send_report(message: types.Message):
    user_id = message.from_user.id
    role = logged_in.get(user_id, {}).get("role", 0)
    if role not in [1, 2]:
        await message.answer("❌ Нет доступа.")
        return
    try:
        generate_report()
        await message.answer_document(FSInputFile("report.pdf"))
    except Exception as e:
        await message.answer(f"❌ Ошибка при создании отчёта: {str(e)}")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))