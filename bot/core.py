import time
import json
import string
import random
import sqlite3
import schedule
import requests
import configparser

from telebot import types
from redis import StrictRedis
from westwallet_api import WestWalletAPI
from datetime import datetime, timedelta
from phpserialize import unserialize
from telegram_bot_pagination import InlineKeyboardPaginator

from sqlite3 import Error as SQLiteError
from telebot.apihelper import ApiTelegramException
from redis.exceptions import ConnectionError


class Configs:
    users = {'admin': 'администратор', 'user': 'пользователь'}
    payments = {
        'types':{'deposit': 'депозит'},
        'statuses': {'accepted': "принято", 'processing': "в процессе", 'rejected': "отклонено"}}
    subscriptions = {
        'types': {
            'demo': {'title': 'пробная', 'type': 'hour', 'duration': 2},
            'week': {'title': 'недельная', 'type': 'day', 'duration': 7},
            'month': {'title': 'недельная', 'type': 'day', 'duration': 30}
        },
        'statuses': {'active': 'активна', 'inactive': 'неактивна'}
    }

    @staticmethod
    def load():
        processor = configparser.ConfigParser()
        processor.read('sources/data/configs.ini')
        return processor

    def initialization(self):
        configs, processor = dict(), self.load()
        sections = processor.sections()

        for section in sections:
            if section not in configs.keys():
                configs[section] = {}
                for key, value in processor[section].items():
                    try:
                        if key == 'admins':
                            configs[section][key] = [int(value)]
                        else:
                            configs[section][key] = int(value)

                    except ValueError:
                        if ',' not in value:
                            configs[section][key] = value
                        else:
                            data = list()
                            items = value.replace(',', ' ').split()

                            for item in items:
                                try:
                                    data.append(int(item))
                                except ValueError:
                                    data.append(item)

                            configs[section][key] = data

        configs['users'] = self.users
        configs['payments'] = self.payments
        configs['subscriptions'] = self.subscriptions

        return configs


