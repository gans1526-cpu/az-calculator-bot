# -*- coding: utf-8 -*-
import telebot
from telebot import types
import sqlite3
import threading
import json
import logging
import time
import sys
import traceback
from datetime import datetime
import os
import requests

# === ДЛЯ СЕРВЕРА ===
from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 AZ-Calculator Bot is RUNNING 24/7!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

web_thread = threading.Thread(target=run_web)
web_thread.daemon = True
web_thread.start()
# === КОНЕЦ ===

# --- СИСТЕМА БЕЗОПАСНОСТИ ---
AUTHORIZED_USERS = {2055761928}
ADMIN_ID = 2055761928

# --- СТАТУС БОТА ---
BOT_START_TIME = datetime.now()
BOT_STATUS = "🟢 ОНЛАЙН"
LAST_UPDATE_TIME = datetime.now()

def update_bot_status():
    global LAST_UPDATE_TIME
    LAST_UPDATE_TIME = datetime.now()

def get_bot_uptime():
    uptime = datetime.now() - BOT_START_TIME
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}д {hours}ч {minutes}м"
    else:
        return f"{hours}ч {minutes}м {seconds}с"

def get_bot_status_info():
    global BOT_STATUS, LAST_UPDATE_TIME
    time_since_last_update = datetime.now() - LAST_UPDATE_TIME
    if time_since_last_update.total_seconds() > 300:
        BOT_STATUS = "🟡 НЕТ СВЯЗИ"
    elif time_since_last_update.total_seconds() > 600:
        BOT_STATUS = "🔴 ОФФЛАЙН"
    else:
        BOT_STATUS = "🟢 ОНЛАЙН"
    return {
        'status': BOT_STATUS,
        'uptime': get_bot_uptime(),
        'last_update': LAST_UPDATE_TIME.strftime("%H:%M:%S"),
        'start_time': BOT_START_TIME.strftime("%d.%m.%Y %H:%M:%S")
    }

def is_user_authorized(chat_id):
    return chat_id in AUTHORIZED_USERS

def add_authorized_user(chat_id):
    AUTHORIZED_USERS.add(chat_id)
    return True

def remove_authorized_user(chat_id):
    if chat_id in AUTHORIZED_USERS and chat_id != ADMIN_ID:
        AUTHORIZED_USERS.remove(chat_id)
        return True
    return False

def security_check(chat_id):
    if not is_user_authorized(chat_id):
        log_error(f"🚨 НЕАВТОРИЗОВАННЫЙ ДОСТУП: chat_id {chat_id}")
        return False
    return True

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_errors.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def log_error(error_message, exc_info=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if exc_info:
        error_details = f"\n{traceback.format_exc()}"
    else:
        error_details = ""
    full_error = f"[{timestamp}] ERROR: {error_message}{error_details}\n{'='*50}\n"
    try:
        with open('bot_errors.log', 'a', encoding='utf-8') as f:
            f.write(full_error)
    except Exception:
        print("Не удалось записать лог в файл.")
    print(full_error)
    logger.error(full_error)

# --- КОНСТАНТЫ ---
API_TOKEN = os.environ.get('API_TOKEN', '8242937436:AAEySDUKm1fjhraDeS3IzgHr9CPmqhDcGc0')
GOAL_PERCENTAGE = 0.015
MAX_STAKE_PERCENTAGE = 0.20
MIN_BANK_AMOUNT = 10.0
MAX_BANK_AMOUNT = 100000.0
MIN_COEFF = 1.1
MAX_COEFF = 9.9
DB_NAME = 'bot_state.db'
MAX_BANKS = 4
MAX_BET_HISTORY = 10

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
try:
    bot = telebot.TeleBot(API_TOKEN)
    print("✅ Бот инициализирован")
except Exception as e:
    log_error(f"Ошибка инициализации бота: {e}", exc_info=True)
    sys.exit(1)

db_lock = threading.Lock()

# --- БАЗА ДАННЫХ ---
def init_db():
    try:
        with db_lock:
            conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    current_bank_id INTEGER,
                    awaiting_input TEXT DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS banks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    name TEXT,
                    balance REAL DEFAULT 0,
                    day INTEGER DEFAULT 1,
                    initial_balance REAL DEFAULT 0,
                    daily_goal REAL DEFAULT 0,
                    current_target REAL DEFAULT 0,
                    current_coeff REAL DEFAULT 0,
                    current_stake REAL DEFAULT 0,
                    in_azamat_mode INTEGER DEFAULT 0,
                    loss_record TEXT DEFAULT '[]',
                    sub_goals TEXT DEFAULT '[]',
                    original_goal REAL DEFAULT 0,
                    total_bets INTEGER DEFAULT 0,
                    total_wins INTEGER DEFAULT 0,
                    bet_history TEXT DEFAULT '[]',
                    awaiting_bet_result INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES users (chat_id)
                )
            ''')
            cursor.execute("PRAGMA table_info(banks)")
            columns = [column[1] for column in cursor.fetchall()]
            new_columns = [
                ('sub_goals', "ALTER TABLE banks ADD COLUMN sub_goals TEXT DEFAULT '[]'"),
                ('original_goal', "ALTER TABLE banks ADD COLUMN original_goal REAL DEFAULT 0"),
                ('total_bets', "ALTER TABLE banks ADD COLUMN total_bets INTEGER DEFAULT 0"),
                ('total_wins', "ALTER TABLE banks ADD COLUMN total_wins INTEGER DEFAULT 0"),
                ('bet_history', "ALTER TABLE banks ADD COLUMN bet_history TEXT DEFAULT '[]'"),
                ('awaiting_bet_result', "ALTER TABLE banks ADD COLUMN awaiting_bet_result INTEGER DEFAULT 0")
            ]
            for col_name, sql in new_columns:
                if col_name not in columns:
                    cursor.execute(sql)
                    print(f"✅ Добавлена колонка '{col_name}'")
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_banks_chat_id ON banks(chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_chat_id ON users(chat_id)')
            conn.commit()
            conn.close()
        print("✅ База данных инициализирована")
    except Exception as e:
        log_error(f"Ошибка инициализации БД: {e}", exc_info=True)

def get_user_state(chat_id):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with db_lock:
                conn = sqlite3.connect(DB_NAME, check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE chat_id = ?', (chat_id,))
                user_data = cursor.fetchone()
                if not user_data:
                    cursor.execute(
                        'INSERT INTO users (chat_id, current_bank_id, awaiting_input) VALUES (?, NULL, "")',
                        (chat_id,)
                    )
                    conn.commit()
                    user_data = (chat_id, None, '', None)
                state = {
                    'chat_id': user_data[0],
                    'current_bank_id': user_data[1],
                    'awaiting_input': user_data[2] or ''
                }
                if state['current_bank_id']:
                    cursor.execute('SELECT * FROM banks WHERE id = ?', (state['current_bank_id'],))
                    bank_data = cursor.fetchone()
                    if bank_data:
                        columns = [description[0] for description in cursor.description]
                        bank_dict = dict(zip(columns, bank_data))
                        state.update({
                            'bank_id': bank_dict['id'],
                            'bank_name': bank_dict['name'],
                            'bank': float(bank_dict['balance'] or 0.0),
                            'day': int(bank_dict['day'] or 1),
                            'initial_balance': float(bank_dict['initial_balance'] or 0.0),
                            'daily_goal': float(bank_dict['daily_goal'] or 0.0),
                            'current_target': float(bank_dict['current_target'] or 0.0),
                            'current_coeff': float(bank_dict['current_coeff'] or 0.0),
                            'current_stake': float(bank_dict['current_stake'] or 0.0),
                            'in_azamat_mode': bool(bank_dict['in_azamat_mode']),
                            'loss_record': json.loads(bank_dict['loss_record']) if bank_dict['loss_record'] else [],
                            'sub_goals': json.loads(bank_dict.get('sub_goals', '[]')) if bank_dict.get('sub_goals') else [],
                            'original_goal': float(bank_dict.get('original_goal', 0) or 0.0),
                            'total_bets': int(bank_dict.get('total_bets', 0) or 0),
                            'total_wins': int(bank_dict.get('total_wins', 0) or 0),
                            'bet_history': json.loads(bank_dict.get('bet_history', '[]')) if bank_dict.get('bet_history') else [],
                            'awaiting_bet_result': bool(bank_dict.get('awaiting_bet_result', 0))
                        })
                conn.close()
                return state
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < max_retries - 1:
                time.sleep(0.1)
                continue
            else:
                log_error(f"Ошибка БД после {attempt + 1} попыток: {e}", exc_info=True)
                return {'chat_id': chat_id, 'awaiting_input': ''}
        except Exception as e:
            log_error(f"Неожиданная ошибка в get_user_state для {chat_id}: {e}", exc_info=True)
            return {'chat_id': chat_id, 'awaiting_input': ''}

def save_user_state(state):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with db_lock:
                conn = sqlite3.connect(DB_NAME, check_same_thread=False)
                cursor = conn.cursor()
                current_bank_id = state.get('bank_id')
                if current_bank_id is None:
                    current_bank_id = state.get('current_bank_id')
                cursor.execute('''
                    UPDATE users SET 
                    current_bank_id = ?, awaiting_input = ?
                    WHERE chat_id = ?
                ''', (
                    current_bank_id,
                    state.get('awaiting_input', ''),
                    state['chat_id']
                ))
                if 'bank_id' in state:
                    cursor.execute('''
                        UPDATE banks SET
                        balance = ?, day = ?, initial_balance = ?, daily_goal = ?, 
                        current_target = ?, current_coeff = ?, current_stake = ?, 
                        in_azamat_mode = ?, loss_record = ?, sub_goals = ?, original_goal = ?,
                        total_bets = ?, total_wins = ?, bet_history = ?, awaiting_bet_result = ?
                        WHERE id = ?
                    ''', (
                        float(state.get('bank', 0.0)),
                        int(state.get('day', 1)),
                        float(state.get('initial_balance', 0.0)),
                        float(state.get('daily_goal', 0.0)),
                        float(state.get('current_target', 0.0)),
                        float(state.get('current_coeff', 0.0)),
                        float(state.get('current_stake', 0.0)),
                        1 if state.get('in_azamat_mode', False) else 0,
                        json.dumps(state.get('loss_record', [])),
                        json.dumps(state.get('sub_goals', [])),
                        float(state.get('original_goal', 0.0)),
                        int(state.get('total_bets', 0)),
                        int(state.get('total_wins', 0)),
                        json.dumps(state.get('bet_history', [])),
                        1 if state.get('awaiting_bet_result', False) else 0,
                        int(state['bank_id'])
                    ))
                conn.commit()
                conn.close()
                return True
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < max_retries - 1:
                time.sleep(0.1)
                continue
            else:
                log_error(f"Ошибка БД при сохранении после {attempt + 1} попыток: {e}", exc_info=True)
                return False
        except Exception as e:
            log_error(f"Ошибка сохранения состояния пользователя {state.get('chat_id')}: {e}", exc_info=True)
            return False

def create_bank(chat_id, bank_name):
    try:
        bank_name = bank_name.strip()
        if not bank_name:
            return None, "❌ Название банка не может быть пустым!"
        if len(bank_name) > 30:
            return None, "❌ Название банка слишком длинное (макс. 30 символов)"
        with db_lock:
            conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM banks WHERE chat_id = ?', (chat_id,))
            bank_count = cursor.fetchone()[0]
            if bank_count >= MAX_BANKS:
                conn.close()
                return None, f"❌ Максимум {MAX_BANKS} банка!"
            cursor.execute('''
                INSERT INTO banks (chat_id, name, balance, day, initial_balance, daily_goal, sub_goals, original_goal, total_bets, total_wins, bet_history, awaiting_bet_result)
                VALUES (?, ?, 0, 1, 0, 0, '[]', 0, 0, 0, '[]', 0)
            ''', (chat_id, bank_name))
            bank_id = cursor.lastrowid
            cursor.execute(
                'UPDATE users SET current_bank_id = ? WHERE chat_id = ?',
                (bank_id, chat_id)
            )
            conn.commit()
            conn.close()
            return bank_id, f"✅ Банк '{bank_name}' создан!"
    except Exception as e:
        log_error(f"Ошибка создания банка для пользователя {chat_id}: {e}", exc_info=True)
        return None, "❌ Ошибка при создании банка"

def get_user_banks(chat_id):
    try:
        with db_lock:
            conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT id, name, balance, day FROM banks WHERE chat_id = ? ORDER BY created_at DESC', (chat_id,))
            banks = cursor.fetchall()
            bank_list = []
            for row in banks:
                bank_list.append({
                    'id': row[0], 
                    'name': row[1], 
                    'balance': float(row[2] or 0.0), 
                    'day': int(row[3] or 1)
                })
            conn.close()
            return bank_list
    except Exception as e:
        log_error(f"Ошибка получения банков пользователя {chat_id}: {e}", exc_info=True)
        return []

def switch_bank(chat_id, bank_id):
    try:
        with db_lock:
            conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE users SET current_bank_id = ? WHERE chat_id = ?',
                (bank_id, chat_id)
            )
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        log_error(f"Ошибка переключения банка {bank_id} для пользователя {chat_id}: {e}", exc_info=True)
        return False

def reset_bank_stats(bank_id):
    try:
        with db_lock:
            conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE banks SET 
                total_bets = 0, total_wins = 0, bet_history = '[]'
                WHERE id = ?
            ''', (bank_id,))
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        log_error(f"Ошибка очистки статистики банка {bank_id}: {e}", exc_info=True)
        return False

