import os
import re
import sys
import subprocess


def _run_proc(args, last_arg, env, stdin=None):
    p = subprocess.Popen(args, env=env, stdin=stdin ,stdout=subprocess.PIPE)
    if last_arg:
        return p.communicate()[0]
    else:
        return p.stdout


def _exec_fdisk_and_grep(as_root, env, grep_str, extra_cmd=None):
    args = []
    if as_root:
        args.extend(['sudo'])
    args.extend(['fdisk', '-l', '2>/dev/null'])
    pipe = _run_proc(args, False, env)
    if extra_cmd is None:
        return _run_proc(['grep', '%s' % grep_str, '--color=never'], True,
            env, stdin=pipe)
    else:
        pipe = _run_proc(['grep', '%s' % grep_str], False, env,
            stdin=pipe)
        return _run_proc(extra_cmd, True, env, stdin=pipe)


def _find_device(as_root, device, env):
    return _exec_fdisk_and_grep(as_root, env, '\"Disk %s\"' % device,
        extra_cmd=['awk', '{print $2}'])


def _print_fdisk_dev(as_root, env):
    sys.stdout.write('\nfdisk -l:\n')
    _exec_fdisk_and_grep(as_root, env, '\"Disk /dev/\"')


def _print_mounted_devices():
    mount_file = '/etc/mtab'
    sys.stdout.write('\nmount:\n')
    try:
        with open(mount_file) as f:
            for line in f:
                if re.match('/dev/', line) is not None:
                    sys.stdout.write(line)
    except IOError:
        sys.stdout.write('IOError: cannot read %s\n' % mount_file)


def _select_device(device):
    resp = raw_input('Are you 100% sure, on selecting [%s] (y/n)? ' % device)
    if resp.lower() != 'y':
        return False
    return True


def _get_extended_env(ext):
    return os.environ.update(ext)


def check_device(device, as_root=True):
    """ Checks that a selected device exists.

    :param device: The selected device.
    :param as_root: Indicates if this function should be run as root.
    """
    env = _get_extended_env({'LC_ALL': 'C'})

    fdisk = _find_device(as_root, device, env)
    if ('-%s-' % fdisk) == ('-%s:-' % device):
        sys.stdout.write('\nI see...\n')
        _print_fdisk_dev(as_root, env)
        _print_mounted_devices()
        if _select_device(device):
            return 0
    else:
        sys.stdout.write('\nAre you sure? I do not see [%s].\n' % device)
        sys.stdout.write('Here is what I see...\n')
        _print_fdisk_dev(as_root, env)
        _print_mounted_devices()

    return 1


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print 'usage: ' + sys.argv[0] + ' <DEVICE>'
        sys.exit(1)

    device = sys.argv[1]
    sys.exit(check_device(device))