class Database:
    tables = ['logs', 'users', 'subscriptions', 'payments', 'domains', 'mailings']

    def __init__(self, configs):
        self.configs = configs

    @staticmethod
    def connect():
        connection = sqlite3.connect('sources/data/database.sqlite')
        controller = connection.cursor()
        return connection, controller

    def create_pure_table(self, table):
        try:
            query = str()
            connection, controller = self.connect()

            match table:
                case 'logs':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `userid` INT NOT NULL,
                    `username` VARCHAR NOT NULL,
                    `usertype` VARCHAR NOT NULL,
                    `date` INT NOT NULL,
                    `action` VARCHAR NOT NULL
                    )"""

                case 'users':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `id` INT NOT NULL,
                    `name` VARCHAR NOT NULL,
                    `registration` INT NOT NULL,
                    `balance` FLOAT NOT NULL,
                    `inviter` INT NOT NULL,
                    `percentage` INT NOT NULL,
                    `ban` INT NOT NULL,
                    `cause` VARCHAR NOT NULL
                    )"""
                case 'subscriptions':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `type` VARCHAR NOT NULL,
                    `user` INT NOT NULL,
                    `status` VARCHAR NOT NULL,
                    `purchased` INT NOT NULL,
                    `expiration` INT NOT NULL
                    )"""

                case 'payments':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `id` VARCHAR NOT NULL,
                    `date` INT NOT NULL,
                    `status` VARCHAR NOT NULL,
                    `type` VARCHAR NOT NULL,
                    `user` INT NOT NULL,
                    `summary` FLOAT NOT NULL,
                    `expiration` INT NOT NULL
                    )"""

                case 'domains':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `domain` VARCHAR NOT NULL,
                    `status` VARCHAR NOT NULL,
                    `registration` INT NOT NULL
                    )"""

                case 'mailings':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `id` VARCHAR NOT NULL,
                    `date` INT NOT NULL,
                    `status` VARCHAR NOT NULL,
                    `domain` VARCHAR NOT NULL,
                    `user` INT NOT NULL,
                    `mail` TEXT NOT NULL
                    )"""

            controller.execute(query)
            connection.commit()
            connection.close()
            return True

        except SQLiteError as error:
            print(f"ERROR | TYPE: SQLite | FUNC: {self.create_pure_table.__name__} | DESC: {error}")
            return False

    def delete_table(self, table):
        try:
            connection, controller = self.connect()

            if table in self.tables:
                controller.execute(f"""DROP TABLE `{table}`""")

                connection.commit()
                connection.close()

                return True
            else:
                print(f"ERROR | Sqlite: Table {table} isn't recognize")
                return False
        except SQLiteError as error:
            print(f"ERROR | TYPE: SQLite | FUNC: {self.delete_table.__name__} | DESC: {error}")
            return False

    def recreate_table(self, value='all'):
        if value == 'all':
            for table in self.tables:
                self.delete_table(table)
                self.create_pure_table(table)
        else:
            if value in self.tables:
                self.delete_table(value)
                self.create_pure_table(value)

    def get_data(self, table):
        if table in self.tables:
            controller = self.connect()[1]
            controller.execute(f"""SELECT * FROM `{table}`""")
            return controller.fetchall()

    def get_data_by_value(self, table, value, data, value_=None, data_=None):
        if table in self.tables:
            try:
                connection, controller = self.connect()
                if value_ is None and data_ is None:
                    if type(data) == int:
                        controller.execute(f"""SELECT * FROM `{table}` WHERE `{value}` = {data}""")
                    else:
                        controller.execute(f"""SELECT * FROM `{table}` WHERE `{value}` = '{data}'""")
                else:
                    if type(data) == int:
                        if type(data_) == int:
                            controller.execute(
                                f"""SELECT * FROM `{table}` WHERE `{value}` = {data} OR `{value_}` = {data_}""")
                        else:
                            controller.execute(
                                f"""SELECT * FROM `{table}` WHERE `{value}` = {data} OR `{value_}` = '{data_}'""")
                    else:
                        if type(data_) == int:
                            controller.execute(
                                f"""SELECT * FROM `{table}` WHERE `{value}` = '{data}' OR `{value_}` = {data_}""")
                        else:
                            controller.execute(
                                f"""SELECT * FROM `{table}` WHERE `{value}` = '{data}' OR `{value_}` = '{data_}'""")

                return controller.fetchall()
            except SQLiteError as error:
                print(f"ERROR | TYPE: SQLite | FUNC: {self.get_data_by_value.__name__} | DESC: {error}")
                return False

    def add_data(self, table, **items):
        query = str()
        if table in self.tables:
            connection, controller = self.connect()
            try:
                match table:
                    case 'logs':
                        query = f"""
                        INSERT INTO `{table}` (`userid`, `username`, `usertype`, `date`, `action`)
                        VALUES (
                        {items['userid']}, '{items['username']}', '{items['usertype']}',
                        {int(time.time())}, '{items['action']}'
                        )"""

                    case 'users':
                        query = f"""
                        INSERT INTO `{table}` (
                        `id`, `name`, `registration`, `balance`, `inviter`, `percentage`, `ban`, `cause`)
                        VALUES (
                        {items['id']}, '{items['name']}', {int(time.time())}, 0, 
                        {items['inviter']}, {items['percentage']}, 0, 'None')
                        """

                    case 'subscriptions':
                        status = list(self.configs['subscriptions']['statuses'].keys())[0]

                        query = f"""
                        INSERT INTO `{table}` (`type`, `user`, `status`, `purchased`, `expiration`)
                        VALUES (
                        '{items['type']}', {items['user']}, '{status}', 
                        {items['dates']['now']}, {items['dates']['expiration']})
                        """

                    case 'payments':
                        status = list(self.configs['payments']['statuses'].keys())[1]
                        query = f"""
                        INSERT INTO `{table}` (`id`, `date`, `status`, `type`, `user`, `summary`, `expiration`)
                        VALUES (
                        {items['id']}, {int(time.time())}, '{status}', '{items['type']}', 
                        {items['user']}, {items['summary']}, {items['expiration']})
                        """

                    case 'domains':
                        query = f"""
                        INSERT INTO `{table}` (`domain`, `status`, `registration`)
                        VALUES ('{items['domain']}', '{items['status']}', {int(time.time())})
                        """

                    case 'mailings':
                        status = list(self.configs['statuses'].keys())[1]
                        query = f"""
                        INSERT INTO `{table}` (`id`, `date`, `status`, `domain`, `user`, `mail `)
                        VALUES ({items['id']}, {int(time.time())}, '{status}', 
                        '{items['domain']}', {items['user']}, '{items['mail']}')
                        """

                if query is not None:
                    controller.execute(query)
                    connection.commit()
                    connection.close()
                    return True

            except SQLiteError as error:
                print(f"ERROR | TYPE: SQLite | FUNC: {self.add_data.__name__} | DESC: {error}")
                return False
        else:
            return False

    def change_data(self, table, setter, data, value, column='id'):
        if table in self.tables:
            try:
                connection, controller = self.connect()
                if type(data) == int or type(data) == float:
                    if type(value) == int:
                        controller.execute(
                            f"""UPDATE `{table}` SET `{setter}` = {data} WHERE `{table}`.`{column}` = {value}""")
                    else:
                        controller.execute(
                            f"""UPDATE `{table}` SET `{setter}` = {data} WHERE `{table}`.`{column}` = '{value}'""")
                elif type(data) == str:
                    if type(value) == int or type(value) == float:
                        controller.execute(
                            f"""UPDATE `{table}` SET `{setter}` = '{data}' WHERE `{table}`.`{column}` = {value}""")
                    else:
                        controller.execute(
                            f"""UPDATE `{table}` SET `{setter}` = '{data}' WHERE `{table}`.`{column}` = '{value}'""")
                elif type(data) == list:
                    controller.execute(
                        f'''UPDATE `{table}` SET `{setter}` = "{data}" WHERE `{table}`.`{column}` = {value}''')

                connection.commit()
                connection.close()
                return True
            except SQLiteError as error:
                print(f"ERROR | TYPE: SQLite | FUNC: {self.change_data.__name__} | DESC: {error}")
                return False

    def delete_data(self, table, value, data):
        if table in self.tables:
            connection, controller = self.connect()
            try:
                if type(data) == int:
                    controller.execute(f"""DELETE FROM `{table}` WHERE {value} = {data}""")
                else:
                    controller.execute(f"""DELETE FROM `{table}` WHERE {value} = '{data}'""")

                connection.commit()
                connection.close()
                return True
            except SQLiteError as error:
                print(f"ERROR | TYPE: SQLite | FUNC: {self.delete_data.__name__} | DESC: {error}")
                return False
        else:
            return False