def delete_bank(chat_id, bank_id):
    try:
        with db_lock:
            conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM banks WHERE id = ? AND chat_id = ?', (bank_id, chat_id))
            bank_info = cursor.fetchone()
            if not bank_info:
                conn.close()
                return False, "❌ Банк не найден"
            bank_name = bank_info[0]
            cursor.execute('DELETE FROM banks WHERE id = ? AND chat_id = ?', (bank_id, chat_id))
            cursor.execute('SELECT current_bank_id FROM users WHERE chat_id = ?', (chat_id,))
            user_data = cursor.fetchone()
            if user_data and user_data[0] == bank_id:
                cursor.execute('UPDATE users SET current_bank_id = NULL WHERE chat_id = ?', (chat_id,))
            conn.commit()
            conn.close()
            return True, f"✅ Банк '{bank_name}' удален"
    except Exception as e:
        log_error(f"Ошибка удаления банка {bank_id} для пользователя {chat_id}: {e}", exc_info=True)
        return False, "❌ Ошибка при удалении банка"

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def calculate_stake(target, coefficient):
    try:
        if coefficient <= 1.0 or target <= 0:
            return 0.0
        stake = target / (coefficient - 1)
        return round(stake, 2)
    except Exception as e:
        log_error(f"Ошибка в calculate_stake: {e}", exc_info=True)
        return 0.0

def calculate_target_bank(initial_balance, day):
    try:
        return round(float(initial_balance) * (1.015 ** day), 2)
    except Exception as e:
        log_error(f"Ошибка в calculate_target_bank: {e}", exc_info=True)
        return 0.0

def calculate_daily_goal(current_bank, target_bank):
    try:
        return round(float(target_bank) - float(current_bank), 2)
    except Exception as e:
        log_error(f"Ошибка в calculate_daily_goal: {e}", exc_info=True)
        return 0.0

def get_target_day(current_bank, initial_balance):
    try:
        current_bank = float(current_bank or 0.0)
        initial_balance = float(initial_balance or 0.0)
        if initial_balance <= 0:
            return 1
        if current_bank < initial_balance:
            return 1
        target_day = 1
        for day in range(1, 301):
            target_bank = calculate_target_bank(initial_balance, day)
            if current_bank >= target_bank:
                target_day = day
            else:
                break
        return target_day
    except Exception as e:
        log_error(f"Ошибка в get_target_day: {e}", exc_info=True)
        return 1

def check_and_advance_day(state):
    try:
        initial = state.get('initial_balance', 0)
        current_bank = state.get('bank', 0)
        current_day = state.get('day', 1)
        target_day = get_target_day(current_bank, initial)
        new_day = target_day + 1
        if new_day > current_day:
            state['day'] = new_day
            state['in_azamat_mode'] = False
            state['loss_record'] = []
            state['sub_goals'] = []
            state['original_goal'] = 0
            target_bank_new = calculate_target_bank(initial, new_day)
            state['current_target'] = calculate_daily_goal(current_bank, target_bank_new)
            state['daily_goal'] = state['current_target']
            save_user_state(state)
            return True
        return False
    except Exception as e:
        log_error(f"Ошибка в check_and_advance_day: {e}", exc_info=True)
        return False

def calculate_azamat_target(state):
    try:
        loss_record = state.get('loss_record', [])
        if not loss_record:
            initial = state.get('initial_balance', 0)
            current_day = state.get('day', 1)
            target_bank = calculate_target_bank(initial, current_day)
            current_bank = state.get('bank', 0)
            return calculate_daily_goal(current_bank, target_bank)
        if len(loss_record) >= 2:
            return sum(loss_record[:2])
        else:
            initial = state.get('initial_balance', 0)
            current_day = state.get('day', 1)
            target_bank = calculate_target_bank(initial, current_day)
            current_bank = state.get('bank', 0)
            return calculate_daily_goal(current_bank, target_bank)
    except Exception as e:
        log_error(f"Ошибка в calculate_azamat_target: {e}", exc_info=True)
        initial = state.get('initial_balance', 0)
        current_day = state.get('day', 1)
        target_bank = calculate_target_bank(initial, current_day)
        current_bank = state.get('bank', 0)
        return calculate_daily_goal(current_bank, target_bank)

def add_bet_to_history(state, coefficient, result):
    try:
        bet_history = state.get('bet_history', [])
        bet_record = {
            'coefficient': coefficient,
            'result': result
        }
        bet_history.insert(0, bet_record)
        if len(bet_history) > MAX_BET_HISTORY:
            bet_history = bet_history[:MAX_BET_HISTORY]
        state['bet_history'] = bet_history
        return state
    except Exception as e:
        log_error(f"Ошибка добавления ставки в историю: {e}", exc_info=True)
        return state

