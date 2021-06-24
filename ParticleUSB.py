import subprocess
import sys
from parse import parse

class ParticleUSB:
    known_platforms = [
        'photon',
        'p1',
        'electron',
        'argon',
        'boron',
        'xenon',
        'asom',
        'bsom',
        'xsom',
        'b5som',
        'tracker',
    ]

    class Platform:
        name = '';
        id = 0
        vid = 0x2B04
        pid_cdc = 0x0
        pid_dfu = 0x0
        user_flash_size = 0

        def __init__(self, name, platform_id, pid_cdc=-1, pid_dfu=-1):
            self.name = name
            self.id = platform_id
            self.pid_cdc = 0xC000 + pid_cdc if pid_cdc > 0 else id
            self.pid_dfu = 0xD000 + pid_dfu if pid_dfu > 0 else id

        def is_gen3(self):
            return self.id > 10

        def is_tracker(self):
            return self.id == 26

    known_platforms = {
        'Photon':        Platform('photon',    6),
        'P1':            Platform('p1',        8),
        'Electron':      Platform('electron', 10),
        'Argon':         Platform('argon',    12),
        'Boron':         Platform('boron',    13),
        'A SoM':         Platform('asom',     22),
        'B SoM':         Platform('bsom',     23),
        'B5 SoM':        Platform('b5som',    25),
        'Asset Tracker': Platform('tracker',  26),
    }

    class DeviceInfo:
        def __init__(self, name: str, deviceID: str, platform):
            self.name = name
            self.deviceID = deviceID
            self.platform = platform

        def is_gen3(self):
            return self.platform in self.gen3_platforms

        def is_tracker(self):
            return self.platform == 'Asset Tracker'

        def __repr__(self):
            return "Particle Device: {{name: {}, deviceID: {}, platform: {}}}".format(self.name, self.deviceID, self.platform)

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
                platform = device_info['platform'].split(', ')[0]
                name = None if device_info['name'] == '<no name>' else device_info['name']
                devices.append(self.DeviceInfo(name, device_info['deviceID'], platform))

            return devices

    def enter_dfu_mode(self, device='', all=False):
        args = ['particle', 'usb', 'dfu']
        if device:
            args.append(device)
        elif all:
            args.append('--all')
        result = self.run_shell_cmd(args)
        return result.strip().endswith("Done.")
