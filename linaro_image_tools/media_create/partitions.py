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

from contextlib import contextmanager
from math import ceil
import atexit
import dbus
import glob
import logging
import re
import subprocess
import time

from parted import (
    Device,
    Disk,
    PARTITION_NORMAL,
    PARTITION_EXTENDED,
)

from linaro_image_tools import cmd_runner

logger = logging.getLogger(__name__)

HEADS = 128
SECTORS = 32
SECTOR_SIZE = 512  # bytes
CYLINDER_SIZE = HEADS * SECTORS * SECTOR_SIZE
DBUS_PROPERTIES = 'org.freedesktop.DBus.Properties'
UDISKS = "org.freedesktop.UDisks"
# Max number of attempts to sleep (total sleep time in seconds =
# 1+2+...+MAX_TTS)
MAX_TTS = 10
# Image size should be a multiple of 1MiB, expressed in bytes. This is also
# the minimum image size possible.
ROUND_IMAGE_TO = 2 ** 20
MIN_IMAGE_SIZE = ROUND_IMAGE_TO


def setup_android_partitions(board_config, media, image_size, bootfs_label,
                             should_create_partitions,
                             should_align_boot_part=False):
    cylinders = None
    if not media.is_block_device:
        image_size_in_bytes = get_partition_size_in_bytes(image_size)
        cylinders = image_size_in_bytes / CYLINDER_SIZE
        proc = cmd_runner.run(
            ['dd', 'of=%s' % media.path,
             'bs=1', 'seek=%s' % image_size_in_bytes, 'count=0'],
            stderr=open('/dev/null', 'w'))
        proc.wait()

    if should_create_partitions:
        create_partitions(
            board_config, media, HEADS, SECTORS, cylinders,
            should_align_boot_part=should_align_boot_part)

    if media.is_block_device:
        bootfs, system, cache, data, sdcard = \
            get_android_partitions_for_media(media, board_config)
        ensure_partition_is_not_mounted(bootfs)
        ensure_partition_is_not_mounted(system)
        ensure_partition_is_not_mounted(cache)
        ensure_partition_is_not_mounted(data)
        ensure_partition_is_not_mounted(sdcard)
    else:
        partitions = get_android_loopback_devices(media.path)
        bootfs = partitions[0]
        system = partitions[1]
        cache = partitions[2]
        data = partitions[3]
        sdcard = partitions[4]

    print "\nFormating boot partition\n"
    proc = cmd_runner.run(
        ['mkfs.vfat', '-F', str(board_config.fat_size), bootfs, '-n',
         bootfs_label],
        as_root=True)
    proc.wait()

    ext4_partitions = {"system": system, "cache": cache, "userdata": data}
    for label, dev in ext4_partitions.iteritems():
        mkfs = 'mkfs.%s' % "ext4"
        proc = cmd_runner.run(
            [mkfs, dev, '-L', label],
            as_root=True)
        proc.wait()

    proc = cmd_runner.run(
        ['mkfs.vfat', '-F32', sdcard, '-n',
         "sdcard"],
        as_root=True)
    proc.wait()

    return bootfs, system, cache, data, sdcard


