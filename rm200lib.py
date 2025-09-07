#!/usr/bin/env python3
# Licensed under AGPL 3.0 https://www.gnu.org/licenses/agpl-3.0.en.html
# richardaburton@gmail.com

import os
import struct
import usb.core

dev = None
commsize = 140
debug = False

def Connect():
    global dev
    dev = usb.core.find(idVendor=0x0765, idProduct=0x6001)
    if dev is None:
        raise Exception('No RM200 found')

    usb.control.set_feature(dev, 1)
    usb.control.set_configuration(dev, 0)
    usb.control.set_configuration(dev, 1)

    GetComBufSize()

def Disconnect():
    global dev
    if dev != None:
        usb.util.dispose_resources(dev)
        dev = None

# enable some debugging in this code
def SetDebug(enabled):
    global debug
    debug = enabled

def GetComBufSize():
    # remember this value for our use as well
    global commsize

    ret = CommandData(b'\x78\x11')
    if len(ret) == 4:
        commsize = int.from_bytes(ret, 'big')
        return commsize
    return None

# allows use of the commands with Extended in the name, and 8823 (GetMultiColorCmd(true))
def UnlockExtendedCommands(password):
    # multiple passwords, why?
    if password == None:
        password = '873gwe31xah1'
    return CommandBool(b"\x89\x00" + password.encode('utf8') + b'\0')

# gets various device info: serial, mfg date, device rev?, disk spcae total, used, free
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

# utility function to get the device serial number
def GetSerialNum():
    info = GetInfo()
    if info == None:
        return None
    return info[0]

# gets array of colours, first the selected and then all scanned (inc selected again)
# each colour is array of 5 strings: fandeck, colour, page, row, column
def GetMultiColorCmd():
    data = CommandData(b"\x78\x23")

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

# bootloader version (when running normal firmware)
def GetBLInfo():
    #'2.41   Bootloader ' (null terminated)
    bin = CommandData(b'\x78\x2d')
    if bin == None:
        return None
    return str(bin[:-1], 'utf8')

# current running firmware (or bootloader if that's running)
def GetFWInfo():
    #'2.16   RM200' (null terminated)
    #'2.16    RM200 Cosmetics' (null terminated)
    bin = CommandData(b'\x77\x01')
    if bin == None:
        return None
    return str(bin[:-1], 'utf8')

# the chip id/ security id, used when syncing with the server
def GetChipId():
    bin = CommandData(b'\x78\x07')
    if bin == None:
        return None
    return '0x' + bytes(bin).hex()

def GetDeltaEParameter():
    # also has a set method, function unknown, 5 little endian ints
    bin = CommandData(b'\x78\x37')
    if len(bin) == 20:
        return [int.from_bytes(bin[0:4], 'little'), int.from_bytes(bin[4:8], 'little'), int.from_bytes(bin[8:12], 'little'),
                int.from_bytes(bin[12:16], 'little'), int.from_bytes(bin[16:20], 'little')]
    else:
        return None

# get a directory listing
def FileDir():
    data = CommandData(b'\x77\x24')
    # 32bit int (string count), then array of strings null terminated/separated
    return str(data[4:-1], 'utf8').split('\0')

def FileDelete(file):
    return CommandBool(b"\x77\x25" + file.encode('utf8') + b'\0')

# reboto to bootloader
def EnterBootloader():
    return CommandBool(b'\x78\x10\x87\xef\x3a\x1a')

# significance of this not really clear
def GetDeviceMode():
    # 1=eGeneral, 2=eBatteryOnly, 3=eSync, 4=eRemote, 5=eTukan, 6=eBatteryPowered, 9=eMSD
    ret = CommandData(b'\x78\x2a')
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
    return CommandBool(b'\x78\x29' + bytes([mode]))

# returns array containing int percentage???, float voltage, int mode (0=charged, 2=charging, maybe 1=discharging?)
def GetBatteryState():
    data = CommandData(b'\x79\x05')
    if data == None or len(data) != 6:
        return None
    state = [data[0]]
    state.append(struct.unpack('>f', data[1:5])[0])
    state.append(data[5])
    return state

# GenericCmd provides a whole load more functions
# there are lots of "sub commands", most of which are unknown
# this is a special case command that does its own usb, as repsonse
# is different to the normal commands
def GenericCmd(cmd, v1, v2, v3, v4, v5, v6, string, quiet = 0):
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

    return GenericCmd(0x032a, 0x00001d7e, 0x000005de, 0, 0, 0, 0, serial)

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

    return GenericCmd(0x0167, 0x00bc614e, 0x00001fa9, mode, 0, 0, 0, '')

