# Copyright (C) 2010, 2011 Linaro
#
# Author: Guilherme Salgado <guilherme.salgado@linaro.org>
#
# This file is part of Linaro Image Tools.
# 
# Linaro Image Tools is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Linaro Image Tools.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys

from linaro_image_tools import cmd_runner
from linaro_image_tools.utils import (
    is_arm_host,
    find_command,
    )


# It'd be nice if we could use atexit here, but all the things we need to undo
# have to happen right after install_hwpacks completes and the atexit
# functions would only be called after l-m-c.py exits.
local_atexit = []

def prepare_chroot(chroot_dir, tmp_dir):
    """Prepares a chroot to run commands in it (networking and QEMU setup)."""
    chroot_etc = os.path.join(chroot_dir, 'etc')
    temporarily_overwrite_file_on_dir('/etc/resolv.conf', chroot_etc, tmp_dir)
    temporarily_overwrite_file_on_dir('/etc/hosts', chroot_etc, tmp_dir)

    if not is_arm_host():
        copy_file('/usr/bin/qemu-arm-static',
                  os.path.join(chroot_dir, 'usr', 'bin'))

def install_hwpacks(
    chroot_dir, tmp_dir, tools_dir, hwpack_force_yes, verified_files, *hwpack_files):
    """Install the given hwpacks onto the given chroot."""
    prepare_chroot(chroot_dir, tmp_dir)

    linaro_hwpack_install_path = find_command(
        'linaro-hwpack-install', prefer_dir=tools_dir)
    # FIXME: shouldn't use chroot/usr/bin as this might conflict with installed
    # packages; would be best to use some custom directory like
    # chroot/linaro-image-tools/bin
    copy_file(linaro_hwpack_install_path,
              os.path.join(chroot_dir, 'usr', 'bin'))

    try:
        mount_chroot_proc(chroot_dir)
        for hwpack_file in hwpack_files:
            hwpack_verified = False
            if os.path.basename(hwpack_file) in verified_files:
                hwpack_verified = True
            install_hwpack(chroot_dir, hwpack_file, hwpack_force_yes or hwpack_verified)
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
    print "Installing (linaro-hwpack-install) %s in target rootfs." % (
        hwpack_basename)
    args = ['linaro-hwpack-install']
    if hwpack_force_yes:
        args.append('--force-yes')
    args.append('/%s' % hwpack_basename)
    cmd_runner.run(args, as_root=True, chroot=chroot_dir).wait()
    print "-" * 60


def install_packages(chroot_dir, tmp_dir, *packages):
    """Install packages in the given chroot.

    This does not run apt-get update before hand."""
    prepare_chroot(chroot_dir, tmp_dir)

    try:
        # TODO: Use the partition_mounted() contextmanager here and get rid of
        # mount_chroot_proc() altogether.
        mount_chroot_proc(chroot_dir)
        print "-" * 60
        print "Installing (apt-get) %s in target rootfs." % " ".join(packages)
        args = ("apt-get", "--yes", "install") + packages
        cmd_runner.run(args, as_root=True, chroot=chroot_dir).wait()
        print "Cleaning up downloaded packages."
        args = ("apt-get", "clean")
        cmd_runner.run(args, as_root=True, chroot=chroot_dir).wait()
        print "-" * 60
    finally:
        run_local_atexit_funcs()


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
    exc_info = None
    while len(local_atexit) > 0:
        func = local_atexit.pop()
        try:
            func()
        except SystemExit:
            exc_info = sys.exc_info()
        except:
            import traceback
            print >> sys.stderr, "Error in local_atexit:"
            traceback.print_exc()
            exc_info = sys.exc_info()

    if exc_info is not None:
        raise exc_info[0], exc_info[1], exc_info[2]
