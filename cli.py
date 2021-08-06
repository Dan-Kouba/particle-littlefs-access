from cmd import Cmd
from littlefs import LittleFS, errors
import subprocess
import sys
import os
from datetime import datetime
from ParticleUSB import ParticleUSB, ParticleDevice

LOCAL_FILENAME = "temp.littlefs"

def run_shell_cmd(cmd):
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    sys.stdout.buffer.write(b'\t')
    for c in iter(lambda: process.stdout.read(1), b''):
        sys.stdout.buffer.write(c)
        if c == b'\n' or c == b'\r':
            sys.stdout.buffer.write(b'\t')
    process.wait()
    print()

def readFilesystem(filename: str, device: ParticleDevice):
    run_shell_cmd(['dfu-util', '-d', ',{vid:04x}:{pid:04x}'.format(
        vid=device.platform.vid, pid=device.platform.pid_dfu
    ), '-a', '2', '-s', '0x80000000:{bytes}'.format(
        bytes=device.platform.fs_block_size * device.platform.user_block_count
    ), '-U', filename])

def writeFilesystem(filename: str, device: ParticleDevice):
    run_shell_cmd(['dfu-util', '-d', ',{vid:04x}:{pid:04x}'.format(
        vid=device.platform.vid, pid=device.platform.pid_dfu
    ), '-a', '2', '-s', '0x80000000', '-D', filename])

def mount_fs(filename: str, block_size=4096):
    block_count = 0

    if os.path.exists(filename):
        fs_file_size = os.path.getsize(filename)
        if fs_file_size == 2097152:
            block_count = 512  # 2MB for Argon/Boron/BSoM (512 * 4096)
            print('\"{}\" mounted as 2MB (Argon/Boron/BSoM) filesystem'.format(filename))
        elif fs_file_size == 4194304:
            block_count = 1024  # 4MB for Tracker (1024 * 4096)
            print('\"{}\" mounted as 4MB (Tracker) filesystem'.format(filename))
        else:
            print("Mount failed: file \"{}\" wrong size (expected [2097152, 4194304])".format(filename))
            _fs = None
            return _fs

    # File does not exist
    else:
        print("Mount failed: file \"{}\" does not exist".format(filename))
        _fs = None
        return _fs

    # Passed our checks — try mounting
    try:
        _fs = LittleFS(block_size=block_size, block_count=block_count, mount=False)
        with open(filename, 'rb') as fh:
            _fs.context.buffer = bytearray(fh.read())
        _fs.mount()
    except Exception as e:
        print("Failed to mount file \"{}\" with error: \"{}\"".format(filename, e))
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
        print('{}{}/'.format(indent, os.path.basename(root)))
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print('{}{}'.format(subindent, f))