def GetAperture():
    # returns 0=small, 1=medium, 2=large/auto
    ret = CommandData(b'\x78\x25')
    if (len(ret) == 1):
        return ret[0]
    else:
        return None

def SetAperture(aperture):
    if aperture < 0 or aperture > 2:
        raise Exception('Aperture must be 0=small, 1=medium, or 2=large/auto')
    return CommandCool(b'\x78\x24' + bytes([aperture]))

# take a sample (like fully pressing the side button)
def TriggerMeasurement(aperture):
    if aperture < 0 or aperture > 2:
        raise Exception('Aperture must be 0=small, 1=medium, or 2=large/auto')

    return CommandBool(b'\x78\x35' + bytes([aperture]))

# reboot the device
def Reboot():
    return CommandBool(b'\x77\x14')

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

    print('Finshed upload, comitting...')

    return BLAction(action, offset)

def BLUploadChunk(offset, chunk):
    chunk_len = len(chunk)
    return CommandBool(b"\x77\x12" + offset.to_bytes(4, "big") + chunk_len.to_bytes(4, "big") + chunk)

def BLAction(action, size):
    # write previously uploaded data to spi (bootloader) or appropriate nand location (firmware/calib/welcome bitmap)
    # or in the case of action=6 size=0 erase the existing welcome bitmap
    if action != 1 and action != 2 and action != 3 and action != 6:
        raise Exception('Action must be 1=bootloader (dangerous!), 2=firmware, 3=calib, 6=welcome')

    return CommandBool(b'\x77\x13' + bytes([action]) + size.to_bytes(4, "big"))

# utility function to upload a new bootloader - dangerous!
# see Ivor Hewitts's blog on how to recover if this goes badly
def BLUploadBootloader(file):
    return BLUpload(file, 1)

# utility function to upload a new firmware
def BLUploadFirmware(file):
    return BLUpload(file, 2)

# utility function to upload new calibration data
def BLUploadCalibration(file):
    return BLUpload(file, 3)

# utility function to upload the boot image
def BLUploadWelcome(file):
    return BLUpload(file, 6)

# utility function to erase the boot image
def BLEraseWelcome(file):
    return BLAction(6, 0)

# get the current content of the screen, pixel data in RGB565, no headers
def GetLcdData():
    return CommandData(b'\x78\x0e')

# open a file on the device
def OpenFile(file, mode):
    if mode < 1 or mode > 2:
        raise Exception('Mode must be 1=read, 2=write')

    return CommandBool(b'\x77\x20' + bytes([mode]) + file.encode() + b'\0')

# read from a file, opened in read mode
def FileRead():
    return CommandData(b"\x77\x22")

# write to a file, opened in write mode
def FileWrite(chunk, length):
    return CommandBool(b'\x77\x23' + length.to_bytes(4, "big") + chunk)

# close the file when done (commits if writing)
def CloseFile(file):
    return CommandBool(b'\x77\x21')

# upload data to a file on the device
def PutFile(file, data):
    if not OpenFile(file, 2):
        return False

    chunk_size = commsize - 40
    offset = 0
    file_len = len(data)

    while True:
        chunk = data[offset : offset + chunk_size]
        offset = offset + chunk_size

        chunk_len = len(chunk)
        if chunk_len == 0:
            break

        if not FileWrite(chunk, chunk_len);
            break

    if not CloseFile(file):
        return False

    return True;

# upload a file from current dir, to same name on device
def UploadFile(file):
    with open(file, "rb") as f:
        data = f.read()
    return PutFile(file, data)

# fetch a file, returns the file contents
def FetchFile(file):
    if not OpenFile(file, 1):
        return None

    data = b''
    while True:
        chunk = FileRead()
        if chunk == None or len(chunk) < 4:
            raise Exception('Bad read')

        chunk_len = int.from_bytes(chunk[:4], "big")
        if chunk_len == 0:
            break
        data += chunk[4:]

    if not CloseFile(file):
        return False

    return data

# download a file, save to same named file on pc
def DownloadFile(file):
    data = FetchFile(file)
    if data == None:
        return False

    with open(file, "wb") as f:
        f.write(data)

    return True

