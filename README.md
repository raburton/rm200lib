rm200lib
--

A Python library to interact with the x-rite RM200 Portable Spectrocolorimeter

This library exposes each USB command giving you more flexibility, but also provides utility functions that combine several commands where appropriate.
For example, you can separatly open, read, and close a file on the device. Or you can use the utility function to just download a file to your pc.

Functions are generally named as per the log messages in the code (generally quite intuitive). To see what it can do, have a look at the comments in the code.

Many functions return actual data (suitably interpreted, e.g. parsed and returned as a string array), not printed messages. For ease of reading you might want to
wrap them in code to make them print out a little prettier, see example below. Functions generally return data (or `None` on error) or `True`/`False` to indicate
success (according to purpose of function). They will raise an exception if the device is not connected or there are parameter errors.

To get started in python3:
```python
import rm200lib as rm

rm.Connect()

rm.GetInfo() # return array of device info strings
print('\n'.join(rm.GetInfo())) # or pretty printed version

rm.FileDir() # list files
rm.DownloadFile('filename') # save file to same name in current dir

rm.Disconnect()
```
