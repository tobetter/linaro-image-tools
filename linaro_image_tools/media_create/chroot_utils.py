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
from linaro_image_tools.hwpack.handler import HardwarepackHandler

# It'd be nice if we could use atexit here, but all the things we need to undo
# have to happen right after install_hwpacks completes and the atexit
# functions would only be called after l-m-c.py exits.
local_atexit = []


class ChrootException(Exception):
    """Base class for chroot exceptions."""


def prepare_chroot(chroot_dir, tmp_dir):
    """Prepares a chroot to run commands in it (networking and QEMU setup)."""
    chroot_etc = os.path.join(chroot_dir, 'etc')
    temporarily_overwrite_file_on_dir('/etc/resolv.conf', chroot_etc, tmp_dir)
    temporarily_overwrite_file_on_dir('/etc/hosts', chroot_etc, tmp_dir)

    if not is_arm_host():
        for root, dirs, files in os.walk('/usr/bin'):
            for file in files:
                # Copy all the QEMU ARM binaries
                if file.startswith('qemu-arm') or \
                        file.startswith('qemu-aarch64'):
                    file_name = os.path.join(root, file)
                    copy_file(file_name,
                              os.path.join(chroot_dir, 'usr', 'bin'))


def install_hwpacks(
        rootfs_dir, tmp_dir, tools_dir, hwpack_force_yes, verified_files,
        extract_kpkgs=False, *hwpack_files):
    """Install the given hwpacks onto the given rootfs."""

    install_command = 'linaro-hwpack-install'
    linaro_hwpack_install_path = find_command(
        install_command, prefer_dir=tools_dir)

    if not linaro_hwpack_install_path:
        raise ChrootException("The program linaro-hwpack-install could not "
                              "be found found: cannot proceed.")
    else:
        linaro_hwpack_install_path = os.path.abspath(
            linaro_hwpack_install_path)

    # In case we just want to extract the kernel packages, don't force qemu
    # with chroot, as we could have archs without qemu support
    if not extract_kpkgs:
        prepare_chroot(rootfs_dir, tmp_dir)

        # FIXME: shouldn't use chroot/usr/bin as this might conflict with
        # installed packages; would be best to use some custom directory like
        # chroot/linaro-image-tools/bin
        copy_file(linaro_hwpack_install_path,
                  os.path.join(rootfs_dir, 'usr', 'bin'))

        mount_chroot_proc(rootfs_dir)
        try:
            # Sometimes the host will have qemu-user-static installed but
            # another package (i.e. scratchbox) will have mangled its config
            # and thus we won't be able to chroot and install the hwpack, so
            # we fail here and tell the user to ensure qemu-arm-static is
            # setup before trying again.
            cmd_runner.run(['true'], as_root=True, chroot=rootfs_dir).wait()
        except:
            print ("Cannot proceed with hwpack installation because "
                   "there doesn't seem to be a binfmt interpreter registered "
                   "to execute arm binaries in the chroot. Please check "
                   "that qemu-user-static is installed and properly "
                   "configured before trying again.")
            raise
    else:
        # We are not in the chroot, we do not copy the linaro-hwpack-install
        # file, but we might not have l-i-t installed, so we need the full path
        # of the linaro-hwpack-install program to run.
        install_command = linaro_hwpack_install_path

    try:
        for hwpack_file in hwpack_files:
            hwpack_verified = False
            if os.path.basename(hwpack_file) in verified_files:
                hwpack_verified = True
            install_hwpack(rootfs_dir, hwpack_file, extract_kpkgs,
                           hwpack_force_yes or hwpack_verified,
                           install_command)
    finally:
        run_local_atexit_funcs()


def install_hwpack(rootfs_dir, hwpack_file, extract_kpkgs, hwpack_force_yes,
                   install_command):
    """Install an hwpack on the given rootfs.

    Copy the hwpack file to the rootfs and run linaro-hwpack-install passing
    that hwpack file to it.  If hwpack_force_yes is True, also pass
    --force-yes to linaro-hwpack-install. In case extract_kpkgs is True, it
    will not install all the packages, but just extract the kernel ones.
    """
    hwpack_basename = os.path.basename(hwpack_file)
    copy_file(hwpack_file, rootfs_dir)
    print "-" * 60
    print "Installing (linaro-hwpack-install) %s in target rootfs." % (
        hwpack_basename)

    # Get information required by linaro-hwpack-install
    with HardwarepackHandler([hwpack_file]) as hwpack:
        version, _ = hwpack.get_field("version")
        architecture, _ = hwpack.get_field("architecture")
        name, _ = hwpack.get_field("name")

    args = [install_command,
            '--hwpack-version', version,
            '--hwpack-arch', architecture,
            '--hwpack-name', name]
    if hwpack_force_yes:
        args.append('--force-yes')

    if extract_kpkgs:
        args.append('--extract-kernel-only')
        args.append(os.path.join(rootfs_dir, hwpack_basename))
        chroot_dir = None
    else:
        args.append('/%s' % hwpack_basename)
        chroot_dir = rootfs_dir

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
    oldpath = os.path.join(directory, basename)
    if os.path.lexists(oldpath):
        cmd_runner.run(
            ['mv', '-f', oldpath, path_to_orig], as_root=True).wait()
    # Now copy the given file onto the given directory.
    cmd_runner.run(['cp', '-a', filepath, directory], as_root=True).wait()

    def undo():
        if os.path.lexists(path_to_orig):
            cmd_runner.run(
                ['mv', '-f', path_to_orig, directory], as_root=True).wait()
        else:
            cmd_runner.run(
                ['rm', '-f', oldpath], as_root=True).wait()
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