# returns array of file details stored in Versions.dat
# each of which is an array: type, id, name, sku, description, version, size, filename
# type is 1=bootloader, 2=firmwire, 6=welcome_screen, 7=fandeck, 12=measure_screen, 13=start_sound
# 14=end_sound, 15=multi_sound, 19=device_config, 20=inversion_matrix
def ReadVersionsDotDat():
    data = FetchFile('Versions.dat')
    if data == None:
        return None

    pos = 0
    files = []

    while pos < len(data):
        fields = []
        # skip record length
        pos += 4

        for i in range(8):
            match i:
                case 0:
                    # file type
                    fields.append(int.from_bytes(data[pos:pos+2], 'little'))
                    pos += 2
                case 6:
                    # file size
                    fields.append(int.from_bytes(data[pos:pos+4], 'little'))
                    pos += 4
                case _:
                    # strings
                    length = int.from_bytes(data[pos:pos+2], 'little')
                    pos += 2
                    fields.append(data[pos:pos+length].decode('utf8'))
                    pos += length
        files.append(fields)

    return files

# see ReadVersionsDotDat for data format
def WriteVersionsDotDat(files):
    data = b''
    for f in range(len(files)):
        file = b''
        # record length
        file += (6 + 12 + len(files[f][1].encode('utf8')) + len(files[f][2].encode('utf8')) + len(files[f][3].encode('utf8')) +
                 len(files[f][4].encode('utf8')) + len(files[f][5].encode('utf8')) + len(files[f][7].encode('utf8'))).to_bytes(4, 'little')

        for i in range(8):
            match i:
                case 0:
                    # file type
                    file += files[f][i].to_bytes(2, 'little')
                case 6:
                    # file size
                    file += files[f][i].to_bytes(4, 'little')
                case _:
                    # strings
                    file += len(files[f][i].encode('utf8')).to_bytes(2, 'little')
                    file += files[f][i].encode('utf8')
        data += file

    return PutFile('Versions.dat', data)

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

# briefly display a picture on the screen
# needs raw RBG565 data 176 x -220 pixels
def Display565Image(file):
    with open(file, 'rb') as f:
        data = f.read()
    if len(data) != 77440:
        raise Exception('invalid RBG565 data, must be 77440 bytes')
    return CommandBool(b'\x79\x03' + data)

# start previewing (like holding the side button half in)
def StartPreview():
    return CommandBool(b'\x78\x34\x01')

# stop previewing
def StopPreview():
    return CommandBool(b'\x78\x34\x00')

# get current preview image (device must be in preview mode, by button or command)
# returns 2 byte width, 2 byte length, then pixel data in RGB565
def GetPreview():
    data = CommandData(b'\x78\x16')
    return data

# utility function to save the preview image to a bmp file
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
        # skip length and width, we assume 160x160
        f.write(body[4:])

    return True

# returns the temperature as a float
def MeasureTemperature():
    data = CommandData(b'\x78\x06')
    if data == None or len(data) != 4:
        return None
    return struct.unpack('>f', data)[0]

# gets the time as an array of values: year, month, day, hours, mins, secs
def GetTime():
    data = CommandData(b'\x97\x0a')
    if data == None or len(data) != 7:
        return None
    return [int.from_bytes(data[0:2]), data[2], data[3], data[4], data[5], data[6]]

# utility function to get date as a formatted string
def GetTimeString():
    data = GetTime()
    if data == None:
        return None
    return f'{data[0]}/{data[1]}/{data[2]} {data[3]}:{data[4]}:{data[5]}'

def SetTime(year, month, day, hours, mins, secs):
    return CommandBool(b'\x79\x04' + year.to_bytes(2, 'big') + bytes([month]) + bytes([day]) +
                        bytes([hours]) + bytes([mins]) + bytes([secs]))

# send a key press event to the device, allowing remote control
def GenerateKeyboardEvent(key):
    if key < 1 or key > 8:
        raise Exception('Key must be 1=centre, 2=up, 3=down, 4=left, 5=right, 6=preview(release), 7=preview(hold), 8=capture')
    # must be previewing before can use capture
    return CommandBool(b'\x78\x0f' + key.to_bytes(2, 'big'))

# returns bitmask of current pressed keys
# 0x1=up, 0x2=down, 0x4=left, 0x8=right, 0x10=centre, 0x20=???, 0x40=???, 0x80=power, 0x100=???
# no preview or capture (return error)
def GetKeyCode():
    data = CommandData(b'\x97\x09')
    if data == None or len(data) != 2:
        return None
    return int.from_bytes(data, 'big')

# get the number of saved colour records
def GetNumberOfEntries():
    data = CommandData(b'\x78\x19')
    if data == None or len(data) != 2:
        return None
    return int.from_bytes(data, 'big')

