import re
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
        'types': {'deposit': 'депозит', 'accrual': 'начисление'},
        'statuses': {'success': "успешно", 'pending': "в процессе", 'error': "отклонено"}}
    subscriptions = {
        'types': {
            'demo': {'title': 'пробная', 'type': 'hour', 'duration': 2},
            'week': {'title': 'недельная', 'type': 'day', 'duration': 7},
            'month': {'title': 'месячная', 'type': 'day', 'duration': 30}
        },
        'statuses': {'active': 'активна', 'inactive': 'неактивна'}
    }
    requests = {
        'types': {'withdraw': 'вывод'},
        'statuses': {'accepted': 'принята', 'processing': 'в обработке', 'rejected': 'отклонена'}
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
        configs['requests'] = self.requests
        configs['mailings'] = self.mailings

        return configs


class Database:
    tables = ['logs', 'users', 'subscriptions', 'payments', 'services', 'requests', 'mailings']

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
                    `user` BIGINT(12) NOT NULL,
                    `username` VARCHAR(255) NOT NULL,
                    `usertype` VARCHAR(255) NOT NULL,
                    `date` DATETIME NOT NULL,
                    `action` TEXT NOT NULL
                    )"""

                case 'users':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `id` BIGINT(12) NOT NULL,
                    `name` VARCHAR(255) NOT NULL,
                    `registration` DATETIME NOT NULL,
                    `balance` FLOAT NOT NULL,
                    `inviter` INT(12) NOT NULL,
                    `percentage` INT(3) NOT NULL,
                    `ban` BOOLEAN NOT NULL,
                    `cause` VARCHAR(255) NOT NULL,
                    `privileges` TEXT NOT NULL,
                    `ip` VARCHAR(255) NOT NULL,
                    `agent` VARCHAR(255) NOT NULL,
                    `data` JSON NOT NULL
                    )"""

                case 'subscriptions':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `type` VARCHAR(255) NOT NULL,
                    `user` BIGINT(12) NOT NULL,
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
                    `user` BIGINT(12) NOT NULL,
                    `amount` FLOAT NOT NULL,
                    `expiration` DATETIME NOT NULL
                    )"""

                case 'services':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `name` VARCHAR(255) NOT NULL,
                    `domains` TEXT NOT NULL,
                    `status` VARCHAR(255) NOT NULL
                    )"""

                case 'requests':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `id` VARCHAR(255) NOT NULL,
                    `date` DATETIME NOT NULL,
                    `type` VARCHAR(255) NOT NULL,
                    `status` VARCHAR(255) NOT NULL,
                    `user` VARCHAR (255) NOT NULL,
                    `data` TEXT NOT NULL
                    )"""

                case 'mailings':
                    query = f"""
                    CREATE TABLE `{table}` (
                    `id` VARCHAR(255) NOT NULL,
                    `date` DATETIME NOT NULL,
                    `status` VARCHAR(255) NOT NULL,
                    `service` VARCHAR(255) NOT NULL,
                    `user` BIGINT(12) NOT NULL,
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
                        `id`, `name`, `registration`, `balance`, `inviter`, `percentage`, 
                        `ban`, `cause`, `privileges`, `ip`, `agent`, `data`)
                        VALUES (
                        {items['id']}, '{items['name']}', '{datetime.now()}', 0, {items['inviter']}, 
                        {items['percentage']}, 0, 'None', '{list()}', 'None', '', '{json.dumps(dict())}')
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
                        status = items['status'] if 'status' in items.keys() \
                            else list(self.configs['payments']['statuses'].keys())[1]

                        query = f"""
                        INSERT INTO `{table}` (`id`, `date`, `status`, `type`, `user`, `amount`, `expiration`)
                        VALUES (
                        '{items['id']}', '{datetime.now()}', '{status}', '{items['type']}', 
                        {items['user']}, {items['amount']}, '{items['expiration']}')
                        """

                    case 'services':
                        domains = str(items['domains']).replace('\'', '"')
                        status = list(self.configs['services']['statuses'].keys())[-1]
                        query = f"""
                        INSERT INTO `{table}` (`name`, `domains`, `status`)
                        VALUES ('{items['name']}', '{domains}', '{status}')
                        """

                    case 'requests':
                        status = list(self.configs['requests']['statuses'].keys())[1]
                        query = f"""
                        INSERT INTO `{table}` (`id`, `date`, `type`, `status`, `user`, `data`)
                        VALUES (
                        '{items['id']}', '{datetime.now()}', '{items['type']}', 
                        '{status}', {items['user']}, '{items['data']}')
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
                    if type(column) is int:
                        controller.execute(
                            f"""UPDATE `{table}` SET `{setter}` = "{data}" WHERE `{table}`.`{column}` = {value}""")
                    else:
                        controller.execute(
                            f"""UPDATE `{table}` SET `{setter}` = "{data}" WHERE `{table}`.`{column}` = '{value}'""")

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
                            status = self.handler.send_message(self.bot, user, text)

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
                                status = self.handler.send_message(self.bot, user['id'], data['text'])

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

    def send_message(self, bot, userid, text, markups=''):
        try:
            bot.send_message(userid, text, parse_mode='markdown', reply_markup=markups)
            return True
        except ApiTelegramException as error:
            return error.error_code

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

            case 'payments':
                payments = self.database.get_data_by_value('payments', 'type', option[:-1])

                for payment in payments:
                    if option == 'deposits':
                        if payment['status'] == 'success':
                            result += payment['amount']
                    else:
                        result += payment['amount']

                result = round(result, 2)

            case 'accrual':
                result = round(data['amount'] / 100 * data['percentage'], 2)

        return result

    @staticmethod
    def replace(text, conditions):
        conditions = dict((re.escape(k), v) for k, v in conditions.iteritems())
        pattern = re.compile("|".join(conditions.keys()))
        return pattern.sub(lambda m: conditions[re.escape(m.group(0))], text)

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
                                if value == 'domains':
                                    domains = ast.literal_eval(service[value])
                                    for domain in domains:
                                        result.append(domain)
                                else:
                                    result.append(service[value])

                    case 'subscribers':
                        subscription = data['subscription']
                        subscriptions = self.database.get_data_by_value('subscriptions', 'type',subscription)

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

                    case 'domains':
                        services = self.database.get_data('services')

                        for service in services:
                            domains = ast.literal_eval(service['domains'])

                            for domain in domains:
                                result.append(domain.replace('/', ' ').split()[1])
                    case 'requests':
                        if 'user' in data.keys():
                            array = self.database.get_data_by_value('requests', 'user', data['user'])

                            for request in array:
                                if request['type'] == value:
                                    result.append(request)

                    case 'promoter':
                        if value == 'accruals':
                            payments = self.database.get_data_by_value('payments', 'user', data['user'])

                            if len(payments) > 0:
                                for payment in payments:
                                    if payment['type'] == 'accrual':
                                        result.append(payment)
            case 'dict':
                result = dict()

                match option:
                    case 'currencies-convert':
                        summary, settings = data['summary'], self.file('read', 'settings')['main']
                        cryptocurrency, currency = settings['cryptocurrency'], settings['currency']
                        courses = requests.get(f'https://api.kuna.io/v3/exchange-rates/{cryptocurrency.lower()}').json()
                        amount = round(summary / courses[currency.lower()] if summary != 0 else summary, 5)
                        result = {currency: summary, cryptocurrency: amount}

                    case 'payments':
                        result = {'total': 0}

                        if value == 'deposits':
                            for key in self.configs['payments']['statuses'].keys():
                                result[key] = list()
                        else:
                            result['data'] = list()

                        payments = self.database.get_data_by_value('payments', 'type', value[:-1])

                        if len(payments) > 0:
                            for payment in payments:
                                match value:
                                    case 'deposits':
                                        result[payment['status']].append(payment)
                                    case 'accruals':
                                        result['data'].append(payment)

                                result['total'] += 1

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
                            privileges = data['privileges'] if type(data['privileges']) is list \
                                else ast.literal_eval(data['privileges'])

                            if 'additional' in data.keys() and data['additional'] == 'menu':
                                for privilege in privileges:
                                    result += f" - {self.configs['users']['privileges'][privilege].capitalize()} | " \
                                              f"Команда: /{privilege}\n"
                            else:
                                if len(privileges) == 0:
                                    result = 'Нет'
                                else:
                                    i = 1
                                    for privilege in privileges:
                                        result += f"{self.configs['users']['privileges'][privilege]}" \
                                                  f"{', ' if i != len(privileges) else ''}"
                                        i += 1

                    case 'admin':
                        if value == 'payments':
                            i, payments = 1, self.format('dict', 'payments', 'deposits')
                            del payments['total']

                            for payment_status, payment_data in payments.items():
                                if len(payment_data) > 0:
                                    result += f"\n{self.recognition('emoji', 'status', status=payment_status)} " \
                                              f"{self.configs['payments']['statuses'][payment_status].capitalize()}"
                                i += 1

                        elif value == 'services':
                            if len(data['services']) > 0:
                                for service in data['services']:
                                    result += f" - {service}\n"
                            else:
                                result = None

                        elif value == 'domains':
                            i = 1
                            if 'domains' in data.keys():
                                domains = data['domains'] if type(data['domains']) is list \
                                    else ast.literal_eval(data['domains'])
                            else:
                                domains = self.format('list', 'domains')

                            if len(domains) > 0:
                                for domain in domains:
                                    result += f"\n{i}. {domain}"
                                    i += 1
                            else:
                                result = None

                        elif value == 'domain-service':
                            for service in self.database.get_data('services'):
                                domains = ast.literal_eval(service['domains'])

                                for domain in domains:
                                    if data['domain'] == domain or data['domain'] in domain:
                                        result = service['name']


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

                elif option == 'title':
                    items = data['items']
                    call, markups = items.data, items.message.json['reply_markup']['inline_keyboard']

                    for column in markups:
                        for markup in column:
                            if call == markup['callback_data']:
                                result = markup['text'].split()[-1]

                elif option == 'privilege':
                    user = self.database.get_data_by_value('users', 'id', data['user'])[0]
                    privileges = ast.literal_eval(user['privileges'])

                    if data['privilege'] in privileges:
                        result = True
                    else:
                        result = False

                elif option == 'active-withdraw-requests':
                    withdraws = self.format('list', 'requests', 'withdraw', user=data['user'])

                    for request in withdraws:
                        if request['status'] == 'processing':
                            result = request
                            break


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
                    '🛍 Подписки', 'Пробная', 'Недельная', 'Месячная',
                    '💰 Финансы', '💳 Платежи', '👁 Посмотреть платежи', '🛠 Управлять', '🪙 Начисления',
                    '⭐️ Проект', '🗞 Логи',
                    '📨 Рассылка', '👥 Всем', '👤 Одному',
                    '⚙️ Настройки', '🪙 Валюта', '🧮 Процент', '🔗 Домены'
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
            case 'promoter':
                result, action = False, data['action']
                privileges = ast.literal_eval(
                    self.database.get_data_by_value('users', 'id', data['user'])[0]['privileges'])

                actions = ['👥 Пользователи', '💸 Начисления', '💰 Запросить выплату']

                if action in actions:
                    if 'promoter' in privileges or data['usertype'] == 'admin':
                        result = True

            case 'emoji':
                if option == 'status':
                    match data['status']:
                        case 'accepted' | 'success' | 'active':
                            result = '🟢'
                        case 'processing' | 'waiting' | 'pending':
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

                        text = "*АДМИН-ПАНЕЛЬ*\n\n" \
                               f"✏️ Логов: *{len(self.database.get_data('logs'))}*\n" \
                               f"👥 Пользователей: *{len(self.database.get_data('users'))}*\n" \
                               f"📨 Рассылок: *{len(self.database.get_data('mailings'))}*\n" \
                               f"⭐️ Подписок: *{len(self.database.get_data('subscriptions'))}*\n\n" \
                               f"*Сервисы*\n" \
                               f"📌 Всего: *{len(self.database.get_data('services'))}*\n" \
                               f"🟢 Активные: " \
                               f"*{len(self.database.get_data_by_value('services', 'status', 'active'))}*\n" \
                               f"🔴 Неактивные: " \
                               f"*{len(self.database.get_data_by_value('services', 'status', 'inactive'))}*\n\n" \
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
                    case 'finances':
                        currency = self.handler.file('read', 'settings')['main']['currency']
                        text = "*Финансы*\n\n" \
                               f"🔸 Всего платежей: *{self.handler.format('dict', 'payments', 'deposits')['total']}*\n" \
                               f"📌 Сумма успешных платежей: " \
                               f"*{self.handler.calculate('payments', 'deposits')} {currency}*\n\n" \
                               f"🔹 Всего начислений: *{self.handler.format('dict', 'payments', 'accruals')['total']}*\n" \
                               f"📌 Начислено: *{self.handler.calculate('payments', 'accruals')} {currency}*\n\n" \
                               "📍 Доступные действия:\n" \
                               "1️⃣ Просмотр и изменение платежей\n" \
                               "2️⃣ Просмотр всех начислений\n\n" \
                               "🔽 Выбери действие 🔽"

                    case 'accruals':
                        pass

                    case 'payments':
                        payments = self.handler.format('dict', 'payments', 'deposits')
                        text += "*Платежи*\n\n" \
                                f"📌 Всего платежей: *{payments['total']}*\n" \

                        statuses = self.configs['payments']['statuses']
                        for key, value in statuses.items():
                            text += f"{self.handler.recognition('emoji', 'status', status=key)} " \
                                    f"{value.capitalize()}: *{len(payments[key])}*\n"

                        if payments['total'] > 0:
                            text += "\n📍 Доступные действия:\n" \
                                    "1️⃣ Просмотр платежей\n"

                            if len(payments['pending']) > 0:
                                "2️⃣ Управление платжем\n" \

                        text += "\n🔽 Выбери действие 🔽"

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
                                "2️⃣ Общего реферального процентат\n" \
                                "3️⃣ Работа с доменами\n\n" \
                                "🔽 Выбери действие 🔽"

            case 'user':
                userdata = self.database.get_data_by_value('users', 'id', data['user'])[0]

                match mode:
                    case 'main':
                        privileges = ast.literal_eval(userdata['privileges'])
                        currency = self.handler.file('read', 'settings')['main']['currency']
                        subscription = self.handler.recognition('subscription', 'user', user=userdata['id'])

                        text = "*ГЛАВНОЕ МЕНЮ*\n\n" \
                               f"💰 Баланс: *{userdata['balance']} {currency}*\n" \
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
                                f"📌 Всего: *{len(self.database.get_data('services'))}*\n" \
                                f"🟢 Активные: " \
                                f"*{len(self.database.get_data_by_value('services', 'status', 'active'))}*\n" \
                                f"🔴 Неактивные: " \
                                f"*{len(self.database.get_data_by_value('services', 'status', 'inactive'))}*\n"

                        if len(privileges) > 0:
                            privileges = self.handler.format('str', 'user', 'privileges',
                                                             privileges=privileges, additional='menu')

                            text += f"\n🔔 У тебя есть доступ к дополнительным меню:\n {privileges}\n"

                        text += "\n🔽 Выбери действие 🔽"

            case 'promoter':
                match mode:
                    case 'main':
                        user = self.database.get_data_by_value('users', 'id', data['user'])[0]

                        text += "*Промоутинг*\n\n" \
                                f"🤝 Приглашено: *" \
                                f"{len(self.database.get_data_by_value('users', 'inviter', user['id']))}*\n" \
                                f"💸 Начислений: *{len(self.handler.format('dict', 'payments', 'accruals')['data'])}*\n" \
                                f"💰 Доступно к выводу: *{user['balance']}*\n" \
                                f"🔗 Ссылка на приглашение: " \
                                f"`https://t.me/{self.configs['bot']['login']}?start={user['id']}`\n\n" \
                                "📍 Доступные действия:\n" \
                                "1️⃣ Просмотр приглашенных пользователей\n" \
                                "2️⃣ Просмотр начислений\n"

                        if user['balance'] > 0:
                            text += "3️⃣ Запрос выплаты средств\n"

                        text += "\n🔽 Выбери действие 🔽"
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
                            f"🧮 Процент: *{item['percentage']}*\n" \
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

                if additional == 'promoter':
                    text += f"🆔 Уникальный ID: `{item['id']}`\n" \
                            f"💰 Сумма: *{item['amount']} {currency}*\n" \
                            f"🗓 Дата: {item['date'].strftime('%H:%M:%S / %d.%m.%Y')}"
                else:
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
                        f"{self.handler.recognition('emoji', 'status', status=item['status'])} " \
                        f"Статус: *{self.configs['services']['statuses'][item['status']].capitalize()}*\n" \
                        f"🔗 Домены: *{len(ast.literal_eval(item['domains']))}*"

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
                    value = "Начисление" if additional == 'promoter' else "Платёж"
                    result = self.show('payment', additional, item=item)

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

                    case 'domains':
                        if 'service' in data.keys():
                            service = self.database.get_data_by_value('services', 'name', data['service'])[0]
                            domains = ast.literal_eval(service['domains'])

                            formatted_domains = self.handler.format('str', 'admin', 'domains', domains=domains)
                            text += "*Управление доменами*\n\n" \
                                    f"⚙️ Сервис: *{service['name']}*\n" \
                                    f"📌 Домены: {formatted_domains if formatted_domains is not None else 'Доменов нет'}\n" \
                                    "\n📍 Доступные действия:\n" \
                                    "1️⃣ Добавление домена\n"

                            if len(domains) > 0:
                                text += "2️⃣ Удаление домена\n"

                            text += "\n🔽 Выбери действие 🔽"
                        else:
                            domains = self.handler.format('str', 'admin', 'domains')
                            text += "*Домены проекта*\n\n" \
                                    f"📍 Доступные домены: " \
                                    f"{'Нет' if domains is None else domains}"
                            if domains is not None:
                                text += "📌 Нажми на кнопку с номером, соответствующим порядоковому номеру домена."

                    case 'domain':
                        if 'services' in data.keys():
                            services = self.handler.format('str', 'admin', 'services', services=data['services'])
                            text += "*Изменение сервиса*\n\n" \
                                    f"🔗 Домен: {data['domain']}\n" \
                                    f"📍 Доступные сервисы:\n" \
                                    f"{'- Сервисов, на которые можно изменить, ещё нет 🤷🏻‍♂️' if services is None else services}"
                            if services is not None:
                                text += "\n 📌 Нажми на кнопку с сервиса, на который хочешь поменять."
                        else:
                            text += "*Управление доменом*\n\n" \
                                    f"🔗 Домен: {data['domain']}\n" \
                                    f"⚙️ Сервис: {data['service']}\n\n" \
                                    "📍 Доступные действия:\n" \
                                    "1️⃣ Изменение сервиса\n" \
                                    "2️⃣ Удаление домена\n\n" \
                                    "🔽 Выбери действие 🔽"

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

                    case 'payments':
                        text += "*Просмотр платежей*\n\n" \
                                "📌 Доступные действия:\n" \
                                "1️⃣ Просмотр всех платежей\n" \
                                f"2️⃣ Просмотр платежей по статусам: " \
                                f"{self.handler.format('str', 'admin', 'payments')}\n\n" \
                                "🔽 Выбери действие 🔽"

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

                elif mode == 'find-payment':
                    text += "*Поиск платежа*\n\n" \
                            "📌 Для того, чтобы найти платёж, введи его уникальный ID. " \
                            "В противном случае отмени действие.\n\n" \
                            "⚠️ Управлять можно только платежами которые находятся в статусе *«В обработке»*\n\n" \
                            "🔽 Введи идентификатор 🔽"

                elif mode == 'update-user-percentage':
                    text = "*Изменение процента*\n\n" \
                           f"🧮 Текущий процент: *{data['percentage']}*\n\n" \
                           "📌 Для того, чтобы изменить процент, введи значение в числовое значение от 1 до 100 " \
                           "и не равное текущему. В противном случае отмени действие."

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
                            match data['action']:
                                case 'add':
                                    text += "*Добавление домена*\n\n" \
                                            "📌 Для того, чтобы добавить домен сервису, введи новое доменное имя, " \
                                            "которое ещё не используется. В противном случае отмени действие.\n\n" \
                                            "🔽 Введи домен 🔽"
                                case 'delete':
                                    domains = self.handler.format('str', 'admin', 'domains', domains=service['domains'])
                                    text += "*Удаление домена*\n\n" \
                                            "*Домены*" \

                                    if domains is None:
                                        text += "\n - Доменов ещё нет 🤷🏻‍♂️"
                                    else:
                                        text += f"{domains}\n\n" \
                                                "📌 Для того, чтобы удалить домен, нажми на кнопку соответствующую " \
                                                "домену, который хочешь удалить. В противном случае вернись назад."

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

                    case 'get-withdraw':
                        action = 'Введи данные'
                        settings = self.handler.file('read', 'settings')['main']
                        cryptocurrency, currency = settings['cryptocurrency'], settings['currency']

                        amount = f"{data['amount']} {currency}" \
                            if 'amount' in data.keys() and data['amount'] is not None else "Не указана"
                        wallet = f"`{data['wallet']}`" \
                            if 'wallet' in data.keys() and data['wallet'] is not None else "*Не указан*"
                        text += f"*Запрос выплаты ({step}/3)*\n\n"

                        if 'error' in data.keys() and data['error'] is not None:
                            text += f"⚠️ {data['error']}️\n\n"

                        text += f"💰 Сумма: *{amount}*\n" \
                                f"👛 Кошелёк ({cryptocurrency}): {wallet}\n\n"

                        match step:
                            case 1:
                                text += f"📌 Введи сумму в {currency}, которую хочешь вывести"
                                action = "Введи сумму"

                            case 2:
                                text += f"📌 Введи {cryptocurrency}-кошелёк, на который хочешь вывести средства"
                                action = "Введи кошелёк"

                            case 3:
                                text += f"📌 Перепроверь и подтверди данные"
                                action = "Подтверди данные"

                        text += f"\n\n🔽 {action} 🔽"
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

            case 'deposit-accepted':
                currency = self.handler.file('read', 'settings')['main']['currency']
                payment = data['payment']
                text += "✅ *Успешный платёж*\n" \
                        f"🔔 Твой платёж успешно оплачен, деньги зачислены на счёт.\n\n" \
                        f"*Информация о платеже*\n" \
                        f"🆔 Уникальный ID: `{payment['id']}`\n" \
                        f"⚙️ Статус: {self.handler.recognition('emoji', 'status', status=payment['status'])} " \
                        f"*{self.configs['payments']['statuses'][payment['status']].capitalize()}*\n" \
                        f"🗓 Дата: *{datetime.now().strftime('%H:%M:%S / %d.%m.%Y')}*\n" \
                        f"💰 Сумма: *{payment['amount']} {currency}*\n"

            case 'deposit-expired':
                text += "⚠️ *Внимание* ⚠️\n\n" \
                        f"🔔 Твой платёж с уникальным ID `{data['id']}` автоматически завершён. " \
                        "Чтобы создать ещё один платёж на пополнение баланса, " \
                        "перейди в раздел *«Баланс»* и нажми *«Депозит»*."

            case 'deposit-canceled':
                if option == 'user':
                    text += "❌ Платёж отклонён ❌\n\n" \
                            f"🔔 Твой платёж успешно отклонен "
                elif option == 'admin':
                    text += "❌ *Платёж отклонён* ❌\n\n" \
                            f"🔔 Твой платёж с уникальным ID `{data['payment']}` был отклонён администратором. " \
                            f"Причину отмены платежа можешь спросить у поддержки сервиса."

            case 'new-accrual':
                currency = self.handler.file('read', 'settings')['main']['currency']
                user, referral = data['user'], data['referral']
                text = "💰 *Новое начисление* 💰\n\n" \
                       "🔔 Поступило новое начисление от пополнениие баланса рефералом.\n\n" \
                       "*Информация о начислении*\n" \
                       f"👤 Реферал: [{referral['name']}](tg://user?id={referral['id']})\n\n" \
                       f"🗓 Дата: *{datetime.now().strftime('%H:%M:%S / %d.%m.%Y')}*\n" \
                       f"💰 Сумма: *{data['amount']} {currency}* ({user['percentage']}%)"

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
                                f"успешно пополнил свой баланс на *{data['summary']} {currency}*."

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

    def error(self, mode, option=None, embedded=False, **data):
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

            case 'no-access':
                text += "У тебя нет прав на просмотр этого раздела. Есл считаешь, что это ошибка - " \
                        "обратись в поддержку.\n" \
                        "🔽 Обратиться в поддержку 🔽"

            case 'empty':
                values = {'first': None, 'second': None, 'third': None}

                match option:
                    case 'users':
                        values['first'], values['second'], values['third'] = \
                            "пользователей", "пользователя", "пользователь"

                    case 'payments':
                        values['first'], values['second'], values['third'] = \
                            "платежей", "платежа", "платёж"

                text = "❌ *Нечего искать* ❌\n\n" \
                       f"⚠️ К сожалению база {values['first']} ещё пуста, не добавлено ни единого " \
                       f"{values['second']} и поэтому некого искать. Эта функция станет доступной тогда, " \
                       f"когда будет добавлен первый {values['third']}."

            case 'exist':
                match option:
                    case 'service-title':
                        text = f"Сервис с таким названием уже добавлен ({data['title']})."
                    case 'service-domain':
                        service = self.handler.format('str', 'admin', 'domain-service', domain=data['domain'])
                        text += f"Домен {data['domain']} уже есть в базе данных и он принадлежит сервису *{service}*."
            case 'more':
                error = f"Значение должно быть *не более {data['value'] if 'value' in data.keys() else 100}*. " \
                        f"Попробуй ещё раз или же отмени действие."

                if embedded:
                    text = error
                else:
                    text += error

            case 'same':
                text += f"Значение *{data['value']}* не должно совпадать с текущим. " \
                        f"Попробуй ещё раз или же отмени действие."

            case 'less':
                error = f"Значение должно быть *не менее {data['value'] if 'value' in data.keys() else 1}*. " \
                        f"Попробуй ещё раз или же отмени действие."

                if embedded:
                    text = error
                else:
                    text += error

            case 'not-exist':
                match option:
                    case 'user':
                        text += f"Пользователь с идентификатором {data['id']} не найден."
                    case 'payment':
                        text += f"Платёж с уникальным идентификатором {data['id']} не найден."

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
                error = "Значение должно быть в числовом формате. Введи значение ещё раз или отмени действие."

                if embedded:
                    text = error
                else:
                    text += error

            case 'not-string':
                text += "Значение должно быть в текстовом формате. Введи значение ещё раз или отмени действие."

            case 'unavailable-or-incorrect':
                text += f"Значение *{data['value']}* указано не правильно или же временно недоступно. " \
                        "Введи значение ещё раз или отмени действие."

            case 'incorrect-status':
                match option:
                    case 'payment':
                        text += f"У платежа с уникальным ID: {data['id']} не подходящий статус " \
                                f"«{self.configs['payments']['statuses'][data['status']].capitalize()}». " \
                                f"Управлять можно только платежами которые " \
                                f"находятся в статусе «В обработке».\n\n" \
                                f"📌  Перепроверь данные или введи идентификатор другого платежа, " \
                                f"в противном случае отмени действие."

        return text

    def success(self, mode, option=None, **data):
        text = "✅ *Успешно* ✅\n\n🔔"

        match mode:
            case 'found-data':
                text = "*Поиск завершён успешно* ✅\n\n🔔"

                if option == 'user':
                    text += f"Пользователь с идентификатором «*{data['id']}*» был успешно найден, формируем данные..."
                elif option == 'payment':
                    text += f"Платёж с идентификатором «*{data['id']}*» был успешно найден, формируем данные..."

            case 'updated-data':
                if 'project' in option:
                    option = option.split('-')[-1]

                    match option:
                        case 'percentage':
                            text += f"Общий реферальный процент успешно изменён с *{data['old']}*  на *{data['new']}*"
                        case 'currency':
                            text += f"Валюта успешно изменена с *{data['old']}* на *{data['new']}*"
                        case 'cryptocurrency':
                            text += f"Криптовалюта успешно изменена с *{data['old']}* на *{data['new']}*"
                else:
                    match option:
                        case 'add-balance':
                            text += "Средства успешно добавлены. Формируем данные..."
                        case 'change-balance':
                            text += "Баланс успешно обновлен. Формируем данные..."
                        case 'change-percentage':
                            text += "Процент успешно обновлен. Формируем данные..."
                        case 'service-title':
                            text += f"Название сервиса успешно изменено с *{data['old']}* на *{data['new']}*"
                        case 'service-domain':
                            text += f"Домен *{data['domain']}* успешно добавлен сервису {data['service']}"
                        case 'subscription-price':
                            text += f"Цена подписки успешно изменена с *{data['old']}* на *{data['new']} {data['currency']}*"

            case 'sent-request':
                match option:
                    case 'withdraw':
                        text += "Запрос на вывод средств был успешно отправлен и в ближайшее время будет рассмотрен " \
                                "администрацией сервиса.\n\n" \
                                f"{self.check('withdraw', withdraw=data['id'])}"

        return text

    def check(self, mode, **data):
        text = str()
        match mode:
            case 'withdraw':
                withdraw = self.database.get_data_by_value('requests', 'id', data['withdraw'])[0]
                withdraw_data = ast.literal_eval(withdraw['data'])
                text = "*Данные заявки*\n" \
                       f"🆔 Уникальный ID: `{withdraw['id']}`\n" \
                       f"⚙️ Статус: {self.handler.recognition('emoji', 'status', status=withdraw['status'])} " \
                       f"{self.configs['requests']['statuses'][withdraw['status']].capitalize()}\n" \
                       f"💰 Сумма: *{withdraw_data['amount']} {withdraw_data['currency']}*\n" \
                       f"👛 Кошелёк ({withdraw_data['cryptocurrency']}): `{withdraw_data['wallet']}`\n\n" \
                       f"🔽 Обновить статус 🔽"

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
    def check(query, text=None, **data):
        markup = types.InlineKeyboardMarkup()
        text = f"👁 Проверить{'' if text is None else ' ' + text}"
        markup.add(types.InlineKeyboardButton(text, callback_data=f"check-{query}"))

        if 'menu' in data.keys():
            markup.add(types.InlineKeyboardButton(
                '↩️ Вернуться в меню', callback_data=f"comeback-to-menu-{data['menu']}"))

        return markup
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
                            types.KeyboardButton('💰 Финансы'),
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
                            '🧮 Процент': {'type': 'update', 'action': 'percentage'},
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
                        print(len(self.database.get_data('services')))
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
                            '🔗 Домены': {'type': 'control', 'action': 'domains'},
                            '❌ Удалить сервис': {'type': 'delete', 'action': 'data'}
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

                    case 'finances':
                        markup.add(
                            types.KeyboardButton('💳 Платежи'),
                            types.KeyboardButton('🪙 Начисления')
                        )

                    case 'payments':
                        comeback = 'финансам'
                        payments = self.handler.format('dict', 'payments', 'deposits')

                        if payments['total'] > 0:
                            markup.add(
                                types.KeyboardButton('👁 Посмотреть платежи'),
                            )

                            if len(payments['pending']) > 0:
                                markup.add(types.KeyboardButton('🛠 Управлять'))

                    case 'payment':
                        comeback, payment = False, data['payment']

                        if payment['status'] == 'pending':
                            markup.add(
                                types.InlineKeyboardButton(
                                    "🟢 Принять", callback_data=f"set-payment-{payment['id']}-status-success"),
                                types.InlineKeyboardButton(
                                    "🔴 Отклонить", callback_data=f"set-payment-{payment['id']}-status-error")
                            )

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
                            types.KeyboardButton("🧮 Процент"),
                            types.KeyboardButton('🔗 Домены')
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
            case 'promoter':
                match menu:
                    case 'main':
                        markup.add(
                            types.KeyboardButton('👥 Пользователи'),
                            types.KeyboardButton('💸 Начисления')
                        )

                        if self.database.get_data_by_value('users', 'id', data['user'])[0]['balance'] > 0:
                            markup.add(types.KeyboardButton('💰 Запросить выплату'))

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
                                services = data['services'] if 'services' in data.keys() \
                                    else self.database.get_data('services')

                                width = data['width'] if 'width' in data.keys() else 2
                                markup, markups, row, additional = dict(), list(), list(), dict()

                                for service in services:
                                    if len(row) < width:
                                        if type(service) is dict:
                                            row.append({
                                                'text': service['name'],
                                                'callback_data': f"select-admin-service-{service['name']}"
                                            })
                                        elif type(service) is str and 'domain' in data.keys():
                                            row.append({
                                                'text': service,
                                                'callback_data': f"select-service-{service}-domain-{data['domain']}"
                                            })

                                    if len(row) == width:
                                        markups.append(row)
                                        row = list()
                                else:
                                    if len(row) != 0:
                                        markups.append(row)

                                if 'domain' in data.keys():
                                    markups.append([{
                                        'text': '↩️ Назад',
                                        'callback_data': f"comeback-to-domain-control-{data['domain']}"
                                    }])
                                markup['inline_keyboard'] = markups
                                markup = str(markup).replace('\'', '"')

                    case 'domains':
                        if 'service' in data.keys():
                            service = self.database.get_data_by_value('services', 'name', data['service'])[0]
                            domains = ast.literal_eval(service['domains'])

                            if 'action' in data.keys() and data['action'] == 'delete':
                                width = data['width'] if 'width' in data.keys() else 2
                                i, markup, markups, row, additional = 0, dict(), list(), list(), dict()

                                for domain in domains:
                                    value = i if '-' in domain else domain.replace('/', ' ').split()[1]
                                    if len(row) < width:
                                        row.append({
                                            'text': domain.replace('/', ' ').split()[1],
                                            'callback_data': f"delete-domain-{value}-service-{service['name']}"
                                        })

                                    if len(row) == width:
                                        markups.append(row)
                                        row = list()

                                    i += 1
                                else:
                                    if len(row) != 0:
                                        markups.append(row)

                                markups.append([{
                                    'text': '↩️ Назад',
                                    'callback_data': f"comeback-to-service-control-domains-{service['name']}"
                                }])
                                markup['inline_keyboard'] = markups
                                markup = str(markup).replace('\'', '"')
                            else:

                                query = f"update-service-{service['name']}"
                                comeback = f"comeback-to-service-control-{service['name']}"

                                markup.add(types.InlineKeyboardButton("➕ Добавить", callback_data=f"{query}-add-domain"))

                                if len(domains) > 0:
                                    markup.add(types.InlineKeyboardButton("➖ Удалить", callback_data=f"{query}-delete-domain"))

                                markup.add(types.InlineKeyboardButton("↩️ Назад", callback_data=comeback))
                        else:
                            domains = self.handler.format('list', 'domains')
                            width = data['width'] if 'width' in data.keys() else 5
                            i, markup, markups, row, additional = 1, dict(), list(), list(), dict()

                            for domain in domains:
                                if len(row) < width:
                                    row.append({'text': i, 'callback_data': f"select-domain-{domain}"})

                                if len(row) == width:
                                    markups.append(row)
                                    row = list()

                                i += 1
                            else:
                                if len(row) != 0:
                                    markups.append(row)

                            markup['inline_keyboard'] = markups
                            markup = str(markup).replace('\'', '"')

                    case 'domain':
                        markup.add(
                            types.InlineKeyboardButton(
                                "⚙️ Изменить сервис", callback_data=f"update-domain-{data['domain']}"),
                            types.InlineKeyboardButton(
                                "❌ Удалить домен", callback_data=f"delete-domain-{data['domain']}"),
                        )
                        markup.add(
                            types.InlineKeyboardButton("↩️ Назад", callback_data=f"comeback-to-domain-selection"))
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

                    case 'payments':
                        payments = self.handler.format('dict', 'payments', 'deposits')
                        del payments['total']
                        width = data['width'] if 'width' in data.keys() else 2
                        markup, markups, row, additional = dict(), list(), list(), dict()

                        markups.append([{'text': '📌 Все', 'callback_data': 'get-payments-all'}])
                        for payments_status, payments_data in payments.items():
                            if len(row) < width:
                                if len(payments_data) > 0:
                                    text = f"{self.handler.recognition('emoji', 'status', status=payments_status)} " \
                                           f"{self.configs['payments']['statuses'][payments_status].capitalize()}"
                                    row.append({
                                        'text': text,
                                        'callback_data': f"get-payments-{payments_status}"
                                    })

                            if len(row) == width:
                                markups.append(row)
                                row = list()
                        else:
                            if len(row) != 0:
                                markups.append(row)

                        markup['inline_keyboard'] = markups
                        markup = str(markup).replace('\'', '"')

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

    _database.recreate_table()

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

    # logs
    # i = 1
    # while i < 15:
    #     user = 1603149905 if random.randint(0, 1) else random.randint(111111111, 999999999)
    #     _database.add_data('logs', user=user,
    #                        username='Дипси' if user == 1603149905 else f'Пользователь-{user}',
    #                        usertype='admin' if user == 1603149905 else 'user',
    #                        action=f"Действие пользователя {user}"
    #     )
    #     i += 1

    # payments
    # _i = 1
    # _users = _database.get_data('users')
    #
    # while _i <= 10:
    #     _database.add_data('payments', id=f'test{random.randint(1, 999)}', type='deposit',
    #                        user=random.choice(_users)['id'], amount=random.randint(10, 1000),
    #                        expiration=datetime.now() + timedelta(days=1))
    #     _i += 1
    #

