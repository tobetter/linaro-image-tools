import sys

from media_create import cmd_runner


def unpack_binary_tarball(tarball, as_root=True):
    proc = cmd_runner.run(
        ['tar', '--numeric-owner', '-xf', tarball], as_root=as_root)
    proc.wait()
    return proc.returncode


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print 'usage: ' + sys.argv[0] + ' <BINARY_TARBALL>'
        sys.exit(1)
    
    tarball = sys.argv[1]
    sys.exit(unpack_binary_tarball(tarball))
