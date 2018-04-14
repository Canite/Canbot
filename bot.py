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
        signal.signal(signal.SIGINT, self.handle_exit_signal)
        self.exit = False

        # Get the channel id, we will need this for v5 API calls
        url = 'https://api.twitch.tv/kraken/users?login=' + channel
        headers = {'Client-ID': client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
        r = requests.get(url, headers=headers).json()
        self.channel_id = r['users'][0]['_id']

        # Create IRC bot connection
        server = 'irc.chat.twitch.tv'
        port = 6667
        print('Connecting to ' + server + ' on port ' + str(port) + '...')
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port, token)], username, username)

        self.counter = edc.EggDupeCounter(config.VIDEO_ID, self, config.EGG_BOTTLE, config.EMPTY_BOTTLE, config.C_RIGHT_COORDS)
        self.counter.start()


    def on_welcome(self, c, e):
        print('Joining ' + self.channel)

        # You must request specific capabilities before you can use them
        c.cap('REQ', ':twitch.tv/membership')
        c.cap('REQ', ':twitch.tv/tags')
        c.cap('REQ', ':twitch.tv/commands')
        c.join(self.channel)

    def on_pubmsg(self, c, e):
        msg = e.arguments[0]
        # If a chat message starts with an exclamation point, try to run it as a command
        if msg[0] == '!':
            cmd = msg.split(' ')[0][1:]
            print("Received command: " + cmd)
            self.do_command(e, cmd, ' '.join(msg.split(' ')[1:]))
        return

    def do_command(self, e, cmd, msg):
        if (cmd == "game"):
            channel_url = "https://api.twitch.tv/kraken/channels/" + self.channel_id
            headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}

            r = requests.get(channel_url, headers=headers).json()
            self.chat("The current game is {}".format(r["game"]))
        elif (cmd == "wr"):
            channel_url = "https://api.twitch.tv/kraken/channels/" + self.channel_id
            headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}

            r = requests.get(channel_url, headers=headers).json()
            game_name = r["game"]
            game_url = urllib.parse.quote(game_name)
            speedrun_url = "https://www.speedrun.com/api/v1/games?name={}".format(game_url)
            r = requests.get(speedrun_url).json()
            game_id = r["data"][0]["id"]
            speedrun_url = "https://www.speedrun.com/api/v1/games/{}/records?top=1".format(game_id)
            r = requests.get(speedrun_url).json()
            first_place = str(datetime.timedelta(seconds=r["data"][0]["runs"][0]["run"]["times"]["primary_t"]))
            user_url = user = r["data"][0]["runs"][0]["run"]["players"][0]["uri"]
            r = requests.get(user_url).json()
            user_name = r["data"]["names"]["international"]
            self.chat("The \"{}\" world record is {} by {}.".format(game_name, first_place, user_name))

    def chat(self, msg):
        self.connection.privmsg(self.channel, msg)

    def handle_exit_signal(self, signal, frame):
        print("Goodbye, cruel world...")
        self.counter.exit = True
        self.die()

def main():
    random.seed()

    bot = TwitchBot(config.USERNAME, config.CLIENT_ID, config.TOKEN, config.CHANNEL)
    bot.start()

if __name__ == "__main__":
    main()
