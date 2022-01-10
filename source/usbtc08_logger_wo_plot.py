#!/usr/bin/python
#coding=utf-8

# Pico Technology TC-08 datalogger

import os
import datetime
from collections import OrderedDict
import sys
import time
import atexit
import logging

import usbtc08

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger()


MAINS = 50
DESKEW = False
#TODO Read config from yaml

# Set thermocouple type for each channel: B, E, J, K, N, R, S or T.
# Set to ' ' to disable a channel. Less active channels allow faster logging rates.
# Set to X for voltage readings.
# Do not change the configuration of the cold-junction channel.
CHANNEL_CONFIG = {
    usbtc08.USBTC08_CHANNEL_CJC: 'C', # Needs to be 'C'.
    usbtc08.USBTC08_CHANNEL_1: 'K',
    usbtc08.USBTC08_CHANNEL_2: ' ',
    usbtc08.USBTC08_CHANNEL_3: ' ',
    usbtc08.USBTC08_CHANNEL_4: ' ',
    usbtc08.USBTC08_CHANNEL_5: ' ',
    usbtc08.USBTC08_CHANNEL_6: ' ',
    usbtc08.USBTC08_CHANNEL_7: ' ',
    usbtc08.USBTC08_CHANNEL_8: ' '}
# Set the name of each channel.
CHANNEL_NAME = {
    usbtc08.USBTC08_CHANNEL_CJC: 'Cold-junction',
    usbtc08.USBTC08_CHANNEL_1: 'Channel 1',
    usbtc08.USBTC08_CHANNEL_2: 'Channel 2',
    usbtc08.USBTC08_CHANNEL_3: 'Channel 3',
    usbtc08.USBTC08_CHANNEL_4: 'Channel 4',
    usbtc08.USBTC08_CHANNEL_5: 'Channel 5',
    usbtc08.USBTC08_CHANNEL_6: 'Channel 6',
    usbtc08.USBTC08_CHANNEL_7: 'Channel 7',
    usbtc08.USBTC08_CHANNEL_8: 'Channel 8'}
# Set the preferred unit of temperature. Options are degC, degF, K and degR.
UNIT = usbtc08.USBTC08_UNITS_CENTIGRADE
     # usbtc08.USBTC08_UNITS_FAHRENHEIT
     # usbtc08.USBTC08_UNITS_KELVIN
     # usbtc08.USBTC08_UNITS_RANKINE

class usbtc08_error(Exception):
    em = {
        usbtc08.USBTC08_ERROR_OK: "No error occurred",
        usbtc08.USBTC08_ERROR_OS_NOT_SUPPORTED: "The driver does not support the current operating system",
        usbtc08.USBTC08_ERROR_NO_CHANNELS_SET: "A call to usb_tc08_set_channel() is required",
        usbtc08.USBTC08_ERROR_INVALID_PARAMETER: "One or more of the function arguments were invalid",
        usbtc08.USBTC08_ERROR_VARIANT_NOT_SUPPORTED: "The hardware version is not supported. Download the latest driver",
        usbtc08.USBTC08_ERROR_INCORRECT_MODE: "An incompatible mix of legacy and non-legacy functions was called (or usb_tc08_get_single() was called while in streaming mode.)",
        usbtc08.USBTC08_ERROR_ENUMERATION_INCOMPLETE: "Function usb_tc08_open_unit_async() was called again while a background enumeration was already in progress",
        usbtc08.USBTC08_ERROR_NOT_RESPONDING: "Cannot get a reply from a USB TC-08",
        usbtc08.USBTC08_ERROR_FW_FAIL: "Unable to download firmware",
        usbtc08.USBTC08_ERROR_CONFIG_FAIL: "Missing or corrupted EEPROM",
        usbtc08.USBTC08_ERROR_NOT_FOUND: "Cannot find enumerated device",
        usbtc08.USBTC08_ERROR_THREAD_FAIL: "A threading function failed",
        usbtc08.USBTC08_ERROR_PIPE_INFO_FAIL: "Can not get USB pipe information",
        usbtc08.USBTC08_ERROR_NOT_CALIBRATED: "No calibration date was found",
        usbtc08.USBTC08_EROOR_PICOPP_TOO_OLD: "An old picopp.sys driver was found on the system",
        usbtc08.USBTC08_ERROR_PICO_DRIVER_FUNCTION: "Undefined error",
        usbtc08.USBTC08_ERROR_COMMUNICATION: "The PC has lost communication with the device"}

    def __init__(self, err = None, note = None):
        self.err = err
        self.note = note
        self.msg = ''
        if err is None:
            self.msg = note
        else:
            if type(err) is int:
                if err in self.em:
                    self.msg = "%d: %s".format(err, self.em[err])
                else:
                    self.msg = "%d: Unknown error".format(err)
            else:
                self.msg = err
            if note is not None:
                self.msg = "%s [%s]".format(self.msg, note)

    def __str__(self):
        return self.msg

