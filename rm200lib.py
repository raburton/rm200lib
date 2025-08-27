#!/usr/bin/env python3

import os
import usb.core

dev = None
commsize = 140
debug = False

def connect():
    global dev
    dev = usb.core.find(idVendor=0x0765, idProduct=0x6001)
    if dev is None:
        raise Exception('No RM200 found')

    usb.control.set_feature(dev, 1)
    usb.control.set_configuration(dev, 0)
    usb.control.set_configuration(dev, 1)

    GetComBufSize()

def disconnect():
    global dev
    if dev != None:
        usb.util.dispose_resources(dev)

def SetDebug(enabled):
    global debug
    debug = enabled

def GetComBufSize():
    # remember this value for our use as well
    global commsize

    ret = command(b'\x78\x11')
    if len(ret) == 4:
        commsize = int.from_bytes(ret, 'big')
        return commsize
    return None

def UnlockExtendedCommands(password):
    # multiple passwords, why?
    # allows use of the commands with Extended in the name, and 8823 (GetMultiColorCmd(true))
    if password == None:
        password = '873gwe31xah1'
    return command_bool(b"\x89\x00" + password.encode('utf8') + b'\0')

def GetInfo():
    # info is: serial num, mfg date, hw rev?, total disk space, used space, free space
    # special case, does own usb command as when called in bootloader it will send back
    # status code/error 0x27 (bug?), BL onyl sends first 3 strings
    global dev
    global debug

    if dev is None:
        raise Exception('Not connected. Call Connect() first.')

    dev.ctrl_transfer(0x40, 0x97, 0, 2, 0)
    dev.write(0x2, b'\x78\x12')

    data = dev.read(0x81, commsize, 1000)

    if debug == True:
        print('len: ' + str(len(data)) + ', data: ' + ' '.join([hex(x) for x in data]))

    if len(data) >= 4 and data[2] == 0x33 and (data[3] == 0x01 or data[3] == 0x27):
        # 32bit int (string count), then array of strings null terminated/separated
        return str(data[8:-1], 'utf8').split('\0')

    return None

def GetSerialNum():
    info = GetInfo()
    if info == None:
        return None
    return info[0]

# gets array of colours, first the selected and then all scanned (inc selected again)
# each colour is array of 5 strings: fandeck, colour, page, row, column
def GetMultiColorCmd():
    data = command(b"\x78\x23")

    if data == None:
        return None

    pos = 0
    colours = []

    # unknown word (always? 00 01)
    pos += 2
    # colour count
    #count = int.from_bytes(data[pos : pos + 2], "big")
    pos += 2

    while pos < len(data):
        # unknown bytes (always? 00 00 00 00 00 00)
        pos += 6

        strings = []
        for i in range(5):
            # find utf16 null terminator
            scan = pos
            while scan < len(data)-1:
                if data[scan] == 0 and data[scan+1] == 0:
                    #print('scan = ' + str(scan) + 'data[scan] ' + str(data[scan]))
                    break
                scan += 2
            strings.append(bytes(data[pos:scan]).decode('utf16'))
            #print(bytes(data[pos:scan]).decode('utf16'))
            pos = scan + 2

        # unknown byte, first (selected) seems to be 0x02, rest 0x14
        pos += 1

        colours.append(strings)

    return colours


def GetBLInfo():
    #'2.41   Bootloader ' (null terminated)
    bin = command(b'\x78\x2d')
    if bin == None:
        return None
    return str(bin[:-1], 'utf8')

def GetFWInfo():
    #'2.16   RM200' (null terminated)
    #'2.16    RM200 Cosmetics' (null terminated)
    bin = command(b'\x77\x01')
    if bin == None:
        return None
    return str(bin[:-1], 'utf8')

def GetChipId():
    bin = command(b'\x78\x07')
    if bin == None:
        return None
    return '0x' + bytes(bin).hex()

def GetDeltaEParameter():
    # also has a set method, function unknown, 5 little endian ints
    bin = command(b'\x78\x37')
    if len(bin) == 20:
        return [int.from_bytes(bin[0:4], 'little'), int.from_bytes(bin[4:8], 'little'), int.from_bytes(bin[8:12], 'little'),
                int.from_bytes(bin[12:16], 'little'), int.from_bytes(bin[16:20], 'little')]
    else:
        return None

def FileDir():
    dat = command(b'\x77\x24')
    # 32bit int (string count), then array of strings null terminated/separated
    return str(dat[4:-1], 'utf8').split('\0')

def FileDelete(file):
    return command_bool(b"\x77\x25" + file.encode('utf8') + b'\0')

def EnterBootloader():
    return command_bool(b'\x78\x10\x87\xef\x3a\x1a')

def GetDeviceMode():
    # 1=eGeneral, 2=eBatteryOnly, 3=eSync, 4=eRemote, 5=eTukan, 6=eBatteryPowered, 9=eMSD
    ret = command(b'\x78\x2a')
    if (len(ret) == 1):
        return ret[0]
    else:
        return None

