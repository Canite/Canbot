#!/usr/bin/env python3
import config
import socket
import time
import re
import signal
import sys
import os
import random

CHAT_MSG = re.compile(r"^:\w+!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :")
filenames = []
quotes = []
new_quotes = []

def signal_handler(signal, frame):
    with open(config.QUOTES_FILE, 'a+') as qf:
        for quote in new_quotes:
            qf.write("{}\n".format(quote))
    sys.exit(0)

def chat(sock, msg):
    print(msg)
    sock.sendall("PRIVMSG {} :{}\r\n".format(config.CHAN, msg).encode("utf-8"))

def ban(sock, user):
    chat(sock, ".ban {}".format(user))

def timeout(sock, user, secs=600):
    chat(sock, ".timeout {}".format(user, secs))

def get_filename(sock, username, msg):
    if (username == "canight"):
        if (filenames):
            new_filename = filenames.pop()
            chat(sock, "New filename: {}".format(new_filename))
        else:
            chat(sock, "No filename suggestions, type !filename <filename> to suggest a filename!")

def add_filename(sock, username, msg):
    split_msg = msg.split(" ")
    if (len(split_msg) > 1):
        filename = " ".join(split_msg[1:])
        if (len(filename) <= 8):
            filenames.insert(0, filename)
            chat(sock, "@{} Added \"{}\" to the list of filenames!".format(username, filename))
        else:
            chat(sock, "@{} Filename is too long, it must be 8 or less characters!".format(username))

def list_commands(sock, username, msg):
    chat(sock, "Commands: {}".format(",".join(config.COMMANDS.keys())))

def add_quote(sock, username, msg):
    msg = msg.lstrip("!newquote").lstrip(" ")
    if (msg != ""):
        quotes.append(msg)
        new_quotes.append(msg)
        chat(sock, "Added a quote!")
    else:
        chat(sock, "No quote given")
    return

def random_quote(sock, username, msg):
    rand_quote = random.randrange(len(quotes))
    quote(sock, username, str(rand_quote))
    return

def quote(sock, username, msg):
    msg = msg.lstrip("!quote").lstrip(" ")
    try:
        q = int(msg)
        if (0 <= q <= len(quotes)):
            chat(sock, quotes[q])
        else:
            chat(sock, "Must choose a quote number from 0 to {}!".format(str(len(quotes))))
    except ValueError:
        chat(sock, "Must choose a quote number from 0 to {}!".format(str(len(quotes))))
    return

def main():
    global quotes
    signal.signal(signal.SIGINT, signal_handler)

    COMMANDS = {"!filename" : add_filename, "!newfile" : get_filename, "!commands" : list_commands, \
                "!newquote" : add_quote, "!random" : random_quote, "!quote" : quote}

    random.seed()

    if (os.path.exists(config.QUOTES_FILE)):
        quotes = open(config.QUOTES_FILE, 'r').readlines()

    s = socket.socket()
    s.connect((config.HOST, config.PORT))
    s.send("PASS {}\r\n".format(config.PASS).encode("utf-8"))
    s.send("NICK {}\r\n".format(config.NICK).encode("utf-8"))
    s.send("JOIN {}\r\n".format(config.CHAN).encode("utf-8"))

    while True:
        response = s.recv(4096).decode("utf-8")
        if (response == "PING :tmi.twitch.tv\r\n"):
            s.send("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
        else:
            username = re.search(r"\w+", response).group(0)
            message = CHAT_MSG.sub("", response).rstrip("\r\n")
            split_message = message.split()
            print(username + ": " + message)
            if (split_message[0] in COMMANDS):
                COMMANDS[split_message[0]](s, username, message)

        time.sleep(config.RATE)

if __name__ == "__main__":
    main()