# I wonder if it'd make sense to convert this into a small shim which calls
# the appropriate function for the given type of device?  I think it's still
# small enough that there's not much benefit in doing that, but if it grows we
# might want to do it.
def setup_partitions(board_config, media, image_size, bootfs_label,
                     rootfs_label, rootfs_type, should_create_partitions,
                     should_format_bootfs, should_format_rootfs,
                     should_align_boot_part=False, part_table="mbr"):
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
    :param part_table: Type of partition table, either 'mbr' or 'gpt'.
    """
    cylinders = None
    if not media.is_block_device:
        image_size_in_bytes = get_partition_size_in_bytes(image_size)
        cylinders = image_size_in_bytes / CYLINDER_SIZE
        proc = cmd_runner.run(
            ['dd', 'of=%s' % media.path,
             'bs=1', 'seek=%s' % image_size_in_bytes, 'count=0'],
            stderr=open('/dev/null', 'w'))
        proc.wait()

    if should_create_partitions:
        create_partitions(
            board_config, media, HEADS, SECTORS, cylinders,
            should_align_boot_part=should_align_boot_part,
            part_table=part_table)

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
        mkfs = 'mkfs.%s' % board_config.bootfs_type
        if board_config.bootfs_type == 'vfat':
            proc = cmd_runner.run(
                [mkfs, '-F', str(board_config.fat_size), bootfs, '-n',
                 bootfs_label],
                as_root=True)
        else:
            proc = cmd_runner.run(
                [mkfs, bootfs, '-L', bootfs_label], as_root=True)
        proc.wait()

    if should_format_rootfs:
        print "\nFormating root partition\n"
        mkfs = 'mkfs.%s' % rootfs_type
        proc = cmd_runner.run(
            [mkfs, rootfs, '-L', rootfs_label],
            as_root=True)
        proc.wait()

    return bootfs, rootfs


def umount(path):
    # The old code used to ignore failures here, but I don't think that's
    # desirable so I'm using cmd_runner.run()'s standard behaviour, which will
    # fail on a non-zero return value.
    cmd_runner.run(['umount', path], as_root=True).wait()


@contextmanager
def partition_mounted(device, path, *args):
    """A context manager that mounts the given device and umounts when done.

    We use a try/finally to make sure the device is umounted even if there's
    an uncaught exception in the with block.

    :param *args: Extra arguments to the mount command.
    """
    subprocess_args = ['mount', device, path]
    subprocess_args.extend(args)
    cmd_runner.run(subprocess_args, as_root=True).wait()
    try:
        yield
    finally:
        try:
            umount(path)
        except cmd_runner.SubcommandNonZeroReturnValue, e:
            logger.warn("Failed to umount %s, but ignoring it because of a "
                        "previous error" % path)
            logger.warn(e)


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


def get_android_loopback_devices(image_file):
    """Return the loopback devices for the given image file.

    Assumes a particular order of devices in the file.
    Register the loopback devices as well.
    """
    devices = []
    device_info = calculate_android_partition_size_and_offset(image_file)
    for device_offset, device_size in device_info:
        devices.append(register_loopback(image_file, device_offset,
                                         device_size))

    return devices


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
            vfat_offset = geometry.start * SECTOR_SIZE
            vfat_size = geometry.length * SECTOR_SIZE
            vfat_partition = partition
        elif vfat_partition is not None:
            # next partition after boot partition is the root partition
            # NB: don't use vfat_partition.nextPartition() as that might return
            # a partition of type PARTITION_FREESPACE; it's much easier to
            # iterate disk.partitions which only returns
            # parted.PARTITION_NORMAL partitions
            geometry = partition.geometry
            linux_offset = geometry.start * SECTOR_SIZE
            linux_size = geometry.length * SECTOR_SIZE
            linux_partition = partition
            break

    assert vfat_partition is not None, (
        "Couldn't find boot partition on %s" % image_file)
    assert linux_partition is not None, (
        "Couldn't find root partition on %s" % image_file)
    return vfat_size, vfat_offset, linux_size, linux_offset


def calculate_android_partition_size_and_offset(image_file):
    """Return the size and offset of the android partitions.

    Both the size and offset are in bytes.

    :param image_file: A string containing the path to the image_file.
    :return: A list of (offset, size) pairs.
    """
    # Here we can use parted.Device to read the partitions because we're
    # reading from a regular file rather than a block device.  If it was a
    # block device we'd need root rights.
    vfat_partition = None
    disk = Disk(Device(image_file))
    partition_info = []
    for partition in disk.partitions:
        # Will ignore any partitions before boot and of type EXTENDED
        if 'boot' in partition.getFlagsAsString():
            vfat_partition = partition
            geometry = partition.geometry
            partition_info.append((geometry.start * SECTOR_SIZE,
                                   geometry.length * SECTOR_SIZE))
        elif (vfat_partition is not None and
              partition.type != PARTITION_EXTENDED):
            geometry = partition.geometry
            partition_info.append((geometry.start * SECTOR_SIZE,
                                   geometry.length * SECTOR_SIZE))
        # NB: don't use vfat_partition.nextPartition() as that might return
        # a partition of type PARTITION_FREESPACE; it's much easier to
        # iterate disk.partitions which only returns
        # parted.PARTITION_NORMAL partitions
    assert vfat_partition is not None, (
        "Couldn't find boot partition on %s" % image_file)
    assert len(partition_info) == 5
    return partition_info


def get_android_partitions_for_media(media, board_config):
    """Return the device files for all the Android partitions of media.

    For boot we use partition number 1 plus the board's defined partition
    offset and for root we use partition number 2 plus the board's offset.

    This function must only be used for block devices.
    """
    assert media.is_block_device, (
        "This function must only be used for block devices")

    boot_partition = _get_device_file_for_partition_number(
        media.path, 1 + board_config.mmc_part_offset)
    system_partition = _get_device_file_for_partition_number(
        media.path, 2 + board_config.mmc_part_offset)
    if board_config.mmc_part_offset != 1:
        cache_partition = _get_device_file_for_partition_number(
            media.path, 3 + board_config.mmc_part_offset)
    else:
        # In the current setup, partition 4 is always the
        # extended partition container, so we need to skip 4
        cache_partition = _get_device_file_for_partition_number(
            media.path, 5)
    data_partition = _get_device_file_for_partition_number(
        media.path, 5 + board_config.mmc_part_offset)
    sdcard_partition = _get_device_file_for_partition_number(
        media.path, 6 + board_config.mmc_part_offset)

    assert boot_partition is not None, (
        "Could not find boot partition for %s" % media.path)
    assert system_partition is not None, (
        "Could not find system partition for %s" % media.path)
    assert cache_partition is not None, (
        "Could not find cache partition for %s" % media.path)
    assert data_partition is not None, (
        "Could not find data partition for %s" % media.path)
    assert sdcard_partition is not None, (
        "Could not find sdcard partition for %s" % media.path)

    return boot_partition, system_partition, cache_partition, \
        data_partition, sdcard_partition


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
    time_to_sleep = 1
    dev_files = glob.glob("%s?*" % device)
    i = 0
    while i < len(dev_files):
        dev_file = dev_files[i]
        try:
            device_path = _get_udisks_device_path(dev_file)
            partition_str = _get_udisks_device_file(device_path, partition)
            if partition_str:
                return partition_str
            i += 1
        except dbus.exceptions.DBusException, e:
            if time_to_sleep > MAX_TTS:
                print "We've waited long enough..."
                raise
            print "*" * 60
            print "UDisks doesn't know about %s: %s" % (dev_file, e)
            bus = dbus.SystemBus()
            manager = dbus.Interface(
                bus.get_object(UDISKS, "/org/freedesktop/UDisks"), UDISKS)
            print "This is what UDisks know about: %s" % (
                manager.EnumerateDevices())
            print "Sleeping for %d seconds" % time_to_sleep
            time.sleep(time_to_sleep)
            time_to_sleep += 1
            print "*" * 60
    return None


def _get_udisks_device_path(device):
    """Return the UDisks path for the given device."""
    bus = dbus.SystemBus()
    udisks = dbus.Interface(
        bus.get_object(UDISKS, "/org/freedesktop/UDisks"), UDISKS)
    return udisks.get_dbus_method('FindDeviceByDeviceFile')(device)


def _get_udisks_device_file(path, part):
    """Return the UNIX special device file for the given partition."""
    udisks_dev = dbus.SystemBus().get_object(UDISKS, path)
    part_number = udisks_dev.Get(
        path, 'PartitionNumber', dbus_interface=DBUS_PROPERTIES)
    if part_number == part:
        return str(udisks_dev.Get(
            path, 'DeviceFile', dbus_interface=DBUS_PROPERTIES))


def get_partition_size_in_bytes(size):
    """Convert a size string in Kbytes, Mbytes or Gbytes to bytes.

    The conversion rounds-up the size to the nearest MiB, considering a minimum
    size of MIN_IMAGE_SIZE bytes. The conversion always assures to have a big
    enough size for the partition.
    """
    unit = size[-1].upper()
    real_size = float(size[:-1])

    # no unit? (ends with a digit)
    if unit in '0123456789':
        real_size = float(size)
    elif unit == 'K':
        real_size = real_size * 1024
    elif unit == 'M':
        real_size = real_size * 1024 * 1024
    elif unit == 'G':
        real_size = real_size * 1024 * 1024 * 1024
    else:
        raise ValueError("Unknown size format: %s.  Use K[bytes], M[bytes] "
                         "or G[bytes]" % size)
    # Guarantee that is a multiple of ROUND_IMAGE_TO
    real_size = _check_min_size(int(ceil(real_size / ROUND_IMAGE_TO) *
                                    ROUND_IMAGE_TO))
    return real_size


def _check_min_size(size):
    """Check that the image size is at least MIN_IMAGE_SIZE bytes.

    :param size: The size of the image to check, as a number.
    """
    if (size < MIN_IMAGE_SIZE):
        size = MIN_IMAGE_SIZE
    return size


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


def run_sgdisk_commands(commands, device, as_root=True, stderr=None):
    args = ['sgdisk', device]
    args.extend(commands.split())
    proc = cmd_runner.run(args, stderr=stderr, as_root=as_root)
    proc.wait()


def create_partitions(board_config, media, heads, sectors, cylinders=None,
                      should_align_boot_part=False, part_table="mbr"):
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
    :param part_table Type of partition table, either 'mbr' or 'gpt'.
    """
    label = 'msdos'
    if part_table == 'gpt':
        label = part_table

    if media.is_block_device:
        # Overwrite any existing partition tables with a fresh one.
        proc = cmd_runner.run(
            ['parted', '-s', media.path, 'mklabel', label], as_root=True)
        proc.wait()

    wait_partition_to_settle(media, part_table)

    if part_table == 'gpt':
        sgdisk_cmd = board_config.get_sgdisk_cmd(
            should_align_boot_part=should_align_boot_part)

        run_sgdisk_commands(sgdisk_cmd, media.path)
    else:  # default partition table to mbr
        sfdisk_cmd = board_config.get_sfdisk_cmd(
            should_align_boot_part=should_align_boot_part)

        run_sfdisk_commands(sfdisk_cmd, heads, sectors, cylinders, media.path)

    # sleep to wait for the partition to settle.
    wait_partition_to_settle(media, part_table)


def wait_partition_to_settle(media, part_table):
    """Sleep in a loop to wait partition to settle

    :param media: A setup_partitions.Media object to partition.
    """
    tts = 1
    while (tts > 0) and (tts <= MAX_TTS):
        try:
            logger.info("Sleeping for %s second(s) to wait "
                        "for the partition to settle" % tts)
            time.sleep(tts)

            args = ['sfdisk', '-l', media.path]
            if part_table == 'gpt':
                args = ['sgdisk', '-L', media.path]
            proc = cmd_runner.run(args, as_root=True,
                                  stdout=open('/dev/null', 'w'))
            proc.wait()
            return 0
        except cmd_runner.SubcommandNonZeroReturnValue:
            logger.info("Partition table is not available "
                        "for device %s" % media.path)
            tts += 1
    logger.error("Couldn't read partition table "
                 "for a reasonable time for device %s" % media.path)
    raise


class Media(object):
    """A representation of the media where Linaro will be installed."""

    def __init__(self, path):
        self.path = path
        self.is_block_device = path.startswith('/dev/')