class Sessions:
    def __init__(self):
        self.admins = dict()
        self.users = dict()

    def start(self, identifier, usertype, session, message=None, userid=None):
        template = {
            'type': session,
            'message': {'id': message},
            'actions': {'step': 0, 'data': {}}
        }

        match usertype:
            case 'admin':
                self.admins[identifier] = template
                self.admins[identifier]['user'] = {'id': userid}

            case 'user':
                self.users[identifier] = template

    def clear(self, usertype, user):
        try:
            match usertype:
                case 'admin':
                    del self.admins[user]
                case 'user':
                    del self.users[user]
        except KeyError:
            pass


class Processes:
    def __init__(self, bot, texts, buttons):
        self.bot = bot
        self.texts = texts
        self.buttons = buttons

    def payments(self):
        pass

    def mailing(self):
        pass

    def run(self):
        schedule.every(1).seconds.do(
            self.payments
        )

        schedule.every(1).seconds.do(
            self.mailing
        )

        while True:
            schedule.run_pending()
            time.sleep(1)


class Merchant:
    def __init__(self, database, handler, generator):
        self.database = database
        self.handler = handler
        self.generator = generator

    def initialization(self):
        tokens = self.handler.file('read', 'settings')['merchant']
        return WestWalletAPI(tokens['public'], tokens['private'])


class Mailing:
    def __init__(self):
        pass