def process_win(state):
    try:
        stake = float(state.get('current_stake', 0) or 0.0)
        coeff = float(state.get('current_coeff', 0) or 0.0)
        profit = stake * (coeff - 1)
        state['bank'] = round(float(state.get('bank', 0) or 0.0) + profit, 2)
        state['total_wins'] = int(state.get('total_wins', 0)) + 1
        state = add_bet_to_history(state, coeff, 'win')
        state['awaiting_bet_result'] = False
        if state.get('in_azamat_mode') and state.get('loss_record'):
            loss_record = state.get('loss_record', [])
            remaining_profit = profit
            new_loss_record = []
            for goal_amount in loss_record:
                if remaining_profit >= goal_amount:
                    remaining_profit -= goal_amount
                else:
                    if remaining_profit > 0:
                        new_goal_amount = goal_amount - remaining_profit
                        new_loss_record.append(round(new_goal_amount, 2))
                        remaining_profit = 0
                    else:
                        new_loss_record.append(goal_amount)
            state['loss_record'] = new_loss_record
            if not new_loss_record:
                state['in_azamat_mode'] = False
                initial = state.get('initial_balance', 0)
                current_day = state.get('day', 1)
                target_bank = calculate_target_bank(initial, current_day)
                current_bank = state.get('bank', 0)
                state['current_target'] = calculate_daily_goal(current_bank, target_bank)
            else:
                state['current_target'] = calculate_azamat_target(state)
                state['in_azamat_mode'] = True
        else:
            initial = state.get('initial_balance', 0)
            current_day = state.get('day', 1)
            target_bank = calculate_target_bank(initial, current_day)
            current_bank = state.get('bank', 0)
            state['current_target'] = calculate_daily_goal(current_bank, target_bank)
            state['in_azamat_mode'] = False
        return state
    except Exception as e:
        log_error(f"Ошибка в process_win: {e}", exc_info=True)
        return state

def process_loss(state):
    try:
        stake = float(state.get('current_stake', 0) or 0.0)
        state['bank'] = round(float(state.get('bank', 0) or 0.0) - stake, 2)
        state = add_bet_to_history(state, state.get('current_coeff', 0), 'loss')
        state['awaiting_bet_result'] = False
        if 'loss_record' not in state or state['loss_record'] is None:
            state['loss_record'] = []
        state['loss_record'].append(stake)
        if len(state['loss_record']) >= 2:
            state['in_azamat_mode'] = True
        if not state.get('in_azamat_mode'):
            initial = state.get('initial_balance', 0)
            current_day = state.get('day', 1)
            target_bank = calculate_target_bank(initial, current_day)
            current_bank = state.get('bank', 0)
            state['current_target'] = calculate_daily_goal(current_bank, target_bank)
        else:
            state['current_target'] = calculate_azamat_target(state)
        return state
    except Exception as e:
        log_error(f"Ошибка в process_loss: {e}", exc_info=True)
        return state

# --- ФОРМАТИРОВАНИЕ ---
def format_loss_record(loss_record):
    if not loss_record:
        return ""
    text = "\n📋 *Проигрыши для отыгрыша:*\n"
    for i, loss in enumerate(loss_record, 1):
        text += f"• Цель {i}) {loss:.2f} руб.\n"
    return text

def format_azamat_mode_info(state):
    if not state.get('in_azamat_mode') or not state.get('loss_record'):
        return ""
    loss_record = state.get('loss_record', [])
    text = format_loss_record(loss_record)
    total_loss = sum(loss_record)
    text += f"💰 *Общая сумма отыгрыша:* {total_loss:.2f} руб.\n"
    return text

def get_bot_status_header():
    status_info = get_bot_status_info()
    return f"{status_info['status']} | 🕐 {status_info['uptime']}"

def format_input_prompt(input_type):
    prompts = {
        'set_coeff': "🎲 *ВВЕДИТЕ КОЭФФИЦИЕНТ*",
        'set_stake': "💰 *ВВЕДИТЕ СУММУ СТАВКИ*", 
        'set_bank': "🏦 *ВВЕДИТЕ НАЧАЛЬНЫЙ БАНК*",
        'modify_goal': "🎯 *ВВЕДИТЕ НОВУЮ ЦЕЛЬ*"
    }
    return f"\n\n{prompts.get(input_type, '')}"

def format_bet_history(bet_history):
    if not bet_history:
        return "📊 *История ставок:*\nНет данных"
    history_text = "📊 *Последние ставки:*\n"
    for i, bet in enumerate(bet_history[:10], 1):
        coeff = bet.get('coefficient', 0)
        result = bet.get('result', '')
        if result == 'win':
            history_text += f"{i}) Кф {coeff} - 🟢 выигрыш\n"
        else:
            history_text += f"{i}) Кф {coeff} - 🔴 проигрыш\n"
    return history_text

def simple_input_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔄 Главное меню", callback_data='main_menu'))
    return markup

def format_bank_movement(state, page=1):
    try:
        initial = state.get('initial_balance', 0)
        current_day = state.get('day', 1)
        if initial <= 0:
            return "❌ *Начальный банк не установлен!*"
        days_per_page = 15
        start_day = (page - 1) * days_per_page + 1
        end_day = min(page * days_per_page, 300)
        text = f"📈 *Движение Банка - Страница {page}/20*\n\n"
        text += f"🏁 *Начальный банк:* {initial:.2f} руб.\n"
        text += f"📅 *Текущий день:* #{current_day}\n\n"
        text += "*План по дням:*\n"
        for day in range(start_day, end_day + 1):
            target_bank = calculate_target_bank(initial, day)
            if day == current_day:
                text += f"🔴 *День {day}: {target_bank:.2f} руб.*\n"
            else:
                text += f"• День {day}: {target_bank:.2f} руб.\n"
        if current_day <= 300:
            current_target = calculate_target_bank(initial, current_day)
            final_target = calculate_target_bank(initial, 300)
            progress_percent = (current_target / final_target * 100) if final_target > 0 else 0
            text += f"\n📊 *Прогресс:* {progress_percent:.1f}%\n"
            text += f"🎯 *Цель 300 дней:* {final_target:.2f} руб."
        return text
    except Exception as e:
        log_error(f"Ошибка в format_bank_movement: {e}", exc_info=True)
        return "❌ Ошибка при формировании движения банка"

# --- КЛАВИАТУРЫ ---
def main_menu_keyboard_security(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("📊 Статистика", callback_data='statistics'),
        types.InlineKeyboardButton("🎯 Заключить пари", callback_data='place_bet')
    )
    markup.row(
        types.InlineKeyboardButton("💰 Мои Банки", callback_data='manage_banks'),
        types.InlineKeyboardButton("🎰 Изменить Цель", callback_data='change_goal')
    )
    if chat_id == ADMIN_ID:
        markup.row(types.InlineKeyboardButton("👥 Управление пользователями", callback_data='manage_users'))
    markup.row(types.InlineKeyboardButton("📊 Статус бота", callback_data='bot_status'))
    return markup

def back_to_menu_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔄 Главное меню", callback_data='main_menu'))
    return markup

def statistics_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("📈 Движение Банка", callback_data='bank_movement'),
        types.InlineKeyboardButton("🗑️ Очистить статистику", callback_data='clear_stats')
    )
    markup.row(types.InlineKeyboardButton("🔄 Главное меню", callback_data='main_menu'))
    return markup

def bank_movement_keyboard(page=1):
    markup = types.InlineKeyboardMarkup()
    row_buttons = []
    if page > 1:
        row_buttons.append(types.InlineKeyboardButton("⬅️ Назад", callback_data=f'bank_movement_{page-1}'))
    if page < 20:
        row_buttons.append(types.InlineKeyboardButton("Вперед ➡️", callback_data=f'bank_movement_{page+1}'))
    if row_buttons:
        markup.row(*row_buttons)
    markup.row(types.InlineKeyboardButton("🔄 Обновить", callback_data=f'bank_movement_{page}'))
    markup.row(types.InlineKeyboardButton("↩️ Назад к статистике", callback_data='statistics'))
    return markup

def bet_confirmation_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Выигрыш", callback_data='result_win'),
        types.InlineKeyboardButton("❌ Проигрыш", callback_data='result_loss')
    )
    markup.row(types.InlineKeyboardButton("✏️ Редактировать ставку", callback_data='edit_bet'))
    markup.row(types.InlineKeyboardButton("🔄 Главное меню", callback_data='main_menu'))
    return markup

def edit_bet_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("↩️ Назад к ставке", callback_data='back_to_bet'),
        types.InlineKeyboardButton("🔄 Главное меню", callback_data='main_menu')
    )
    return markup

def banks_keyboard(banks):
    markup = types.InlineKeyboardMarkup()
    for bank in banks:
        markup.row(
            types.InlineKeyboardButton(
                f"🏦 {bank['name']} (День #{bank['day']})",
                callback_data=f'select_bank_{bank["id"]}'
            )
        )
    if len(banks) < MAX_BANKS:
        markup.row(types.InlineKeyboardButton("➕ Создать банк", callback_data='create_bank'))
    if banks:
        markup.row(types.InlineKeyboardButton("🗑️ Удалить банк", callback_data='delete_bank'))
    markup.row(types.InlineKeyboardButton("🔄 Главное меню", callback_data='main_menu'))
    return markup

def delete_bank_keyboard(banks):
    markup = types.InlineKeyboardMarkup()
    for bank in banks:
        markup.row(
            types.InlineKeyboardButton(
                f"🗑️ {bank['name']}",
                callback_data=f'delete_bank_{bank["id"]}'
            )
        )
    markup.row(types.InlineKeyboardButton("↩️ Назад к банкам", callback_data='manage_banks'))
    return markup

def change_goal_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🔄 Меняем цель", callback_data='modify_goal'),
        types.InlineKeyboardButton("✂️ Разделить цель", callback_data='split_goal')
    )
    markup.row(types.InlineKeyboardButton("🔄 Главное меню", callback_data='main_menu'))
    return markup

def confirm_split_goal_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Да, разделить", callback_data='confirm_split'),
        types.InlineKeyboardButton("❌ Отмена", callback_data='main_menu')
    )
    return markup

