#!/usr/bin/python

import sys
import os.path
import subprocess

def remove_binary_dir(binary_dir='binary/', as_root=True):
    if os.path.exists(binary_dir):
        args = []
        if as_root:
            args.extend('sudo')
        args.extend(['rm', '-rf', binary_dir])
        proc = subprocess.Popen(args)
        proc.wait()
        return proc.returncode
    return 0

if __name__ == '__main__':
    sys.exit(remove_binary_dir())
