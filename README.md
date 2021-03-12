# particle-littlefs-access

## Setup
### littlefs-python
These instructions are from the main littlefs-python repo, but modified for our custom branch that supports the older LittleFS version DeviceOS uses (1.7.2)

Start by checking out the source repository of littlefs-python:

```
git clone https://github.com/Dan-Kouba/littlefs-python
```

The source code for littlefs is included as a submodule which must be checked out after the clone:

```
cd <littlefs-python>
git submodule update --init
```

This ensures that the correct version of littlefs is cloned into the littlefs folder. As a next step install the dependencies and install the package:

```
pip install -r requirements.txt
pip install -e .
```

**Note**: It's highly recommended to install the package in a virtual environment!

### CLI Interface
Just run `python cli.py`

## Usage
NOTE: For now, this utility only supports Tracker One. Support for Gen 3 products will be released in a future commit.

### The Basics
1. Connect a Tracker One to your computer via USB
2. Run `fsread`, which will put the device in DFU mode and create a local copy of the embedded filesystem
3. Mount the filesystem with `mount` (by default it will mount the local copy)
4. Browse around the filesystem using `tree` and `ls`. You can also `mkdir` and `cp` files
5. Copy a local file from your computer to the filesystem using `insert`. Pull a file from the filesystem to your computer using `extract`
6. All changes to the filesystem are done in memory. Write out the final copy after your changes using `sync` or completely unmount the filesystem with `unmount`
7. Write your filesystem to the device using `fswrite`. This command automatically reads out a copy of the existing filesystem, and stores it in the `backups/` folder, in case you need it. Afterwards it copies your new filesystem to the device.

## CLI Commands
| Command | Description         |
|:--------|:--------------------|
| `dfu`   | Put a connected Particle device in DFU mode. This is handled automatically by other commands that require it, and usually is not required on its own.|
| `fsread`   | Copy filesystem from a Particle device to your computer. This command automatically puts the device in DFU mode.
| `fswrite`  | Writes a local filesystem to a Particle device. Backs up the existing filesystem to the `backups/` folder before writing. |
| `mount [littlefs_filesystem]` | Mounts a local LittleFS filesystem from a file. If no argument is supplied it uses the filesystem created by `fswrite` (`copy.littlefs`) |
| `unmount [destination]` | Unmounts mounted LittleFS filesystem, writing it to the optional `[destination]`file supplied. Otherwise it writes back to file originally supplied to `mount` |
| `sync [destination]` | Write changes to the in-memory filesystem to the file `[destination]` without unmounting. Otherwise it writes back to file originally supplied to `mount` |
| `tree [path]` | Print out a file tree for `[path]` if supplied, otherwise for the current directory |
| `ls [path]` | Lists files and directories in `[path]`, or in the current directory. Includes a `d` prefix for directories, and file size |
| `cat file` | Dump the contents of `file` to the command line. Binary files are dumped as a Python bytes string |
| `rm file_or_directory` | Removes `file_or_directory`. Directories are only removed if empty. Does not support wildcards. |
| `mkdir directory` | Create directory `directory` |
| `cp from_file to_file` | Copy `from_file` to `to_file`. Does not create paths for `to_file`. |
| `insert local_file to_file` | Copy `local_file` from your computer into `to_file` in the filesystem. Only copies files, not directories |
| `extract from_file local_file` | Copy `from_file` out of the filesystem to `local_file` on your computer. Only copies files, not directories |



