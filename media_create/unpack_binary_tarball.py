#!/usr/bin/python

import sys
import subprocess

def unpack_binary_tarball(tarball, as_root=True):
    if as_root:
        cmd = 'sudo '
    else:
        cmd = ''
    cmd += 'tar --numeric-owner -xf %s' % tarball
    proc = subprocess.Popen(cmd, shell=True)
    proc.wait()
    return proc.returncode

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print 'usage: ' + sys.argv[0] + ' <BINARY_TARBALL>'
        sys.exit(1)
    
    tarball = sys.argv[1]
    sys.exit(unpack_binary_tarball(tarball))
