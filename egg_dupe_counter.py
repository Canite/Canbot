#!/usr/bin/env python3
import cv2 as cv
import numpy as np
import multiprocessing as mp
import queue
import signal

class EggDupeCounter(mp.Process):
    def __init__(self, video_id, bot, egg_bottle, empty_bottle, c_right_coords):
        mp.Process.__init__(self)
        self.video_id = video_id
        self.bot = bot
        self.egg_bottle = self.normalize(np.load(egg_bottle))
        self.empty_bottle = self.normalize(np.load(empty_bottle))
        self.c_right_coords = c_right_coords
        self.min_size = c_right_coords[1] * c_right_coords[3]
        self.empty = True
        self.count = 0
        self.exit = False

    def normalize(self, arr):
        if (arr.size != 0):
            rng = arr.max()-arr.min()
            amin = arr.min()
            return (arr-amin)*255/rng
        else:
            return arr

    def setup_video_capture(self):
        self.vc = cv.VideoCapture(self.video_id)
        if (not self.vc):
            print("Error loading video capture")
            return False
        else:
            print("Loaded video capture")
            return True

    def run(self):
        success = self.setup_video_capture()
        if (not success):
            return
        while not self.exit:
            ret, frame = self.vc.read()
            ret, frame = self.vc.read()
            if (not ret or frame.size < self.min_size):
                break
            y1,y2,x1,x2 = self.c_right_coords
            c_right = self.normalize(frame[y1:y2, x1:x2])
            if (self.empty):
                diff = np.linalg.norm(self.egg_bottle - c_right)
                if (diff < 5):
                    #print("Egg: {}".format(diff))
                    self.empty = False
                    self.count += 1
                    self.bot.chat(self.sock, "Egg count: {}".format(self.count))
                    self.count = self.count % 7
            else:
                diff = np.linalg.norm(self.empty_bottle - c_right)
                if (diff < 5):
                    #print("Empty: {}".format(diff))
                    self.empty = True
        return
