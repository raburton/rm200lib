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

def GetComBufSize():
    # remember this value for our use as well
    global commsize

    ret = command(b'\x78\x11')
    if len(ret) == 4:
        buffsize = int.from_bytes(ret, 'big')
        commsize = buffsize - 40;
        return buffsize
    return None

def GetInfo():
    # when called in bootloader will send back status code/error 0x27, but also 3 normal strings
    bin = command(b'\x78\x12')
    # 32bit int (string count), then array of strings null terminated/separated
    return str(bin[4:-1], 'utf8').split('\0')

def GetSerialNum():
    info = GetInfo()
    if info == None:
        raise Exception('Unable to get device info')
    return info[0]

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


def command(data):
    global dev
    global debug

    if dev is None:
        raise Exception('Not connected. Call Connect() first.')

    ret = None

    length = len(data)
    dev.ctrl_transfer(0x40, 0x97, (length >> 16), length & 0xffff, 0)
    dev.write(0x2, data)

    data = dev.read(0x81, commsize, 1000)

    if len(data) >= 4 and data[2] == 0x33:
        if data[3] == 0x01:
            ret = data[4:]

    return ret

def command_bool(data):
    global dev

    if dev is None:
        raise Exception('Not connected. Call Connect() first.')

    length = len(data)
    dev.ctrl_transfer(0x40, 0x97, (length >> 16), length & 0xffff, 0)
    dev.write(0x2, data)

    data = dev.read(0x81, commsize, 1000)

    if len(data) >= 4 and data[2] == 0x33:
        if data[3] == 0x01:
            return True

    return False

