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

import atexit
import glob
import re
import subprocess
import time

import dbus
from parted import (
    Device,
    Disk,
    PARTITION_NORMAL,
    )

from linaro_media_create import cmd_runner


HEADS = 128
SECTORS = 32
SECTOR_SIZE = 512 # bytes
CYLINDER_SIZE = HEADS * SECTORS * SECTOR_SIZE
DBUS_PROPERTIES = 'org.freedesktop.DBus.Properties'
UDISKS = "org.freedesktop.UDisks"


# I wonder if it'd make sense to convert this into a small shim which calls
# the appropriate function for the given type of device?  I think it's still
# small enough that there's not much benefit in doing that, but if it grows we
# might want to do it.
def setup_partitions(board_config, media, image_size, bootfs_label,
                     rootfs_label, rootfs_type, should_create_partitions,
                     should_format_bootfs, should_format_rootfs,
                     should_align_boot_part=False):
    """Make sure the given device is partitioned to boot the given board.

    :param board_config: A BoardConfig class.
    :param media: The Media we should partition.
    :param image_size: The size of the image file, in case we're setting up a
        QEMU image.
    :param bootfs_label: Label for the boot partition.
    :param rootfs_label: Label for the root partition.
    :param rootfs_type: Filesystem for the root partition.
    :param should_create_partitions: Whether or not we should erase existing
        partitions and create new ones.
    :param should_format_bootfs: Whether to reuse the filesystem on the boot
        partition.
    :param should_format_rootfs: Whether to reuse the filesystem on the root
        partition.
    :param should_align_boot_part: Whether to align the boot partition too.
    """
    cylinders = None
    if not media.is_block_device:
        image_size_in_bytes = convert_size_to_bytes(image_size)
        cylinders = image_size_in_bytes / CYLINDER_SIZE
        proc = cmd_runner.run(
            ['qemu-img', 'create', '-f', 'raw', media.path,
             str(image_size_in_bytes)],
            stdout=open('/dev/null', 'w'))
        proc.wait()

    if should_create_partitions:
        create_partitions(
            board_config, media, HEADS, SECTORS, cylinders,
            should_align_boot_part=should_align_boot_part)

    if media.is_block_device:
        bootfs, rootfs = get_boot_and_root_partitions_for_media(
            media, board_config)
        # It looks like KDE somehow automounts the partitions after you
        # repartition a disk so we need to unmount them here to create the
        # filesystem.
        ensure_partition_is_not_mounted(bootfs)
        ensure_partition_is_not_mounted(rootfs)
    else:
        bootfs, rootfs = get_boot_and_root_loopback_devices(media.path)

    if should_format_bootfs:
        print "\nFormating boot partition\n"
        proc = cmd_runner.run(
            ['mkfs.vfat', '-F', str(board_config.fat_size), bootfs, '-n',
             bootfs_label],
            as_root=True)
        proc.wait()

    if should_format_rootfs:
        print "\nFormating root partition\n"
        mkfs = 'mkfs.%s' % rootfs_type
        proc = cmd_runner.run(
            [mkfs, rootfs, '-L', rootfs_label],
            as_root=True)
        proc.wait()

    return bootfs, rootfs


def get_uuid(partition):
    """Find UUID of the given partition."""
    proc = cmd_runner.run(
        ['blkid', '-o', 'udev', '-p', '-c', '/dev/null', partition],
        as_root=True,
        stdout=subprocess.PIPE)
    blkid_output, _ = proc.communicate()
    return _parse_blkid_output(blkid_output)


def _parse_blkid_output(output):
    for line in output.splitlines():
        uuid_match = re.match("ID_FS_UUID=(.*)", line)
        if uuid_match:
            return uuid_match.group(1)
    return None


def ensure_partition_is_not_mounted(partition):
    """Ensure the given partition is not mounted, umounting if necessary."""
    if is_partition_mounted(partition):
        cmd_runner.run(['umount', partition], as_root=True).wait()


