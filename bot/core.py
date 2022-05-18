import time
import sqlite3
import schedule
import configparser

from westwallet_api import WestWalletAPI


class Configs:
    statuses = {'accepted': "принято", 'processing': "в процессе", 'rejected': "отклонено"}
    payments = {'deposit': 'депозит'}
    subscriptions = {
        'trial': {'title': 'пробная', 'type': 'hour', 'duration': 2},
        'week': {'title': 'недельная', 'type': 'day', 'duration': 7},
        'month': {'title': 'недельная', 'type': 'day', 'duration': 30}
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

            # configs['statuses'] = self.statuses
            # configs['payments'] = self.payments
            # configs['subscriptions'] = self.subscriptions

        return configs


class Database:
    tables = ['logs', 'users', 'payments', 'domains', 'mailings']

    def __init__(self, configs):
        self.configs = configs

    @staticmethod
    def connect():
        connection = sqlite3.connect('data/database.sqlite')
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
                    `subscription` VARCHAR NOT NULL,
                    `balance` FLOAT NOT NULL,
                    `inviter` INT NOT NULL,
                    `ban` INT NOT NULL
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

        except sqlite3.Error as error:
            print(f"ERROR | Sqlite: {error}")
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
        except sqlite3.Error as error:
            print(f"ERROR | Sqlite: {error}")
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
            except sqlite3.Error as error:
                print(f"ERROR | Sqlite: {error}")
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
                        `id`, `name`, `registration`, `subscription`, `balance`, `inviter`, `ban`)
                        VALUES ({items['id']}, '{items['name']}', {int(time.time())}, 'None', 0, {items['inviter']}, 0)
                        """

                    case 'payments':
                        status = list(self.configs['statuses'].keys())[1]
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

            except sqlite3.Error as error:
                print(f"ERROR | Sqlite: {error}")
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
            except sqlite3.Error as error:
                print(f"ERROR | Sqlite: {error}")
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
            except sqlite3.Error as error:
                print(f"ERROR | Sqlite: {error}")
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


class Processes:
    def __init__(self, bot, texts, buttons):
        self.bot = bot
        self.texts = texts
        self.buttons = buttons

    def payments(self):
        print('payments')

    def mailing(self):
        print('mailing')

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


class Texts:
    def __init__(self, configs, database, handler):
        self.configs = configs
        self.database = database
        self.handler = handler


class Buttons:
    def __init__(self, configs, database, handler):
        self.configs = configs
        self.database = database
        self.handler = handler
