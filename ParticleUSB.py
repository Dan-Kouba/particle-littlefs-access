import subprocess
import sys
from parse import parse

class ParticleUSB:
    class Platform:
        name = ''
        id = 0
        vid = 0x2B04
        pid_cdc = 0xC000
        pid_dfu = 0xD000
        fs_block_size = 0
        user_block_count = 0

        def __init__(self, name='default', platform_id=0, pid_cdc=-1, pid_dfu=-1, user_block_count=0, fs_block_size=4096):
            self.name = name
            self.id = platform_id
            self.pid_cdc += pid_cdc if pid_cdc > 0 else self.id
            self.pid_dfu += pid_dfu if pid_dfu > 0 else self.id
            self.fs_block_size = fs_block_size
            self.user_block_count = user_block_count

        def is_gen3(self):
            return self.id > 10

        def is_tracker(self):
            return self.id == 26

        def __repr__(self):
            return "ParticleUSB.Platform: [name: {}, id: {}, vid: 0x{:04X}, pid_cdc: 0x{:04X}, pid_dfu: 0x{:04X}, user_block_count: {}, fs_block_size: {}]".format(
                self.name, self.id, self.vid, self.pid_cdc, self.pid_dfu, self.user_block_count, self.fs_block_size
            )

    known_platforms = {
        'default': Platform(),
        'Photon': Platform('photon', 6),
        'P1': Platform('p1', 8),
        'Electron': Platform('electron', 10),
        'Argon': Platform('argon', 12, user_block_count=512),
        'Boron': Platform('boron', 13, user_block_count=512),
        'A SoM': Platform('asom', 22, user_block_count=512),
        'B SoM': Platform('bsom', 23, user_block_count=512),
        'B5 SoM': Platform('b5som', 25, user_block_count=512),
        'Asset Tracker': Platform('tracker', 26, user_block_count=1024),
    }

    class DeviceInfo:
        def __init__(self, name: str, device_id: str, platform):
            self.name = name
            self.deviceID = device_id
            self.platform = platform

        def is_gen3(self):
            return self.platform.is_gen3()

        def is_tracker(self):
            return self.platform.is_tracker()

        def __repr__(self):
            return "Particle Device: {{name: {}, deviceID: {}, {}}}".format(self.name, self.deviceID, self.platform)

    @staticmethod
    def run_shell_cmd(cmd, silent=True):
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        result = bytearray()
        result.extend(b'\t')
        for c in iter(lambda: process.stdout.read(1), b''):
            result.extend(c)
            if not silent:
                sys.stdout.buffer.write(c)
                if c == b'\n' or c == b'\r':
                    sys.stdout.buffer.write(b'\t')
        process.wait()
        return result.decode('utf-8')

    def list_devices(self, platform=''):
        args = ['particle', 'usb', 'list']
        if platform and platform in self.known_platforms:
            args.append(platform)
        result = self.run_shell_cmd(args)
        if result.strip() == "No devices found.":
            return []
        else:
            device_strings = result.strip().split('\n')
            devices = []

            for device_string in device_strings:
                device_info = parse("{name} [{deviceID}] ({platform})", device_string)
                # print(device_info)
                name = None if device_info['name'] == '<no name>' else device_info['name']
                platform_str = device_info['platform'].split(', ')[0]
                platform = self.known_platforms[platform_str] if platform_str in self.known_platforms else self.known_platforms['default']
                devices.append(self.DeviceInfo(name, device_info['deviceID'], platform))

            # print(devices)
            return devices

    def enter_dfu_mode(self, device='', all=False):
        args = ['particle', 'usb', 'dfu']
        if device:
            args.append(device)
        elif all:
            args.append('--all')
        result = self.run_shell_cmd(args)
        return result.strip().endswith("Done.")