def split_goal_parts_keyboard(goal_index):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("2 части", callback_data=f'split_parts_{goal_index}_2'),
        types.InlineKeyboardButton("3 части", callback_data=f'split_parts_{goal_index}_3')
    )
    markup.row(
        types.InlineKeyboardButton("4 части", callback_data=f'split_parts_{goal_index}_4'),
        types.InlineKeyboardButton("5 части", callback_data=f'split_parts_{goal_index}_5')
    )
    markup.row(
        types.InlineKeyboardButton("6 частей", callback_data=f'split_parts_{goal_index}_6')
    )
    markup.row(types.InlineKeyboardButton("↩️ Назад", callback_data='split_goal_azamat'))
    return markup

def confirm_clear_stats_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Да, очистить", callback_data='confirm_clear_stats'),
        types.InlineKeyboardButton("❌ Отмена", callback_data='statistics')
    )
    return markup

def users_management_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("➕ Добавить пользователя", callback_data='add_user'),
        types.InlineKeyboardButton("➖ Удалить пользователя", callback_data='remove_user')
    )
    markup.row(
        types.InlineKeyboardButton("📋 Список пользователей", callback_data='list_users'),
        types.InlineKeyboardButton("🔄 Главное меню", callback_data='main_menu')
    )
    return markup

def bot_status_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🔄 Обновить статус", callback_data='bot_status'),
        types.InlineKeyboardButton("🔄 Главное меню", callback_data='main_menu')
    )
    return markup

# --- ОСНОВНЫЕ ХЕНДЛЕРЫ ---
@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    try:
        chat_id = message.chat.id
        update_bot_status()
        if not security_check(chat_id):
            bot.send_message(chat_id, "🚫 *ДОСТУП ЗАПРЕЩЕН*\n\nБот недоступен для вашего аккаунта.", parse_mode='Markdown')
            return
        state = get_user_state(chat_id)
        state['awaiting_input'] = ''
        save_user_state(state)
        welcome_text = (
            f"{get_bot_status_header()}\n\n"
            "👋 *Добро пожаловать в AZ-Calculator*\n"
            "💡 *Логика системы:*\n"
            "• 🏁 Начальный банк - от 10 до 100.000\n"
            "• 💰 Текущий банк - Анализируем и Не Рискуем !\n"
            "• 🎯 Цель дня = Соблюдаем !\n"
            "• 📅 Автоматический переход дней При Выигрыше\n"
            "• 🛡️ Стратегия Азамата при 2+ проигрышах\n\n"
            "_Выберите действия:_"
        )
        bot.send_message(chat_id, welcome_text, 
                        reply_markup=main_menu_keyboard_security(chat_id), 
                        parse_mode='Markdown')
    except Exception as e:
        log_error(f"Ошибка в handle_start: {e}", exc_info=True)

@bot.message_handler(commands=['status'])
def handle_status_command(message):
    try:
        chat_id = message.chat.id
        if not security_check(chat_id):
            return
        update_bot_status()
        handle_bot_status_manual(message)
    except Exception as e:
        log_error(f"Ошибка в handle_status_command: {e}", exc_info=True)

def handle_bot_status_manual(message):
    try:
        chat_id = message.chat.id
        status_info = get_bot_status_info()
        api_status = "🟢 Доступно"
        try:
            bot.get_me()
        except Exception as e:
            api_status = f"🔴 Ошибка: {str(e)}"
        db_status = "🟢 Доступна"
        try:
            conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            conn.close()
        except Exception as e:
            db_status = f"🔴 Ошибка: {str(e)}"
        status_text = (
            f"🤖 *СТАТУС БОТА*\n\n"
            f"📊 *Состояние:* {status_info['status']}\n"
            f"⏱️ *Время работы:* {status_info['uptime']}\n"
            f"🕐 *Запущен:* {status_info['start_time']}\n"
            f"📅 *Последняя активность:* {status_info['last_update']}\n\n"
            f"🔧 *Системные компоненты:*\n"
            f"• Telegram API: {api_status}\n"
            f"• База данных: {db_status}\n"
            f"• Авторизованных пользователей: {len(AUTHORIZED_USERS)}\n\n"
            f"💾 *Память и ресурсы:*\n"
            f"• Файл БД: {os.path.getsize(DB_NAME) / 1024:.1f} КБ\n"
            f"• Файл логов: {os.path.getsize('bot_errors.log') / 1024:.1f} КБ\n\n"
            f"_Статус обновлен: {datetime.now().strftime('%H:%M:%S')}_"
        )
        bot.send_message(chat_id, status_text, 
                        reply_markup=bot_status_keyboard(),
                        parse_mode='Markdown')
    except Exception as e:
        log_error(f"Ошибка в handle_bot_status_manual: {e}", exc_info=True)
        try:
            bot.send_message(chat_id, "❌ Ошибка при получении статуса бота")
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    try:
        chat_id = call.message.chat.id
        update_bot_status()
        if not security_check(chat_id):
            bot.answer_callback_query(call.id, "🚫 Доступ запрещен", show_alert=True)
            return
        print(f"📨 Получен callback: {call.data}")
        if call.data == 'main_menu':
            handle_main_menu(call)
        elif call.data == 'statistics':
            handle_statistics(call)
        elif call.data == 'place_bet':
            handle_place_bet(call)
        elif call.data == 'manage_banks':
            handle_manage_banks(call)
        elif call.data == 'create_bank':
            handle_create_bank(call)
        elif call.data == 'delete_bank':
            handle_delete_bank_menu(call)
        elif call.data.startswith('select_bank_'):
            handle_select_bank(call)
        elif call.data.startswith('delete_bank_'):
            handle_delete_bank_confirm(call)
        elif call.data in ['result_win', 'result_loss']:
            handle_bet_result(call)
        elif call.data == 'change_goal':
            handle_change_goal(call)
        elif call.data == 'modify_goal':
            handle_modify_goal(call)
        elif call.data == 'split_goal':
            handle_split_goal(call)
        elif call.data == 'split_goal_azamat':
            handle_split_goal_azamat(call)
        elif call.data.startswith('select_goal_'):
            handle_select_goal(call)
        elif call.data.startswith('split_parts_'):
            handle_split_parts(call)
        elif call.data == 'confirm_split':
            handle_confirm_split(call)
        elif call.data == 'clear_stats':
            handle_clear_stats(call)
        elif call.data == 'confirm_clear_stats':
            handle_confirm_clear_stats(call)
        elif call.data == 'manage_users':
            handle_manage_users(call)
        elif call.data == 'add_user':
            handle_add_user(call)
        elif call.data == 'remove_user':
            handle_remove_user(call)
        elif call.data == 'list_users':
            handle_list_users(call)
        elif call.data == 'bot_status':
            handle_bot_status(call)
        elif call.data == 'edit_bet':
            handle_edit_bet(call)
        elif call.data == 'back_to_bet':
            handle_back_to_bet(call)
        elif call.data == 'bank_movement':
            handle_bank_movement(call)
        elif call.data.startswith('bank_movement_'):
            handle_bank_movement_page(call)
        else:
            print(f"❌ Неизвестный callback: {call.data}")
            bot.answer_callback_query(call.id, "❌ Неизвестная команда")
    except Exception as e:
        error_msg = f"Ошибка в обработчике callback {getattr(call, 'data', '')}: {e}"
        log_error(error_msg, exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Произошла ошибка")
        except Exception:
            pass

def handle_bot_status(call):
    try:
        chat_id = call.message.chat.id
        status_info = get_bot_status_info()
        api_status = "🟢 Доступно"
        try:
            bot.get_me()
        except Exception as e:
            api_status = f"🔴 Ошибка: {str(e)}"
        db_status = "🟢 Доступна"
        try:
            conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            conn.close()
        except Exception as e:
            db_status = f"🔴 Ошибка: {str(e)}"
        status_text = (
            f"🤖 *СТАТУС БОТА*\n\n"
            f"📊 *Состояние:* {status_info['status']}\n"
            f"⏱️ *Время работы:* {status_info['uptime']}\n"
            f"🕐 *Запущен:* {status_info['start_time']}\n"
            f"📅 *Последняя активность:* {status_info['last_update']}\n\n"
            f"🔧 *Системные компоненты:*\n"
            f"• Telegram API: {api_status}\n"
            f"• База данных: {db_status}\n"
            f"• Авторизованных пользователей: {len(AUTHORIZED_USERS)}\n\n"
            f"💾 *Память и ресурсы:*\n"
            f"• Файл БД: {os.path.getsize(DB_NAME) / 1024:.1f} КБ\n"
            f"• Файл логов: {os.path.getsize('bot_errors.log') / 1024:.1f} КБ\n\n"
            f"_Статус обновлен: {datetime.now().strftime('%H:%M:%S')}_"
        )
        bot.edit_message_text(
            status_text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=bot_status_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, "✅ Статус обновлен")
    except Exception as e:
        log_error(f"Ошибка в handle_bot_status: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при получении статуса")
        except Exception:
            pass

def handle_main_menu(call):
    try:
        bot.answer_callback_query(call.id)
        chat_id = call.message.chat.id
        handle_start(call.message)
    except Exception as e:
        log_error(f"Ошибка в handle_main_menu: {e}", exc_info=True)

def handle_statistics(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if not state.get('bank_id'):
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n"
                "❌ *Нет активного банка*\n\nСоздайте банк в разделе 'Мои Банки'",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id),
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        total_bets = int(state.get('total_bets', 0) or 0)
        total_wins = int(state.get('total_wins', 0) or 0)
        total_losses = total_bets - total_wins
        success_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0.0
        loss_rate = (total_losses / total_bets * 100) if total_bets > 0 else 0.0
        initial = float(state.get('initial_balance', 0) or 0.0)
        current_bank = state.get('bank', 0)
        current_day = state.get('day', 1)
        target_bank = calculate_target_bank(initial, current_day)
        daily_goal = calculate_daily_goal(current_bank, target_bank)
        bet_history_text = format_bet_history(state.get('bet_history', []))
        text = (
            f"{get_bot_status_header()}\n\n"
            f"📊 *Статистика банка:* **{state.get('bank_name', 'Неизвестно')}**\n\n"
            f"🏁 *Начальный банк:* **{initial:.2f} руб.**\n"
            f"💵 *Текущий банк:* **{current_bank:.2f} руб.**\n"
            f"🎯 *Цель дня:* **+{daily_goal:.2f} руб.**\n"
            f"📅 *Текущий день:* **#{current_day}**\n"
            f"🏆 *Целевой банк дня:* **{target_bank:.2f} руб.**\n\n"
            f"📈 *Общая статистика:*\n"
            f"• Всего ставок: **{total_bets}**\n"
            f"• Выигрышей: **{total_wins}** ({success_rate:.1f}%)\n"
            f"• Проигрышей: **{total_losses}** ({loss_rate:.1f}%)\n\n"
            f"{bet_history_text}"
        )
        azamat_info = format_azamat_mode_info(state)
        if azamat_info:
            text += f"\n\n{azamat_info}"
        if state.get('sub_goals'):
            text += f"\n• Разделенных целей: **{len(state['sub_goals'])}**"
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=statistics_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_statistics: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при загрузке статистики")
        except Exception:
            pass

def handle_bank_movement(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if not state.get('bank_id'):
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n"
                "❌ *Нет активного банка*\n\nСоздайте банк в разделе 'Мои Банки'",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id),
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        initial = state.get('initial_balance', 0)
        if initial <= 0:
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n"
                "❌ *Начальный банк не установлен!*\n\nСначала установите начальный банк.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=statistics_keyboard(),
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        text = format_bank_movement(state, 1)
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=bank_movement_keyboard(1),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_bank_movement: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при загрузке движения банка")
        except Exception:
            pass

def handle_bank_movement_page(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if not state.get('bank_id'):
            bot.answer_callback_query(call.id, "❌ Нет активного банка")
            return
        page = int(call.data.replace('bank_movement_', ''))
        initial = state.get('initial_balance', 0)
        if initial <= 0:
            bot.answer_callback_query(call.id, "❌ Начальный банк не установлен")
            return
        text = format_bank_movement(state, page)
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=bank_movement_keyboard(page),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, f"📄 Страница {page}")
    except Exception as e:
        log_error(f"Ошибка в handle_bank_movement_page: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при переключении страницы")
        except Exception:
            pass

def handle_clear_stats(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if not state.get('bank_id'):
            bot.answer_callback_query(call.id, "❌ Нет активного банка")
            return
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n"
            f"🗑️ *Очистка статистики*\n\n"
            f"Вы уверены, что хотите очистить всю статистику банка *{state.get('bank_name', 'Неизвестно')}*?\n\n"
            f"Это действие нельзя отменить!",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=confirm_clear_stats_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_clear_stats: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при очистке статистики")
        except Exception:
            pass

def handle_confirm_clear_stats(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if not state.get('bank_id'):
            bot.answer_callback_query(call.id, "❌ Нет активного банка")
            return
        if reset_bank_stats(state['bank_id']):
            state['total_bets'] = 0
            state['total_wins'] = 0
            state['bet_history'] = []
            save_user_state(state)
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n"
                f"✅ *Статистика очищена!*\n\n"
                f"Все данные статистики банка *{state.get('bank_name', 'Неизвестно')}* были удалены.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id),
                parse_mode='Markdown'
            )
        else:
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n"
                "❌ *Ошибка очистки статистики*",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id),
                parse_mode='Markdown'
            )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_confirm_clear_stats: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при очистке статистики")
        except Exception:
            pass