def is_partition_mounted(partition):
    """Is the given partition mounted?"""
    device_path = _get_udisks_device_path(partition)
    device = dbus.SystemBus().get_object(UDISKS, device_path)
    return device.Get(
        device_path, 'DeviceIsMounted', dbus_interface=DBUS_PROPERTIES)


def get_boot_and_root_loopback_devices(image_file):
    """Return the boot and root loopback devices for the given image file.

    Register the loopback devices as well.
    """
    vfat_size, vfat_offset, linux_size, linux_offset = (
        calculate_partition_size_and_offset(image_file))
    boot_device = register_loopback(image_file, vfat_offset, vfat_size)
    root_device = register_loopback(image_file, linux_offset, linux_size)
    return boot_device, root_device


def register_loopback(image_file, offset, size):
    """Register a loopback device with an atexit handler to de-register it."""
    def undo(device):
        cmd_runner.run(['losetup', '-d', device], as_root=True).wait()

    proc = cmd_runner.run(
        ['losetup', '-f', '--show', image_file, '--offset',
         str(offset), '--sizelimit', str(size)],
        stdout=subprocess.PIPE, as_root=True)
    device, _ = proc.communicate()
    device = device.strip()
    atexit.register(undo, device)
    return device


def calculate_partition_size_and_offset(image_file):
    """Return the size and offset of the boot and root partitions.

    Both the size and offset are in sectors.

    :param image_file: A string containing the path to the image_file.
    :return: A 4-tuple containing the offset and size of the boot partition
        followed by the offset and size of the root partition.
    """
    # Here we can use parted.Device to read the partitions because we're
    # reading from a regular file rather than a block device.  If it was a
    # block device we'd need root rights.
    disk = Disk(Device(image_file))
    vfat_partition = None
    linux_partition = None
    for partition in disk.partitions:
        assert partition.type == PARTITION_NORMAL, (
            "Parted should only return normal partitions but got type %i" %
                partition.type)
        if 'boot' in partition.getFlagsAsString():
            geometry = partition.geometry
            vfat_offset = geometry.start * 512
            vfat_size = geometry.length * 512
            vfat_partition = partition
        elif vfat_partition is not None:
            # next partition after boot partition is the root partition
            # NB: don't use vfat_partition.nextPartition() as that might return
            # a partition of type PARTITION_FREESPACE; it's much easier to
            # iterate disk.partitions which only returns
            # parted.PARTITION_NORMAL partitions
            geometry = partition.geometry
            linux_offset = geometry.start * 512
            linux_size = geometry.length * 512
            linux_partition = partition
            break

    assert vfat_partition is not None, (
        "Couldn't find boot partition on %s" % image_file)
    assert linux_partition is not None, (
        "Couldn't find root partition on %s" % image_file)
    return vfat_size, vfat_offset, linux_size, linux_offset


def get_boot_and_root_partitions_for_media(media, board_config):
    """Return the device files for the boot and root partitions of media.

    For boot we use partition number 1 plus the board's defined partition
    offset and for root we use partition number 2 plus the board's offset.

    This function must only be used for block devices.
    """
    assert media.is_block_device, (
        "This function must only be used for block devices")

    boot_partition = _get_device_file_for_partition_number(
        media.path, 1 + board_config.mmc_part_offset)
    root_partition = _get_device_file_for_partition_number(
        media.path, 2 + board_config.mmc_part_offset)
    assert boot_partition is not None and root_partition is not None, (
        "Could not find boot/root partition for %s" % media.path)
    return boot_partition, root_partition


