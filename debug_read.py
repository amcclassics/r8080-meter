#!/usr/bin/env python3
"""Debug script to dump raw R8080 response bytes."""
import usb.core
import usb.util
import time

VENDOR_ID = 0x04D9
PRODUCT_ID = 0xE000
EP_IN = 0x81
EP_OUT = 0x02

dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
if not dev:
    print("R8080 not found")
    exit(1)

try:
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
except Exception:
    pass
dev.set_configuration()

def drain():
    while True:
        try:
            dev.read(EP_IN, 32, timeout=100)
        except Exception:
            break

def send_header(cmd_type, length):
    dev.ctrl_transfer(
        0x21, 0x09, 0x0200, 0,
        bytes([0x43, cmd_type, length & 0xFF, (length >> 8) & 0xFF, 0, 0, 0, 0]),
        timeout=1000,
    )

for i in range(20):
    try:
        try:
            send_header(0x01, 7)
        except Exception:
            pass

        dev.write(EP_OUT, bytes([0x07, 0x02, 0x41, 0x00, 0x00, 0x00, 0x00, 0x03]), timeout=1000)
        drain()
        send_header(0x04, 32)

        for _ in range(5):
            try:
                raw = bytes(dev.read(EP_IN, 32, timeout=1500))
                cnt = raw[0]
                data = raw[1:cnt+1]
                db_val = (data[5] * 256 + data[6]) / 10.0 if len(data) > 6 else None
                print(f"Read #{i+1}:")
                print(f"  Raw ({len(raw)} bytes): {raw.hex(' ')}")
                print(f"  Count byte: {cnt}")
                print(f"  Data ({len(data)} bytes): {' '.join(f'{b:02x}' for b in data)}")
                print(f"  Data (decimal):          {' '.join(f'{b:3d}' for b in data)}")
                if db_val:
                    print(f"  dB value: {db_val}")
                print()
                break
            except Exception as e:
                print(f"  Read attempt failed: {e}")
                break
    except Exception as e:
        print(f"Read #{i+1} failed: {e}")

    time.sleep(0.5)
