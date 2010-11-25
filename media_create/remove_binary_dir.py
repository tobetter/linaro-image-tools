#!/usr/bin/python

import sys
import os.path
import subprocess

BINARY_DIR = 'binary/'

def remove_binary_dir(as_root=True):
    if os.path.exists(BINARY_DIR):
        if as_root:
            cmd = 'sudo '
        else:
            cmd = ''
        cmd += 'sudo rm -rf %s' % BINARY_DIR
        proc = subprocess.Popen(cmd, shell=True)
        proc.wait()
        return proc.returncode
    return 0

if __name__ == '__main__':
    sys.exit(remove_binary_dir())
