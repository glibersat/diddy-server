"""Legacy Nordic DFU to InfiniTime over BLE (see src/components/ble/DfuService.cpp).

usage: infinitime_dfu.py <address> <dfu.zip>
"""

import asyncio
import json
import struct
import sys
import zipfile

from bleak import BleakClient

CONTROL = "00001531-1212-efde-1523-785feabcd123"
PACKET = "00001532-1212-efde-1523-785feabcd123"
CHUNK = 20  # DfuService: dfuImage.Init(20, ...), the watch expects 20-byte writes
PRN = 10  # packet receipt notification every 10 packets


async def main(address: str, path: str) -> None:
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read("manifest.json"))["manifest"]["application"]
        image = z.read(manifest["bin_file"])
        init = z.read(manifest["dat_file"])
    print(f"image {len(image)} bytes, init {len(init)} bytes")

    notes: asyncio.Queue[bytes] = asyncio.Queue()

    def on_note(_, data: bytearray) -> None:
        notes.put_nowait(bytes(data))

    async def expect(prefix: bytes, timeout: float = 30) -> bytes:
        while True:
            data = await asyncio.wait_for(notes.get(), timeout)
            if data.startswith(prefix):
                return data
            if data[0] == 0x10:
                raise RuntimeError(f"unexpected response {data.hex()}")

    async with BleakClient(address, timeout=30) as client:
        print("connected, mtu", client.mtu_size)
        await client.start_notify(CONTROL, on_note)
        await client.write_gatt_char(CONTROL, bytes([0x01, 0x04]), response=True)
        await client.write_gatt_char(PACKET, struct.pack("<III", 0, 0, len(image)), response=False)
        await expect(bytes([0x10, 0x01, 0x01]), timeout=60)  # erase can take a while
        print("start ok")
        await client.write_gatt_char(CONTROL, bytes([0x02, 0x00]), response=True)
        await client.write_gatt_char(PACKET, init, response=False)
        await client.write_gatt_char(CONTROL, bytes([0x02, 0x01]), response=True)
        await expect(bytes([0x10, 0x02, 0x01]))
        print("init ok")
        await client.write_gatt_char(CONTROL, bytes([0x08, PRN]), response=True)
        await client.write_gatt_char(CONTROL, bytes([0x03]), response=True)
        sent = 0
        packets = 0
        last = -1
        while sent < len(image):
            chunk = image[sent : sent + CHUNK]
            await client.write_gatt_char(PACKET, chunk, response=False)
            sent += len(chunk)
            packets += 1
            if packets % PRN == 0 and sent < len(image):
                note = await expect(bytes([0x11]))
                got = struct.unpack("<I", note[1:5])[0]
                if got != sent:
                    raise RuntimeError(f"watch has {got} bytes, sent {sent}")
            pct = sent * 100 // len(image)
            if pct // 10 != last:
                last = pct // 10
                print(f"{pct}%", flush=True)
        await expect(bytes([0x10, 0x03, 0x01]))
        print("upload ok")
        await client.write_gatt_char(CONTROL, bytes([0x04]), response=True)
        await expect(bytes([0x10, 0x04, 0x01]))
        print("validated (CRC ok), activating")
        try:
            await client.write_gatt_char(CONTROL, bytes([0x05]), response=True)
        except Exception as error:  # the watch resets right away
            print("reset:", type(error).__name__)
    print("done")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
