import ast
import time
import json
import string
import random
import schedule
import requests
import configparser
import mysql.connector

from telebot import types
from redis import StrictRedis
from westwallet_api import WestWalletAPI
from datetime import datetime, timedelta
from phpserialize import unserialize
from telegram_bot_pagination import InlineKeyboardPaginator
from mysql.connector import Error as SQLError
from mysql.connector import InternalError as SQLInternalError
from telebot.apihelper import ApiTelegramException
from redis.exceptions import ConnectionError


class Configs:
    users = {
        'types': {'admin': 'администратор', 'user': 'пользователь'},
        'privileges': {'promoter': 'промоутер', 'test': 'тест'}
    }
    services = {'statuses': {'active': 'работает', 'inactive': 'не работает'}}
    payments = {
        'types': {'deposit': 'депозит', 'accruals': 'начисления'},
        'statuses': {'accepted': "принято", 'processing': "в процессе", 'rejected': "отклонено"}}
    subscriptions = {
        'types': {
            'demo': {'title': 'пробная', 'type': 'hour', 'duration': 2},
            'week': {'title': 'недельная', 'type': 'day', 'duration': 7},
            'month': {'title': 'месячная', 'type': 'day', 'duration': 30}
        },
        'statuses': {'active': 'активна', 'inactive': 'неактивна'}
    }
    mailings = {
        'types': {},
        'statuses': {'success': "успешно", 'waiting': "ожидание", 'error': "ошибка"}
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
        configs['services'] = self.services
        configs['payments'] = self.payments
        configs['subscriptions'] = self.subscriptions
        configs['mailings'] = self.mailings

        return configs


class Database:
    tables = ['logs', 'users', 'subscriptions', 'payments', 'services', 'mailings']

    def __init__(self, configs):
        self.configs = configs

    def connect(self):
        configs = {
            'user': self.configs['database']['username'],
            'password': self.configs['database']['password'],
            'host': self.configs['database']['host'],
            'port': self.configs['database']['port'],
            'database': self.configs['database']['name'],
            'raise_on_warnings': True,
        }

        connection = mysql.connector.connect(**configs)
        controller = connection.cursor(dictionary=True)
        return connection, controller

    @staticmethod
    def close(connection, controller):
        connection.close()
        try:
            controller.close()
        except SQLInternalError:
            pass

    def create_pure_table(self, table):
        try:
            query = str()
            connection, controller = self.connect()

            match table:
                case 'logs':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `user` INT(11) NOT NULL,
                    `username` VARCHAR(255) NOT NULL,
                    `usertype` VARCHAR(255) NOT NULL,
                    `date` DATETIME NOT NULL,
                    `action` TEXT NOT NULL
                    )"""

                case 'users':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `id` INT(11) NOT NULL,
                    `name` VARCHAR(255) NOT NULL,
                    `registration` DATETIME NOT NULL,
                    `balance` FLOAT NOT NULL,
                    `inviter` INT(11) NOT NULL,
                    `percentage` INT(3) NOT NULL,
                    `ban` BOOLEAN NOT NULL,
                    `cause` VARCHAR(255) NOT NULL,
                    `privileges` TEXT NOT NULL,
                    `ip` VARCHAR(255) NOT NULL,
                    `agent` VARCHAR(255) NOT NULL
                    )"""
                case 'subscriptions':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `type` VARCHAR(255) NOT NULL,
                    `user` INT(11) NOT NULL,
                    `status` VARCHAR(255) NOT NULL,
                    `purchased` DATETIME NOT NULL,
                    `expiration` DATETIME NOT NULL
                    )"""

                case 'payments':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `id` VARCHAR(255) NOT NULL,
                    `date` DATETIME NOT NULL,
                    `status` VARCHAR(255) NOT NULL,
                    `type` VARCHAR(255) NOT NULL,
                    `user` INT(11) NOT NULL,
                    `amount` FLOAT NOT NULL,
                    `expiration` DATETIME NOT NULL
                    )"""

                case 'services':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `name` VARCHAR(255) NOT NULL,
                    `domain` VARCHAR(255) NOT NULL,
                    `status` VARCHAR(255) NOT NULL
                    )"""

                case 'mailings':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `id` VARCHAR(255) NOT NULL,
                    `date` DATETIME NOT NULL,
                    `status` VARCHAR(255) NOT NULL,
                    `service` VARCHAR(255) NOT NULL,
                    `user` INT(11) NOT NULL,
                    `mail` JSON NOT NULL
                    )"""

            controller.execute(f'{query} CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci')
            connection.commit()
            self.close(connection, controller)
            return True

        except SQLError as error:
            print(f"ERROR | TYPE: SQL | FUNC: {self.create_pure_table.__name__} | DESC: {error}")
            return False

    def delete_table(self, table):
        status = False
        try:
            connection, controller = self.connect()

            if table in self.tables:
                controller.execute(f"""DROP TABLE `{table}`""")
                connection.commit()
                status = True
            else:
                print(f"ERROR | SQL: Table {table} isn't recognize")

            self.close(connection, controller)
        except SQLError as error:
            print(f"ERROR | TYPE: SQL | FUNC: {self.delete_table.__name__} | DESC: {error}")

        return status

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
            connection, controller = self.connect()
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
            except SQLError as error:
                print(f"ERROR | TYPE: SQL | FUNC: {self.get_data_by_value.__name__} | DESC: {error}")
                return False

    def add_data(self, table, **items):
        status, query = False, str()
        if table in self.tables:
            connection, controller = self.connect()
            try:
                match table:
                    case 'logs':
                        query = f"""
                        INSERT INTO `{table}` (`user`, `username`, `usertype`, `date`, `action`)
                        VALUES (
                        {items['user']}, '{items['username']}', '{items['usertype']}',
                        '{datetime.now()}', '{items['action']}'
                        )"""

                    case 'users':
                        query = f"""
                        INSERT INTO `{table}` (
                        `id`, `name`, `registration`, `balance`, `inviter`, 
                        `percentage`, `ban`, `cause`, `privileges`, `ip`, `agent`)
                        VALUES (
                        {items['id']}, '{items['name']}', '{datetime.now()}', 0, {items['inviter']}, 
                        {items['percentage']}, 0, 'None', '{list()}', 'None', '')
                        """

                    case 'subscriptions':
                        status = list(self.configs['subscriptions']['statuses'].keys())[0]
                        query = f"""
                        INSERT INTO `{table}` (`type`, `user`, `status`, `purchased`, `expiration`)
                        VALUES (
                        '{items['type']}', {items['user']}, '{status}', 
                        '{items['dates']['now']}', '{items['dates']['expiration']}')
                        """

                    case 'payments':
                        status = list(self.configs['payments']['statuses'].keys())[1]
                        query = f"""
                        INSERT INTO `{table}` (`id`, `date`, `status`, `type`, `user`, `amount`, `expiration`)
                        VALUES (
                        {items['id']}, '{datetime.now()}', '{status}', '{items['type']}', 
                        {items['user']}, {items['amount']}, '{items['expiration']}')
                        """

                    case 'services':
                        status = list(self.configs['services']['statuses'].keys())[-1]
                        query = f"""
                        INSERT INTO `{table}` (`name`, `domain`, `status`)
                        VALUES ('{items['name']}', '{items['domain']}', '{status}')
                        """

                    case 'mailings':
                        status = list(self.configs['mailings']['statuses'].keys())[1]
                        query = f"""
                        INSERT INTO `{table}` (`id`, `date`, `status`, `service`, `user`, `mail`)
                        VALUES ('{items['id']}', '{datetime.now()}', '{status}', 
                        '{items['service']}', {items['user']}, '{items['mail']}')
                        """

                if query is not None:
                    status = True
                    controller.execute(query)
                    connection.commit()

            except SQLError as error:
                print(f"ERROR | TYPE: SQL | FUNC: {self.add_data.__name__} | DESC: {error}")
            finally:
                self.close(connection, controller)

        return status

    def change_data(self, table, setter, data, value, column='id'):
        status = False
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
                self.close(connection, controller)
                status = True
            except SQLError as error:
                print(f"ERROR | TYPE: SQL | FUNC: {self.change_data.__name__} | DESC: {error}")
        return status

    def delete_data(self, table, value, data):
        status = False
        if table in self.tables:
            connection, controller = self.connect()
            try:
                if type(data) == int:
                    controller.execute(f"""DELETE FROM `{table}` WHERE {value} = {data}""")
                else:
                    controller.execute(f"""DELETE FROM `{table}` WHERE {value} = '{data}'""")

                connection.commit()
                connection.close()
                status = True
            except SQLError as error:
                print(f"ERROR | TYPE: SQL | FUNC: {self.delete_data.__name__} | DESC: {error}")
            finally:
                self.close(connection, controller)
        return status


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

    def clear(self, user):
        try:
            del self.admins[user]
        except KeyError:
            pass

        try:
            del self.users[user]
        except KeyError:
            pass


