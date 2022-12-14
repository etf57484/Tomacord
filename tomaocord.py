import discord
from discord import Option
from discord.ext import tasks
import os, datetime, uuid, asyncio
from dotenv import load_dotenv

import MySQLdb
import os

from notion_control import NotionEdit

load_dotenv()

class DBConnection:

    def __init__(self,sql,params):
        self.sql = sql
        self.params = params

        self.host = os.environ['DB_HOST']
        self.user = os.environ['DB_USER']
        self.password = os.environ['DB_PASSWORD']
        self.db = os.environ['DB_NAME']

        self.conn = MySQLdb.connect(host=self.host, user=self.user, password =self.password, db=self.db, charset='utf8mb4')

        self.rows = None

        self.sql_type = sql.split()[0]

    def select(self):
        cursor = self.conn.cursor()
        try:
            # self.rows = cursor.execute(self.sql,self.params)
            cursor.execute(self.sql,self.params)
        finally:
            self.conn.close()

        return cursor

    def insert(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute(self.sql,self.params)
            self.conn.commit()
        finally:
            self.conn.close()

    def execute(self):
        if self.sql_type=='SELECT':
            return self.select()

        if self.sql_type=='INSERT' or self.sql_type=='UPDATE':
            self.insert()

active_task = None
interval_end = None

bot = discord.Bot()
'''
CREATE TABLE `tasks` (pomodoro_id int auto_increment, task_id varchar(36), task_name varchar(50), start datetime, end datetime, achieved BOOLEAN DEFAULT False, INDEX(pomodoro_id));
'''
class ActivePomodoro:
    def __init__(self,task_id):
        self.task_id = task_id

        sql = "SELECT * FROM `tasks` WHERE `task_id`=%(task_id)s ORDER BY `pomodoro_id` DESC LIMIT 1"
        params = {
            'task_id': self.task_id
        }
        conn = DBConnection(sql, params)
        result = conn.execute().fetchone()

        self.pomodoro_id = result[0]
        self.task_name = result[2]
        self.start = result[3]
        self.end = result[4]

        self.work_time = int(os.environ['WORK_TIME'])
        self.interval_time = int(os.environ['INTERVAL_TIME'])

        self.notion = NotionEdit()

    def get_total_pomodoro(self):
        sql = "SELECT COUNT(`pomodoro_id`) FROM `tasks` WHERE `task_id`=%(task_id)s "
        params = {
            'task_id':self.task_id
        }
        conn = DBConnection(sql,params)
        result = conn.execute().fetchone()
        return result[0]

    def add(self):
        self.start = datetime.datetime.now()
        self.end = datetime.datetime.now() + datetime.timedelta(minutes=self.work_time)

        sql = "INSERT INTO `tasks`(`task_id`,`task_name`,`start`,`end`) VALUES(%(task_id)s,%(task_name)s,%(start)s,%(end)s)"
        params = {
            'task_id': self.task_id,
            'task_name': self.task_name,
            'start': self.start,
            'end': self.end
        }
        conn = DBConnection(sql,params)
        conn.execute()
        del conn

        page_id = self.notion.get_id_from_task_id(self.task_id)
        self.notion.update_pomodoro(page_id,self.end,self.get_total_pomodoro(),False)

    def achieved(self):
        self.end = datetime.datetime.now()

        sql = "UPDATE `tasks` SET `end`=%(end)s, `achieved`=1 WHERE `pomodoro_id`=%(pomodoro_id)s"
        params = {
            'end': self.end,
            'pomodoro_id': self.pomodoro_id
        }
        conn = DBConnection(sql,params)
        conn.execute()
        del conn

        page_id = self.notion.get_id_from_task_id(self.task_id)
        self.notion.update_pomodoro(page_id,self.end,self.get_total_pomodoro(),True)

        pomodoro_management = PomodoroManagement()
        pomodoro_management.update_pomodoro_count()


class NewTask:
    def __init__(self,task_name):
        self.task_name = task_name
        self.task_id = str(uuid.uuid4())

        self.work_time = int(os.environ['WORK_TIME'])
        self.interval_time = int(os.environ['INTERVAL_TIME'])
        self.start = datetime.datetime.now()
        self.end = datetime.datetime.now() + datetime.timedelta(minutes=int(self.work_time))
        
        global active_task
        sql = "INSERT INTO `tasks`(`task_id`,`task_name`,`start`,`end`) VALUES(%(task_id)s,%(task_name)s,%(start)s,%(end)s)"
        params = {
            'task_id': self.task_id,
            'task_name': self.task_name,
            'start': self.start,
            'end': self.end
        }
        conn = DBConnection(sql,params)
        conn.execute()
        del conn

        notion = NotionEdit()
        notion.add_new_task(self.task_id, self.task_name, self.start, self.end, False, 1)

        active_task = self.task_id

class PomodoroManagement:
    def __init__(self):
        sql = "SELECT COUNT(`pomodoro_id`) FROM `tasks` WHERE `achieved`=1"
        conn = DBConnection(sql,{})
        result = conn.execute().fetchone()
        self.count_all_pomodoro = result[0]

        sql = "SELECT COUNT(`pomodoro_id`) FROM `tasks` WHERE `achieved`=1 and `start` LIKE %(today)s"
        params = {
            'today': str(datetime.datetime.today().strftime('%Y-%m-%d'))+"%"
        }
        conn = DBConnection(sql,params)
        result = conn.execute().fetchone()
        self.count_today_pomodoro = result[0]

    def update_pomodoro_count(self):
        notion = NotionEdit()
        notion.update_pomodoro_count(self.count_all_pomodoro,self.count_today_pomodoro)

@bot.slash_command(name="start", description="???????????????????????????")
async def start(ctx, task_name: Option(str, required=True, description="???????????????????????????????????????")):
    if not task_name:
        task_name = '??????????????????'
    new_task = NewTask(task_name=task_name)

    await ctx.respond(f'**[{task_name}]**?????????????????????????????????????????????????')

    global active_task
    active_task = new_task.task_id

    end = new_task.end.strftime('%Y-%m-%d %H:%M')
    await ctx.respond(f'**[{new_task.task_name}]**\n1??????????????????????????????????\n> ???? ???????????? : _{end}_')

@bot.slash_command(name="finish", description="???????????????????????????")
async def finish(ctx):
    global active_task
    if active_task is None:
        await ctx.respond(f'?????????????????????????????????????????????????')
    else:
        finished_task = ActivePomodoro(task_id=active_task)
        finished_task.achieved()

        await ctx.respond(f'**[{finished_task.task_name}]**????????????????????????????????????????????????')
        del finished_task
        active_task = None
        interval_end = None

@bot.slash_command(name="result", description="????????????????????????????????????????????????")
async def result(ctx):
    result = PomodoroManagement()
    await ctx.respond(f'**???????????????????????????????????**\n>>> ?????????????????? : **{result.count_all_pomodoro}**???????????????\n?????????????????? : **{result.count_today_pomodoro}**???????????????')

@tasks.loop(seconds=60)
async def loop():
    # bot???????????????????????????
    await bot.wait_until_ready()
    channel = bot.get_channel(int(os.environ['CHANNEL_ID']))

    now = datetime.datetime.now()
    now_ymdhm = now.strftime('%Y-%m-%d %H:%M')
    midnight = datetime.datetime(year=now.year, month=now.month, day=now.day, hour=23, minute=59)
    midnight_ymdhm = midnight.strftime('%Y-%m-%d %H:%M')

    global active_task, interval_end
    print(f'active_task:{active_task}')
    if active_task is not None:

        task = ActivePomodoro(task_id=active_task)
        if task.end.strftime('%Y-%m-%d %H:%M') == now_ymdhm:
            pomodoro_count = task.get_total_pomodoro()
            await channel.send(f'???? {pomodoro_count}???????????????????????????????????????????????????????????????????????????')
            task.achieved()

            interval_end = datetime.datetime.now() + datetime.timedelta(minutes=int(os.environ['INTERVAL_TIME']))
        if interval_end is not None:
            if interval_end.strftime('%Y-%m-%d %H:%M') == now_ymdhm:
                await channel.send(f'**???????????????**??????????????????????????????????')
                task.add()
                pomodoro_count = task.get_total_pomodoro()
                pomodoro_emoji = '????' * pomodoro_count
                end = task.end.strftime('%Y-%m-%d %H:%M')
                await channel.send(f'**[{task.task_name}]**\n{pomodoro_count}??????????????????????????????{pomodoro_emoji}\n> ???? ???????????? : _{end}_')
                interval_end = None

    if now_ymdhm == midnight_ymdhm:
        result = PomodoroManagement()
        await channel.send(f'**???????????????????????????????????**\n>>> ?????????????????? : **{result.count_all_pomodoro}**???????????????\n?????????????????? : **{result.count_today_pomodoro}**???????????????')
        
        await asyncio.sleep(60)
        
        pomodoro_management = PomodoroManagement()
        pomodoro_management.update_pomodoro_count()

loop.start()
bot.run(os.environ['API_KEY'])