def handle_manage_banks(call):
    try:
        chat_id = call.message.chat.id
        banks = get_user_banks(chat_id)
        if not banks:
            text = f"{get_bot_status_header()}\n\n💼 *Управление банками*\n\nУ вас пока нет банков. Создайте первый банк!"
        else:
            text = f"{get_bot_status_header()}\n\n💼 *Ваши банки* ({len(banks)}/{MAX_BANKS}):\n\nВыберите банк:"
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=banks_keyboard(banks),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        error_msg = f"Ошибка в handle_manage_banks: {e}"
        log_error(error_msg, exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при загрузке банков")
        except Exception:
            pass

def handle_create_bank(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        state['awaiting_input'] = 'bank_name'
        save_user_state(state)
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n💼 *Создание банка*\n\nВведите название для нового банка:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_to_menu_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        error_msg = f"Ошибка в handle_create_bank: {e}"
        log_error(error_msg, exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при создании банка")
        except Exception:
            pass

def handle_delete_bank_menu(call):
    try:
        chat_id = call.message.chat.id
        banks = get_user_banks(chat_id)
        if not banks:
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n❌ У вас нет банков для удаления",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_mukup=main_menu_keyboard_security(chat_id)
            )
            bot.answer_callback_query(call.id)
            return
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n🗑️ *Удаление банка*\n\nВыберите банк для удаления:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=delete_bank_keyboard(banks),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        error_msg = f"Ошибка в handle_delete_bank_menu: {e}"
        log_error(error_msg, exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при загрузке меню удаления")
        except Exception:
            pass

def handle_delete_bank_confirm(call):
    try:
        chat_id = call.message.chat.id
        bank_id = int(call.data.replace('delete_bank_', ''))
        success, message = delete_bank(chat_id, bank_id)
        if success:
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n{message}",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id)
            )
        else:
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n{message}",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id)
            )
        bot.answer_callback_query(call.id)
    except Exception as e:
        error_msg = f"Ошибка в handle_delete_bank_confirm: {e}"
        log_error(error_msg, exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при удалении банка")
        except Exception:
            pass

def handle_select_bank(call):
    try:
        chat_id = call.message.chat.id
        bank_id = int(call.data.replace('select_bank_', ''))
        if switch_bank(chat_id, bank_id):
            state = get_user_state(chat_id)
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n"
                f"✅ *Банк активирован!*\n\n🏦 **{state.get('bank_name', 'Неизвестно')}**\n💵 Баланс: **{state.get('bank', 0):.2f} руб.**\n📅 День: **#{state.get('day', 1)}**",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id),
                parse_mode='Markdown'
            )
        else:
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n❌ Ошибка при активации банка",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id)
            )
        bot.answer_callback_query(call.id)
    except Exception as e:
        error_msg = f"Ошибка в handle_select_bank: {e}"
        log_error(error_msg, exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при выборе банка")
        except Exception:
            pass

def handle_place_bet(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if not state.get('bank_id'):
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n"
                "❌ *Нет активного банка*\n\nСоздайте банк в разделе 'Мои Банки'",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id),
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        if state.get('awaiting_bet_result') and state.get('current_coeff', 0) != 0 and state.get('current_stake', 0) != 0:
            stake = state.get('current_stake', 0)
            coeff = state.get('current_coeff', 0)
            potential_profit = stake * (coeff - 1)
            confirmation_text = (
                f"{get_bot_status_header()}\n\n"
                f"💾 *СОХРАНЕННАЯ СТАВКА*\n\n"
                f"💰 *Сумма:* **{stake:.2f} руб.**\n"
                f"⚙️ *Коэффициент:* **{coeff:.2f}**\n"
                f"🎯 *Цель:* **{state.get('current_target', 0):.2f} руб.**\n"
                f"💵 *Прибыль:* **+{potential_profit:.2f} руб.**\n\n"
                f"🎲 *Зафиксируйте результат события:*"
            )
            bot.edit_message_text(
                confirmation_text,
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=bet_confirmation_keyboard(),
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        if state.get('bank', 0) < MIN_BANK_AMOUNT:
            state['awaiting_input'] = 'set_bank'
            save_user_state(state)
            text = (
                f"{get_bot_status_header()}\n\n"
                f"💰 *Установка банка*\n\n"
                f"Введите начальную сумму банка:\n"
                f"_Диапазон: {MIN_BANK_AMOUNT}-{MAX_BANK_AMOUNT} руб._"
                f"{format_input_prompt('set_bank')}"
            )
            bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=simple_input_keyboard(),
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        if not state.get('initial_balance') or state.get('initial_balance', 0) == 0:
            state['initial_balance'] = state['bank']
            current_day = state.get('day', 1)
            target_bank = calculate_target_bank(state['bank'], current_day)
            state['current_target'] = calculate_daily_goal(state['bank'], target_bank)
            state['daily_goal'] = state['current_target']
            save_user_state(state)
        initial = state.get('initial_balance', 0)
        current_bank = state.get('bank', 0)
        current_day = state.get('day', 1)
        target_bank = calculate_target_bank(initial, current_day)
        daily_goal = calculate_daily_goal(current_bank, target_bank)
        status = "🛡️ АЗАМАТ РЕЖИМ" if state.get('in_azamat_mode') else "🎯 ОСНОВНОЙ РЕЖИМ"
        text = (
            f"{get_bot_status_header()}\n\n"
            f"*{status}*\n\n"
            f"🏁 *Начальный банк:* **{initial:.2f} руб.**\n"
            f"💵 *Текущий банк:* **{current_bank:.2f} руб.**\n"
            f"🎯 *Текущая цель:* **{state.get('current_target', daily_goal):.2f} руб.**\n"
            f"📅 *День:* **#{current_day}**\n"
            f"🏆 *Целевой банк дня:* **{target_bank:.2f} руб.**\n"
        )
        azamat_info = format_azamat_mode_info(state)
        if azamat_info:
            text += azamat_info
        if state.get('sub_goals'):
            text += f"\n✂️ *Разделенные цели:* **{len(state['sub_goals'])} часть(и)**\n"
        text += format_input_prompt('set_coeff')
        state['awaiting_input'] = 'set_coeff'
        save_user_state(state)
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=simple_input_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_place_bet: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при заключении пари")
        except Exception:
            pass

def handle_bet_result(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if state.get('current_stake', 0) <= 0:
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n❌ Ошибка: ставка не рассчитана",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id),
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        state['total_bets'] = int(state.get('total_bets', 0)) + 1
        if call.data == 'result_win':
            state = process_win(state)
            stake = state.get('current_stake', 0)
            coeff = state.get('current_coeff', 0)
            profit = stake * (coeff - 1)
            text = f"✅ *ВЫИГРЫШ!*\n+{profit:.2f} руб. (ставка: {stake:.2f} руб.)"
        else:
            state = process_loss(state)
            text = f"❌ *ПРОИГРЫШ!*\n-{state.get('current_stake', 0):.2f} руб."
        day_advanced_count = 0
        while check_and_advance_day(state):
            day_advanced_count += 1
        state['current_stake'] = 0
        state['current_coeff'] = 0
        state['awaiting_bet_result'] = False
        save_user_state(state)
        initial = state.get('initial_balance', 0)
        current_bank = state.get('bank', 0)
        current_day = state.get('day', 1)
        target_bank = calculate_target_bank(initial, current_day)
        daily_goal = calculate_daily_goal(current_bank, target_bank)
        progress = f"\n\n💵 *Текущий банк:* {current_bank:.2f} руб.\n"
        progress += f"🎯 *Цель дня:* +{daily_goal:.2f} руб.\n"
        progress += f"📅 *День:* #{current_day}\n"
        progress += f"🏆 *Целевой банк дня:* {target_bank:.2f} руб."
        azamat_info = format_azamat_mode_info(state)
        if azamat_info:
            progress += f"\n\n{azamat_info}"
        if day_advanced_count > 0:
            progress += f"\n\n📈 *АВТОПЕРЕХОД! День #{current_day}*"
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n{text}{progress}",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=main_menu_keyboard_security(chat_id),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_bet_result: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при обработке результата")
        except Exception:
            pass

def handle_change_goal(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if not state.get('bank_id'):
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n❌ *Нет активного банка*\n\nСоздайте банк в разделе 'Мои Банки'",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=main_menu_keyboard_security(chat_id),
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            return
        current_target = state.get('current_target', 0)
        initial = state.get('initial_balance', 0)
        current_day = state.get('day', 1)
        target_bank = calculate_target_bank(initial, current_day)
        text = (
            f"{get_bot_status_header()}\n\n"
            f"🎰 *Изменение Цели*\n\n"
            f"🏁 *Начальный банк:* **{initial:.2f} руб.**\n"
            f"💵 *Текущий банк:* **{state.get('bank', 0):.2f} руб.**\n"
            f"🎯 *Текущая цель:* **{current_target:.2f} руб.**\n"
            f"📅 *День:* **#{current_day}**\n"
            f"🏆 *Целевой банк дня:* **{target_bank:.2f} руб.**\n\n"
            f"Выберите действие:"
        )
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=change_goal_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_change_goal: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при загрузке меню")
        except:
            pass

def handle_modify_goal(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if not state.get('bank_id'):
            bot.answer_callback_query(call.id, "❌ Нет активного банка")
            return
        state['awaiting_input'] = 'modify_goal'
        save_user_state(state)
        current_target = state.get('current_target', 0)
        text = (
            f"{get_bot_status_header()}\n\n"
            f"🔄 *Изменение цели дня*\n\n"
            f"Текущая цель: **{current_target:.2f} руб.**\n\n"
            f"Введите новую цель дня (сумма в рублях):"
        )
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_to_menu_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_modify_goal: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при изменении цели")
        except:
            pass

def handle_edit_bet(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        current_coeff = state.get('current_coeff', 0)
        current_stake = state.get('current_stake', 0)
        current_target = state.get('current_target', 0)
        state['awaiting_input'] = 'edit_coeff'
        state['edit_original_coeff'] = current_coeff
        state['edit_original_stake'] = current_stake
        save_user_state(state)
        potential_profit = current_stake * (current_coeff - 1)
        edit_text = (
            f"{get_bot_status_header()}\n\n"
            f"✏️ *РЕДАКТИРОВАНИЕ СТАВКИ*\n\n"
            f"📊 *Текущие параметры:*\n"
            f"• Коэффициент: **{current_coeff:.2f}**\n"
            f"• Сумма ставки: **{current_stake:.2f} руб.**\n"
            f"• Потенциальная прибыль: **+{potential_profit:.2f} руб.**\n\n"
            f"🎯 *Цель:* **{current_target:.2f} руб.**\n\n"
            f"✍️ *Введите новый коэффициент:*\n"
            f"_Текущий: {current_coeff:.2f}_"
        )
        bot.edit_message_text(
            edit_text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=edit_bet_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_edit_bet: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при редактировании ставки")
        except:
            pass

def handle_back_to_bet(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        state['awaiting_input'] = ''
        save_user_state(state)
        stake = state.get('current_stake', 0)
        coeff = state.get('current_coeff', 0)
        potential_profit = stake * (coeff - 1)
        confirmation_text = (
            f"{get_bot_status_header()}\n\n"
            f"✅ *СТАВКА ПОДТВЕРЖДЕНА!*\n\n"
            f"💰 *Сумма:* **{stake:.2f} руб.**\n"
            f"⚙️ *Коэффициент:* **{coeff:.2f}**\n"
            f"🎯 *Цель:* **{state.get('current_target', 0):.2f} руб.**\n"
            f"💵 *Прибыль:* **+{potential_profit:.2f} руб.**\n\n"
            f"🎲 *Зафиксируйте результат события:*"
        )
        bot.edit_message_text(
            confirmation_text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=bet_confirmation_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_back_to_bet: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при возврате к ставке")
        except:
            pass

def handle_split_goal_azamat(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if not state.get('in_azamat_mode') or not state.get('loss_record'):
            bot.answer_callback_query(call.id, "❌ Нет проигрышей для разделения")
            return
        loss_record = state.get('loss_record', [])
        markup = types.InlineKeyboardMarkup()
        for i, goal in enumerate(loss_record):
            markup.row(types.InlineKeyboardButton(
                f"Цель {i+1}: {goal:.2f} руб.", 
                callback_data=f'select_goal_{i}'
            ))
        markup.row(types.InlineKeyboardButton("↩️ Назад", callback_data='change_goal'))
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n"
            f"✂️ *Разделение цели в режиме Азамата*\n\n"
            f"Выберите цель для разделения:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_split_goal_azamat: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при разделении цели")
        except:
            pass

def handle_select_goal(call):
    try:
        chat_id = call.message.chat.id
        goal_index = int(call.data.replace('select_goal_', ''))
        state = get_user_state(chat_id)
        loss_record = state.get('loss_record', [])
        if goal_index >= len(loss_record):
            bot.answer_callback_query(call.id, "❌ Неверный выбор цели")
            return
        selected_goal = loss_record[goal_index]
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n"
            f"✂️ *Разделение цели*\n\n"
            f"Выбранная цель: **{selected_goal:.2f} руб.**\n\n"
            f"На сколько частей разделить?",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=split_goal_parts_keyboard(goal_index),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_select_goal: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при выборе цели")
        except:
            pass

def handle_split_parts(call):
    try:
        chat_id = call.message.chat.id
        parts_data = call.data.replace('split_parts_', '').split('_')
        goal_index = int(parts_data[0])
        num_parts = int(parts_data[1])
        state = get_user_state(chat_id)
        loss_record = state.get('loss_record', [])
        if goal_index >= len(loss_record):
            bot.answer_callback_query(call.id, "❌ Неверный выбор цели")
            return
        original_goal = loss_record[goal_index]
        part_value = round(original_goal / num_parts, 2)
        parts = [part_value] * (num_parts - 1)
        last_part = original_goal - sum(parts)
        parts.append(round(last_part, 2))
        new_loss_record = (loss_record[:goal_index] + parts + loss_record[goal_index+1:])
        state['loss_record'] = new_loss_record
        state['current_target'] = calculate_azamat_target(state)
        save_user_state(state)
        parts_text = "\n".join([f"• Часть {i+1}: **{part:.2f} руб.**" for i, part in enumerate(parts)])
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n"
            f"✅ *Цель успешно разделена!*\n\n"
            f"✂️ Исходная цель: **{original_goal:.2f} руб.**\n"
            f"Разделена на {num_parts} частей:\n{parts_text}\n\n"
            f"🎯 *Текущая цель:* **{state['current_target']:.2f} руб.**",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=change_goal_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_split_parts: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при разделении цели")
        except:
            pass

def handle_split_goal(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        if not state.get('bank_id'):
            bot.answer_callback_query(call.id, "❌ Сначала создайте банк")
            return
        if state.get('in_azamat_mode') and state.get('loss_record'):
            handle_split_goal_azamat(call)
            return
        if state.get('current_target', 0) <= 0:
            bot.answer_callback_query(call.id, "❌ Нет активной цели для разделения")
            return
        if state.get('sub_goals'):
            bot.answer_callback_query(call.id, "❌ Цель уже разделена")
            return
        if state.get('in_azamat_mode'):
            bot.answer_callback_query(call.id, "❌ Используйте разделение через список проигрышей")
            return
        current_target = state.get('current_target', 0)
        one_fourth = round(current_target / 4, 2)
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n"
            f"✂️ *Подтверждение разделения цели*\n\n"
            f"Текущая цель: **{current_target:.2f} руб.**\n"
            f"После разделения на 4 части:\n"
            f"• Каждая часть: **{one_fourth:.2f} руб.**\n"
            f"• Всего частей: **4**\n\n"
            f"*Вы уверены, что хотите разделить цель?*",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=confirm_split_goal_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_split_goal: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при разделении цели")
        except:
            pass

def handle_confirm_split(call):
    try:
        chat_id = call.message.chat.id
        state = get_user_state(chat_id)
        current_target = state.get('current_target', 0)
        one_fourth = round(current_target / 4, 2)
        sub_goals = [one_fourth] * 3
        last_part = current_target - (one_fourth * 3)
        sub_goals.append(round(last_part, 2))
        if 'loss_record' not in state or state['loss_record'] is None:
            state['loss_record'] = []
        state['loss_record'].extend(sub_goals)
        state['in_azamat_mode'] = True
        state['current_target'] = calculate_azamat_target(state)
        state['sub_goals'] = sub_goals
        state['original_goal'] = current_target
        state['awaiting_input'] = ''
        save_user_state(state)
        goals_text = "\n".join([f"• Часть {i+1}: **{goal:.2f} руб.**" for i, goal in enumerate(sub_goals)])
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n"
            f"✅ *Цель успешно разделена!*\n\n"
            f"✂️ Исходная цель: **{current_target:.2f} руб.**\n"
            f"Разделена на 4 части:\n{goals_text}\n\n"
            f"🛡️ *Активирован режим Азамата*\n"
            f"🎯 *Текущая цель:* **{state['current_target']:.2f} руб.**",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=change_goal_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_confirm_split: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при подтверждении разделения")
        except:
            pass

def handle_manage_users(call):
    try:
        chat_id = call.message.chat.id
        if chat_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Недостаточно прав")
            return
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n"
            "👥 *Управление пользователями*\n\n"
            "Добавление и удаление пользователей из белого списка:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=users_management_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_manage_users: {e}", exc_info=True)

def handle_add_user(call):
    try:
        chat_id = call.message.chat.id
        if chat_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Недостаточно прав")
            return
        state = get_user_state(chat_id)
        state['awaiting_input'] = 'add_user'
        save_user_state(state)
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n"
            "➕ *Добавление пользователя*\n\n"
            "Введите ID пользователя для добавления в белый список:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=back_to_menu_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_add_user: {e}", exc_info=True)

def handle_remove_user(call):
    try:
        chat_id = call.message.chat.id
        if chat_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Недостаточно прав")
            return
        users_list = "\n".join([f"• {user_id}" for user_id in AUTHORIZED_USERS if user_id != ADMIN_ID])
        if not users_list:
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n"
                "❌ *Нет пользователей для удаления*\n\nВ белом списке только вы.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=users_management_keyboard(),
                parse_mode='Markdown'
            )
        else:
            state = get_user_state(chat_id)
            state['awaiting_input'] = 'remove_user'
            save_user_state(state)
            bot.edit_message_text(
                f"{get_bot_status_header()}\n\n"
                f"➖ *Удаление пользователя*\n\n"
                f"Текущие пользователи:\n{users_list}\n\n"
                f"Введите ID пользователя для удаления:",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=back_to_menu_keyboard(),
                parse_mode='Markdown'
            )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_remove_user: {e}", exc_info=True)

def handle_list_users(call):
    try:
        chat_id = call.message.chat.id
        if chat_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Недостаточно прав")
            return
        users_count = len(AUTHORIZED_USERS)
        users_list = "\n".join([f"• {user_id} {'(Владелец)' if user_id == ADMIN_ID else ''}" 
                              for user_id in AUTHORIZED_USERS])
        bot.edit_message_text(
            f"{get_bot_status_header()}\n\n"
            f"📋 *Список пользователей*\n\n"
            f"Всего пользователей: {users_count}\n\n"
            f"{users_list}",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=users_management_keyboard(),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        log_error(f"Ошибка в handle_list_users: {e}", exc_info=True)

@bot.message_handler(func=lambda message: True)
def handle_input(message):
    chat_id = message.chat.id
    update_bot_status()
    if not security_check(chat_id):
        bot.send_message(chat_id, "🚫 *ДОСТУП ЗАПРЕЩЕН*\n\nБот недоступен для вашего аккаунта.", parse_mode='Markdown')
        return
    try:
        text = (message.text or '').strip()
        state = get_user_state(chat_id)
        if not state.get('awaiting_input'):
            bot.send_message(chat_id, "Используйте кнопки меню для управления", 
                           reply_markup=main_menu_keyboard_security(chat_id))
            return
        if state['awaiting_input'] == 'add_user':
            if chat_id != ADMIN_ID:
                bot.send_message(chat_id, "❌ Недостаточно прав")
                return
            try:
                new_user_id = int(text)
                if add_authorized_user(new_user_id):
                    bot.send_message(
                        chat_id,
                        f"{get_bot_status_header()}\n\n✅ *Пользователь добавлен!*\n\nID: {new_user_id}",
                        reply_markup=main_menu_keyboard_security(chat_id),
                        parse_mode='Markdown'
                    )
                    state['awaiting_input'] = ''
                    save_user_state(state)
                else:
                    bot.send_message(chat_id, "❌ Ошибка при добавлении пользователя")
            except ValueError:
                bot.send_message(chat_id, "❌ Неверный формат ID. Введите числовой ID.")
        elif state['awaiting_input'] == 'remove_user':
            if chat_id != ADMIN_ID:
                bot.send_message(chat_id, "❌ Недостаточно прав")
                return
            try:
                remove_user_id = int(text)
                if remove_authorized_user(remove_user_id):
                    bot.send_message(
                        chat_id,
                        f"{get_bot_status_header()}\n\n✅ *Пользователь удален!*\n\nID: {remove_user_id}",
                        reply_markup=main_menu_keyboard_security(chat_id),
                        parse_mode='Markdown'
                    )
                else:
                    bot.send_message(chat_id, "❌ Не удалось удалить пользователя")
                state['awaiting_input'] = ''
                save_user_state(state)
            except ValueError:
                bot.send_message(chat_id, "❌ Неверный формат ID. Введите числовой ID.")
        elif state['awaiting_input'] == 'bank_name':
            if not text:
                bot.send_message(chat_id, "❌ Введите название банка!")
                return
            bank_id, result_msg = create_bank(chat_id, text)
            if bank_id:
                state = get_user_state(chat_id)
                bot.send_message(chat_id, f"{get_bot_status_header()}\n\n{result_msg}", reply_markup=main_menu_keyboard_security(chat_id))
                state['awaiting_input'] = 'set_bank'
                save_user_state(state)
                bank_text = (
                    f"{get_bot_status_header()}\n\n"
                    f"💰 *Установка начального банка*\n\n"
                    f"Введите начальную сумму банка:\n"
                    f"_Диапазон: {MIN_BANK_AMOUNT}-{MAX_BANK_AMOUNT} руб._"
                    f"{format_input_prompt('set_bank')}"
                )
                bot.send_message(
                    chat_id,
                    bank_text,
                    reply_markup=simple_input_keyboard(),
                    parse_mode='Markdown'
                )
            else:
                bot.send_message(chat_id, f"{get_bot_status_header()}\n\n{result_msg}", reply_markup=main_menu_keyboard_security(chat_id))
        elif state['awaiting_input'] == 'set_bank':
            try:
                amount = float(text.replace(',', '.'))
            except Exception:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Неверный формат суммы!*\n\nПожалуйста, введите число.{format_input_prompt('set_bank')}",
                    reply_markup=simple_input_keyboard(),
                    parse_mode='Markdown'
                )
                return
            if amount < MIN_BANK_AMOUNT or amount > MAX_BANK_AMOUNT:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Сумма вне диапазона!*\n\nДопустимый диапазон: {MIN_BANK_AMOUNT}-{MAX_BANK_AMOUNT} руб.{format_input_prompt('set_bank')}",
                    reply_markup=simple_input_keyboard(),
                    parse_mode='Markdown'
                )
                return
            state['bank'] = round(amount, 2)
            state['initial_balance'] = round(amount, 2)
            current_day = state.get('day', 1)
            target_bank = calculate_target_bank(amount, current_day)
            state['current_target'] = calculate_daily_goal(amount, target_bank)
            state['daily_goal'] = state['current_target']
            state['awaiting_input'] = ''
            save_user_state(state)
            target_bank_day1 = calculate_target_bank(amount, 1)
            success_text = (
                f"{get_bot_status_header()}\n\n"
                f"✅ *БАНК УСТАНОВЛЕН!*\n\n"
                f"🏁 *Начальный банк:* **{amount:.2f} руб.**\n"
                f"🎯 *Цель дня:* **+{calculate_daily_goal(amount, target_bank_day1):.2f} руб.**\n"
                f"📅 *День:* **#1**\n"
                f"🏆 *Целевой банк дня:* **{target_bank_day1:.2f} руб.**\n\n"
                f"Теперь можно заключать пари!"
            )
            bot.send_message(
                chat_id,
                success_text,
                reply_markup=main_menu_keyboard_security(chat_id),
                parse_mode='Markdown'
            )
        elif state['awaiting_input'] == 'set_coeff':
            try:
                coeff = float(text.replace(',', '.'))
            except Exception:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Неверный формат коэффициента!*\n\nПожалуйста, введите число от 1.1 до 9.9.{format_input_prompt('set_coeff')}",
                    reply_markup=simple_input_keyboard(),
                    parse_mode='Markdown'
                )
                return
            if coeff < MIN_COEFF or coeff > MAX_COEFF:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Коэффициент вне диапазона!*\n\nДопустимый диапазон: {MIN_COEFF}-{MAX_COEFF}.{format_input_prompt('set_coeff')}",
                    reply_markup=simple_input_keyboard(),
                    parse_mode='Markdown'
                )
                return
            state['current_coeff'] = coeff
            stake = calculate_stake(state.get('current_target', 0), coeff)
            state['current_stake'] = stake
            state['awaiting_input'] = 'set_stake'
            save_user_state(state)
            potential_profit = stake * (coeff - 1)
            max_stake = float(state.get('bank', 0)) * MAX_STAKE_PERCENTAGE
            bet_text = (
                f"{get_bot_status_header()}\n\n"
                f"🧮 *КАЛЬКУЛЯТОР СТАВКИ*\n"
                f"• Цель: {state.get('current_target', 0):.2f} руб.\n"
                f"• Коэффициент: {state.get('current_coeff', 0):.2f}\n"
                f"• 💵 Потенциальная прибыль: +{potential_profit:.2f} руб.\n\n"
                f"💳 *Информация о банке:*\n"
                f"• Текущий банк: {state.get('bank', 0):.2f} руб.\n"
                f"• Макс. ставка: {max_stake:.2f} руб.\n\n"
                f"💰 *РЕКОМЕНДУЕМАЯ СУММА СТАВКИ: {stake:.2f} руб.*\n\n"
                f"{format_input_prompt('set_stake')}"
            )
            bot.send_message(
                chat_id,
                bet_text,
                reply_markup=simple_input_keyboard(),
                parse_mode='Markdown'
            )
        elif state['awaiting_input'] == 'set_stake':
            try:
                stake = float(text.replace(',', '.'))
            except Exception:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Неверный формат суммы!*\n\nПожалуйста, введите число.{format_input_prompt('set_stake')}",
                    reply_markup=simple_input_keyboard(),
                    parse_mode='Markdown'
                )
                return
            max_stake = float(state.get('bank', 0)) * MAX_STAKE_PERCENTAGE
            if stake > max_stake:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Сумма превышает максимальную!*\n\nМаксимальная ставка: {max_stake:.2f} руб.{format_input_prompt('set_stake')}",
                    reply_markup=simple_input_keyboard(),
                    parse_mode='Markdown'
                )
                return
            if stake <= 0:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Сумма должна быть положительной!*{format_input_prompt('set_stake')}",
                    reply_markup=simple_input_keyboard(),
                    parse_mode='Markdown'
                )
                return
            state['current_stake'] = round(stake, 2)
            state['awaiting_input'] = ''
            state['awaiting_bet_result'] = True
            save_user_state(state)
            potential_profit = stake * (state.get('current_coeff', 0) - 1)
            confirmation_text = (
                f"{get_bot_status_header()}\n\n"
                f"✅ *СТАВКА ПОДТВЕРЖДЕНА!*\n\n"
                f"💰 *Сумма:* **{stake:.2f} руб.**\n"
                f"⚙️ *Коэффициент:* **{state.get('current_coeff', 0):.2f}**\n"
                f"🎯 *Цель:* **{state.get('current_target', 0):.2f} руб.**\n"
                f"💵 *Прибыль:* **+{potential_profit:.2f} руб.**\n\n"
                f"🎲 *Зафиксируйте результат события:*"
            )
            bot.send_message(
                chat_id,
                confirmation_text,
                reply_markup=bet_confirmation_keyboard(),
                parse_mode='Markdown'
            )
        elif state['awaiting_input'] == 'modify_goal':
            try:
                new_goal = float(text.replace(',', '.'))
            except Exception:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Неверный формат суммы!*\n\nПожалуйста, введите число.",
                    reply_markup=back_to_menu_keyboard(),
                    parse_mode='Markdown'
                )
                return
            if new_goal <= 0:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Цель должна быть положительной!*",
                    reply_markup=back_to_menu_keyboard(),
                    parse_mode='Markdown'
                )
                return
            state['current_target'] = round(new_goal, 2)
            state['awaiting_input'] = ''
            save_user_state(state)
            success_text = (
                f"{get_bot_status_header()}\n\n"
                f"✅ *Цель успешно изменена!*\n\n"
                f"🎯 *Новая цель дня:* **{new_goal:.2f} руб.**\n\n"
                f"Теперь можно заключать пари с новой целью."
            )
            bot.send_message(
                chat_id,
                success_text,
                reply_markup=main_menu_keyboard_security(chat_id),
                parse_mode='Markdown'
            )
        elif state['awaiting_input'] == 'edit_coeff':
            try:
                coeff = float(text.replace(',', '.'))
            except Exception:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Неверный формат коэффициента!*\n\nПожалуйста, введите число от 1.1 до 9.9.",
                    reply_markup=edit_bet_keyboard(),
                    parse_mode='Markdown'
                )
                return
            if coeff < MIN_COEFF or coeff > MAX_COEFF:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Коэффициент вне диапазона!*\n\nДопустимый диапазон: {MIN_COEFF}-{MAX_COEFF}.",
                    reply_markup=edit_bet_keyboard(),
                    parse_mode='Markdown'
                )
                return
            state['current_coeff'] = coeff
            state['awaiting_input'] = 'edit_stake'
            save_user_state(state)
            current_target = state.get('current_target', 0)
            stake = calculate_stake(current_target, coeff)
            edit_stake_text = (
                f"{get_bot_status_header()}\n\n"
                f"✏️ *РЕДАКТИРОВАНИЕ СТАВКИ*\n\n"
                f"✅ *Новый коэффициент:* **{coeff:.2f}**\n\n"
                f"💰 *РЕКОМЕНДУЕМАЯ СУММА:* **{stake:.2f} руб.**\n\n"
                f"✍️ *Введите новую сумму ставки:*\n"
                f"_Текущая: {state.get('edit_original_stake', 0):.2f} руб._"
            )
            bot.send_message(
                chat_id,
                edit_stake_text,
                reply_markup=edit_bet_keyboard(),
                parse_mode='Markdown'
            )
        elif state['awaiting_input'] == 'edit_stake':
            try:
                stake = float(text.replace(',', '.'))
            except Exception:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Неверный формат суммы!*\n\nПожалуйста, введите число.",
                    reply_markup=edit_bet_keyboard(),
                    parse_mode='Markdown'
                )
                return
            max_stake = float(state.get('bank', 0)) * MAX_STAKE_PERCENTAGE
            if stake > max_stake:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Сумма превышает максимальную!*\n\nМаксимальная ставка: {max_stake:.2f} руб.",
                    reply_markup=edit_bet_keyboard(),
                    parse_mode='Markdown'
                )
                return
            if stake <= 0:
                bot.send_message(
                    chat_id,
                    f"{get_bot_status_header()}\n\n❌ *Сумма должна быть положительной!*",
                    reply_markup=edit_bet_keyboard(),
                    parse_mode='Markdown'
                )
                return
            state['current_stake'] = round(stake, 2)
            state['awaiting_input'] = ''
            state['awaiting_bet_result'] = True
            save_user_state(state)
            coeff = state.get('current_coeff', 0)
            potential_profit = stake * (coeff - 1)
            updated_text = (
                f"{get_bot_status_header()}\n\n"
                f"✅ *СТАВКА ОБНОВЛЕНА!*\n\n"
                f"📊 *Новые параметры:*\n"
                f"• Коэффициент: **{coeff:.2f}**\n"
                f"• Сумма ставки: **{stake:.2f} руб.**\n"
                f"• Потенциальная прибыль: **+{potential_profit:.2f} руб.**\n\n"
                f"🎯 *Цель:* **{state.get('current_target', 0):.2f} руб.**\n\n"
                f"🎲 *Зафиксируйте результат события:*"
            )
            bot.send_message(
                chat_id,
                updated_text,
                reply_markup=bet_confirmation_keyboard(),
                parse_mode='Markdown'
            )
    except Exception as e:
        log_error(f"Ошибка в handle_input: {e}", exc_info=True)
        try:
            bot.send_message(chat_id, "❌ Произошла ошибка при обработке запроса")
        except Exception:
            pass

# === ЗАПУСК ДЛЯ СЕРВЕРА ===
if __name__ == '__main__':
    print("🤖 Бот запускается на Railway...")
    init_db()
    try:
        while True:
            try:
                print("🔄 Запуск бота...")
                bot.infinity_polling(timeout=60, long_polling_timeout=60)
            except Exception as e:
                print(f"❌ Ошибка: {e}")
                print("🔄 Перезапуск через 10 секунд...")
                time.sleep(10)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")