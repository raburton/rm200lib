#!/usr/bin/env python3

import os
import usb.core

dev = None
debug = False

def connect():
    global dev
    dev = usb.core.find(idVendor=0x0765, idProduct=0x6001)
    if dev is None:
        raise Exception('No RM200 found')

    usb.control.set_feature(dev, 1)
    usb.control.set_configuration(dev, 0)
    usb.control.set_configuration(dev, 1)

def disconnect():
    global dev
    if dev != None:
        usb.util.dispose_resources(dev)

def GetBLInfo():
    #'2.41   Bootloader ' (null terminated)
    bin = command(b'\x78\x2d')
    return str(bin[:-1], 'utf8')

def GetFWInfo():
    #'2.16   RM200' (null terminated)
    #'2.16    RM200 Cosmetics' (null terminated)

    bin = command(b'\x77\x01')
    return str(bin[:-1], 'utf8')

def GetChipId():
    bin = command(b'\x78\x07')
    return '0x' + bytes(bin).hex()

def command(data):
    global dev
    global debug

    if dev is None:
        raise Exception('Not connected. Call Connect() first.')

    ret = None

    length = len(data)
    dev.ctrl_transfer(0x40, 0x97, (length >> 16), length & 0xffff, 0)
    dev.write(0x2, data)

    data = dev.read(0x81, 100008, 1000)

    if len(data) >= 4 and data[2] == 0x33:
        if data[3] == 0x01:
            ret = data[4:]

    return ret

