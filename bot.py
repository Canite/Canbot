#!/usr/bin/env python
import config
import irc.bot
import requests
import signal
import sys
import os
import random
from datetime import datetime, timedelta
import urllib
import shlex
import pickle
import threading
import re
from sortedcontainers import SortedList

class TwitchBot(irc.bot.SingleServerIRCBot):
    def __init__(self, username, client_id, token, channel):
        self.client_id = client_id
        self.token = "oauth:" + token
        self.channel = "#" + channel
        self.twitch_header = {'Client-ID': client_id, "Authorization": "Bearer " + token} 
        signal.signal(signal.SIGINT, self.handle_exit_signal)
        self.exit = False
        self.commands = self.load_commands()
        self.viewers = self.load_viewers()
        self.viewer_ranks = SortedList(self.viewers.values())
        self.stop_timer_event = threading.Event()
        self.points_timer = RecurrentTimer(self.stop_timer_event, 60.0, self.add_points)
        self.category_re = re.compile(r"[any|100|glitchless]", re.IGNORECASE)

        # Get the channel id, we will need this for v5 API calls
        url = "{}/users?login={}".format(config.TWITCH_API, channel)
        r = requests.get(url, headers=self.twitch_header).json()
        print(r)
        self.channel_id = r['data'][0]['id']
        print(self.channel_id)

        # Create IRC bot connection
        server = 'irc.chat.twitch.tv'
        port = 6667
        print('Connecting to ' + server + ' on port ' + str(port) + '...')
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port, self.token)], username, username)

    def on_welcome(self, c, e):
        print('Joining ' + self.channel)

        # You must request specific capabilities before you can use them
        c.cap('REQ', ':twitch.tv/membership')
        c.cap('REQ', ':twitch.tv/tags')
        c.cap('REQ', ':twitch.tv/commands')
        c.join(self.channel)

    def add_points(self):
        #current_viewers = self.channels[self.channel].users()
        # Have to use the old API to get chatters I guess...
        chatters_url = "https://tmi.twitch.tv/group/user/{}/chatters".format(config.CHANNEL)
        r = requests.get(chatters_url).json()
        for viewer_list in r["chatters"].values():
            for viewer in viewer_list:
                if (viewer not in self.viewers):
                    self.viewers[viewer] = 50
                else:
                    self.viewers[viewer] += 15

        self.viewer_ranks = SortedList(self.viewers.values())

    def on_pubmsg(self, c, e):
        msg = e.arguments[0]
        # If a chat message starts with an exclamation point, try to run it as a command
        if msg[0] == '!':
            cmd = msg.split(' ')[0][1:]
            print("Received command: " + cmd)
            self.do_command(e, cmd, ' '.join(msg.split(' ')[1:]))
        return

    def load_commands(self):
        commands_filename = "commands.pkl"
        if (os.path.exists(commands_filename)):
            with open(commands_filename, 'rb') as commands_file:
                print("Loading commands file")
                return pickle.load(commands_file)
        else:
            return {}

    def load_viewers(self):
        viewers_filename = "viewers.pkl"
        if (os.path.exists(viewers_filename)):
            with open(viewers_filename, 'rb') as viewers_file:
                print("Loading viewers file")
                return pickle.load(viewers_file)
        else:
            return {}

    def save_commands(self):
        commands_filename = "commands.pkl"
        with open(commands_filename, 'wb') as commands_file:
            return pickle.dump(self.commands, commands_file, pickle.HIGHEST_PROTOCOL)

    def save_viewers(self):
        viewers_filename = "viewers.pkl"
        with open(viewers_filename, 'wb') as viewers_file:
            return pickle.dump(self.viewers, viewers_file, pickle.HIGHEST_PROTOCOL)

    def get_game_name_twitch(self):
        channel_url = "{}/streams?user_id={}".format(config.TWITCH_API, self.channel_id)
        r = requests.get(channel_url, headers=self.twitch_header).json()
        game_name = ""
        game_id = 0
        category = ""
        if (r["data"]):
            game_id = r["data"][0]["game_id"]
            game_url = "{}/games?id={}".format(config.TWITCH_API, game_id)
            r = requests.get(game_url, headers=self.twitch_header).json()
            if (r["data"]):
                game_name = r["data"][0]["name"]
                stream_title = r["data"][0]["title"]
                catgeory_match = category_re.match(stream_title)
                if (catgeory_match):
                    category = category_match.group(0)
        return game_name, game_id, category

    def get_game_name_srl(self, name):
        game_url = urllib.parse.quote(name)
        speedrun_url = "{}/games?abbreviation={}".format(config.SRL_API, game_url)
        r = requests.get(speedrun_url).json()
        if ("data" not in r or not r["data"]):
            speedrun_url = "{}/games?name={}".format(config.SRL_API, game_url)
            r = requests.get(speedrun_url).json()
            if ("data" not in r or not r["data"]):
                self.chat("Could not find game {}.".format(name))
                return None, None
        game_name = r["data"][0]["names"]["international"]
        game_id = r["data"][0]["id"]
        return game_name, game_id

    def get_category(self, category, game_id):
        cat_url = urllib.parse.quote(category)
        speedrun_url = "{}/games/{}/categories".format(config.SRL_API, game_id)
        r = requests.get(speedrun_url).json()
        cat_name = None
        cat_id = None
        if(r["data"]):
            for cat in r["data"]:
                name = cat["name"]
                if (category in name.lower() and cat["type"] == "per-game"):
                    cat_name = name
                    cat_id = cat["id"]
                    break

            if (cat_name == None):
                cat_name = r["data"][0]["name"]
                cat_id = r["data"][0]["id"]

        return cat_name, cat_id

    def get_pb(self, msg):
        twitch_game_name, game_id = self.get_game_name_twitch()
        split_msg = shlex.split(msg.rstrip('\r\n').lower())
        if (len(split_msg) > 2):
            username, category = split_msg[:2]
            twitch_game_name = ' '.join(split_msg[2:])
        elif (len(split_msg) == 2):
            username, category = split_msg
        elif (len(split_msg) == 1 and split_msg[0] != ""):
            username = split_msg[0]
            category = "any"
        else:
            username = config.CHANNEL
            category = "any"

        game_name, game_id = self.get_game_name_srl(twitch_game_name)
        if (game_name == None):
            self.chat("Couldn't find \"{}\" on speedrun.com".format(twitch_game_name))
            return

        cat_name, cat_id = self.get_category(category, game_id)
        if (cat_name == None):
            self.chat("Couldn't find category containing \"{}\" for \"{}\"".format(category, game_name))
            return

        speedrun_url = "{}/users/{}/personal-bests?game={}".format(config.SRL_API, username, game_id)
        r = requests.get(speedrun_url).json()
        if ("status" not in r):
            pb_run = None
            for run in r["data"]:
                if (run["run"]["category"] == cat_id):
                    pb_run = run
                    break

            if (pb_run != None):
                place = pb_run["place"]
                pb = str(timedelta(seconds=pb_run["run"]["times"]["primary_t"]))
                self.chat("{} is rank {} in \"{}\" {} with a time of {}.".format(username, place, game_name, cat_name, pb))
            else:
                self.chat("{} has no PB for \"{}\" {}.".format(username, game_name, cat_name))
        else:
            self.chat("Could not find user {}.".format(username))

    def get_wr(self, msg):
        twitch_game_name, game_id, category = self.get_game_name_twitch()
        split_msg = shlex.split(msg.rstrip('\r\n').lower())
        if (len(split_msg) > 1):
            category = split_msg[0]
            twitch_game_name = ' '.join(split_msg[1:])
        elif (len(split_msg) == 1 and split_msg[0] != ""):
            if (twitch_game_name == ""):
                twitch_game_name = split_msg[0]
            else:
                category = split_msg[0]
        elif (category == ""):
            category = "any"

        if (twitch_game_name == ""):
            self.chat("Couldn't find game name from category")
            return

        game_name, game_id = self.get_game_name_srl(twitch_game_name)
        if (game_name == None):
            self.chat("Couldn't find \"{}\" on speedrun.com".format(twitch_game_name))
            return

        cat_name, cat_id = self.get_category(category, game_id)
        if (cat_name == None):
            self.chat("Couldn't find category containing \"{}\" for \"{}\"".format(category, game_name))
            return

        speedrun_url = "{}/leaderboards/{}/category/{}?top=1".format(config.SRL_API, game_id, cat_id)
        r = requests.get(speedrun_url).json()
        wr_run = None
        if ("status" not in r and "data" in r):
            wr_run = r["data"]

        if (wr_run):
            first_place = str(timedelta(seconds=wr_run["runs"][0]["run"]["times"]["primary_t"]))
            user_url = user = wr_run["runs"][0]["run"]["players"][0]["uri"]
            r = requests.get(user_url).json()
            user_name = r["data"]["names"]["international"]
            self.chat("The world record for \"{}\" {} is {} by {}.".format(game_name, cat_name, first_place, user_name))
        else:
            self.chat("Could not find world record for \"{}\".".format(game_name))

    def print_help(self, msg):
        if (msg == "pb"):
            self.chat("!pb <srl_username> \"<category>\" \"<game>\"")

        elif (msg == "wr"):
            self.chat("!wr \"<category>\" \"<game>\"")

        elif (msg == "commands"):
            self.chat("!commands <add/edit> <!command> <text>")

        else:
            self.chat("!help <pb/wr/commands>")

    def edit_commands(self, e, msg):
        mod = False
        for tag in e.tags:
            if (tag["key"] == "badges"):
                badges = tag["value"]
                broadcaster = badges.split(",")[0].split("/")[1]
                mod = bool(broadcaster)
                if (broadcaster):
                    break
            if (tag["key"] == "mod"):
                mod = bool(tag["value"])

        if (mod):
            split_msg = msg.rstrip('\r\n').split(" ")
            if (len(split_msg) > 2):
                if (split_msg[0] == "add"):
                    command = split_msg[1][1:]
                    if (not command in self.commands):
                        text = " ".join(split_msg[2:])
                        self.commands[command] = text
                        self.chat("Added command !{}".format(command))
                    else:
                        self.chat("Command \"!{}\" already exists. Use !commands edit to modify it.".format(command))
                if (split_msg[0] == "edit"):
                    command = split_msg[1][1:]
                    if (command in self.commands):
                        text = " ".join(split_msg[2:])
                        self.commands[command] = text
                        self.chat("Edited command !{}".format(command))
                    else:
                        self.chat("Command \"!{}\" does not exist. Use !commands add to add it.".format(command))
            else:
                self.chat("Usage: !commands <add/edit> <!command> <text>")
        else:
            self.chat("Only moderators can edit commands.")

    def get_followage(self, e):
        user_id = ""
        user_name = ""
        for tag in e.tags:
            if (tag["key"] == "user-id"):
                user_id = tag["value"]
            elif (tag["key"] == "display-name"):
                user_name = tag["value"]

        twitch_url = "{}/users/follows?from_id={}&to_id={}".format(config.TWITCH_API, user_id, self.channel_id)
        r = requests.get(twitch_url, headers=self.twitch_header).json()
        if ("total" in r and r["total"] > 0):
            follow_date = datetime.strptime(r["data"][0]["followed_at"], "%Y-%m-%dT%H:%M:%SZ")
            today = datetime.today()
            followage = td_format(today - follow_date)
            self.chat("{} has been following {} for {}.".format(user_name, config.CHANNEL, followage))
        else:
            self.chat("{} is not following {}.".format(user_name, config.CHANNEL))

    def get_points(self, e):
        user_name = ""
        for tag in e.tags:
            if (tag["key"] == "display-name"):
                user_name = tag["value"]

        if (user_name.lower() in self.viewers):
            points = self.viewers[user_name.lower()]
            total_viewers = len(self.viewer_ranks)
            rank = total_viewers - self.viewer_ranks.index(points)
            self.chat("@{}, you are rank {}/{} with {} points.".format(user_name, rank, total_viewers, points))

    def get_top(self, e):
        top5 = self.viewer_ranks[-5:]
        msgs = ["Rank {}: ".format(i + 1) for i in range(5)]
        for name, points in self.viewers.items():
            if (points in top5):
                rank = 4 - top5.index(points)
                msgs[rank] += name + " "

        for i in range(5):
            msgs[i] += " ({})".format(top5[4 - i])
        self.chat("; ".join(msgs))


    def gift_points(self, e, msg):
        mod = False
        for tag in e.tags:
            if (tag["key"] == "badges"):
                badges = tag["value"]
                broadcaster = badges.split(",")[0].split("/")[1]
                mod = bool(broadcaster)
                if (broadcaster):
                    break
            if (tag["key"] == "mod"):
                mod = bool(tag["value"])

        if (mod):
            split_msg = msg.rstrip('\r\n').split(" ")
            if (len(split_msg) < 1):
                self.chat("!gift <points> <user/all>")
                return
            elif (len(split_msg) == 1):
                try:
                    points = int(split_msg[0])
                    user = "all"
                except ValueError:
                    self.chat("Points must be a number")
                    return
            else:
                try:
                    points = int(split_msg[0])
                    user = split_msg[1].lower()
                except ValueError:
                    self.chat("Points must be a number")
                    return

            chatters_url = "https://tmi.twitch.tv/group/user/{}/chatters".format(config.CHANNEL)
            r = requests.get(chatters_url).json()
            for viewer_list in r["chatters"].values():
                for viewer in viewer_list:
                    if ((user == "all" or user == viewer.lower())):
                        if (viewer in self.viewers):
                            self.viewers[viewer] += points
                        else:
                            self.viewers[viewer] = points

            self.viewer_ranks = SortedList(self.viewers.values())

            if (user == "all"):
                self.chat("Gifted {} points to everyone!".format(points))
            else:
                self.chat("Gifted {} points to {}!".format(points, user))

    def gamble(self, e, msg):
        user_name = ""
        for tag in e.tags:
            if (tag["key"] == "display-name"):
                user_name = tag["value"]

        if (user_name.lower() in self.viewers):
            split_msg = msg.rstrip('\r\n').split(" ")
            if (len(split_msg) < 1):
                self.chat("!gamble <points/all>")
                return
            elif (len(split_msg) == 1):
                total_points = self.viewers[user_name.lower()]
                try:
                    if (split_msg[0] == "all"):
                        points = total_points
                    else:
                        points = int(split_msg[0])
                except ValueError:
                    self.chat("Points must be a number")
                    return

            if (points > total_points):
                self.chat("@{}, You don't have {} points!".format(user_name, points))
                return

            if (random.random() < 0.5):
                self.viewers[user_name.lower()] += points
                self.viewer_ranks = SortedList(self.viewers.values())
                self.chat("@{}, You won {} points! Wow.".format(user_name, points))
            else:
                self.viewers[user_name.lower()] -= points
                self.viewer_ranks = SortedList(self.viewers.values())
                self.chat("@{}, You lost {} points... That's not good.".format(user_name, points))

    def do_command(self, e, cmd, msg):
        if (cmd == "game"):
            current_game, game_id = self.get_game_name_twitch()
            self.chat("The current game is {}".format(current_game))

        elif (cmd == "wr"):
            self.get_wr(msg)

        elif (cmd == "pb"):
            self.get_pb(msg)

        elif (cmd == "help"):
            self.print_help(msg)

        elif (cmd == "commands" or cmd =="command"):
            self.edit_commands(e, msg)

        elif (cmd == "followage"):
            self.get_followage(e)

        elif (cmd == "points"):
            self.get_points(e)

        elif (cmd == "top"):
            self.get_top(e)

        elif (cmd == "gift"):
            self.gift_points(e, msg)

        elif (cmd == "gamble"):
            self.gamble(e, msg)

        elif(cmd in self.commands):
            self.chat(self.commands[cmd])

    def chat(self, msg):
        self.connection.privmsg(self.channel, msg)

    def handle_exit_signal(self, signal, frame):
        print("Goodbye, cruel world...")
        self.save_commands()
        self.save_viewers()
        self.stop_timer_event.set()
        self.die()

class RecurrentTimer(threading.Thread):
    def __init__(self, event, wait_time, func):
        threading.Thread.__init__(self)
        self.stopped = event
        self.wait_time = wait_time
        self.func = func

    def run(self):
        while not self.stopped.wait(self.wait_time):
            self.func()

def td_format(td_object):
    seconds = int(td_object.total_seconds())
    periods = [
        ('year',        60*60*24*365),
        ('month',       60*60*24*30),
        ('day',         60*60*24),
        ('hour',        60*60),
        ('minute',      60),
        ('second',      1)
    ]

    strings=[]
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value , seconds = divmod(seconds, period_seconds)
            has_s = 's' if period_value > 1 else ''
            strings.append("%s %s%s" % (period_value, period_name, has_s))

    return ", ".join(strings)

def main():
    random.seed()

    bot = TwitchBot(config.USERNAME, config.CLIENT_ID, config.OAUTH_TOKEN, config.CHANNEL)
    bot.start()

if __name__ == "__main__":
    main()
