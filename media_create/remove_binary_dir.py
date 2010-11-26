#!/usr/bin/python

import sys
import os.path
import subprocess

def remove_binary_dir(binary_dir='binary/', as_root=True):
    if os.path.exists(binary_dir):
        if as_root:
            cmd = 'sudo '
        else:
            cmd = ''
        cmd += 'rm -rf %s' % binary_dir
        proc = subprocess.Popen(cmd, shell=True)
        proc.wait()
        return proc.returncode
    return 0

if __name__ == '__main__':
    sys.exit(remove_binary_dir())
