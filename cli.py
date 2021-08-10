from cmd import Cmd
from littlefs import LittleFS, errors
import subprocess
import sys
import os
import shutil
from datetime import datetime
from ParticleUSB import ParticleUSB, ParticleDevice

try:
    import readline
except ImportError:
    readline = None

histfile = 'someconsole_history'
histfile_size = 1000

import logging
logging.basicConfig(filename='debug.log', level=logging.DEBUG)

LOCAL_PATH = os.path.dirname(os.path.realpath(__file__))
LOCAL_FILENAME = "temp.littlefs"

def run_shell_cmd(cmd, filter_str='', indent_char='\t'):
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    line_buffer = b''
    for c in iter(lambda: process.stdout.read(1), b''):
        line_buffer += c
        if c == b'\r' or c == b'\n':
            out_str = line_buffer.decode("utf-8")
            if filter_str and not out_str.startswith(filter_str):
                line_buffer = b''
                continue

            sys.stdout.write(indent_char)
            sys.stdout.write(out_str)
            line_buffer = b''

    process.wait()
    print()

def readFilesystem(filename: str, device: ParticleDevice):
    run_shell_cmd(['dfu-util',
                   '-d', f',{device.platform.vid:04x}:{device.platform.pid_dfu:04x}',
                   '-a', '2',
                   '-s', f'0x80000000:{device.platform.fs_size_bytes()}',
                   '-U', filename],
                  filter_str='Upload')

def writeFilesystem(filename: str, device: ParticleDevice):
    run_shell_cmd(['dfu-util',
                   '-d', f',{device.platform.vid:04x}:{device.platform.pid_dfu:04x}',
                   '-a', '2',
                   '-s', '0x80000000',
                   '-D', filename],
                  filter_str='Download')

def mount_fs(filename: str, block_size=4096):
    _fs = None

    if os.path.exists(filename):
        fs_file_size = os.path.getsize(filename)
        gen3_bytes = ParticleUSB.known_platforms['Argon'].fs_size_bytes()
        tracker_bytes = ParticleUSB.known_platforms['Asset Tracker'].fs_size_bytes()

        if fs_file_size == gen3_bytes:
            block_count = 512  # 2MB for Argon/Boron/BSoM (512 * 4096)
            print(f'\"{filename}\" mounted as 2MB (Argon/Boron/BSoM) filesystem')
        elif fs_file_size == tracker_bytes:
            block_count = 1024  # 4MB for Tracker (1024 * 4096)
            print(f'\"{filename}\" mounted as 4MB (Tracker) filesystem')
        else:
            print(f"Mount failed: file \"{filename}\" wrong size (expected {gen3_bytes}, {tracker_bytes}])")
            _fs = None
            return None

    # File does not exist
    else:
        print(f"Mount failed: file \"{filename}\" does not exist")
        _fs = None
        return None

    # Passed our checks - try mounting
    try:
        _fs = LittleFS(block_size=block_size, block_count=block_count, mount=False)
        with open(filename, 'rb') as fh:
            _fs.context.buffer = bytearray(fh.read())
        _fs.mount()
    except Exception as e:
        print(f"Failed to mount file \"{filename}\" with error: \"{e}\"")
        _fs = None
    finally:
        return _fs


def tree(_fs, root, prefix=''):
    # https://stackoverflow.com/questions/9727673/list-directory-tree-structure-in-python
    space = '    '
    branch = '│   '
    # pointers:
    tee = '├── '
    last = '└── '

    contents = list(_fs.scandir(root))
    pointers = [tee] * (len(contents) - 1) + [last]
    for pointer, path in zip(pointers, contents):
        yield prefix + pointer + path.name + ('/' if path.type == 34 else '')
        if path.type == 34: # extend the prefix and recurse:
            extension = branch if pointer == tee else space
            # i.e. space because last, └── , above so no more |
            yield from tree(_fs, root + '/' + path.name, prefix=prefix+extension)

def list_files(startpath):
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print(f'{subindent}{f}')

