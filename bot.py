#!/usr/bin/env python3
import config
import socket
import time
import re
import signal
import sys
import os
import random
import cv2 as cv
import numpy as np
import multiprocessing as mp
import queue

CHAT_MSG = re.compile(r"^:\w+!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :")
filenames = []
quotes = []
new_quotes = []

class EggDupeCounter(mp.Process):
    def __init__(self, video_id, sock):
        mp.Process.__init__(self)
        self.video_id = video_id
        self.sock = sock
        self.egg_bottle = self.normalize(np.load(config.EGG_BOTTLE))
        self.empty_bottle = self.normalize(np.load(config.EMPTY_BOTTLE))
        self.empty = True
        self.count = 0

    def normalize(self, arr):
        rng = arr.max()-arr.min()
        amin = arr.min()
        return (arr-amin)*255/rng

    def setup_video_capture(self):
        self.vc = cv.VideoCapture(self.video_id)
        if (not self.vc):
            print("Error loading video capture")
            return 1
        else:
            print("Loaded video capture")
            return 0

    def run(self):
        self.setup_video_capture()
        while True:
            ret, frame = self.vc.read()
            ret, frame = self.vc.read()
            if (not ret):
                break
            y1,y2,x1,x2 = config.C_RIGHT_COORDS
            c_right = self.normalize(frame[y1:y2, x1:x2])
            if (self.empty):
                diff = np.linalg.norm(self.egg_bottle - c_right)
                if (diff < 5):
                    #print("Egg: {}".format(diff))
                    self.empty = False
                    self.count += 1
                    chat(self.sock, "Egg count: {}".format(self.count))
                    self.count = self.count % 7
            else:
                diff = np.linalg.norm(self.empty_bottle - c_right)
                if (diff < 5):
                    #print("Empty: {}".format(diff))
                    self.empty = True
        return

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

    counter = EggDupeCounter(config.VIDEO_ID, s)
    counter.start()

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