class logger_error(Exception):
    em = {
        0: "No error occurred.",
        1: "Undefined error.",
        2: "Undefined error.",
        3: "Undefined error.",
        4: "Undefined error.",
        5: "Undefined error.",
        6: "Undefined error.",
        7: "Undefined error.",
        8: "Undefined error.",
        9: "Undefined error."}

    def __init__(self, err = None, note = None):
        self.err = err
        self.note = note
        self.msg = ''
        if err is None:
            self.msg = note
        else:
            if type(err) is int:
                if err in self.em:
                    self.msg = "%d: %s".format(err, self.em[err])
                else:
                    self.msg = "%d: Unknown error".format(err)
            else:
                self.msg = err
            if note is not None:
                self.msg = "%s [%s]".format(self.msg, note)

    def __str__(self):
        return self.msg

class usbtc08_logger():
    def __init__(self):
        self.units = {
            usbtc08.USBTC08_UNITS_CENTIGRADE : self.unit_celsius,
            usbtc08.USBTC08_UNITS_FAHRENHEIT : self.unit_fahrenheit,
            usbtc08.USBTC08_UNITS_KELVIN : self.unit_kelvin,
            usbtc08.USBTC08_UNITS_RANKINE : self.unit_rankine}
        atexit.register(self.close_unit)
        self.info = usbtc08.USBTC08_INFO()
        self.info.size = usbtc08.sizeof_USBTC08_INFO
        self.charbuffer = usbtc08.charArray(usbtc08.USBTC08_MAX_INFO_CHARS)
        self.channelbuffer = usbtc08.floatArray(usbtc08.USBTC08_MAX_CHANNELS + 1)
        self.tempbuffer = usbtc08.floatArray(usbtc08.USBTC08_MAX_SAMPLE_BUFFER)
        self.timebuffer = usbtc08.intArray(usbtc08.USBTC08_MAX_SAMPLE_BUFFER)
        self.flags = usbtc08.shortArray(1)
        self.data = []
        # Print header to console
        print("-------------------------------------------'")
        print("Pico Technology USB-TC08 logger'")
        print("-------------------------------------------'")

        # Settings
        self.units[UNIT]()
        # Start communication with device
        self.open_unit_async()
        self.open_unit_progress()
        self.get_unit_info2()
        self.config()

    def config(self):
        for i in CHANNEL_CONFIG:
            self.set_channel(i, CHANNEL_CONFIG.get(i))
        self.set_mains(MAINS)

    def logging(self, duration, interval):
        self.duration = duration
        if (interval > self.get_minimum_interval_ms()):
            self.interval = interval
        else:
            self.interval = self.get_minimum_interval_ms()
        self.clear_data()
        # Take a single measurement for the cold-junction temperature
        self.get_single()
        # Start sampling at the maximum rate
        self.run(self.interval)
        timestamp = 0
        while timestamp < duration:
            for i in CHANNEL_CONFIG:
                # Only record active channels
                if CHANNEL_CONFIG.get(i) != ' ':
                    if DESKEW:
                        logger.debug("deskew")
                        samples = self.get_temp_deskew(i)
                    else:
                        samples = self.get_temp(i)
                    last_timestamp = self.process_data(i, samples)
                    if last_timestamp > timestamp:
                        timestamp = last_timestamp
            # Sleep until new data should be available
            time.sleep(self.interval / 1000);
        # Stop sampling
        self.stop()

    def test(self):
        logger.info("Entered test function.'")
        #self.get_unit_info()
        #self.get_unit_info2()
        self.get_formatted_info()
        self.get_single()

    def clear_data(self):
        self.data = []
        for i in range(0, usbtc08.USBTC08_MAX_CHANNELS + 1):
            self.data.append(OrderedDict())

    def process_data(self, channel, samples):