def SetDeviceMode(mode):
    # 1=eGeneral, 2=eBatteryOnly, 3=eSync, 4=eRemote, 5=eTukan, 6=eBatteryPowered, 9=eMSD
    # 2 will turn off the screen, puts to sleep?, wakes with differnet mode or key press
    # 3 will display the teh sync image if on the flash as SyncMode.bmp
    # 4 makes screen yellow!
    if (mode < 1 or mode > 6) and mode != 9:
        raise Exception('Mode must be 1=eGeneral, 2=eBatteryOnly, 3=eSync, 4=eRemote, 5=eTukan, 6=eBatteryPowered, 9=eMSD')
    return command_bool(b'\x78\x29' + bytes([mode]))

# GenericCmd provides a whole load more functions
# there are lots of "sub commands", most of which are unknown
# this is a special case command that does its own usb, as repsonse
# is different to the normal commands
def Genericcommand(cmd, v1, v2, v3, v4, v5, v6, string, quiet = 0):
    global dev
    global debug

    if dev is None:
        raise Exception('Not connected. Call Connect() first.')

    data = b'\x77\x17' + cmd.to_bytes(2, "big") + v1.to_bytes(4, "big") + v2.to_bytes(4, "big") + v3.to_bytes(4, "big") + \
        v4.to_bytes(4, "big") + v5.to_bytes(4, "big") + v6.to_bytes(4, "big") + string.encode('utf8') + b'\0'

    length = len(data)
    dev.ctrl_transfer(0x40, 0x97, (length >> 16), length & 0xffff, 0)
    dev.write(0x2, data)

    data = dev.read(0x81, commsize, 1000)

    if debug == True:
        print('len: ' + str(len(data)) + ', data: ' + ' '.join([hex(x) for x in data]))

    # often returns a message
    if len(data) > 30 and not quiet:
        print(str(data[30:-1], 'utf8'))

    if len(data) > 0 and data[2] == 0x33:
        if data[3] == 0x01:
            return True

    return False

# Changes the device serial number. Serial should be 10 digits long.
# Regular models start with 0, QC with 2, cosmetic with 3
# Causes a usb error and disconnect, but otherwise works fine.
def SetSerialNum(serial):

    length = len(serial)
    if (length != 10):
        raise Exception('Serial must be 10 digits long')

    return Genericcommand(0x032a, 0x00001d7e, 0x000005de, 0, 0, 0, 0, serial)
    #return rm.command_bool(b'\x00\x00\x1d\x7e \x00\x00\x05\xde \x00\x00\x00\x00 \x00\x00\x00\x00 \x00\x00\x00\x00 \x00\x00\x00\x00' +
    #       serial.encode('utf8') + b'\0')

# Backup the calib data to a file on the nand.
# Two readable text formats, and one binary dump (most useful for backup)
# Call this, then download the file from the nand.
def BackupCalibData(mode):
    if mode == 1:
        mode = 0x0000
    elif mode == 2:
        mode = 0x0064
    elif mode == 3:
        mode = 0x1d7e
    else:
        raise Exception('Mode must be 1=text, 2=textcompat, 3=binary')

    return Genericcommand(0x0167, 0x00bc614e, 0x00001fa9, mode, 0, 0, 0, '')

def GetAperture():
    # returns 0=small, 1=medium, 2=large/auto
    ret = command(b'\x78\x25')
    if (len(ret) == 1):
        return ret[0]
    else:
        return None

def TriggerMeasurement(aperture):
    if aperture < 0 or aperture > 2:
        raise Exception('Aperture must be 0=small, 1=medium, or 2=large/auto')

    return command_bool(b'\x78\x35' + bytes([aperture]))

def Reboot():
    return command_bool(b'\x77\x14')

def BLUpload(file, action):

    # todo check in bootloader mode
    if action != 1 and action != 2 and action != 3 and action != 6:
        raise Exception('Action must be 1=bootloader (dangerous!), 2=firmware, 3=calib, 6=welcome')

    with open(file, "rb") as f:
        data = f.read()

    chunk_max = commsize - 40
    offset = 0

    while True:
        chunk = data[offset : offset + chunk_max]

        chunk_len = len(chunk)
        if chunk_len == 0:
            break

        ret = BLUploadChunk(offset, chunk)
        if ret == False:
            return False
        offset += chunk_size

    print('Fnished upload, comitting...')

    return BLAction(action, offset)

def BLUploadChunk(offset, chunk):
    chunk_len = len(chunk)
    return command_bool(b"\x77\x12" + offset.to_bytes(4, "big") + chunk_len.to_bytes(4, "big") + chunk)

def BLAction(action, size):
    # write previously uploaded data to spi (bootloader) or appropriate nand location (firmware/calib/welcome bitmap)
    # or in the case of action=6 size=0 erase the existing welcome bitmap
    if action != 1 and action != 2 and action != 3 and action != 6:
        raise Exception('Action must be 1=bootloader (dangerous!), 2=firmware, 3=calib, 6=welcome')

    return command_bool(b'\x77\x13' + bytes([action]) + size.to_bytes(4, "big"))

def BLUploadBootloader(file):
    return BLUpload(file, 1)

def BLUploadFirmware(file):
    return BLUpload(file, 2)