class LittleFSCLI(Cmd):
    prompt = 'lfs> '
    mounted_prompt = "[{} | {}] lfs> "
    unmounted_prompt = "lfs> "

    intro = "Particle LittleFS Command Line Utility"

    fs = None
    local_file = "copy.littlefs"
    fs_filename = ""
    cur_dir = '/'
    target_device = None

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
                print("{}. {}: {}".format(idx + 1, device.platform, device.device_id))
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
                print("Selected device: {{name:\"{}\", platform:\"{}\", id:\"{}\"}}".format(
                    self.target_device.name, self.target_device.platform.name, self.target_device.device_id
                ))
        else:
            print("No devices found!")

        if self.target_device or self.fs:
            self.prompt = self.mounted_prompt.format(
                self.target_device.device_id if self.target_device else "<No Target>",
                self.fs_filename if self.fs else "<No FS>"
            )
        else:
            self.prompt = self.unmounted_prompt

    def do_fsread(self, inp=''):
        if not self.target_device:
            self.do_target()

        self.do_dfu()
        # ParticleUSB.enter_dfu_mode(device=self.target_device.device_id)

        if os.path.exists(LOCAL_FILENAME):
            # print("Deleting existing local filesystem copy")
            os.remove(LOCAL_FILENAME)

        print("Creating local copy of device filesystem...")
        print()
        readFilesystem(LOCAL_FILENAME, self.target_device)

        print("Wrote filesystem to local temporary file: \"{}\". Use \'mount\' to mount it\n".format(LOCAL_FILENAME))

    def help_fsread(self):
        print("Make a local copy of a device's embedded filesystem. Device must be in DFU mode.")

    # TODO: Add filename argument
    # TODO: Add --nobackup flag to skip read & backup
    def do_fswrite(self, inp=''):
        if not self.target_device:
            self.do_target()

        if os.path.exists(LOCAL_FILENAME):
            # TODO: Add some sanity checking here - file size since we know it, maybe try to mount it first?
            self.do_dfu()

            backup_fn = "backup_{}.littlefs".format(datetime.now().strftime("%Y_%m_%d-%I_%M_%S_%p"))
            print("Backing up existing filesystem...")
            readFilesystem("backups/" + backup_fn, self.target_device)
            print("Device filesystem backed up to \"{}\"".format(backup_fn))
            print()

            print("Writing local filesystem \"{}\" to device...".format(LOCAL_FILENAME))
            print("NOTE: Ignore warnings about DFU Suffix being incorrect!")
            print()
            writeFilesystem(LOCAL_FILENAME, self.target_device)
            print("Wrote new filesystem to device")
        else:
            print("No local filesystem copy exists to write! Use fsread first.")

    # TODO: Add "write backup" function which allows you to select a backup image from the backups/ folder and write it
    def do_restorefs(self, inp=''):
        print("Available backup images:")
        for file in os.listdir("backups/"):
            print("\t" + file)

    def do_mount(self, inp=''):
        self.fs = None
        self.fs_filename = inp if inp else LOCAL_FILENAME
        try:
            self.fs = mount_fs(self.fs_filename)
        except FileNotFoundError as e:
            print("mount: {}: Not a file".format(self.fs_filename))
        except errors.LittleFSError as e:
            print(e)
        finally:
            if self.target_device or self.fs:
                self.prompt = self.mounted_prompt.format(
                    self.target_device.device_id if self.target_device else "<No Target>",
                    self.fs_filename if self.fs else "<No FS>"
                )
            else:
                self.prompt = self.unmounted_prompt

    def help_mount(self):
        print("Mount local copy of device filesystem")

    def do_unmount(self, inp=''):
        if self.fs:
            out_file = inp if inp else self.fs_filename
            with open(out_file, 'wb') as fh:
                fh.write(self.fs.context.buffer)
            print("Wrote filesystem to file: \"{}\"".format(out_file))
            self.fs = None
            self.target_device = None
        else:
            print("No filesystem mounted!")

        if self.target_device or self.fs:
            self.prompt = self.mounted_prompt.format(
                self.target_device.device_id if self.target_device else "<No Target>",
                self.fs_filename if self.fs else "<No FS>"
            )
        else:
            self.prompt = self.unmounted_prompt

    def do_sync(self, inp=''):
        if self.fs:
            with open(self.fs_filename, 'wb') as fh:
                fh.write(self.fs.context.buffer)
            print("Wrote filesystem to file: \"{}\"".format(LOCAL_FILENAME))
        else:
            print("No filesystem mounted!")

    def do_tree(self, inp=''):
        if self.fs:
            path = inp if inp else self.cur_dir
            try:
                self.fs.stat(path)
            except errors.LittleFSError as e:
                if e.name == "ERR_NOENT":
                    print("tree: {}: Not a directory".format(path))
                else:
                    print(e)
                return
            print(path)
            for line in tree(self.fs, path):
                print(line)
        else:
            print("No filesystem mounted!")

    def do_ls(self, inp=''):
        if self.fs:
            ls_path = inp if inp else self.cur_dir
            try:
                for dir_item in self.fs.scandir(ls_path):
                    print("{} {:>8} {}".format("d" if dir_item.type == 34 else "-", dir_item.size, dir_item.name))
            except errors.LittleFSError as e:
                if e.name == "ERR_NOENT":
                    print("ls: {}: No such file or directory".format(ls_path))
                elif e.name == "ERR_NOTDIR":
                    print("ls: {}: Not a directory".format(ls_path))
                else:
                    print(e)
        else:
            print("No filesystem mounted!")

    def do_cat(self, inp=''):
        if self.fs:
            size = 0
            try:
                stat = self.fs.stat(inp)
                if stat.type == 34:
                    print("cat: {}: Is a directory")
                    return
                size = stat.size
                # print("Size of {}: {} bytes".format(inp, size))
            except errors.LittleFSError as e:
                if e.name == "ERR_NOENT":
                    print("ls: {}: No such file or directory".format(inp))
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

    def do_rm(self, inp=''):
        if self.fs:
            try:
                self.fs.remove(inp)
            except errors.LittleFSError as e:
                if e.name == "ERR_NOENT":
                    print("ls: {}: No such file or directory".format(inp))
                elif e.name == "ERR_NOTEMPTY":
                    print("ls: {}: Directory not empty".format(inp))
                else:
                    print(e)
                return

        else:
            print("No filesystem mounted!")

    # TODO: cd
    # def do_cd(self, inp):
    #     if self.fs:
    #         pass
    #     else:
    #         print("No filesystem mounted!")

    def do_mkdir(self, inp=''):
        if self.fs:
            if inp:
                try:
                    self.fs.mkdir(inp)
                except FileExistsError as e:
                    print("mkdir: {}: Directory exists".format(inp))
                except errors.LittleFSError as e:
                    print(e)
            else:
                print("usage: mkdir [directory]")
        else:
            print("No filesystem mounted!")

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
                                print("cp: {}: No file or directory".format(paths[1]))
                            elif e.name == "ERR_ISDIR":
                                print("cp: {}: Is a directory".format(paths[1]))
                            else:
                                print("cp: {}: Error: {}".format(paths[1], e))
                except errors.LittleFSError as e:
                    if e.name == "ERR_ISDIR":
                        print("cp: {}: Is a directory".format(paths[0]))
                    elif e.name == "ERR_NOENT":
                        print("cp: {}: No file or directory".format(paths[0]))
                    else:
                        print("cp: {}: {}".format(paths[0], e))

            else:
                print("usage: cp [path_from] [path_to]")
        else:
            print("No filesystem mounted!")

    def do_insert(self, inp=''):
        if self.fs:
            paths = inp.split(" ")
            if len(paths) == 2:
                try:
                    # Does the target file already exist? If so,
                    try:
                        self.fs.stat(paths[1])
                        print("insert: {}: Target file already exists".format(paths[1]))
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
                            print("Copied {} bytes: local:{} > littlefs:{}".format(size, os.path.realpath(from_file.name), paths[1]))
                        except errors.LittleFSError as e:
                            if e.name == "ERR_NOENT":
                                print("insert: {}: Path does not exist — do you need to mkdir?".format(paths[1]))
                            elif e.name == "ERR_ISDIR":
                                print("insert: {}: Is a directory".format(paths[1]))
                            else:
                                print("insert: {}: Error: {}".format(paths[1], e))
                except errors.LittleFSError as e:
                    if e.name == "ERR_ISDIR":
                        print("insert: {}: Is a directory".format(paths[0]))
                    else:
                        print("insert: {}: {}".format(paths[0], e))
                except FileNotFoundError as e:
                    print("insert: {}: Not a file".format(paths[0]))

            else:
                print("usage: cp [local_path] [path_to]")
        else:
            print("No filesystem mounted!")

    # TODO: extract
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
                                print("Copied {} bytes: littlefs:{} > local:{}".format(size, paths[0], os.path.realpath(to_file.name)))
                        except errors.LittleFSError as e:
                            if e.name == "ERR_NOENT":
                                print("insert: {}: Not a file".format(paths[1]))
                            elif e.name == "ERR_ISDIR":
                                print("insert: {}: Is a directory".format(paths[1]))
                            else:
                                print("insert: {}: Error: {}".format(paths[1], e))
                        except FileExistsError:
                            print("insert: {}: Destination file exists".format(paths[1]))
                except errors.LittleFSError as e:
                    if e.name == "ERR_ISDIR":
                        print("insert: {}: Is a directory".format(paths[0]))
                    else:
                        print("insert: {}: {}".format(paths[0], e))
                except FileNotFoundError as e:
                    print("insert: {}: Not a file".format(paths[0]))

            else:
                print("usage: cp [local_path] [path_to]")
        else:
            print("No filesystem mounted!")

    def default(self, inp=''):
        if inp == 'x' or inp == 'q':
            return self.do_exit(inp)

        print("Default: {}".format(inp))

    do_EOF = do_exit
    help_EOF = help_exit


if __name__ == '__main__':
    LittleFSCLI().cmdloop()