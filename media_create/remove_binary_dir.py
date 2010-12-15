import sys
import os.path

from media_create import cmd_runner


def remove_binary_dir(binary_dir='binary/', as_root=True):
    if os.path.exists(binary_dir):
        proc = cmd_runner.run(
            ['rm', '-rf', binary_dir], as_root=as_root)
        proc.wait()
        return proc.returncode
    return 0

if __name__ == '__main__':
    sys.exit(remove_binary_dir())