#        logger.debug("Processing %i samples of channel %i.'.format(samples, channel)")
        if samples > 0:
            time_data = []
            temp_data = []
            for i in range(0, samples):
                time_data.append(self.timebuffer[i] / 1000.0)
                temp_data.append(self.tempbuffer[i])
            new_data = OrderedDict(zip(time_data, temp_data))
            self.data[channel].update(new_data)
            return max(time_data)
        return 0

    def open_unit_async(self):
        result = usbtc08.usb_tc08_open_unit_async()
        if result == 1:
            logger.debug("Started enumerating USB TC-08 units")
        elif result == 0:
            logger.debug("ERROR: No more USB TC-08 units found")
            sys.exit(1)
        elif result == -1:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(0), 'Failed to start enumerating')

    def open_unit_progress(self):
        result, self.handle, progress = usbtc08.usb_tc08_open_unit_progress()
        while result == usbtc08.USBTC08_PROGRESS_PENDING:
            time.sleep(0.1);
            result, self.handle, progress = usbtc08.usb_tc08_open_unit_progress()
        if result == usbtc08.USBTC08_PROGRESS_FAIL:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(0), 'Waiting completion of enumeration')
        elif self.handle <= 0:
            logger.debug("ERROR: No TC-08 units detected")
            sys.exit(1)
        elif result == usbtc08.USBTC08_PROGRESS_COMPLETE:
            logger.debug("Completed enumeration")

    def get_unit_info(self):
        result = usbtc08.usb_tc08_get_unit_info(self.handle, self.info)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Reading unit info')
        else:
            logger.debug("Received information about the USB TC-08 unit")
            logger.debug("Driver version: " + str(''.join(chr(i) for i in self.info.DriverVersion if i in range(32, 127))))
            logger.info("Picopp version: {0}".format(self.info.PicoppVersion))
            logger.info("Hardware version: {0}".format(self.info.HardwareVersion))
            logger.info("Variant: %i'.formatself.info.Variant")
            logger.info("Serial number: %s'.format''.join(chr(i) for i in self.info.szSerial if i in range(32, 127))")
            logger.info("Calibration date: %s'.format''.join(chr(i) for i in self.info.szCalDate if i in range(32, 127))")

    def get_unit_info2(self):
        result = usbtc08.usb_tc08_get_unit_info2(self.handle, self.charbuffer, usbtc08.USBTC08_MAX_VERSION_CHARS, usbtc08.USBTC08LINE_DRIVER_VERSION)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Reading driver version.')
        else:
            length = result
            self.info_driver = ''.join(chr(self.charbuffer[i]) for i in range(0, length) if self.charbuffer[i] in range(32, 127))
            logger.debug("Driver version: " + self.info_driver)
        result = usbtc08.usb_tc08_get_unit_info2(self.handle, self.charbuffer, usbtc08.USBTC08_MAX_VERSION_CHARS, usbtc08.USBTC08LINE_KERNEL_DRIVER_VERSION)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Reading kernel driver version.')
        else:
            length = result
            self.info_kernel = ''.join(chr(self.charbuffer[i]) for i in range(0, length) if self.charbuffer[i] in range(32, 127))
            logger.info("Kernel driver version: {0}".format(self.info_kernel))
        result = usbtc08.usb_tc08_get_unit_info2(self.handle, self.charbuffer, usbtc08.USBTC08_MAX_VERSION_CHARS, usbtc08.USBTC08LINE_HARDWARE_VERSION)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Reading hardware version.')
        else:
            length = result
            self.info_hardware = ''.join(chr(self.charbuffer[i]) for i in range(0, length) if self.charbuffer[i] in range(32, 127))
            logger.info("Hardware version: {0}".format(self.info_hardware))
        result = usbtc08.usb_tc08_get_unit_info2(self.handle, self.charbuffer, usbtc08.USBTC08_MAX_INFO_CHARS, usbtc08.USBTC08LINE_VARIANT_INFO)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Reading variant info.')
        else:
            length = result
            self.info_variant = ''.join(chr(self.charbuffer[i]) for i in range(0, length) if self.charbuffer[i] in range(32, 127))
            logger.debug("Variant info: {0}".format(self.info_variant))
        result = usbtc08.usb_tc08_get_unit_info2(self.handle, self.charbuffer, usbtc08.USBTC08_MAX_SERIAL_CHARS, usbtc08.USBTC08LINE_BATCH_AND_SERIAL)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Reading batch and serial.')
        else:
            length = result
            self.info_serial = ''.join(chr(self.charbuffer[i]) for i in range(0, length) if self.charbuffer[i] in range(32, 127))
            logger.debug("Batch and serial: ${0}".format(self.info_serial))
        result = usbtc08.usb_tc08_get_unit_info2(self.handle, self.charbuffer, usbtc08.USBTC08_MAX_DATE_CHARS, usbtc08.USBTC08LINE_CAL_DATE)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Reading calibration date.')
        else:
            length = result
            self.info_calibration = ''.join(chr(self.charbuffer[i]) for i in range(0, length) if self.charbuffer[i] in range(32, 127))
            logger.debug("Calibration date: {0}".format(self.info_calibration))

    def get_formatted_info(self):
        result = usbtc08.usb_tc08_get_formatted_info(self.handle, self.charbuffer, usbtc08.USBTC08_MAX_INFO_CHARS)
        if result == 0:
            logger.debug("ERROR: Too many bytes to copy.'")
        else:
            logger.debug("Formatted unit info: \n%s'.format''.join(chr(self.charbuffer[i]) for i in range(0, usbtc08.USBTC08_MAX_INFO_CHARS))")

    def set_channel(self, channel, tc):
        result = usbtc08.usb_tc08_set_channel(self.handle, channel, ord(tc))
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Setting channel')
        else:
            if tc != ' ':
                logger.debug("Set channel {0} to {1}-type thermocouple".format(channel, tc))

    def disable_channel(self, channel):
        result = usbtc08.usb_tc08_set_channel(self.handle, channel, ord(' '))
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Disabling channel')
        else:
            logger.debug("Disabled channel %i.'.format(channel)")

    def set_mains(self, freq):
        if freq == 60:
            result = usbtc08.usb_tc08_set_mains(self.handle, 1)
        elif freq == 50:
            result = usbtc08.usb_tc08_set_mains(self.handle, 0)
        else:
            logger.debug("ERROR: Incorrect mains frequency. Default to filter 50 Hz.")
            result = usbtc08.usb_tc08_set_mains(self.handle, 0)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Setting mains filter.')
        else:
            logger.info("Set USB TC-08 unit to reject {0} Hz".format(freq))

    def get_minimum_interval_ms(self):
        result = usbtc08.usb_tc08_get_minimum_interval_ms(self.handle)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Read the minimum sample interval.')
        else:
            interval = result
            logger.info("Minimum sampling interval is {0} ms".format(interval))
        return interval

    def run(self, interval):
        result = usbtc08.usb_tc08_run(self.handle, interval)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Issue run command.')
        else:
            logger.debug("Started sampling with {0} ms interval".format(interval))

    def get_temp(self, channel):
        result = usbtc08.usb_tc08_get_temp(self.handle, self.tempbuffer, self.timebuffer, usbtc08.USBTC08_MAX_SAMPLE_BUFFER, self.flags, channel, self.unit, 0)
        if result:
            logger.debug("Received result:" + str(result))
        samples = 0
        if result == -1:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Reading data of channel.')
        elif result == 0:
            logger.debug("Channel #{0}: No samples available".format(channel))
            pass
        else:
            samples = result
            logger.debug("Read {0} samples to the buffer".format(samples))
            pass
        for i in range(0, samples):
            logger.debug("{0} {1}".format(self.timebuffer[i], self.tempbuffer[i]))
            #print("Flags: %s'.format"{0:b}".format(self.flags[0]).zfill(9)")
        return samples

    def get_temp_deskew(self, channel):
        result = usbtc08.usb_tc08_get_temp_deskew(self.handle, self.tempbuffer, self.timebuffer, usbtc08.USBTC08_MAX_SAMPLE_BUFFER, self.flags, channel, self.unit, 0)
        samples = 0
        if result == -1:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Reading deskewed data of channel')
        elif result == 0:
            logger.debug("No samples available'")
            pass
        else:
            samples = result
            logger.debug("Read {0} samples to the buffer".format(samples))
        for i in range(0, samples):
            logger.debug("{0} {1}".format(self.timebuffer[i], self.tempbuffer[i]))
            #print("Flags: %s'.format"{0:b}".format(self.flags[0]).zfill(9)")
        return samples

    def stop(self):
        result = usbtc08.usb_tc08_stop(self.handle)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Stop sampling')
        else:
            logger.debug("Stopped sampling")

    def get_single(self):
        result = usbtc08.usb_tc08_get_single(self.handle, self.channelbuffer, self.flags, self.unit)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Take single measurement of all channels')
        else:
            i = 1
            #logger.debug('Channel {0}: {1}'.format(i, self.channelbuffer[i]))
            logger.debug("Take a single measurement of all channels")
            for i in range(0, 9):
                logger.debug("Channel {0}: {1}".format(i, self.channelbuffer[i]))

    def unit_celsius(self):
        self.unit = usbtc08.USBTC08_UNITS_CENTIGRADE
        self.unit_text = u'°C'
        logger.debug('Unit set to ' + self.unit_text)

    def unit_fahrenheit(self):
        self.unit = usbtc08.USBTC08_UNITS_FAHRENHEIT
        self.unit_text = u'°F'
        logger.debug("Unit set to %s.'.formatself.unit_text")

    def unit_kelvin(self):
        self.unit = usbtc08.USBTC08_UNITS_KELVIN
        self.unit_text = 'K'
        logger.debug("Unit set to %s.'.formatself.unit_text")

    def unit_rankine(self):
        self.unit = usbtc08.USBTC08_UNITS_RANKINE
        self.unit_text = u'°R'
        logger.debug("Unit set to %s.'.formatself.unit_text")

    def close_unit(self):
        result = usbtc08.usb_tc08_close_unit(self.handle)
        if result == 0:
            raise usbtc08_error(usbtc08.usb_tc08_get_last_error(self.handle), 'Closing communication')
        else:
            logger.debug("Unit closed successfully")

if __name__ == '__main__':
    # Read mode as first argument
    mode = 'help'
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    # Read logging duration as second argument or default to 60 seconds
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    # Read sample interval (in ms) as default to as fast as possible
    interval = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    if mode == 'log':
        device = usbtc08_logger()
        logger.info("Enter logging mode")
        device.logging(duration, interval)
    elif mode == 'test':
        device = usbtc08_logger()
        logger.info("Enter test mode")
        device.test()
    else:
        print("Usage: python usbtc08_logger.py log <duration in seconds> <interval in ms>'")
        print("The default is a duration of 60 seconds, sampling as fast as possible.'")
