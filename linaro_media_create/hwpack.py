import os

from linaro_media_create import cmd_runner
from linaro_media_create.utils import is_arm_host


# It'd be nice if we could use atexit here, but all the things we need to undo
# have to happen right after install_hwpacks completes and the atexit
# functions would only be called after l-m-c.py exits.
local_atexit = []

def install_hwpacks(chroot_dir, tmp_dir, hwpack_force_yes, *hwpack_files):
    """Install the given hwpacks onto the given chroot."""

    chroot_etc = os.path.join(chroot_dir, 'etc')
    temporarily_overwrite_file_on_dir('/etc/resolv.conf', chroot_etc, tmp_dir)
    temporarily_overwrite_file_on_dir('/etc/hosts', chroot_etc, tmp_dir)

    if not is_arm_host():
        copy_file('/usr/bin/qemu-arm-static',
                  os.path.join(chroot_dir, 'usr', 'bin'))

    # FIXME: This is an ugly hack to make sure we use the l-h-i script from
    # the current development tree when possible.
    here = os.path.dirname(__file__)
    linaro_hwpack_install_path = os.path.join(
        here, '..', 'linaro-hwpack-install')
    if not os.path.exists(linaro_hwpack_install_path):
        linaro_hwpack_install_path = '/usr/bin/linaro-hwpack-install'
    copy_file(linaro_hwpack_install_path,
              os.path.join(chroot_dir, 'usr', 'bin'))

    try:
        mount_chroot_proc(chroot_dir)
        for hwpack_file in hwpack_files:
            install_hwpack(chroot_dir, hwpack_file, hwpack_force_yes)
    finally:
        run_local_atexit_funcs()


def install_hwpack(chroot_dir, hwpack_file, hwpack_force_yes):
    """Install an hwpack on the given chroot.

    Copy the hwpack file to the chroot and run linaro-hwpack-install passing
    that hwpack file to it.  If hwpack_force_yes is True, also pass
    --force-yes to linaro-hwpack-install.
    """
    hwpack_basename = os.path.basename(hwpack_file)
    copy_file(hwpack_file, chroot_dir)
    print "-" * 60
    print "Installing (apt-get) %s in target rootfs." % hwpack_basename
    args = ['chroot', chroot_dir, 'linaro-hwpack-install']
    if hwpack_force_yes:
        args.append('--force-yes')
    args.append('/%s' % hwpack_basename)
    cmd_runner.run(args, as_root=True).wait()
    print "-" * 60


def mount_chroot_proc(chroot_dir):
    """Mount a /proc filesystem on the given chroot.

    Also register a function in local_atexit to unmount that /proc filesystem.
    """
    chroot_proc = os.path.join(chroot_dir, 'proc')

    def umount_chroot_proc():
        cmd_runner.run(['umount', '-v', chroot_proc], as_root=True).wait()
    local_atexit.append(umount_chroot_proc)

    proc = cmd_runner.run(
        ['mount', 'proc', chroot_proc, '-t', 'proc'], as_root=True)
    proc.wait()


def copy_file(filepath, directory):
    """Copy the given file to the given directory.

    The copying of the file is done in a subprocess and run using sudo.

    We also register a function in local_atexit to remove the file from the
    given directory.
    """
    cmd_runner.run(['cp', filepath, directory], as_root=True).wait()

    def undo():
        new_path = os.path.join(directory, os.path.basename(filepath))
        cmd_runner.run(['rm', '-f', new_path], as_root=True).wait()
    local_atexit.append(undo)


def temporarily_overwrite_file_on_dir(filepath, directory, tmp_dir):
    """Temporarily replace a file on the given directory.

    We'll move the existing file on the given directory to a temp dir, then
    copy over the given file to that directory and register a function in
    local_atexit to move the orig file back to the given directory.
    """
    basename = os.path.basename(filepath)
    path_to_orig = os.path.join(tmp_dir, basename)
    # Move the existing file from the given directory to the temp dir.
    cmd_runner.run(
        ['mv', '-f', os.path.join(directory, basename), path_to_orig],
        as_root=True).wait()
    # Now copy the given file onto the given directory.
    cmd_runner.run(['cp', filepath, directory], as_root=True).wait()

    def undo():
        cmd_runner.run(
            ['mv', '-f', path_to_orig, directory], as_root=True).wait()
    local_atexit.append(undo)


def run_local_atexit_funcs():
    # Run the funcs in LIFO order, just like atexit does.
    while len(local_atexit) > 0:
        local_atexit.pop()()
