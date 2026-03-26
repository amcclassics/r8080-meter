#!/usr/bin/env python3
"""Send a USB-level reset to the REED R8080 to unfreeze it."""
import usb.core

dev = usb.core.find(idVendor=0x04D9, idProduct=0xE000)
if dev:
    dev.reset()
    print("USB reset sent — meter should recover")
else:
    print("R8080 not found — try power-cycling the meter")