def _get_device_file_for_partition_number(device, partition):
    """Return the device file for the partition number on the given device.

    e.g. /dev/sda1 for the first partition on device /dev/sda or
    /dev/mmcblk0p3 for the third partition on /dev/mmcblk0.
    """
    # This could be simpler but UDisks doesn't make it easy for us:
    # https://bugs.freedesktop.org/show_bug.cgi?id=33113.
    for dev_file in glob.glob("%s?*" % device):
        device_path = _get_udisks_device_path(dev_file)
        udisks_dev = dbus.SystemBus().get_object(UDISKS, device_path)
        part_number = udisks_dev.Get(
            device_path, 'PartitionNumber', dbus_interface=DBUS_PROPERTIES)
        if part_number == partition:
            return str(udisks_dev.Get(
                device_path, 'DeviceFile', dbus_interface=DBUS_PROPERTIES))
    return None


def _get_udisks_device_path(device):
    """Return the UDisks path for the given device."""
    bus = dbus.SystemBus()
    udisks = dbus.Interface(
        bus.get_object(UDISKS, "/org/freedesktop/UDisks"), UDISKS)
    return udisks.get_dbus_method('FindDeviceByDeviceFile')(device)


def convert_size_to_bytes(size):
    """Convert a size string in Kbytes, Mbytes or Gbytes to bytes."""
    unit = size[-1].upper()
    real_size = int(size[:-1])
    if unit == 'K':
        real_size = real_size * 1024
    elif unit == 'M':
        real_size = real_size * 1024 * 1024
    elif unit == 'G':
        real_size = real_size * 1024 * 1024 * 1024
    else:
        raise ValueError("Unknown size format: %s.  Use K[bytes], M[bytes] "
                         "or G[bytes]" % size)

    return real_size


def run_sfdisk_commands(commands, heads, sectors, cylinders, device,
                        as_root=True, stderr=None):
    """Run the given commands under sfdisk.

    Every time sfdisk is invoked it will repartition the device so to create
    multiple partitions you should craft a list of newline-separated commands
    to be executed in a single sfdisk run.

    :param commands: A string of sfdisk commands; each on a separate line.
    :return: A 2-tuple containing the subprocess' stdout and stderr.
    """
    # --force is unfortunate, but a consequence of having partitions not
    # starting on cylinder boundaries: sfdisk will abort with "Warning:
    # partition 2 does not start at a cylinder boundary"
    args = ['sfdisk',
            '--force',
            '-D',
            '-uS',
            '-H', str(heads),
            '-S', str(sectors)]
    if cylinders is not None:
        args.extend(['-C', str(cylinders)])
    args.append(device)
    proc = cmd_runner.run(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
        as_root=as_root)
    return proc.communicate("%s\n" % commands)


def create_partitions(board_config, media, heads, sectors, cylinders=None,
                      should_align_boot_part=False):
    """Partition the given media according to the board requirements.

    :param board_config: A BoardConfig class.
    :param media: A setup_partitions.Media object to partition.
    :param heads: Number of heads to use in the disk geometry of
        partitions.
    :param sectors: Number of sectors to use in the disk geometry of
        partitions.
    :param cylinders: The number of cylinders to pass to sfdisk's -C argument.
        If None the -C argument is not passed.
    :param should_align_boot_part: Whether to align the boot partition too.
    """
    if media.is_block_device:
        # Overwrite any existing partition tables with a fresh one.
        proc = cmd_runner.run(
            ['parted', '-s', media.path, 'mklabel', 'msdos'], as_root=True)
        proc.wait()

    sfdisk_cmd = board_config.get_sfdisk_cmd(
        should_align_boot_part=should_align_boot_part)
    run_sfdisk_commands(sfdisk_cmd, heads, sectors, cylinders, media.path)

    # Sync and sleep to wait for the partition to settle.
    cmd_runner.run(['sync']).wait()
    # Sleeping just 1 second seems to be enough here, but if we start getting
    # errors because the disk is not partitioned then we should revisit this.
    # XXX: This sleep can probably die now; need to do more tests before doing
    # so, though.
    time.sleep(1)


class Media(object):
    """A representation of the media where Linaro will be installed."""

    def __init__(self, path):
        self.path = path
        self.is_block_device = path.startswith('/dev/')
