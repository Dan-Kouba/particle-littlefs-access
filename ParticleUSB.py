import subprocess
import sys
from parse import parse


class ParticlePlatform:
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

    def fs_size_bytes(self):
        return self.fs_block_size * self.user_block_count

    def is_gen3(self):
        return self.id > 10

    def is_tracker(self):
        return self.id == 26

    def __repr__(self):
        return "ParticleUSB.Platform: [name: {}, id: {}, vid: 0x{:04X}, pid_cdc: 0x{:04X}, pid_dfu: 0x{:04X}, user_block_count: {}, fs_block_size: {}]".format(
            self.name, self.id, self.vid, self.pid_cdc, self.pid_dfu, self.user_block_count, self.fs_block_size
        )


class ParticleDevice:
    def __init__(self, name: str, device_id: str, platform):
        self.name = name
        self.device_id = device_id
        self.platform = platform

    def is_gen3(self):
        return self.platform.is_gen3()

    def is_tracker(self):
        return self.platform.is_tracker()

    def __repr__(self):
        return "Particle Device: {{name: {}, deviceID: {}, {}}}".format(self.name, self.device_id, self.platform)


class ParticleUSB:
    known_platforms = {
        'default': ParticlePlatform(),
        'Photon': ParticlePlatform('photon', 6),
        'P1': ParticlePlatform('p1', 8),
        'Electron': ParticlePlatform('electron', 10),
        'Argon': ParticlePlatform('argon', 12, user_block_count=512),
        'Boron': ParticlePlatform('boron', 13, user_block_count=512),
        'A SoM': ParticlePlatform('asom', 22, user_block_count=512),
        'B SoM': ParticlePlatform('bsom', 23, user_block_count=512),
        'B5 SoM': ParticlePlatform('b5som', 25, user_block_count=512),
        'Asset Tracker': ParticlePlatform('tracker', 26, user_block_count=1024),
    }

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

    @staticmethod
    def list_devices(platform=''):
        args = ['particle', 'usb', 'list']
        if platform and platform in ParticleUSB.known_platforms:
            args.append(platform)
        result = ParticleUSB.run_shell_cmd(args)
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
                platform = ParticleUSB.known_platforms[platform_str] if platform_str in ParticleUSB.known_platforms \
                    else ParticleUSB.known_platforms['default']
                devices.append(ParticleDevice(name, device_info['deviceID'], platform))

            # print(devices)
            return devices

    @staticmethod
    def enter_dfu_mode(device='', all=False):
        args = ['particle', 'usb', 'dfu']
        if device:
            args.append(device)
        elif all:
            args.append('--all')
        result = ParticleUSB.run_shell_cmd(args)
        return result.strip().endswith("Done.")