def BLUploadCalibration(file):
    return BLUpload(file, 3)

def BLUploadWelcome(file):
    return BLUpload(file, 6)

def BLEraseWelcome(file):
    return BLAction(6, 0)

# get the current content of the screen, pixel data in RGB565, no headers
def GetLcdData():
    return command(b'\x78\x0e')

def OpenFile(file, mode):
    if mode < 1 or mode > 2:
        raise Exception('Mode must be 1=read, 2=write')

    return command_bool(b'\x77\x20' + bytes([mode]) + file.encode() + b'\0')

def FileRead():
    return command(b"\x77\x22")

def CloseFile(file):
    return command_bool(b'\x77\x21')

def UploadFile(file):
    if not OpenFile(file, 2):
        raise Exception('Unable to open file')

    with open(file, "rb") as f:
        data = f.read()

    ret = None
    chunk_size = commsize - 40
    offset = 0
    file_len = len(data)

    while True:
        chunk = data[offset : offset + chunk_size]
        offset = offset + chunk_size

        chunk_len = len(chunk)
        if chunk_len == 0:  # does firmware upload need a final zero?
            break

        ret = command(b'\x77\x23' + chunk_len.to_bytes(4, "big") + chunk)
        if ret is None:
            break

    if not CloseFile(file):
        raise Exception('Unable to close file')

def DownloadFile(file):
    if not OpenFile(file, 1):
        #raise Exception('Unable to open file')
        return False

    with open(file, "wb") as f:
        while True:
            chunk = FileRead()
            if chunk == None or len(chunk) < 4:
                raise Exception('Bad read')

            chunk_len = int.from_bytes(chunk[:4], "big")
            if chunk_len == 0:
                break
            f.write(chunk[4:])

    if not CloseFile(file):
        raise Exception('Unable to close file')

    return True

# save screenshot to bmp file
def SaveScreenshot(file):
    header = bytes([
        0x42, 0x4d, 0x0a, 0x2f, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x8a, 0x00, 0x00, 0x00, 0x7c, 0x00,
        0x00, 0x00, 0xb0, 0x00, 0x00, 0x00, 0x24, 0xff, 0xff, 0xff, 0x01, 0x00, 0x10, 0x00, 0x03, 0x00,
        0x00, 0x00, 0x80, 0x2e, 0x01, 0x00, 0x23, 0x2e, 0x00, 0x00, 0x23, 0x2e, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf8, 0x00, 0x00, 0xe0, 0x07, 0x00, 0x00, 0x1f, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x42, 0x47, 0x52, 0x73, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ])
    body = GetLcdData()
    if (body == None):
        return False

    with open(file, 'wb') as f:
        f.write(header)
        f.write(body)

    return True

def StartPreview():
    return command_bool(b'\x78\x34\x01')

def StopPreview():
    return command_bool(b'\x78\x34\x00')

# get current view image (must be in preview mode)
# 2 byte width, 2 byte length, then pixel data in RGB565
def GetPreview():
    # only works while previewing (via button or command)
    data = command(b'\x78\x16')
    #if (data == None):
    #    raise Exception('Nothing returned. Device not previewing?')
    return data

def SavePreview(file):
    header = bytes([
        0x42, 0x4d, 0x8a, 0xc8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x8a, 0x00, 0x00, 0x00, 0x7c, 0x00,
        0x00, 0x00, 0xa0, 0x00, 0x00, 0x00, 0x60, 0xff, 0xff, 0xff, 0x01, 0x00, 0x10, 0x00, 0x03, 0x00,
        0x00, 0x00, 0x00, 0xc8, 0x00, 0x00, 0x23, 0x2e, 0x00, 0x00, 0x23, 0x2e, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf8, 0x00, 0x00, 0xe0, 0x07, 0x00, 0x00, 0x1f, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x42, 0x47, 0x52, 0x73, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ])

    body = GetPreview()
    if (body == None):
        return False

    with open(file, 'wb') as f:
        f.write(header)
        # skip length and width and just assume 160x160
        f.write(body[4:])

    return True

def command(data):
    global dev
    global debug

    if dev is None:
        raise Exception('Not connected. Call Connect() first.')

    length = len(data)
    dev.ctrl_transfer(0x40, 0x97, (length >> 16), length & 0xffff, 0)
    dev.write(0x2, data)

    data = dev.read(0x81, commsize, 1000)

    if debug == True:
        print('len: ' + str(len(data)) + ', data: ' + ' '.join([hex(x) for x in data]))

    if len(data) >= 4 and data[2] == 0x33:
        if data[3] == 0x01:
            return data[4:]

    return None

def command_bool(data):
    global dev

    if dev is None:
        raise Exception('Not connected. Call Connect() first.')

    length = len(data)
    dev.ctrl_transfer(0x40, 0x97, (length >> 16), length & 0xffff, 0)
    dev.write(0x2, data)

    data = dev.read(0x81, commsize, 1000)

    if debug == True:
        print('len: ' + str(len(data)) + ', data: ' + ' '.join([hex(x) for x in data]))

    if len(data) >= 4 and data[2] == 0x33:
        if data[3] == 0x01:
            return True

    return False