class Handler:
    def __init__(self, configs, database):
        self.configs = configs
        self.database = database

    def initialization(self, mode, **data):
        match mode:
            case 'user':
                users, log, additional = self.format('list', 'users', 'ids'), str(), None
                username = self.format('str', 'user', 'username', first=data['first'], last=data['last'])

                if data['user'] not in users:
                    inviter, percentage = 0, self.file('read', 'settings')['main']['percentage']

                    try:
                        if len(data['commands']) == 2:
                            inviter_data = self.database.get_data_by_value('users', 'id', data['commands'][1])
                            additional = f"Пользователь использовал реферальный код `{data['commands'][1]}`, "
                            if len(inviter_data) and not inviter_data[0][6]:
                                inviter = inviter_data[0][0]
                                additional += f"пригласитель [{inviter_data[0][1]}](tg://user?id={inviter_data[0][0]}) | " \
                                              f"ID: {inviter_data[0][0]}."
                            else:
                                additional += "но пригласитель либо не найден, либо заблокирован."
                    except KeyError:
                        pass

                    log = f"Добавлен новый пользователь [{username}](tg://user?id={data['user']}). " \
                          f"{'' if additional is None else additional}"
                    self.database.add_data('users', id=data['user'], name=username,
                                           inviter=inviter, percentage=percentage)
                else:
                    log = "Пользователь использовал команду `/start` для запуска/перезапуска бота."

                if 'commands' in data.keys():
                    usertype = self.recognition('usertype', user=data['user'])
                    self.database.add_data('logs', userid=data['user'], username=username, usertype=usertype, action=log)

    @staticmethod
    def file(action, file, data=None):
        filepath = str()
        buffering = action[0] if action == 'read' or action == 'write' else 'r'

        match file:
            case 'processings':
                filepath += 'sources/data/processings.json'
            case 'settings':
                filepath += 'sources/data/settings.json'

        with open(filepath, buffering, encoding='utf-8') as file:
            match action:
                case 'read':
                    return json.load(file)
                case 'write':
                    json.dump(data, file, ensure_ascii=False)

    def calculate(self, mode, option=None, **data):
        result = 0

        match mode:
            case 'subscription':
                if option == 'dates':
                    data = self.configs['subscriptions']['types'][data['type']]
                    now, calculated = int(time.time()), 0

                    current = datetime.fromtimestamp(now)

                    match data['type']:
                        case 'hour':
                            calculated = current + timedelta(hours=data['duration'])
                        case 'day':
                            calculated = current + timedelta(days=data['duration'])

                    expiration = int(calculated.timestamp())
                    result = {'now': now, 'expiration': expiration}

        return result

    def format(self, mode, option=None, value=None, **data):
        result = None

        match mode:
            case 'list':
                result = list()

                match option:
                    case 'users':
                        users = self.database.get_data('users')

                        if value == 'ids':
                            for user in users:
                                result.append(user[0])

            case 'dict':
                result = dict()

                match option:
                    case 'currencies-convert':
                        summary, settings = data['summary'], self.file('read', 'settings')['main']
                        cryptocurrency, currency = settings['cryptocurrency'], settings['currency']
                        courses = requests.get(f'https://api.kuna.io/v3/exchange-rates/{cryptocurrency.lower()}').json()
                        amount = round(summary / courses[currency.lower()] if summary != 0 else summary, 5)
                        result = {currency: summary, cryptocurrency: amount}

            case 'str':
                result = str()

                match option:
                    case 'user':
                        if value == 'username':
                            name, surname = data['first'], data['last']

                            if name == 'ᅠ' or name is None or name == '':
                                name = 'Неизвестно'
                            else:
                                name = name

                            if surname is None or surname == '':
                                surname = ''
                            else:
                                surname = surname

                            result = f"{name}{f' {surname}' if surname != '' else surname}"

            case 'int':
                result = 0

        return result

    def recognition(self, mode, option=None, **data):
        result = None

        match mode:
            case 'ban':
                if option == 'user':
                    userdata = self.database.get_data_by_value('users', 'id', data['user'])[0]
                    result = True if userdata[6] else False
                elif option == 'cause':
                    match data['cause']:
                        case 'abuse':
                            result = 'абьюз сервиса или попытка нарушить работоспособность сервиса, или его процессов'
                        case _:
                            result = 'причину блокировки можешь узнать у администрации сервиса'

            case 'usertype':
                result = 'admin' if data['user'] in self.configs['main']['admins'] else 'user'

            case 'subscription':
                if option == 'price':
                    settings = self.file('read', 'settings')
                    prices, currency = settings['prices'], settings['main']['currency']
                    result = "Бесплатно" if prices[data['type']] == 0 else f"{prices[data['type']]} {currency}"

                elif option == 'user':
                    template = '%H:%M:%S / %d.%m.%Y'
                    subscriptions = self.database.get_data_by_value('subscriptions', 'user', data['user'])

                    if len(subscriptions):
                        for subscription in subscriptions:
                            if subscription[2] == 'active':
                                result = {
                                    'title': self.configs['subscriptions']['types'][subscription[0]]['title'],
                                    'expiration': datetime.fromtimestamp(subscription[4]).strftime(template)
                                }

            case 'abuse':
                result, action = False, data['action']

                actions = [
                    '👨🏻‍💻 Пользователи', '🛠 Сервисы', '⭐️ Проект'
                ]

                if action in actions:
                    if data['user'] not in self.configs['main']['admins']:
                        result, user = True, self.database.get_data_by_value('users', 'id', data['user'])[0]
                        bot, texts, buttons = data['bot'], data['texts'], data['buttons']

                        self.database.change_data('users', 'ban', 1, user[0])
                        self.database.change_data('users', 'cause', 'abuse', user[0])
                        self.database.add_data('logs', id=self.generate('unique-id'), userid=user[0],
                                               username=user[1], usertype=data['usertype'],
                                               action=texts.logs('abuse', 'action', action=action))

                        bot.send_message(user[0], texts.error('banned', user=user[0]), parse_mode='markdown',
                                         reply_markup=buttons.support())

        return result

    def generate(self, mode):
        match mode:
            case 'unique-id':
                chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
                return ''.join(random.choice(chars) for x in range(random.randint(10, 12)))