# fetches the data of a saved sample
# numbered from 0 to GetNumberOfEntries-1
# returns array of 11 strings: date/time, fandeck, colour code, page, row, column, colour name, ??, page code, ??, ??
#   and 1 byte array containing image in BGR565 (not RGB565)
def GetRecordData(num):
    data = CommandData(b'\x78\x20' +  num.to_bytes(2, 'big'))
    if data == None:
        return None

    pos = 0
    record = []

    # unknown word, record type? always? 00 01
    pos += 2
    # date and time
    record.append(f'{int.from_bytes(data[2:4], 'big')}/{data[4]}/{data[5]} {data[6]}:{data[7]}:{data[8]}')
    pos += 7

    # unknown bytes (always? 00 00 00 00 00 00)
    pos += 6

    for i in range(10):
        # find utf16 null terminator
        scan = pos
        while scan < len(data)-1:
            if data[scan] == 0 and data[scan+1] == 0:
                #print('scan = ' + str(scan) + 'data[scan] ' + str(data[scan]))
                break
            scan += 2
        record.append(bytes(data[pos:scan]).decode('utf16'))
        #print(bytes(data[pos:scan]).decode('utf16'))
        pos = scan + 2

    # unknown word, record type? always? 00 02
    pos += 2

    record.append(data[pos:])

    return record

# save the image from a saved sample record
# pass the record returned by GetRecordData and a filename to write to
def SaveRecordImage(record, file):
    header = bytes([
        0x42, 0x4d, 0xaa, 0x4e, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x8a, 0x00, 0x00, 0x00, 0x7c, 0x00,
        0x00, 0x00, 0x64, 0x00, 0x00, 0x00, 0x9c, 0xff, 0xff, 0xff, 0x01, 0x00, 0x10, 0x00, 0x03, 0x00,
        0x00, 0x00, 0x20, 0x4e, 0x00, 0x00, 0x13, 0x0b, 0x00, 0x00, 0x13, 0x0b, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1f, 0x00, 0x00, 0x00, 0xe0, 0x07, 0x00, 0x00, 0x00, 0xf8,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x42, 0x47, 0x52, 0x73, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ])

    if (len(record) != 12 or record[11] == None):
        return False

    with open(file, 'wb') as f:
        f.write(header)
        f.write(record[11])

    return True

# get array of fandecks on the device
def GetFandecks():
    data = CommandData(b'\x78\x21')
    if data == None:
        return None

    pos = 0
    fandecks = []

    # unknown bytes (always? 00 01)
    pos += 2
    # fandeck count
    pos += 2

    while pos < len(data):
        fields = []
        for i in range(8):

            # find utf16 null terminator
            scan = pos
            while scan < len(data)-1:
                if data[scan] == 0 and data[scan+1] == 0:
                    #print('scan = ' + str(scan) + 'data[scan] ' + str(data[scan]))
                    break
                scan += 2
            fields.append(bytes(data[pos:scan]).decode('utf16'))
            pos = scan + 2

            # after first string is a byte indicating 0=disabled, 1=enabled, 2=priority
            if i == 0:
                fields.append(data[pos])
                pos += 1

        fandecks.append(fields)

        # unknown bytes (variable content) size?
        fields.append(int.from_bytes(data[pos:pos+4], 'big'))
        pos += 4

    return fandecks

# Activate/deactivate/prioritise a fandeck
def SetFandeckActive(name, state):
    if state < 0 or state > 2:
        raise Exception('State must be 0=disabled, 1=enabled, 2=priority')
    return CommandBool(b'\x78\x22' + name.encode('utf-16le') + b'\0\0' + bytes([state]))

# Delete a fandeck, you should deactivate it first and then reboot after.
def DeleteFandeck(name):
    return CommandBool(b'\x78\x32' + name.encode('utf-16le') + b'\0\0')

# number of second till device need calibtating again
def GetTimeToCalibExpired():
    data = CommandData(b'\x78\x2e')
    if data == None or len(data) != 4:
        return None
    return int.from_bytes(data, 'big')

# returns 0=not calibrated, 1=calibrated
def GetCalibrationState():
    data = CommandData(b'\x78\x28')
    if data == None or len(data) != 1:
        return None
    return data[0]

# Send a command, get data back (or None in case of error)
# Pass the full command, including any data, as byte sequence
# Will throw exception if not connected
def CommandData(data):
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

# Send a command and get a bool back to indicate success
# Pass the full command, including any data, as byte sequence
# Will throw exception if not connected
def CommandBool(data):
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

