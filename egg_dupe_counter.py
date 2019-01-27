#!/usr/bin/env python3
import win32gui, win32ui, win32con
import numpy as np
import multiprocessing as mp
import queue
import signal
import glob
import os

class EggDupeCounter(mp.Process):
    def __init__(self, socket, channel, egg_bottle, empty_bottle, c_right_coords):
        mp.Process.__init__(self)
        self.socket = socket
        self.channel = channel
        self.egg_bottle = self.normalize(np.load(egg_bottle))
        self.empty_bottle = self.normalize(np.load(empty_bottle))
        self.c_right_x, self.c_right_y, self.c_right_w, self.c_right_h = c_right_coords
        self.empty = True
        self.count = 0
        self.exit = False

    def normalize(self, arr):
        if (arr.size != 0):
            rng = arr.max()-arr.min()
            amin = arr.min()
            if (rng != 0):
                return (arr-amin)*255/rng
            else:
                return arr
        else:
            return arr

    def run(self):
        signal.signal(signal.SIGINT, self.handle_exit_signal)
        hwin = win32gui.GetDesktopWindow()
        hwindc = win32gui.GetWindowDC(hwin)
        srcdc = win32ui.CreateDCFromHandle(hwindc)
        memdc = srcdc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(srcdc, self.c_right_w, self.c_right_h)
        memdc.SelectObject(bmp)

        while not self.exit:
            try:
                memdc.BitBlt((0, 0), (self.c_right_w, self.c_right_h), srcdc, (self.c_right_x, self.c_right_y), win32con.SRCCOPY)
            except win32ui.error:
                pass
            screen_rect = np.fromstring(bmp.GetBitmapBits(True), dtype="uint8").reshape((self.c_right_h, self.c_right_w, 4))
            c_right = self.normalize(screen_rect)
            if (self.empty):
                diff = np.linalg.norm(self.egg_bottle - c_right)
                if (diff < 5):
                    #print("Egg: {}".format(diff))
                    self.empty = False
                    self.count += 1
                    self.socket.sendall("PRIVMSG {} :{}\r\n".format(self.channel, "Egg count: {}".format(self.count)).encode("utf-8"))
                    self.count = self.count % 7
            else:
                diff = np.linalg.norm(self.empty_bottle - c_right)
                if (diff < 5):
                    #print("Empty: {}".format(diff))
                    self.empty = True
        return

    def handle_exit_signal(self, signal, frame):
        print("Killing video capture")
        self.exit = True