class LittleFSCLI(Cmd):

    mounted_prompt = "[{}] {}:{}$ "
    unmounted_prompt = "$ "
    prompt = unmounted_prompt

    intro = "Particle LittleFS Command Line Utility"

    fs = None
    fs_filename = ""
    cur_dir = '/'
    target_device = None

    def preloop(self):
        if readline and os.path.exists(histfile):
            readline.read_history_file(histfile)

    def postloop(self):
        if readline:
            readline.set_history_length(histfile_size)
            readline.write_history_file(histfile)

    def postcmd(self, stop: bool, line: str) -> bool:
        if self.target_device or self.fs:
            self.prompt = self.mounted_prompt.format(
                self.target_device.device_id if self.target_device else "<No Target>",
                self.fs_filename if self.fs else "<No FS>",
                self.cur_dir
            )
        else:
            self.prompt = self.unmounted_prompt

        return False  # continue execution

    def fs_autocomplete(self, text, line, start_index, end_index):
        search_dir = self.cur_dir
        # TODO: need to grab the last arg, rather than the first
        arg_start_idx = line.index(' ') + 1
        if start_index > arg_start_idx:
            search_dir += line[arg_start_idx:start_index]
        logging.debug(f"Tab completion: {{search_dir: {search_dir}}}")

        if text:
            results = [
                "{}{}".format(dir_item.name, "/" if dir_item.type == 34 else "")
                for dir_item in self.fs.scandir(search_dir)
                if dir_item.name.startswith(text)
            ]
        else:
            results = [
                "{}{}".format(dir_item.name, "/" if dir_item.type == 34 else "")
                for dir_item in self.fs.scandir(search_dir)
            ]

        logging.debug(f"fs_autocomplete(): {{search_text: {text}, line: {line}, search_dir: {search_dir}, start_index: {start_index}, end_index: {end_index}, results: {results}}}")
        return results

    def os_autocomplete(self, text, line, start_index, end_index):
        search_dir = LOCAL_PATH
        arg_start_idx = line.index(' ') + 1
        if start_index > arg_start_idx:
            search_dir += line[arg_start_idx:start_index]
        logging.debug(f"Tab completion: {{search_dir: {search_dir}}}")

        if text:
            results = [
                f"{dir_item.name}{'/' if dir_item.is_dir() else ''}"
                for dir_item in os.scandir(search_dir)
                if dir_item.name.startswith(text)
            ]
        else:
            results = [
                f"{dir_item.name}{'/' if dir_item.is_dir() else ''}"
                for dir_item in os.scandir(search_dir)
            ]

        logging.debug(f"os_autocomplete: {{search_text: {text}, line: {line}, search_dir: {search_dir}, start_index: {start_index}, end_index: {end_index}, results: {results}}}")
        return results

    def do_exit(self, inp):
        print("Bye")
        return True

    def help_exit(self):
        print('exit the application. Shorthand: x q Ctrl-D.')

    def do_dfu(self, inp=''):
        if self.target_device:
            print("Putting target device in DFU mode...")
            ParticleUSB.enter_dfu_mode(device=self.target_device.device_id)
        else:
            self.do_target()
            if self.target_device:
                self.do_dfu()

    def help_dfu(self):
        print("Put a device in DFU mode")

    def do_target(self, inp=''):
        devices = ParticleUSB.list_devices()
        if len(devices) > 1:
            for idx, device in enumerate(devices):
                print(f"{idx+1}. {device.platform}: {device.device_id}")
            while True:
                try:
                    choice = int(input("Which device do you want to target? "))
                    if choice in range(1, len(devices) + 1):
                        self.target_device = devices[choice - 1]

                except ValueError:
                    print("Invalid choice")
                    continue

        elif len(devices) == 1:
            self.target_device = devices[0]

        else:
            self.target_device = None

        if self.target_device:
            if not self.target_device.is_gen3() and not self.target_device.is_tracker():
                print("This utility only works with Asset Tracker and Gen 3 devices")
                self.target_device = None
            else:
                print(f"Selected device: {{name:\"{self.target_device.name}\", platform:\"{self.target_device.platform.name}\", id:\"{self.target_device.device_id}\"}}")
        else:
            print("No devices found!")

    def help_target(self):
        print("Set target Particle device")

    def do_fsread(self, inp=''):
        if not self.target_device:
            self.do_target()

        if self.target_device:
            self.do_dfu()
            # ParticleUSB.enter_dfu_mode(device=self.target_device.device_id)

            if os.path.exists(LOCAL_FILENAME):
                # print("Deleting existing local filesystem copy")
                os.remove(LOCAL_FILENAME)

            print("Creating local copy of device filesystem...")
            print()
            readFilesystem(LOCAL_FILENAME, self.target_device)

            print(f"Wrote filesystem to local temporary file: \"{LOCAL_FILENAME}\". Use \'mount\' to mount it\n")

    def help_fsread(self):
        print("Make a local copy of a device's embedded filesystem")

    # TODO: Add filename argument
    # TODO: Add --nobackup flag to skip read & backup
    def do_fswrite(self, inp=''):
        if not self.target_device:
            self.do_target()

        if self.target_device:
            if os.path.exists(LOCAL_FILENAME):
                # TODO: Add some sanity checking here - file size since we know it, maybe try to mount it first?
                self.do_dfu()

                backup_fn = f"{self.target_device.device_id}-{datetime.now().strftime('%Y.%m.%d-%H.%M.%S')}.littlefs"
                print("Backing up existing filesystem...")
                readFilesystem("backups/" + backup_fn, self.target_device)
                print(f"Device filesystem backed up to \"{backup_fn}\"")
                print()

                print(f"Writing local filesystem \"{LOCAL_FILENAME}\" to device...")
                print("NOTE: Ignore warnings about DFU Suffix being incorrect!")
                print()
                writeFilesystem(LOCAL_FILENAME, self.target_device)
                print("Wrote new filesystem to device")
            else:
                print("No local filesystem copy exists to write! Use \'fsread\' first.")

    def help_fswrite(self):
        print("Write local filesystem to device")

    # TODO: Add "write backup" function which allows you to select a backup image from the backups/ folder and write it
    def do_fsrestore(self, inp=''):
        print("Available backup images:")
        for file in os.listdir("backups/"):
            print("\t" + file)

    def help_fsrestore(self):
        print("Unimplemented")

    def do_save(self, inp=''):
        if self.fs:
            if inp:
                if inp.find('~') != -1:
                    save_path = os.path.expanduser(inp)
                else:
                    save_path = LOCAL_PATH + '/' + inp
                if os.path.exists(os.path.dirname(save_path)):
                    if os.path.exists(save_path):
                        confirm = input("File already exists, overwrite? [Y/n] ")
                        if confirm.lower() != 'y':
                            return

                    # Do the copy
                    try:
                        shutil.copy(LOCAL_PATH + '/' + LOCAL_FILENAME, save_path)
                        print(f"Saved filesystem copy to \"{save_path}\"")
                    except Exception as e:
                        print("Error copying file: {}".format(e))
                else:
                    print(f"Error: \"{save_path}\" is not a valid path")
            else:
                print("Error: No path supplied. Usage is \'save <path>\'")
        else:
            print("No filesystem mounted! Use \'mount\' to mount one.")
            return

    def complete_save(self, text, line, start_index, end_index):
        return self.os_autocomplete(text, line, start_index, end_index)

    def help_save(self):
        print("Save a copy of the temporary filesystem read out from a device. Usage: \'save <path>\'")

    def do_mount(self, inp=''):
        self.fs = None
        self.fs_filename = inp if inp else LOCAL_FILENAME
        self.cur_dir = '/'
        try:
            self.fs = mount_fs(self.fs_filename)
        except FileNotFoundError as e:
            print(f"mount: {self.fs_filename}: Not a file")
        except errors.LittleFSError as e:
            print(e)

    def complete_mount(self, text, line, start_index, end_index):
        return self.os_autocomplete(text, line, start_index, end_index)

    def help_mount(self):
        print("Mount local copy of device filesystem")

    def do_unmount(self, inp=''):
        if self.fs:
            out_file = inp if inp else self.fs_filename
            with open(out_file, 'wb') as fh:
                fh.write(self.fs.context.buffer)
            print(f"Wrote filesystem to file: \"{out_file}\"")
            self.fs = None
            self.cur_dir = '/'
        else:
            print("No filesystem mounted!")

    def help_unmount(self):
        print("Unmount local copy of device filesystem")

    def do_sync(self, inp=''):
        if self.fs:
            with open(self.fs_filename, 'wb') as fh:
                fh.write(self.fs.context.buffer)
            print(f"Wrote filesystem to file: \"{LOCAL_FILENAME}\"")
        else:
            print("No filesystem mounted!")

    def help_sync(self):
        print("Save in-memory filesystem changes to file")

    def do_tree(self, inp=''):
        if self.fs:
            path = inp if inp else self.cur_dir
            try:
                self.fs.stat(path)
            except errors.LittleFSError as e:
                if e.name == "ERR_NOENT":
                    print(f"tree: {path}: Not a directory")
                else:
                    print(e)
                return
            print(path)
            for line in tree(self.fs, path):
                print(line)
        else:
            print("No filesystem mounted!")

    def complete_tree(self, text, line, start_index, end_index):
        return self.fs_autocomplete(text, line, start_index, end_index)

    def help_tree(self):
        print("Print a filesystem tree")

    def do_ls(self, inp=''):
        if self.fs:
            ls_path = inp if inp else self.cur_dir
            try:
                for dir_item in self.fs.scandir(ls_path):
                    print(f"{'d' if dir_item.type == 34 else '-'} {dir_item.size:>8} {dir_item.name}")
            except errors.LittleFSError as e:
                if e.name == "ERR_NOENT":
                    print(f"ls: {ls_path}: No such file or directory")
                elif e.name == "ERR_NOTDIR":
                    print(f"ls: {ls_path}: Not a directory")
                else:
                    print(e)
        else:
            print("No filesystem mounted!")

    def complete_ls(self, text, line, start_index, end_index):
        return self.fs_autocomplete(text, line, start_index, end_index)

    def do_cat(self, inp=''):
        if self.fs:
            size = 0
            try:
                stat = self.fs.stat(inp)
                if stat.type == 34:
                    print(f"cat: {inp}: Is a directory")
                    return
                size = stat.size
                # print("Size of {}: {} bytes".format(inp, size))
            except errors.LittleFSError as e:
                if e.name == "ERR_NOENT":
                    print(f"ls: {inp}: No such file or directory")
                else:
                    print(e)
                return

            try:
                with self.fs.open(inp, 'r') as fh:
                    file = fh.read(size)
                    try:
                        print(file.decode('utf-8'))
                    except UnicodeDecodeError as e:
                        print(file)
            except errors.LittleFSError as e:
                print(e)
        else:
            print("No filesystem mounted!")

    def complete_cat(self, text, line, start_index, end_index):
        return self.fs_autocomplete(text, line, start_index, end_index)

    def do_rm(self, inp=''):
        if self.fs:
            try:
                self.fs.remove(inp)
            except errors.LittleFSError as e:
                if e.name == "ERR_NOENT":
                    print(f"ls: {inp}: No such file or directory")
                elif e.name == "ERR_NOTEMPTY":
                    print(f"ls: {inp}: Directory not empty")
                else:
                    print(e)
                return

        else:
            print("No filesystem mounted!")

    def complete_rm(self, text, line, start_index, end_index):
        return self.fs_autocomplete(text, line, start_index, end_index)

    # TODO: cd
    def do_cd(self, inp):
        if self.fs:
            # Absolute path supplied
            if inp.startswith('/'):
                new_path = inp

            # Relative path
            else:
                inp_split = inp.split('/')
                cur_dir_split = self.cur_dir.split('/')

                for cd_dir in inp_split:
                    if cd_dir == '..':
                        if len(cur_dir_split) > 1:
                            cur_dir_split.pop()
                        else:
                            print(f"cd: {inp}: No such file or directory")
                            return
                    else:
                        cur_dir_split.append(cd_dir)

                new_path = '/' + '/'.join(filter(None, cur_dir_split))

            try:
                new_path_stat = self.fs.stat(new_path)
                if new_path_stat.type == 34:
                    self.cur_dir = new_path
                else:
                    print(f"cd: {new_path}: Not a directory")
            except errors.LittleFSError as e:
                if e.name == "ERR_NOENT":
                    print(f"cd: {new_path}: No such file or directory")
                else:
                    print(f"cd: {new_path}: Error: {e}")

            # print("New Directory: \"{}\"".format(self.cur_dir))
        else:
            print("No filesystem mounted!")

    def complete_cd(self, text, line, start_index, end_index):
        return self.fs_autocomplete(text, line, start_index, end_index)

    def do_mkdir(self, inp=''):
        if self.fs:
            if inp:
                dir_to_make = self.cur_dir + '/' + inp
                try:
                    self.fs.mkdir(dir_to_make)
                except FileExistsError as e:
                    print(f"mkdir: {dir_to_make}: Directory exists")
                except errors.LittleFSError as e:
                    print(e)
            else:
                print("usage: mkdir [directory]")
        else:
            print("No filesystem mounted!")

    def complete_mkdir(self, text, line, start_index, end_index):
        return self.fs_autocomplete(text, line, start_index, end_index)

    def do_cp(self, inp=''):
        if self.fs:
            paths = inp.split(" ")
            if len(paths) == 2:
                try:
                    from_file_stat = self.fs.stat(paths[0])
                    if from_file_stat.type == 34:
                        raise errors.LittleFSError(code=-21)    # Cannot copy directories, raise ERR_ISDIR
                    with self.fs.open(paths[0], 'rb') as from_file:
                        try:
                            with self.fs.open(paths[1], 'wb') as to_file:
                                to_file.write(from_file.read(from_file_stat.size))
                            print("Copied {} bytes from {} to {}".format(from_file_stat.size, paths[0], paths[1]))
                        except errors.LittleFSError as e:
                            if e.name == "ERR_NOENT":
                                print(f"cp: {paths[1]}: No file or directory")
                            elif e.name == "ERR_ISDIR":
                                print(f"cp: {paths[1]}: Is a directory")
                            else:
                                print(f"cp: {paths[1]}: Error: {e}")
                except errors.LittleFSError as e:
                    if e.name == "ERR_ISDIR":
                        print(f"cp: {paths[0]}: Is a directory")
                    elif e.name == "ERR_NOENT":
                        print(f"cp: {paths[0]}: No file or directory")
                    else:
                        print(f"cp: {paths[0]}: {e}")

            else:
                print("usage: cp [path_from] [path_to]")
        else:
            print("No filesystem mounted!")

    def complete_cp(self, text, line, start_index, end_index):
        return self.fs_autocomplete(text, line, start_index, end_index)

    def do_insert(self, inp=''):
        if self.fs:
            paths = inp.split(" ")
            if len(paths) == 2:
                try:
                    # Does the target file already exist? If so,
                    try:
                        self.fs.stat(paths[1])
                        print(f"insert: {paths[1]}: Target file already exists")
                        return
                    except errors.LittleFSError as e:
                        if e.name != "ERR_NOENT":
                            raise e;
                    # dir_path = os.path.dirname(os.path.realpath(__file__))
                    # file_path = dir_path + '/' + paths[0]
                    size = os.stat(paths[0]).st_size
                    with open(paths[0], 'rb') as from_file:
                        try:
                            with self.fs.open(paths[1], 'wb') as to_file:
                                for chunk in iter((lambda: from_file.read(256)), b''):
                                    to_file.write(chunk)
                            print(f"Copied {size} bytes: local:{os.path.realpath(from_file.name)} > littlefs:{paths[1]}")
                        except errors.LittleFSError as e:
                            if e.name == "ERR_NOENT":
                                print(f"insert: {paths[1]}: Path does not exist — do you need to mkdir?")
                            elif e.name == "ERR_ISDIR":
                                print(f"insert: {paths[1]}: Is a directory")
                            else:
                                print(f"insert: {paths[1]}: Error: {e}")
                except errors.LittleFSError as e:
                    if e.name == "ERR_ISDIR":
                        print(f"insert: {paths[0]}: Is a directory")
                    else:
                        print(f"insert: {paths[0]}: {e}")
                except FileNotFoundError as e:
                    print(f"insert: {paths[0]}: Not a file")

            else:
                print("usage: cp [local_path] [path_to]")
        else:
            print("No filesystem mounted!")

    def help_insert(self):
        print("Insert a file from your computer into the LittleFS filesystem")

    def do_extract(self, inp=''):
        if self.fs:
            paths = inp.split(" ")
            if len(paths) == 2:
                try:
                    # Open source file
                    size = self.fs.stat(paths[0]).size
                    with self.fs.open(paths[0], 'rb') as from_file:
                        try:
                            # Open destination file
                            if os.path.exists(paths[1]):
                                raise FileExistsError
                            with open(paths[1], 'wb') as to_file:
                                for chunk in iter((lambda: from_file.read(256)), b''):
                                    to_file.write(chunk)
                                print(f"Copied {size} bytes: littlefs:{paths[0]} > local:{os.path.realpath(to_file.name)}")
                        except errors.LittleFSError as e:
                            if e.name == "ERR_NOENT":
                                print(f"insert: {paths[1]}: Not a file")
                            elif e.name == "ERR_ISDIR":
                                print(f"insert: {paths[1]}: Is a directory")
                            else:
                                print(f"insert: {paths[1]}: Error: {e}")
                        except FileExistsError:
                            print(f"insert: {paths[1]}: Destination file exists")
                except errors.LittleFSError as e:
                    if e.name == "ERR_ISDIR":
                        print(f"insert: {paths[0]}: Is a directory")
                    else:
                        print(f"insert: {paths[0]}: {e}")
                except FileNotFoundError as e:
                    print(f"insert: {paths[0]}: Not a file")

            else:
                print("usage: cp [local_path] [path_to]")
        else:
            print("No filesystem mounted!")

    def help_extract(self):
        print("Extract a file from the LittleFS filesystem to your computer")

    def default(self, inp=''):
        if inp == 'x' or inp == 'q':
            return self.do_exit(inp)

        print(f"Unknown Command: \"{inp}\"")

    do_EOF = do_exit
    help_EOF = help_exit


if __name__ == '__main__':
    LittleFSCLI().cmdloop()
