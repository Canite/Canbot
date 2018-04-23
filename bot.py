#!/usr/bin/env python3
import config
import egg_dupe_counter as edc
import irc.bot
import requests
import signal
import sys
import os
import random
import datetime
import urllib

class TwitchBot(irc.bot.SingleServerIRCBot):
    def __init__(self, username, client_id, token, channel):
        self.client_id = client_id
        self.token = token
        self.channel = "#" + channel
        self.twitch_header = {'Client-ID': client_id} 
        signal.signal(signal.SIGINT, self.handle_exit_signal)
        self.exit = False

        # Get the channel id, we will need this for v5 API calls
        url = "{}/users?login={}".format(config.TWITCH_API, channel)
        r = requests.get(url, headers=self.twitch_header).json()
        self.channel_id = r['data'][0]['id']
        print(self.channel_id)

        # Create IRC bot connection
        server = 'irc.chat.twitch.tv'
        port = 6667
        print('Connecting to ' + server + ' on port ' + str(port) + '...')
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port, token)], username, username)

    def on_welcome(self, c, e):
        print('Joining ' + self.channel)

        # You must request specific capabilities before you can use them
        c.cap('REQ', ':twitch.tv/membership')
        c.cap('REQ', ':twitch.tv/tags')
        c.cap('REQ', ':twitch.tv/commands')
        c.join(self.channel)

        self.counter = edc.EggDupeCounter(c.socket, self.channel, config.EGG_BOTTLE, config.EMPTY_BOTTLE, config.C_RIGHT_COORDS)
        self.counter.start()

    def on_pubmsg(self, c, e):
        msg = e.arguments[0]
        # If a chat message starts with an exclamation point, try to run it as a command
        if msg[0] == '!':
            cmd = msg.split(' ')[0][1:]
            print("Received command: " + cmd)
            self.do_command(e, cmd, ' '.join(msg.split(' ')[1:]))
        return

    def get_game_name_twitch(self):
        channel_url = "{}/streams?user_id={}".format(config.TWITCH_API, self.channel_id)
        r = requests.get(channel_url, headers=self.twitch_header).json()
        game_name = ""
        game_id = 0
        if (r["data"]):
            game_id = r["data"][0]["game_id"]
            game_url = "{}/games?id={}".format(config.TWITCH_API, game_id)
            r = requests.get(game_url, headers=self.twitch_header).json()
            if (r["data"]):
                game_name = r["data"][0]["name"]
        return game_name, game_id

    def get_game_name_srl(self, name):
        game_url = urllib.parse.quote(name)
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
        for cat in r["data"]:
            name = cat["name"]
            if (category in name.lower()):
                cat_name = name
                cat_id = cat["id"]
                break

        if (cat_id == ""):
            self.chat("Could not find {} category for \"{}\".".format(category, game_name))
        return cat_name, cat_id

    def get_pb(self, msg):
        twitch_game_name, game_id = self.get_game_name_twitch()
        split_msg = msg.rstrip('\r\n').split(" ")
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

        speedrun_url = "{}/users/{}/personal-bests?game=".format(config.SRL_API, username, game_id)
        r = requests.get(speedrun_url).json()
        if ("status" not in r):
            pb_run = None
            for run in r["data"]:
                if (run["run"]["category"] == cat_id):
                    pb_run = run
                    break

            if (pb_run != None):
                place = pb_run["place"]
                pb = str(datetime.timedelta(seconds=pb_run["run"]["times"]["primary_t"]))
                self.chat("{} is rank {} in \"{}\" {} with a time of {}.".format(username, place, game_name, cat_name, pb))
            else:
                self.chat("{} has no PB for \"{}\" {}.".format(username, game_name, cat_name))
        else:
            self.chat("Could not find user {}.".format(username))

    def get_wr(self, msg):
        twitch_game_name, game_id = self.get_game_name_twitch()
        split_msg = msg.rstrip('\r\n').split(" ")
        if (len(split_msg) > 1):
            category = split_msg[0]
            twitch_game_name = ' '.join(split_msg[1:])
        elif (len(split_msg) == 1 and split_msg[0] != ""):
            category = split_msg[0]
        else:
            category = "any"

        game_name, game_id = self.get_game_name_srl(twitch_game_name)
        if (game_name == None):
            self.chat("Couldn't find \"{}\" on speedrun.com".format(twitch_game_name))
            return

        cat_name, cat_id = self.get_category(category, game_id)
        if (cat_name == None):
            self.chat("Couldn't find category containing \"{}\" for \"{}\"".format(category, game_name))
            return

        speedrun_url = "{}/games/{}/records?top=1&miscellaneous=no".format(config.SRL_API, game_id)
        r = requests.get(speedrun_url).json()
        wr_run = None
        for run in r["data"]:
            print(run)
            if (run["category"] == cat_id):
                wr_run = run
                break

        if (wr_run):
            first_place = str(datetime.timedelta(seconds=wr_run["runs"][0]["run"]["times"]["primary_t"]))
            user_url = user = wr_run["runs"][0]["run"]["players"][0]["uri"]
            r = requests.get(user_url).json()
            user_name = r["data"]["names"]["international"]
            self.chat("The world record for \"{}\" {} is {} by {}.".format(game_name, cat_name, first_place, user_name))

    def do_command(self, e, cmd, msg):
        if (cmd == "game"):
            current_game, game_id = self.get_game_name_twitch()
            self.chat("The current game is {}".format(current_game))

        elif (cmd == "wr"):
            self.get_wr(msg)

        elif (cmd == "pb"):
            self.get_pb(msg)

    def chat(self, msg):
        self.connection.privmsg(self.channel, msg)

    def handle_exit_signal(self, signal, frame):
        print("Goodbye, cruel world...")
        self.die()

def main():
    random.seed()

    bot = TwitchBot(config.USERNAME, config.CLIENT_ID, config.TOKEN, config.CHANNEL)
    bot.start()

if __name__ == "__main__":
    main()