class Processes:
    def __init__(self, configs, database, handler, bot, texts, buttons):
        self.configs = configs
        self.database = database
        self.handler = handler
        self.bot = bot
        self.texts = texts
        self.buttons = buttons

    def send_message(self, userid, text):
        try:
            self.bot.send_message(userid, text, parse_mode='markdown')
            return True
        except ApiTelegramException as error:
            return error.error_code

    def messagings(self):
        processes = self.handler.file('read', 'processes')
        status, cause = False, None

        for message_type in processes['messages']:
            if len(processes['messages'][message_type].keys()) > 0:
                if message_type == 'all':
                    for key in list(processes['messages'][message_type].keys()):
                        sent, unsent, blocked, deleted = 0, 0, 0, 0
                        users = self.handler.format('list', 'users', 'ids-without-banned')
                        text = processes['messages'][message_type][key]['text']

                        for user in users:
                            status = self.send_message(user, text)

                            if type(status) is bool:
                                if status:
                                    sent += 1
                            else:
                                unsent += 1

                                match status:
                                    case 403:
                                        blocked += 1
                                    case 400:
                                        if self.database.delete_data('users', 'id', user):
                                            deleted += 1

                        unsent += len(self.database.get_data('users')) - sent
                        admin = self.database.get_data_by_value('users', 'id', key)[0]
                        log = self.texts.logs('admin', 'messaging', message_type, sent=sent,
                                              unsent=unsent, blocked=blocked, deleted=deleted)

                        self.database.add_data(
                            'logs', id=self.handler.generate('unique-id'), user=admin['id'], username=admin['name'],
                            usertype=list(self.configs['users']['types'].keys())[0], action=log)

                        self.bot.send_message(
                            self.configs['chats']['notifications'],
                            self.texts.notifications('group', 'messaging', id=admin['id'], name=admin['name'],
                                                     sent=sent, unsent=unsent, blocked=blocked, deleted=deleted),
                            parse_mode='markdown')

                        del processes['messages'][message_type][key]

                    self.handler.file('write', 'processes', processes)

                else:
                    if len(processes['messages'][message_type].keys()) > 0:
                        for user, data in list(processes['messages'][message_type].items()):
                            try:
                                user = self.database.get_data_by_value('users', 'id', user)[0]
                            except IndexError:
                                user = {'id': user, 'name': 'Неизвестно'}

                            if 'ban' in user.keys() and not user['ban']:
                                status = self.send_message(user['id'], data['text'])

                            if type(status) is bool and not status:
                                cause = "Пользователь ранее был заблокирован"
                            else:
                                match status:
                                    case 403:
                                        cause = "Пользователь заблокировал бота " \
                                                "(был автоматически заблокирован в ответ)"

                                    case 400:
                                        if self.database.delete_data('users', 'id', user['id']):
                                            cause = "Пользователю не может быть отправлено сообщение, " \
                                                    "скорее всего некорректный ID. " \
                                                    "Пользователь удалён с базы данных."

                            text_status = '🟢 Доставлено' if type(status) is bool and status else '🔴 Не доставлено'
                            text_cause = '' if type(status) is bool and status else f'⚠️ Причина: {cause}'

                            log = self.texts.logs('admin', 'messaging', message_type, user=user,
                                                  status=text_status, cause=text_cause)

                            self.database.add_data(
                                'logs', id=self.handler.generate('unique-id'), user=user['id'], username=user['name'],
                                usertype=list(self.configs['users']['types'].keys())[0], action=log)

                            del processes['messages'][message_type][str(user['id'])]

                        self.handler.file('write', 'processes', processes)

    def payments(self):
        pass

    def mailings(self):
        pass

    def run(self):
        schedule.every(1).seconds.do(
            self.mailings
        )

        schedule.every(1).seconds.do(
            self.payments
        )

        schedule.every(1).seconds.do(
            self.messagings
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
                            if len(inviter_data) and not inviter_data[0]['ban']:
                                inviter = inviter_data[0]['id']
                                additional += f"пригласитель [{inviter_data[0]['name']}]" \
                                              f"(tg://user?id={inviter_data[0]['id']}) | " \
                                              f"ID: {inviter_data[0]['id']}."
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
                    self.database.add_data('logs', user=data['user'], username=username, usertype=usertype, action=log)


    @staticmethod
    def file(action, file, data=None):
        filepath = str()
        buffering = action[0] if action == 'read' or action == 'write' else 'r'

        if file == 'processes' or file == 'settings':
            filepath += f'sources/data/{file}.json'

        with open(filepath, buffering, encoding='utf-8') as file:
            match action:
                case 'read':
                    return json.load(file)
                case 'write':
                    json.dump(data, file, ensure_ascii=False)

    @staticmethod
    def paginator(character_pages, option, page=1, close=True, **data):
        pattern = f"set-page-{option}-" + "{page}"

        try:
            if len(option.replace('-', ' ').split()) > 1 and 'user' in option:
                pattern = f"set-page-{option}-{data['id']}-" + "{page}"
        except KeyError:
            pass

        paginator = InlineKeyboardPaginator(
            len(character_pages),
            current_page=page,
            data_pattern=pattern
        )

        try:
            if close:
                markups = ast.literal_eval(paginator.markup)
                markups['inline_keyboard'].append([{"text": "❌", "callback_data": "close-page"}])
                markups = str(markups).replace('\'', '"')
            else:
                markups = paginator.markup
        except ValueError:
            if close:
                markups = types.InlineKeyboardMarkup()
                markups.add(types.InlineKeyboardButton('❌', callback_data=f"close-page"))
            else:
                markups = paginator.markup

        return character_pages[page - 1], markups

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

                    result = {'now': current, 'expiration': calculated}

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
                                result.append(user['id'])
                        elif value == 'ids-without-banned':
                            for user in users:
                                if not user['ban']:
                                    result.append(user['id'])
                    case 'services':
                        services = self.database.get_data('services')

                        if value is not None:
                            for service in services:
                                result.append(service[value])

                    case 'subscribers':
                        subscription = data['subscription']
                        subscriptions = self.database.get_data_by_value('subscriptions', 'type' ,subscription)

                        if value == 'active':
                            for subscription in subscriptions:
                                if subscription['status'] == 'active':
                                    result.append(subscription)
                        else:
                            result = subscriptions

                        if 'sort' in data.keys() and data['sort'] == 'users':
                            array = list()
                            for subscription in result:
                                user = self.database.get_data_by_value('users', 'id', subscription['user'])[0]
                                array.append(user)

                            result = array

                    case 'privileges':
                        privileges = self.configs['users']['privileges']
                        user_privileges = ast.literal_eval(
                                    self.database.get_data_by_value('users', 'id', data['user'])[0]['privileges'])
                        match data['type']:
                            case 'add':
                                if len(user_privileges) == 0:
                                    result = list(privileges.keys())
                                else:
                                    for privilege in privileges:
                                        if privilege not in user_privileges:
                                            result.append(privilege)
                            case 'delete':
                                for privilege in privileges:
                                    if privilege in user_privileges:
                                        result.append(privilege)

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

                        elif value == 'location':
                            result = "Неизвестно" if data['location'] is None \
                                else f"{data['location']['city']}, {data['location']['country']}"

                        elif value == 'privileges':
                            privileges = ast.literal_eval(data['privileges'])

                            if len(privileges) == 0:
                                result = 'Нет'
                            else:
                                i = 1
                                for privilege in privileges:
                                    result += f"{self.configs['users']['privileges'][privilege]}" \
                                              f"{', ' if i != len(privileges) else ''}"
                                    i += 1
            case 'int':
                result = 0

        return result

    def recognition(self, mode, option=None, **data):
        result = None

        match mode:
            case 'ban':
                if option == 'user':
                    userdata = self.database.get_data_by_value('users', 'id', data['user'])[0]
                    result = True if userdata['ban'] else False
                elif option == 'cause':
                    match data['cause']:
                        case 'abuse':
                            result = 'абьюз сервиса или попытка нарушить работоспособность сервиса, или его процессов'
                        case _:
                            result = 'причину блокировки можешь узнать у администрации сервиса'

            case 'user':
                if option == 'location':
                    answer = requests.get(f"http://ip-api.com/json/{data['ip']}").json()

                    if answer['status'] == 'success':
                        result = {'city': answer['city'], 'country': answer['country']}

                if option == 'title':
                    items = data['items']
                    call, markups = items.data, items.message.json['reply_markup']['inline_keyboard']

                    for column in markups:
                        for markup in column:
                            if call == markup['callback_data']:
                                result = markup['text'].split()[-1]

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
                            if subscription['status'] == 'active':
                                result = {
                                    'title': self.configs['subscriptions']['types'][subscription['type']]['title'],
                                    'expiration': subscription['expiration'].strftime(template)
                                }

            case 'abuse':
                result, action = False, data['action']

                actions = [
                    '👨🏻‍💻 Пользователи', '👁 Посмотреть всех', '🕹 Управлять',
                    '🛠 Сервисы', '➕ Добавить', '⚙️ Управлять',
                    '🛍 Подписки', 'Пробная', 'Недельная', 'Месячная'
                    '⭐️ Проект', '🗞 Логи',
                    '📨 Рассылка', '👥 Всем', '👤 Одному',
                    '⚙️ Настройки', '🪙 Валюта', '🧮 Процент'
                ]

                if action in actions:
                    if data['user'] not in self.configs['main']['admins']:
                        result, user = True, self.database.get_data_by_value('users', 'id', data['user'])[0]
                        bot, texts, buttons = data['bot'], data['texts'], data['buttons']

                        self.database.change_data('users', 'ban', 1, user['id'])
                        self.database.change_data('users', 'cause', 'abuse', user['id'])
                        self.database.add_data('logs', id=self.generate('unique-id'), user=user['id'],
                                               username=user['name'], usertype=data['usertype'],
                                               action=texts.logs('abuse', 'action', action=action))

                        bot.send_message(user['id'], texts.error('banned', user=user['id']), parse_mode='markdown',
                                         reply_markup=buttons.support())
            case 'emoji':
                if option == 'status':
                    match data['status']:
                        case 'accepted' | 'success' | 'active':
                            result = '🟢'
                        case 'processing' | 'waiting':
                            result = '🟡'
                        case 'rejected' | 'error' | 'inactive':
                            result = '🔴'
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

                        text = "*АДМИН-ПАНЕЛЬ*\n\n" \
                               f"✏️ Логов: *{len(self.database.get_data('logs'))}*\n" \
                               f"👥 Пользователей: *{len(self.database.get_data('users'))}*\n" \
                               f"📨 Рассылок: *{len(self.database.get_data('mailings'))}*\n" \
                               f"⭐️ Подписок: *{len(self.database.get_data('subscriptions'))}*\n\n" \
                               f"🔽 Выбери действие 🔽"

                    case 'users':
                        text += "*Пользователи*\n\n" \
                                "📍 Доступные действия:\n" \
                                "1️⃣ Просмотр всех пользователей\n" \
                                "2️⃣ Просмотр и изменение данных пользователя\n\n" \
                                "🔽 Выбери действие 🔽"

                    case 'services':
                        text += "*Сервисы*\n\n" \
                                "📍 Доступные действия:\n" \
                                "1️⃣ Добавление нового сервиса\n"
                        if len(self.database.get_data('services')) > 0:
                            text += "2️⃣ Управление сервисом и его данными\n"

                        text += "\n🔽 Выбери действие 🔽"

                    case 'subscriptions':
                        settings = self.handler.file('read', 'settings')
                        prices = settings['prices']
                        currency, cryptocurrency = settings['main']['currency'], settings['main']['cryptocurrency']

                        text += "*Подписки*\n\n" \
                                "*Подписки и цены*\n"

                        for subscription, subscription_data in self.configs['subscriptions']['types'].items():
                            subscription_prices = self.handler.format(
                                'dict', 'currencies-convert', summary=prices[subscription])
                            text += f" - {subscription_data['title'].capitalize()}: " \
                                    f"*{subscription_prices[currency]} {currency} " \
                                    f"({subscription_prices[cryptocurrency]} {cryptocurrency})*\n"

                        text += "\n🔽 Выбери подписку 🔽"

                    case 'project':
                        text += "*Проект*\n\n" \
                                "📍 Доступные действия:\n" \
                                "1️⃣ Просмотр логов\n" \
                                "2️⃣ Рассылка сообщений пользователям\n\n" \
                                "🔽 Выбери действие 🔽"

                    case 'messaging':
                        text += "*Рассылка сообщений*\n\n" \
                                "📍 Доступна рассылка:\n" \
                                "1️⃣ Всем пользователям\n" \
                                "2️⃣ Определённому пользователю\n\n" \
                                "🔽 Выбери действие 🔽"

                    case 'settings':
                        text += "*Настройки*\n\n" \
                                "📍 Доступные изменения:\n" \
                                "1️⃣ Валюты или криптовалюты\n" \
                                "2️⃣ Общего реферального процента\n\n" \
                                "🔽 Выбери действие 🔽"

            case 'user':
                userdata = self.database.get_data_by_value('users', 'id', data['user'])[0]

                match mode:
                    case 'main':
                        # f"`https://t.me/{self.configs['bot']['login']}?start={userdata[0]}`\n"
                        currency = self.handler.file('read', 'settings')['main']['currency']
                        subscription = self.handler.recognition('subscription', 'user', user=userdata['id'])

                        text = "*ГЛАВНОЕ МЕНЮ*\n\n" \
                               f"💰 Баланс: *{0} {currency}*\n" \
                               f"⭐️ Текущая подписка: " \
                               f"*{'Нет' if subscription is None else subscription['title']}*\n"

                        if subscription is not None:
                            text += f"🗓 Подписка истекает: *{subscription['expiration']}*\n"

                        text += f"📨 Рассылки: " \
                                f"*{len(self.database.get_data_by_value('mailings', 'user', userdata['id']))}* шт.\n\n" \
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

    def show(self, mode, additional=None, amount=5, reverse=True, option=None, **data):
        array, text, i = list(), '', 0
        separated = list()

        match mode:
            case 'log':
                item = data['item']
                text += f"👤 Пользователь: [{item['username']}](tg://user?id={item['user']}) | ID:`{item['user']}`\n" \
                        f"⚙️ Тип: {self.configs['users']['types'][item['usertype']].capitalize()}\n" \
                        f"🗓 Дата: {item['date'].strftime('%H:%M:%S / %d.%m.%Y')}\n" \
                        f"🔔 Действие: {item['action']}"

                return text

            case 'user':
                item = data['item']
                currency = self.handler.file('read', 'settings')['main']['currency']
                subscription = self.handler.recognition('subscription', 'user', user=item['id'])

                text += f"👤 Имя: [{item['name']}](tg://user?id={item['id']}) | ID:`{item['id']}`\n" \
                        f"🗓 Дата регистрации: {item['registration'].strftime('%H:%M:%S / %d.%m.%Y')}\n" \
                        f"💰 Баланс: *{item['balance']} {currency}*\n" \
                        f"🚫 Бан: {'❎' if not item['ban'] else '✅'}\n" \
                        f"🛍 Подписок: *{len(self.database.get_data_by_value('subscriptions', 'user', item['id']))}*"

                if subscription is not None:
                    text += f"\n⭐️ Подписка: *{subscription['title'].capitalize()}*\n" \
                            f"🗓 Подписка истекает: {subscription['expiration']}\n"

                if additional == 'full':
                    privileges = self.handler.format('str', 'user', 'privileges', privileges=item['privileges'])
                    inviter = False if not item['inviter'] else \
                        self.database.get_data_by_value('users', 'id', item['inviter'])[0]
                    inviter = "*Без пригласителя*" if not inviter else f"[{inviter['name']}]" \
                                                                       f"(tg://user?id={inviter['id']}) | " \
                                                                       f"ID:`{inviter['id']}`"
                    text += f"\n😎 Привилегии: *{privileges}*\n" \
                            f"🤝 Пригласил: {inviter}\n" \
                            f"🔗 Приглашено: " \
                            f"*{len(self.database.get_data_by_value('users', 'inviter', item['id']))}*\n" \
                            f"💳 Платежей:" \
                            f" *{len(self.database.get_data_by_value('payments', 'user', item['id']))}*\n" \
                            f"📨 Рассылок: " \
                            f"*{len(self.database.get_data_by_value('mailings', 'user', item['id']))}*\n" \
                            f"⚙️ Действий : " \
                            f"*{len(self.database.get_data_by_value('logs', 'user', item['id']))}*"

                    if item['ip'] != 'None' and item['agent'] != '':
                        location = self.handler.format(
                            'str', 'user', 'location',
                            location=self.handler.recognition('user', 'location', ip=item['ip']))

                        text += f"\n📍 Локация: `{item['ip']}` ({location})\n" \
                                f"🐾 Юзер-агент: `{item['agent']}`"

                return text

            case 'subscription':
                item = data['item']
                userdata = self.database.get_data_by_value('users', 'id', item['user'])[0]
                text += f"⚙️ Тип: *{self.configs['subscriptions']['types'][item['type']]['title'].capitalize()}*\n" \
                        f"{'🟢' if item['status'] == 'active' else '🔴'} Статус: " \
                        f"*{self.configs['subscriptions']['statuses'][item['status']].capitalize()}*\n" \
                        f"👤 Пользователь: " \
                        f"[{userdata['name']}](tg://user?id={userdata['id']}) | ID:`{userdata['id']}`\n" \
                        f"▶️ Активирована: *{item['purchased'].strftime('%H:%M:%S / %d.%m.%Y')}\n*" \
                        f"⏹ Завершается: *{item['expiration'].strftime('%H:%M:%S / %d.%m.%Y')}*"

                return text

            case 'payment':
                item = data['item']
                currency = self.handler.file('read', 'settings')['main']['currency']
                userdata = self.database.get_data_by_value('users', 'id', item['user'])[0]
                text += f"🆔 Уникальный ID: `{item['id']}`\n" \
                        f"⚙️ Тип: *{self.configs['payments']['types'][item['type']].capitalize()}*\n" \
                        f"{self.handler.recognition('emoji', 'status', status=item['status'])} " \
                        f"Статус: *{self.configs['payments']['statuses'][item['status']].capitalize()}*\n" \
                        f"💰 Сумма: *{item['amount']} {currency}*\n" \
                        f"👤 Пользователь: [{userdata['name']}](tg://user?id={userdata['id']}) | ID:`{userdata['id']}`\n" \
                        f"🗓 Дата: {item['date'].strftime('%H:%M:%S / %d.%m.%Y')}"

                return text

            case 'referral':
                item = data['item']
                currency = self.handler.file('read', 'settings')['main']['currency']
                subscription = self.handler.recognition('subscription', 'user', user=item['id'])
                text += f"👤 Имя: [{item['name']}](tg://user?id={item['id']}) | ID:`{item['id']}`\n" \
                        f"💰 Баланс: *{item['balance']} {currency}*\n" \
                        f"⭐️ Подписка: *{subscription['title'].capitalize() if subscription is not None else 'Нет'}*\n"

                if subscription is not None:
                    text += f"🗓 Подписка истекает: {subscription['expiration']}\n"

                text += f"📨 Рассылок: *{len(self.database.get_data_by_value('mailings', 'user', item['id']))}*\n" \
                        f"🚫 Бан: {'❎' if not item['ban'] else '✅'}"

                return text

            case 'mailing':
                item = data['item']
                userdata = self.database.get_data_by_value('users', 'id', item['user'])[0]
                extended_data = json.loads(item['mail'])
                text += f"🆔 Уникальный ID:`{item['id']}`\n" \
                        f"🗓 Дата: *{item['date'].strftime('%H:%M:%S / %d.%m.%Y')}*\n" \
                        f"{self.handler.recognition('emoji', 'status', status=item['status'])} " \
                        f"Статус: *{self.configs['mailings']['statuses'][item['status']].capitalize()}*\n" \
                        f"⚙️ Сервис: {item['service']}\n" \
                        f"👤 Пользователь: [{userdata['name']}](tg://user?id={userdata['id']}) | " \
                        f"ID:`{userdata['id']}`\n\n" \
                        f"*Данные*"

                return text

            case 'service':
                item = data['item']
                text += f"📍 Название: *{item['name']}*\n" \
                        f"🔗 Домен: {item['domain']}\n" \
                        f"{self.handler.recognition('emoji', 'status', status=item['status'])} " \
                        f"Статус: *{self.configs['services']['statuses'][item['status']].capitalize()}*"

                return text

            case _:
                array = data['array']

        for item in array[::-1] if reverse else array:
            value, result = None, None

            if i % amount == 0 and text != '':
                separated.append(text)
                text = ''

            match mode:
                case 'logs':
                    value = 'Лог'
                    result = self.show('log', item=item)

                case 'users':
                    value = 'Пользователь'
                    result = self.show('user', item=item)

                case 'subscriptions':
                    value = 'Подписка'
                    result = self.show('subscription', item=item)

                case 'payments':
                    value = 'Платёж'
                    result = self.show('payment', item=item)

                case 'referrals':
                    value = 'Реферал'
                    result = self.show('referral', item=item)

                case 'mailings':
                    value = 'Рассылка'
                    result = self.show('mailing', item=item)

            text += f"{value} #{len(array) - i if reverse else i + 1}\n" \
                    f"{result}\n\n"
            i += 1

        separated.append(text)
        return separated

    def control(self, mode, option=None, step=1, **data):
        text = str()
        match mode:
            case 'user':
                userdata = self.database.get_data_by_value('users', 'id', data['id'])[0]

                match option:
                    case 'ban':
                        status = True if userdata['id'] else False
                        text = "*Блокировка/разблокировка*\n\n" \
                               f"📌 Текущий статус: {'🟢 Не заблокирован' if not status else '🔴 Заблокирован'}\n\n" \
                               f"⚠️ Чтобы {'заблокировать' if not status else 'разблокировать'} пользователя, " \
                               f"нажми кнопку {'блокировки' if not status else 'разблокировки'} ниже.\n\n" \
                               f"🔽 {'Заблокировать пользователя' if not status else 'Разблокировать пользователя'} 🔽"

                    case 'balance':
                        currency = self.handler.file('read', 'settings')['main']['currency']
                        balance = self.database.get_data_by_value('users', 'id', data['id'])[0]['balance']
                        text += "*Баланс*\n\n" \
                                f"💰 Текущий баланс: *{balance} {currency}*\n\n" \
                                "📍 Возможные действия:\n" \
                                "1️⃣ Добавить средства\n" \
                                "2️⃣ Изменить баланс\n\n" \
                                "🔽 Выбери действие 🔽"

                    case 'privileges':
                        privileges = self.configs['users']['privileges']
                        user_privileges = ast.literal_eval(
                            self.database.get_data_by_value('users', 'id', data['id'])[0]['privileges'])

                        text += "*Привилегии*\n\n"

                        for privilege in privileges:
                            text += f"{'✅' if privilege in user_privileges else '❎'} " \
                                    f"{privileges[privilege].capitalize()}\n"

                        match step:
                            case 1:
                                text += "\n📍 Доступные действия:\n"
                                if len(user_privileges) < len(privileges.keys()):
                                    text += "🔸 Добавление привилегий\n"
                                if len(user_privileges) > 0:
                                    text += "🔹 Удаление привилегий\n"

                                text += "\n🔽 Выбери действие 🔽"

                            case 2:
                                action = "добавить её пользователю" \
                                    if data['type'] == 'add' else "удалить её у пользователя"
                                text += f"\n🔔 Нажми на выбранную привилегию, чтобы {action}.\n\n" \
                                        "🔽 Выбери привилегию 🔽"

            case 'admin':
                match option:
                    case 'services':
                        services = self.database.get_data('services')
                        text = "*Управление сервисами*\n\n" \
                               f"📌 Всего сервисов: *{len(services)}*\n\n" \
                               "*Сервисы*\n"
                        if len(services) > 0:
                            for service in services:
                                text += f"{'🟢' if service['status'] == 'active' else '🔴'} {service['name']}\n"
                            text += "\n🔽 Выбери сервис 🔽"
                        else:
                            text += " - Сервисов ещё нет 🤷🏻‍♂️"

                    case 'subscription':
                        subscription = self.configs['subscriptions']['types'][data['subscription']]

                        if 'users' in data.keys() and data['users']:
                            subscribers_all = self.handler.format(
                                'list', 'subscribers', subscription=data['subscription'])
                            subscribers_active = self.handler.format(
                                'list', 'subscribers', 'active', subscription=data['subscription'])

                            text += f"*Пользователи {subscription['title'][:-2]}ой подписки*\n\n" \
                                    f"🟡 Всего: *{len(subscribers_all)}*\n" \
                                    f"🟢 С активной подпиской: *{len(subscribers_active)}*\n\n" \
                                    "📌 Доступные действия:\n" \
                                    "1️⃣ Просмотр всех пользователей\n" \
                                    "2️⃣ Просмотр пользователей с активной подпиской"

                        else:
                            settings = self.handler.file('read', 'settings')
                            currency, cryptocurrency = settings['main']['currency'], settings['main']['cryptocurrency']
                            price = settings['prices'][data['subscription']]
                            subscription_prices = self.handler.format('dict', 'currencies-convert', summary=price)

                            text = "*Управление подпиской*\n\n" \
                                   f"📍 Название: *{subscription['title'].capitalize()}*\n" \
                                   f"🗓 Продолжительность: *{subscription['duration']} " \
                                   f"{'ч.' if subscription['type'] == 'hour' else 'дн.'}*\n" \
                                   f"💰 Цена: *{subscription_prices[currency]} {currency} " \
                                   f"({subscription_prices[cryptocurrency]} {cryptocurrency})*\n\n" \
                                   "📌 Доступные действия:\n" \
                                   "1️⃣ Изменять цену подписки\n" \
                                   "2️⃣ Посмотреть пользователей купивших подписку"

                        text += "\n\n🔽 Выбери действие 🔽"

                    case 'currencies':
                        settings = self.handler.file('read', 'settings')['main']
                        text += "*Изменение валюты*\n\n" \
                                f"▫️ Текущая валюта: *{settings['currency']}*\n" \
                                f"▪️ Текущая криптовалюта: *{settings['cryptocurrency']}*\n\n" \
                                f"📌 Доступные действия:\n" \
                                f"1️⃣ Изменить текущую валюту\n" \
                                f"2️⃣ Изменить текущую криптовалюту\n\n" \
                                f"🔽 Выбери действие 🔽"

        return text

    def processes(self, user, mode, option=None, step=0, **data):
        text = str()

        match user:
            case 'admin':
                if mode == 'find-user':
                    text += "*Поиск пользователя*\n\n" \
                            "📌 Для того, чтобы найти пользователя, введи его ID. " \
                            "В противном случае отмени действие.\n\n" \
                            "🔽 Введи идентификатор 🔽"

                elif mode == 'add-service':
                    value = 'данные'

                    text += f"*Добавление сервиса ({step}/{3})*\n\n"

                    if 'error' in data.keys():
                        text += f"⚠️ {data['error']}\n\n"

                    text += f"📍 Название: *{data['title'] if 'title' in data.keys() else 'Не установлено'}*\n" \
                            f"🔗 Домен: {data['domain'] if 'domain' in data.keys() else '*Не установлен*'}\n\n" \

                    if option is None:
                        text += f"📌 Нужно ввести: "

                        match step:
                            case 1:
                                value = 'название'
                                text += f"*{value.capitalize()} сервиса*"
                            case 2:
                                value = 'домен'
                                text += f'*{value}*'

                        text += f"\n\n🔽 Введи {value} 🔽"
                    else:
                        text += "🔽 Подтверди добавление 🔽"

                elif mode == 'update-service':
                    service = self.database.get_data_by_value('services', 'name', data['service'])[0]

                    match option:
                        case 'title':
                            text += "*Изменение названия*\n\n" \
                                    f"📍 Текущее название: *{service['name']}*\n\n" \
                                    "📌 Для того, чтобы изменить название сервиса, введи новое, " \
                                    "на которое хочешь заменить. В противном случае отмени действие.\n\n" \
                                    "🔽 Введи название 🔽"

                        case 'domain':
                            text += "*Изменение домена*\n\n" \
                                    f"📍 Текущий домен: {service['domain']}\n\n" \
                                    "📌 Для того, чтобы изменить домен сервиса, введи новый, " \
                                    "на который хочешь заменить. В противном случае отмени действие.\n\n" \
                                    "🔽 Введи домен 🔽"

                elif mode == 'send-message':
                    steps = 0
                    recipient, message, action = None, "*Не установлен*", str()

                    match option:
                        case 'all':
                            steps = 2
                            recipient = "*Всем пользователям*"

                            match step:
                                case 1:
                                    action = "📌 Введи текст сообщения, который хочешь отправить пользователям"

                                case 2:
                                    message = f"{data['text']}"

                        case 'individual':
                            steps = 3

                            match step:
                                case 1:
                                    recipient = "*Пользователю*"
                                    action = "📌 Введи ID пользователя, которому хочешь отправить сообщениею. " \
                                             "В противном случае отмени действие."
                                case 2:
                                    user = self.database.get_data_by_value('users', 'id', data['id'])[0]
                                    recipient = f"[{user['name']}](tg://user?id={user['id']})"
                                    action = "📌 Введи текст сообщения, который хочешь отправить пользователю. " \
                                             "В противном случае отмени действие."
                                case 3:
                                    user = self.database.get_data_by_value('users', 'id', data['id'])[0]
                                    recipient = f"[{user['name']}](tg://user?id={user['id']})"
                                    message = f"{data['text']}"

                    text = f"*Отправка сообщения ({step}/{steps})*\n\n" \
                           f"👤 Кому: {recipient}\n" \
                           f"💬 Текст: {message}\n\n" \
                           f"{action}"

                elif mode == 'update-subscription-price':
                    settings = self.handler.file('read', 'settings')
                    subscription = self.configs['subscriptions']['types'][data['subscription']]
                    price, currency = settings['prices'][data['subscription']], settings['main']['currency']
                    subscription_prices = self.handler.format('dict', 'currencies-convert', summary=price)

                    text = "*Изменение цены* \n\n" \
                           f"⭐️ Подписка: *{subscription['title'].capitalize()}*\n" \
                           f"📍 Текущая цена: *{subscription_prices[currency]} {currency}*\n\n" \
                           "📌 Для того, чтобы изменить текущую цену на подписку, введи число не равное " \
                           "текущему и не менее 0.\n\n" \
                           f"⚠️ Цена должна быть указана исключительно в *{currency}*.\n\n" \
                           "🔽 Введи данные 🔽"

                elif mode == 'change-project-data':
                    datatype = data['type']

                    match datatype:
                        case 'percentage':
                            text = "*Изменение общего процента*\n\n" \
                                   f"🧮 Текущий процент: " \
                                   f"*{self.handler.file('read', 'settings')['main']['percentage']}*\n\n" \
                                   "Для того, чтобы изменить общий реферальный процент, введи число не равное " \
                                   "текущему проценту и не ниже 0. \n\n" \
                                   "🔽 Введи данные 🔽"

                        case 'currencies':
                            text = f"*Изменение {'валюты' if option == 'currency' else 'криптовалюты'}*\n\n" \
                                   f"📌  Для того, чтобы изменить {'валюту' if option == 'currency' else 'криптовалюту'}," \
                                   f" введи новую. В противном случае отмени дейтвие."

            case 'user':
                match mode:
                    case 'balance':
                        if option == 'add':
                            text = "*Добавление средств*\n\n" \
                                   "📌 Для того, чтобы добавить средства, введи значение в числовом формате. " \
                                   "В противном  случае отмени действие.\n\n" \
                                   "🔽 Введи значение 🔽"
                        elif option == 'change':
                            text = "*Изменение баланса*\n\n" \
                                   "📌 Для того, чтобы изменить баланс, введи значение в числовом формате. " \
                                   "В противном  случае отмени действие.\n\n" \
                                   "🔽 Введи значение 🔽"

        return text

    def notifications(self, mode, option=None, **data):
        text = str()

        match mode:
            case 'bot-crashed':
                text += "⚠️ *Внимание* ⚠️\n\n" \
                        "🔔 Бот был экстренно остановлен в связи с возникшей ошибкой, данные об ошибке " \
                        "записаны на сервере.\n\n" \
                        f"📁 Путь: `{data['path']}`\n" \
                        f"📄 Файл: `{data['file']}`"

            case 'deposit-expired':
                text += "⚠️ *Внимание* ⚠️\n\n" \
                        f"🔔 Твой платёж с уникальным ID `{data['id']}` автоматически завершён. " \
                        f"Чтобы создать ещё один платёж на пополнение баланса, " \
                        f"перейди в раздел *«Баланс»* и нажми *«Депозит»*."

            case 'deposit-closed':
                text += "Платёж отклонён\n\n" \
                        f"🔔 Твой платёж успешно отклонен"

            case 'group':
                match option:
                    case 'abuse-admin':
                        text += "⚠️ *Абьюз бота* ⚠️\n\n" \
                                f"🔔 Пользователь [{data['name']}](tg://user?id={data['id']}) | ID:{data['id']} " \
                                "попытался запустить админ-панель, но у него нет на это доступа, поэтому он был " \
                                "автоматически забанен."

                    case 'abuse-action':
                        text += "⚠️ *Абьюз бота* ⚠️\n\n" \
                                f"🔔 Пользователь [{data['name']}](tg://user?id={data['id']}) | ID:{data['id']} " \
                                f"попытался воспользоваться командой «{data['action']}», но не смог. " \
                                "Скорее этот человек пытается абьюзить бота или ищет дырки, " \
                                "поэтому он был автоматически забанен."

                    case 'add-funds':
                        currency = self.handler.file('read', 'settings')['main']['currency']
                        text += "💸 *Новое пополнение* 💸\n\n" \
                                f"🔔 Пользователь [{data['name']}](tg://user?id={data['id']}) | ID:{data['id']} " \
                                f"успешно пополнил совй баланс на *{data['summary']} {currency}*."

                    case 'messaging':
                        text += "📥 *Результаты рассылки* 📤\n\n" \
                                f"🔔 Администратор [{data['name']}](tg://user?id={data['id']}) произвёл рассылку.\n\n" \
                                "*Результаты*\n" \
                                f"🟢 Отправлено: *{data['sent']}*\n" \
                                f"🔴 Не отправлено: *{data['unsent']}*\n" \
                                f"🚫 Забанено: *{data['blocked']}*\n" \
                                f"⛔️ Удалено: *{data['deleted']}*"
        return text

    def logs(self, mode, option=None, value=None, **data):
        text = str()

        match mode:
            case 'abuse':
                if option == 'start':
                    pass
                elif option == 'action':
                    text = f"Попытался воспользоваться командой «{data['action']}», но не смог. Скорее этот человек " \
                           f"пытается абьюзить бота или ищет дырки, поэтому он был автоматически забанен."
            case 'admin':
                match option:
                    case 'user':
                        if value == 'ban':
                            text = f"{'Забанил' if data['status'] else 'Разбанил'} пользователя " \
                                   f"[{data['name']}](tg://user?id={data['id']}) | ID:`{data['id']}`."
                    case 'service':
                        if value == 'status':
                            service = data['array']
                            text = f"{'Включил' if service['status'] == 'active' else 'Выключил'} сервис " \
                                   f"{service['name']}."
                    case 'messaging':
                        if value == 'all':
                            text += f"Произвёл общую рассылку всем пользователям.\n\n" \
                                    f"*Результаты рассылки*\n" \
                                    f"🟢 Отправлено: *{data['sent']}*\n" \
                                    f"🔴 Не отправлено: *{data['unsent']}*\n" \
                                    f"🚫 Забанено: *{data['blocked']}*\n" \
                                    f"⛔️ Удалено: *{data['deleted']}*"

                        elif value == 'individual':
                            text += f"Произведена автоматическая рассылка пользователю " \
                                    f"[{data['user']['name']}](tg://user?id={data['user']['id']}) | " \
                                    f"ID: `{data['user']['id']}`.\n" \
                                    f"⚙️ Статус: *{data['status']}*\n" \
                                    f"{data['cause']}"

        return text

    def error(self, mode, option=None, **data):
        text = "🚫 *Ошибка*\n\n⚠️ "

        match mode:
            case 'banned':
                userdata = self.database.get_data_by_value('users', 'id', data['user'])[0]
                cause = self.handler.recognition('ban', 'cause', cause=userdata['cause'])
                text += "Ты был заблокирован администрацией, за нарушение правил использования сервиса.\n\n" \
                        f"📍 *Причина*: {cause}.\n\n" \
                        "📌 Если ты считаешь это ошибкой, то ты можешь обратиться в поддержку, " \
                        "для решения текущего вопроса.\n\n" \
                        "🔽 Обратиться в поддержку 🔽"

            case 'empty':
                values = {'first': None, 'second': None, 'third': None}

                match option:
                    case 'users':
                        values['first'], values['second'], values['third'] = \
                            "пользователей", "пользователя", "пользователь"

                text = "❌ *Нечего искать* ❌\n\n" \
                       f"⚠️ К сожалению база {values['first']} ещё пуста, не добавлено ни единого " \
                       f"{values['second']} и поэтому некого искать. Эта функция станет доступной тогда, " \
                       f"когда будет добавлен первый {values['third']}."

            case 'exist':
                match option:
                    case 'service-title':
                        text = f"Сервис с таким названием уже добавлен ({data['title']})."
                    case 'service-domain':
                        service = self.database.get_data_by_value('services', 'domain', data['domain'])[0]['name']
                        text = f"Домен {data['domain']} уже есть в базе данных и он принадлежит сервису *{service}*."

            case 'same':
                text += f"Значение *{data['value']}* не должно совпадать с текущим. " \
                        f"Попробуй ещё раз или же отмени действие."

            case 'less':
                text += f"Значение должно быть *не менее {data['value'] if 'value' in data.keys() else 1}*. " \
                        f"Попробуй ещё раз или же отмени действие."
            case 'not-exist':
                match option:
                    case 'user':
                        text += f"Пользователь с идентификатором {data['id']} не найден."
            case 'not-found':
                value = None

                match option:
                    case 'user':
                        value = 'пользователь'

                text += f"{value.capitalize()} с идентификатором «*{data['id']}*» не найден. "

            case 'not-link':
                text += "Неправильный формат ссылки. Попробуй ввести ссылку " \
                        "ещё раз в формате https://yourdomain.com."

            case 'not-numeric':
                text += "Значение должно быть в числовом формате. Введи значение ещё раз или отмени действие."

            case 'not-string':
                text += "Значение должно быть в текстовом формате. Введи значение ещё раз или отмени действие."

        return text

    def success(self, mode, option=None, **data):
        text = "✅ *Успешно* ✅\n\n🔔"

        match mode:
            case 'found-data':
                text = "*Поиск завершён успешно* ✅\n\n🔔"

                if option == 'user':
                    text += f"Пользователь с идентификатором «*{data['id']}*» был успешно найден, формируем данные..."
            case 'updated-data':
                if option == 'add-balance':
                    text += "Средства успешно добавлены. Формируем данные..."
                elif option == 'change-balance':
                    text += "Баланс успешно обновлен. Формируем данные..."
                elif option == 'service-title':
                    text += f"Название сервиса успешно изменено с *{data['old']}* на *{data['new']}*"
                elif option == 'service-domain':
                    text += f"Домен сервиса успешно изменён с *{data['old']}* на *{data['new']}*"
                elif option == 'subscription-price':
                    text += f"Цена подписки успешно изменена с *{data['old']}* на *{data['new']} {data['currency']}*"
                elif 'project' in option:
                    option = option.split('-')[-1]

                    match option:
                        case 'percentage':
                            text += f"Общий реферальный процент успешно изменён с *{data['old']}*  на *{data['new']}*"
                        case 'currency':
                            text += f"Валюта успешно изменена с *{data['old']}*  на *{data['new']}*"
                        case 'cryptocurrency':
                            text += f"Криптовалюта успешно изменена с *{data['old']}*  на *{data['new']}*"



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

    @staticmethod
    def cancel_reply(text):
        markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        return markup.add(types.KeyboardButton(f'❌ Отменить {text}'))

    @staticmethod
    def cancel_inline(action, user=None, additional=None):
        markup = types.InlineKeyboardMarkup()
        query = f'cancel-{action}-{user}' if user else f'cancel-{action}'
        return markup.add(types.InlineKeyboardButton(
            '🚫 Отменить', callback_data=f"{f'{query}-{additional}' if additional is not None else query}"))

    @staticmethod
    def comeback_reply(text):
        markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        return markup.add(types.KeyboardButton(f'↩️ Назад к {text}'))

    @staticmethod
    def comeback_inline(action, text=None, **data):
        markup = types.InlineKeyboardMarkup()
        try:
            query = f"comeback-{action}-{data['id']}"
        except KeyError:
            query = f"comeback-{action}"

        return markup.add(types.InlineKeyboardButton(
            '↩️ Назад' if text is None else f'↩️ Назад к {text}', callback_data=query))

    @staticmethod
    def confirm(action, **data):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('✅ Подтвердить', callback_data=f"confirm-{action}"))

        if 'comeback' in data.keys():
            markup.add(types.InlineKeyboardButton('↩️ Назад', callback_data=f"comeback-{data['comeback']}"))

        if 'cancel' in data.keys():
            markup.add(types.InlineKeyboardButton('🚫 Отменить', callback_data=f"cancel-{data['cancel']}"))

        return markup

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
                            types.KeyboardButton('🛍 Подписки'),
                            types.KeyboardButton('⭐️ Проект')
                        )

                    case 'users':
                        markup.add(
                            types.KeyboardButton('👁 Посмотреть всех'),
                            types.KeyboardButton('🕹 Управлять')
                        )

                    case 'user':
                        markup, markups, row, additional = dict(), list(), list(), dict()
                        comeback = False
                        user = data['id']

                        items = {
                            '⛔️ Блокировка': {'type': 'control', 'action': 'ban'},
                            '💰 Баланс': {'type': 'control', 'action': 'balance'},
                            '😎 Привилегии': {'type': 'control', 'action': 'privileges'}
                        }

                        if len(self.database.get_data_by_value('logs', 'user', user)):
                            items['⚙️ Действия'] = {'type': 'get', 'action': 'logs'}

                        if len(self.database.get_data_by_value('payments', 'user', user)):
                            items['💳 Платежи'] = {'type': 'get', 'action': 'payments'}

                        if len(self.database.get_data_by_value('subscriptions', 'user', user)):
                            items['⭐️ Подписки'] = {'type': 'get', 'action': 'subscriptions'}

                        if len(self.database.get_data_by_value('users', 'inviter', user)):
                            items['🔗 Рефералы'] = {'type': 'get', 'action': 'referrals'}

                        if len(self.database.get_data_by_value('mailings', 'user', user)):
                            items['📨 Рассылки'] = {'type': 'get', 'action': 'mailings'}

                        for name, values in items.items():
                            if len(row) < width:
                                row.append({
                                    'text': name,
                                    'callback_data': f'{values["type"]}-user-{user}-{values["action"]}'
                                })

                                if values['action'] == 'ban':
                                    markups.append(row)
                                    row = list()

                            if len(row) == width:
                                markups.append(row)
                                row = list()
                        else:
                            if len(row) != 0:
                                markups.append(row)

                        markup['inline_keyboard'] = markups
                        markup = str(markup).replace('\'', '"')

                    case 'services':
                        markup.add(
                            types.KeyboardButton('➕ Добавить'),
                            types.KeyboardButton('⚙️ Управлять') if len(self.database.get_data('services')) > 0 else ''
                        )

                    case 'service':
                        comeback = False
                        service = data['array']
                        markup, markups, row, additional = dict(), list(), list(), dict()

                        mode = '🔴 Выключить' if service['status'] == 'active' else '🟢 Включить'
                        items = {
                            mode: {'type': 'set', 'action': 'status'},
                            '📍 Название': {'type': 'update', 'action': 'title'},
                            '🔗 Домен': {'type': 'update', 'action': 'domain'},
                            '➖ Удалить сервис': {'type': 'delete', 'action': 'data'}
                        }

                        for name, values in items.items():
                            if len(row) < width:
                                row.append({
                                    'text': name,
                                    'callback_data': f"{values['type']}-service-{service['name']}-{values['action']}"
                                })
                                if values['action'] == 'status':
                                    markups.append(row)
                                    row = list()

                            if len(row) == width:
                                markups.append(row)
                                row = list()
                        else:
                            if len(row) != 0:
                                markups.append(row)

                        markups.append([{'text': '↩️ Назад', 'callback_data': 'comeback-to-select-services-admin'}])
                        markup['inline_keyboard'] = markups
                        markup = str(markup).replace('\'', '"')

                    case 'subscriptions':
                        row = list()

                        for subscription in self.configs['subscriptions']['types'].values():
                            if len(row) < width:
                                row.append(subscription['title'].capitalize())

                                if subscription['title'] == 'пробная':
                                    markup.keyboard.append(row)
                                    row = list()

                            if len(row) == width:
                                markup.keyboard.append(row)
                                row = list()
                        else:
                            if len(row) != 0:
                                markup.keyboard.append(row)

                    case 'project':
                        markup.add(
                            types.KeyboardButton('🗞 Логи'),
                            types.KeyboardButton('📨 Рассылка'),
                            types.KeyboardButton('⚙️ Настройки')
                        )

                    case 'messaging':
                        comeback = 'проекту'
                        markup.add(
                            types.KeyboardButton("👥 Всем"),
                            types.KeyboardButton("👤 Одному")
                        )

                    case 'settings':
                        comeback = 'проекту'
                        markup.add(
                            types.KeyboardButton("🪙 Валюта"),
                            types.KeyboardButton("🧮 Процент")
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

    def control(self, mode, option=None, step=1, **data):
        markup = types.InlineKeyboardMarkup()

        match mode:
            case 'user':
                comeback, cancel, query = True, False, None
                userdata = self.database.get_data_by_value('users', 'id', data['id'])[0]

                match option:
                    case 'ban':
                        status = True if userdata['ban'] else False
                        markup.add(types.InlineKeyboardButton(
                            "🔴 Забанить" if not status else "🟢 Разбанить",
                            callback_data=f"set-ban-{True if not status else False}-user-{userdata['id']}"))

                    case 'balance':
                        markup.add(
                            types.InlineKeyboardButton(
                                "➕ Добавить", callback_data=f"update-balance-user-{userdata['id']}-add"),
                            types.InlineKeyboardButton(
                                "🔄 Изменить", callback_data=f"update-balance-user-{userdata['id']}-change")
                        )

                    case 'privileges':
                        match step:
                            case 1:
                                privileges = self.configs['users']['privileges']
                                user_privileges = ast.literal_eval(
                                    self.database.get_data_by_value('users', 'id', data['id'])[0]['privileges'])

                                if len(user_privileges) < len(privileges.keys()):
                                    markup.add(types.InlineKeyboardButton(
                                        "➕ Добавить", callback_data=f"control-privileges-user-{data['id']}-add"))
                                if len(user_privileges) > 0:
                                    markup.add(types.InlineKeyboardButton(
                                        "➖Удалить", callback_data=f"control-privileges-user-{data['id']}-delete"))
                            case 2:
                                comeback, width = False, 2
                                markup, markups, row, additional = dict(), list(), list(), dict()

                                privileges = self.handler.format('list', 'privileges',
                                                                 type=data['type'], user=data['id'])

                                for privilege in privileges:
                                    if len(row) < width:
                                        query = f"update-user-{data['id']}-{data['type']}-privilege-{privilege}"
                                        row.append({
                                            'text': self.configs['users']['privileges'][privilege].capitalize(),
                                            'callback_data': query
                                        })

                                    if len(row) == width:
                                        markups.append(row)
                                        row = list()

                                else:
                                    if len(row) != 0:
                                        markups.append(row)

                                markups.append([{
                                    'text': '↩️ Назад',
                                    'callback_data': f"comeback-to-user-{data['id']}-privileges-control"
                                }])
                                markup['inline_keyboard'] = markups
                                markup = str(markup).replace('\'', '"')

                if comeback:
                    markup.add(
                        types.InlineKeyboardButton(
                            "↩️ Назад", callback_data=f"comeback-to-user-menu-{userdata['id']}"))

                if cancel:
                    markup.add(
                        types.InlineKeyboardButton(
                            f"🚫 Отменить{'' if type(cancel) == bool else f' {cancel}'}",
                            callback_data=f"cancel-{query}"))

            case 'admin':
                match option:
                    case 'services':
                        match step:
                            case 1:
                                services = self.database.get_data('services')
                                width = data['width'] if 'width' in data.keys() else 2
                                markup, markups, row, additional = dict(), list(), list(), dict()

                                for service in services:
                                    if len(row) < width:
                                        row.append({
                                            'text': service['name'],
                                            'callback_data': f"select-admin-service-{service['name']}"
                                        })

                                    if len(row) == width:
                                        markups.append(row)
                                        row = list()
                                else:
                                    if len(row) != 0:
                                        markups.append(row)

                                markup['inline_keyboard'] = markups
                                markup = str(markup).replace('\'', '"')

                    case 'subscription':
                        if 'users' in data.keys() and data['users']:
                            query = f"get-subscription-{data['subscription']}-users"
                            markup.add(
                                types.InlineKeyboardButton("🟢 Активные", callback_data=f"{query}-active"),
                                types.InlineKeyboardButton("🟡 Все", callback_data=f"{query}-all")
                            )

                        else:
                            markup.add(
                                types.InlineKeyboardButton(
                                    "💰 Цена", callback_data=f"update-subscription-{data['subscription']}-price"),
                                types.InlineKeyboardButton(
                                    "👥 Пользователи", callback_data=f"control-subscription-{data['subscription']}-users"))

                        if 'comeback' in data.keys():
                            markup.add(types.InlineKeyboardButton(
                                "↩️ Назад", callback_data=f"comeback-{data['comeback']}"))

                    case 'currencies':
                        markup.add(types.InlineKeyboardButton("▫️ Валюта", callback_data='update-project-currency'))
                        markup.add(types.InlineKeyboardButton(
                            "▪️ Криптовалюта", callback_data='update-project-cryptocurrency'))
                        markup.add(types.InlineKeyboardButton("↩️ Назад", callback_data='comeback-to-project-settings'))

                    case 'send-message':
                        markup.add(
                            types.InlineKeyboardButton("📩 Отправить", callback_data=f"send-message"))
                        markup.add(
                            types.InlineKeyboardButton(
                                "↩️ Назад", callback_data=f"comeback-to-messaging-{data['type']}-{step}")
                        )
        return markup


if __name__ == '__main__':
    _configs = Configs().initialization()
    _database = Database(_configs)
    # _database.recreate_table()
    # _database.add_data(
    #     'mailings',
    #     id='test234244375675',
    #     service='test',
    #     user=1603149905,
    #     mail=json.dumps({
    #         'recipient': 'test@test.com',
    #         'domain': 'test.com',
    #         'template': 'test.com/template'
    #     })
    # )

    # i = 1
    # while i < 15:
    #     user = 1603149905 if random.randint(0, 1) else random.randint(111111111, 999999999)
    #     _database.add_data('logs', user=user,
    #                        username='Дипси' if user == 1603149905 else f'Пользователь-{user}',
    #                        usertype='admin' if user == 1603149905 else 'user',
    #                        action=f"Действие пользователя {user}"
    #     )
    #     i += 1