class Texts:
    def __init__(self, configs, database, handler):
        self.configs = configs
        self.database = database
        self.handler = handler

    def menu(self, usertype, mode, **data):
        text = str()

        match usertype:
            case 'admin':
                match mode:
                    case 'main':
                        settings = self.handler.file('read', 'settings')
                        prices = settings['prices']
                        currency, cryptocurrency = settings['main']['currency'], settings['main']['cryptocurrency']

                        demo = self.handler.format('dict', 'currencies-convert', summary=prices['demo'])
                        week = self.handler.format('dict', 'currencies-convert', summary=prices['week'])
                        month = self.handler.format('dict', 'currencies-convert', summary=prices['month'])

                        text = "*АДМИН-ПАНЕЛЬ*\n\n" \
                               f"✏️ Логов: *{len(self.database.get_data('logs'))}*\n" \
                               f"👥 Пользователей: *{len(self.database.get_data('users'))}*\n" \
                               f"📨 Рассылок: *{len(self.database.get_data('mailings'))}*\n" \
                               f"⭐️ Подписок: *{len(self.database.get_data('subscriptions'))}*\n\n" \
                               f"*Цены на подписки*\n" \
                               f" - Пробная: " \
                               f"*{demo[currency]} {currency} ({demo[cryptocurrency]} {cryptocurrency})*\n" \
                               f" - Недельная: " \
                               f"*{week[currency]} {currency} ({week[cryptocurrency]} {cryptocurrency})*\n" \
                               f" - Месячная: " \
                               f"*{month[currency]} {currency} ({month[cryptocurrency]} {cryptocurrency})*\n\n" \
                               f"🔽 Выбери действие 🔽"

            case 'user':
                userdata = self.database.get_data_by_value('users', 'id', data['user'])[0]

                match mode:
                    case 'main':
                        currency = self.handler.file('read', 'settings')['main']['currency']
                        subscription = self.handler.recognition('subscription', 'user', user=userdata[0])

                        text = "*ГЛАВНОЕ МЕНЮ*\n\n" \
                               f"💰 Баланс: *{0} {currency}*\n" \
                               f"⭐️ Текущая подписка: " \
                               f"*{'Нет' if subscription is None else subscription['title']}*\n"

                        if subscription is not None:
                            text += f"🗓 Подписка истекает: *{subscription['expiration']}*\n"

                        text += f"📨 Рассылки: " \
                                f"*{len(self.database.get_data_by_value('mailings', 'user', userdata[0]))}* шт.\n" \
                                f"🔗 Реферальная ссылка:\n" \
                                f"`https://t.me/{self.configs['bot']['login']}?start={userdata[0]}`\n" \
                                f"*Подписки*\n" \
                                f" - Пробная: " \
                                f"*{self.handler.recognition('subscription', 'price', type='demo')}*\n" \
                                f" - Недельная: " \
                                f"*{self.handler.recognition('subscription', 'price', type='week')}*\n" \
                                f" - Месячная: " \
                                f"*{self.handler.recognition('subscription', 'price', type='month')}*\n\n" \
                                f"*Сервисы*\n" \
                                f" - None\n\n"

                        text += "🔽 Выбери действие 🔽"

        return text

    def logs(self, mode, option, **data):
        text = str()

        match mode:
            case 'abuse':
                if option == 'start':
                    pass
                elif option == 'action':
                    text = f"Попытался воспользоваться командой «{data['action']}», но не смог. Скорее этот человек " \
                           f"пытается абьюзить бота или ищет дырки, поэтому он был автоматически забанен."

        return text



    def error(self, mode, **data):
        text = "🚫 *Ошибка*\n\n⚠️ "

        match mode:
            case 'banned':
                userdata = self.database.get_data_by_value('users', 'id', data['user'])[0]
                cause = self.handler.recognition('ban', 'cause', cause=userdata[7])
                text += "Ты был заблокирован администрацией, за нарушение правил использования сервиса.\n\n" \
                        f"📍 *Причина*: {cause}.\n\n" \
                        "📌 Если ты считаешь это ошибкой, то ты можешь обратиться в поддержку, " \
                        "для решения текущего вопроса.\n\n" \
                        "🔽 Обратиться в поддержку 🔽"

        return text


