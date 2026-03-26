#!/usr/bin/env python3
"""
Replug the REED R8080 USB device.

Replicates HTUSB.dll's HTUSB_ReplugHIDDevice (DICS_STOP + DICS_START)
by unbinding and rebinding the USB device on Linux.
"""
import glob
import os
import sys
import time

VENDOR_ID = "04d9"
PRODUCT_ID = "e000"


def find_device_path():
    for devpath in glob.glob("/sys/bus/usb/devices/[0-9]*"):
        try:
            vid = open(os.path.join(devpath, "idVendor")).read().strip()
            pid = open(os.path.join(devpath, "idProduct")).read().strip()
            if vid == VENDOR_ID and pid == PRODUCT_ID:
                return devpath
        except FileNotFoundError:
            continue
    return None


def replug(devpath):
    devname = os.path.basename(devpath)
    driver_link = os.path.join(devpath, "driver")

    if os.path.islink(driver_link):
        driver_path = os.path.realpath(driver_link)
        print(f"Unbinding {devname}...")
        with open(os.path.join(driver_path, "unbind"), "w") as f:
            f.write(devname)
        time.sleep(1)
        print(f"Rebinding {devname}...")
        with open(os.path.join(driver_path, "bind"), "w") as f:
            f.write(devname)
    else:
        auth = os.path.join(devpath, "authorized")
        print(f"Deauthorizing {devname}...")
        with open(auth, "w") as f:
            f.write("0")
        time.sleep(1)
        print(f"Reauthorizing {devname}...")
        with open(auth, "w") as f:
            f.write("1")

    print("Replug complete.")


devpath = find_device_path()
if not devpath:
    print("R8080 not found")
    sys.exit(1)

print(f"Found R8080 at {devpath}")
replug(devpath)
