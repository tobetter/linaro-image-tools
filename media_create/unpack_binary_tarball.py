#!/usr/bin/python

import sys
import subprocess

def unpack_binary_tarball(tarball, as_root=True):
    args = []
    if as_root:
        args.extend(['sudo'])
    args.extend(['tar', '--numeric-owner', '-xf', tarball])    
    proc = subprocess.Popen(args)
    proc.wait()
    return proc.returncode

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print 'usage: ' + sys.argv[0] + ' <BINARY_TARBALL>'
        sys.exit(1)
    
    tarball = sys.argv[1]
    sys.exit(unpack_binary_tarball(tarball))
