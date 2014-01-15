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
import subprocess
import tempfile

from linaro_image_tools import cmd_runner

from linaro_image_tools.media_create.partitions import partition_mounted


def populate_partition(content_dir, root_disk, partition):
    os.makedirs(root_disk)
    with partition_mounted(partition, root_disk):
        move_contents(content_dir, root_disk)


def rootfs_mount_options(rootfs_type):
    """Return mount options for the specific rootfs type."""
    if rootfs_type == "btrfs":
        return "defaults"
    if rootfs_type in ('ext2', 'ext3', 'ext4'):
        return "errors=remount-ro"
    raise ValueError('Unsupported rootfs type')


def populate_rootfs(content_dir, root_disk, partition, rootfs_type,
                    rootfs_id, should_create_swap, swap_size,
                    mmc_device_id, partition_offset, os_release_id,
                    board_config=None):
    """Populate the rootfs and make the necessary tweaks to make it usable.

    This consists of:
      1. Create a directory on the path specified by root_disk
      2. Mount the given partition onto the created directory.
      3. Setup an atexit handler to unmount the partition mounted above.
      4. Move the contents of content_dir to that directory.
      5. If should_create_swap, then create it with the given size.
      6. Add fstab entries for the / filesystem and swap (if created).
      7. Create a /etc/flash-kernel.conf containing the target's boot device.
    """
    print "\nPopulating rootfs partition"
    print "Be patient, this may take a few minutes\n"
    # Create a directory to mount the rootfs partition.
    os.makedirs(root_disk)

    with partition_mounted(partition, root_disk):
        move_contents(content_dir, root_disk)

        mount_options = rootfs_mount_options(rootfs_type)
        fstab_additions = ["%s / %s  %s 0 1" % (
            rootfs_id, rootfs_type, mount_options)]
        if should_create_swap:
            print "\nCreating SWAP File\n"
            if has_space_left_for_swap(root_disk, swap_size):
                proc = cmd_runner.run([
                    'dd',
                    'if=/dev/zero',
                    'of=%s/SWAP.swap' % root_disk,
                    'bs=1M',
                    'count=%s' % swap_size], as_root=True)
                proc.wait()
                proc = cmd_runner.run(
                    ['mkswap', '%s/SWAP.swap' % root_disk], as_root=True)
                proc.wait()
                fstab_additions.append("/SWAP.swap  none  swap  sw  0 0")
            else:
                print ("Swap file is bigger than space left on partition; "
                       "continuing without swap.")

        append_to_fstab(root_disk, fstab_additions)

        if os_release_id == 'debian' or os_release_id == 'ubuntu' or \
                os.path.exists('%s/etc/debian_version' % root_disk):
            print "\nCreating /etc/flash-kernel.conf\n"
            create_flash_kernel_config(
                root_disk, mmc_device_id, 1 + partition_offset)

            if board_config is not None:
                print "\nUpdating /etc/network/interfaces\n"
                update_network_interfaces(root_disk, board_config)


def update_network_interfaces(root_disk, board_config):
    interfaces = []
    if board_config.wired_interfaces is not None:
        interfaces.extend(board_config.wired_interfaces)
    if board_config.wireless_interfaces is not None:
        interfaces.extend(board_config.wireless_interfaces)

    if_path = os.path.join(root_disk, 'etc', 'network', 'interfaces')
    if os.path.exists(if_path):
        with open(if_path) as if_file:
            config = if_file.read()
    else:
        config = ''
    for interface in interfaces:
        if interface not in config:
            config += "auto %(if)s\niface %(if)s inet dhcp\n" % (
                {'if': interface})
    if config != '':
        write_data_to_protected_file(if_path, config)


def create_flash_kernel_config(root_disk, mmc_device_id,
                               boot_partition_number):
    """Create a flash-kernel.conf file under root_disk/etc.

    Uses the given partition number to figure out the boot partition.
    """
    target_boot_dev = '/dev/mmcblk%dp%s' % (
        mmc_device_id, boot_partition_number)
    flash_kernel = os.path.join(root_disk, 'etc', 'flash-kernel.conf')
    write_data_to_protected_file(
        flash_kernel, "UBOOT_PART=%s\n" % target_boot_dev)


def _list_files(directory):
    """List the files and dirs under the given directory.

    Runs as root because we want to list everything, including stuff that may
    not be world-readable.
    """
    p = cmd_runner.run(
        ['find', directory, '-maxdepth', '1', '-mindepth', '1',
         '!', '-name', 'lost+found'],
        stdout=subprocess.PIPE, as_root=True)
    stdout, _ = p.communicate()
    return stdout.split()


def move_contents(from_, root_disk):
    """Move everything under from_ to the given root disk.

    Uses sudo for moving.
    """
    assert os.path.isdir(from_), "%s is not a directory" % from_
    files = _list_files(from_)
    mv_cmd = ['mv']
    mv_cmd.extend(sorted(files))
    mv_cmd.append(root_disk)
    cmd_runner.run(mv_cmd, as_root=True).wait()


def has_space_left_for_swap(root_disk, swap_size_in_mega_bytes):
    """Is there enough space for a swap file in the given root disk?"""
    statvfs = os.statvfs(root_disk)
    free_space = statvfs.f_bavail * statvfs.f_bsize
    swap_size_in_bytes = int(swap_size_in_mega_bytes) * 1024 ** 2
    if free_space >= swap_size_in_bytes:
        return True
    return False


def append_to_fstab(root_disk, fstab_additions):
    fstab = os.path.join(root_disk, 'etc', 'fstab')
    data = open(fstab).read() + '\n' + '\n'.join(fstab_additions) + '\n'
    write_data_to_protected_file(fstab, data)


def write_data_to_protected_file(path, data):
    """Write data to the file on the given path.

    This is meant to be used when the given file is only writable by root, and
    we overcome that by writing the data to a tempfile and then moving the
    tempfile on top of the given one using sudo.
    """
    _, tmpfile = tempfile.mkstemp()
    with open(tmpfile, 'w') as fd:
        fd.write(data)
    cmd_runner.run(['mv', '-f', tmpfile, path], as_root=True).wait()