class Buttons:
    def __init__(self, configs, database, handler):
        self.configs = configs
        self.database = database
        self.handler = handler

    def support(self):
        markup = types.InlineKeyboardMarkup()
        return markup.add(
            types.InlineKeyboardButton('☎️ Поддержка', url=f"tg://user?id={self.configs['main']['support']}")
        )

    def menu(self, usertype, menu, additional=False, markups_type='reply', width=2, **data):
        markup, comeback, query = None, True, None

        if markups_type == 'reply':
            markup = types.ReplyKeyboardMarkup(row_width=width, resize_keyboard=True)
        elif markups_type == 'inline':
            markup = types.InlineKeyboardMarkup()

        match usertype:
            case 'admin':
                match menu:
                    case 'main':
                        comeback = False
                        markup.add(
                            types.KeyboardButton('👨🏻‍💻 Пользователи'),
                            types.KeyboardButton('🛠 Сервисы'),
                            types.KeyboardButton('⭐️ Проект')
                        )
            case 'user':
                match menu:
                    case 'main':
                        comeback = False
                        markup.add(
                            types.KeyboardButton('⚙️ Сервисы'),
                            types.KeyboardButton('⭐️ Подписки'),
                            types.KeyboardButton('🗞 Информация')
                        )

        if comeback:
            if markups_type == 'reply':
                if usertype == 'user':
                    markup.add(types.KeyboardButton('↩️ Назад к профилю'))
                elif usertype == 'admin':
                    markup.add(types.KeyboardButton(f'↩️ Назад к {"админ панели" if comeback is True else comeback}'))

                else:
                    markup.add(types.KeyboardButton(f'↩️ Назад к '
                                                    f'{"главной панели" if comeback is True else comeback}'))
            else:
                markup.add(types.InlineKeyboardButton("↩️ Назад", callback_data=f"comeback-to-{query}"))

        return markup


if __name__ == '__main__':
    _configs = Configs().initialization()
    _database = Database(_configs)
    _database.recreate_table()
