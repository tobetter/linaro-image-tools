import subprocess
import sys
import time

import dbus
from parted import (
    Device,
    Disk,
    )

from media_create import cmd_runner


HEADS = 255
SECTORS = 63
SECTOR_SIZE = 512 # bytes
CYLINDER_SIZE = HEADS * SECTORS * SECTOR_SIZE


# I wonder if it'd make sense to convert this into a small shim which calls
# the appropriate function for the given type of device?  I think it's still
# small enough that there's not much benefit in doing that, but if it grows we
# might want to do it.
def setup_partitions(board, media, fat_size, image_size,
                     bootfs_label, rootfs_label, rootfs_type, rootfs_uuid,
                     should_create_partitions, should_format_bootfs,
                     should_format_rootfs):
    """Make sure the given device is partitioned to boot the given board.

    :param board: The board's name, as a string.
    :param media: The Media we should partition.
    :param fat_size: The FAT size (16 or 32) for the boot partition.
    :param image_size: The size of the image file, in case we're setting up a
        QEMU image.
    :param should_create_partitions: A string with values "yes" or "no",
        specifying whether or not we should erase existing partitions and
        create new ones.
    """
    cylinders = None
    if not media.is_block_device:
        image_size_in_bytes = convert_size_to_bytes(image_size)
        cylinders = image_size_in_bytes / CYLINDER_SIZE
        image_size_in_bytes = cylinders * CYLINDER_SIZE
        proc = cmd_runner.run(
            ['qemu-img', 'create', '-f', 'raw', media.path, image_size],
            stdout=open('/dev/null', 'w'))
        proc.wait()

    if should_create_partitions == "yes":
        create_partitions(board, media, fat_size, HEADS, SECTORS, cylinders)

    if media.is_block_device:
        bootfs, rootfs = get_boot_and_root_partitions_for_media(media)
    else:
        bootfs, rootfs = get_boot_and_root_loopback_devices(media.path)

    if should_format_bootfs:
        print "\nFormating boot partition\n"
        # It looks like KDE somehow automounts the partitions after you
        # repartition a disk so we need to unmount them here to create the
        # filesystem.
        _umount_partition_if_mounted(bootfs)
        proc = cmd_runner.run(
            ['mkfs.vfat', '-F', str(fat_size), bootfs, '-n', bootfs_label],
            as_root=True)
        proc.wait()

    if should_format_rootfs:
        print "\nFormating root partition\n"
        mkfs = 'mkfs.%s' % rootfs_type
        _umount_partition_if_mounted(rootfs)
        proc = cmd_runner.run(
            [mkfs, '-U', rootfs_uuid, rootfs, '-L', rootfs_label],
            as_root=True)
        proc.wait()

    return bootfs, rootfs


def _umount_partition_if_mounted(partition):
    if partition in open('/proc/mounts').read():
        cmd_runner.run(['umount', partition], as_root=True).wait()


def get_boot_and_root_loopback_devices(image_file):
    """Return the boot and root loopback devices for the given image file.

    Register the loopback devices as well.
    """
    vfat_size, vfat_offset, linux_size, linux_offset = (
        calculate_partition_size_and_offset(image_file))
    proc = cmd_runner.run(
        ['losetup', '-f', '--show', image_file, '--offset',
         str(vfat_offset), '--sizelimit', str(vfat_size)],
        stdout=subprocess.PIPE, as_root=True)
    boot_device, _ = proc.communicate()
    proc = cmd_runner.run(
        ['losetup', '-f', '--show', image_file, '--offset',
         str(linux_offset), '--sizelimit', str(linux_size)],
        stdout=subprocess.PIPE, as_root=True)
    root_device, _ = proc.communicate()

    return boot_device.strip(), root_device.strip()


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
    for partition in disk.partitions:
        if 'boot' in partition.getFlagsAsString():
            geometry = partition.geometry
            vfat_offset = geometry.start * 512
            vfat_size = geometry.length * 512
            vfat_partition = partition

    assert vfat_partition is not None, (
        "Couldn't find boot partition on %s" % image_file)
    linux_partition = vfat_partition.nextPartition()
    geometry = linux_partition.geometry
    linux_offset = geometry.start * 512
    linux_size = geometry.length * 512
    return vfat_size, vfat_offset, linux_size, linux_offset


def get_boot_and_root_partitions_for_media(media):
    """Return the device files for the boot and root partitions of media.

    If the given media has 2 partitions, the first is boot and the second is
    root. If there are 3 partitions, the second is boot and third is root.

    If there are any other number of partitions, ValueError is raised.

    This function must only be used for block devices.
    """
    assert media.is_block_device, (
        "This function must only be used for block devices")

    partition_count = _get_partition_count(media)

    if partition_count == 2:
        partition_offset = 0
    elif partition_count == 3:
        partition_offset = 1
    else:
        raise ValueError(
            "Unexpected number of partitions on %s: %d" % (
                media.path, partition_count))

    boot_partition = "%s%d" % (media.path, 1 + partition_offset)
    root_partition = "%s%d" % (media.path, 2 + partition_offset)
    return boot_partition, root_partition


def _get_partition_count(media):
    """Return the number of partitions on the given media."""
    # We could do the same easily using python-parted but it requires root
    # rights to read block devices, so we use UDisks here.
    bus = dbus.SystemBus()
    udisks = dbus.Interface(
        bus.get_object("org.freedesktop.UDisks", "/org/freedesktop/UDisks"),
        'org.freedesktop.UDisks')
    device_path = udisks.get_dbus_method('FindDeviceByDeviceFile')(media.path)
    device = bus.get_object("org.freedesktop.UDisks", device_path)
    return device.Get(
        device_path, 'partition-table-count',
        dbus_interface='org.freedesktop.DBus.Properties')


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

    # Round the size of the raw disk image up to a multiple of 256K so it is
    # an exact number of SD card erase blocks in length.  Otherwise Linux
    # under qemu cannot access the last part of the card and is likely to
    # complain that the last partition on the disk has been truncated.  This
    # doesn't appear to work in all cases, though, as can be seen on
    # https://bugs.launchpad.net/linux-linaro/+bug/673335.
    if real_size % (1024 * 256):
        cylinders = real_size / CYLINDER_SIZE
        real_size = cylinders * CYLINDER_SIZE
        real_size = ((((real_size - 1) / (1024 * 256)) + 1) * (1024 * 256))

    return real_size


def run_sfdisk_commands(commands, heads, sectors, cylinders, device,
                        as_root=True, stderr=None):
    """Run the given commands under sfdisk.

    :param commands: A string of sfdisk commands; each on a separate line.
    :return: A 2-tuple containing the subprocess' stdout and stderr.
    """
    args = ['sfdisk',
            '-D',
            '-H', str(heads),
            '-S', str(sectors)]
    if cylinders is not None:
        args.extend(['-C', str(cylinders)])
    args.append(device)
    proc = cmd_runner.run(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
        as_root=as_root)
    return proc.communicate("%s\n" % commands)


def create_partitions(board, media, fat_size, heads, sectors, cylinders=None):
    """Partition the given media according to the board requirements.

    :param board: A string with the board type (e.g. beagle, panda, etc)
    :param media: A setup_partitions.Media object to partition.
    :param fat_size: The type of FATs used in the boot partition (16 or 32).
    :param heads: Number of heads to use in the disk geometry of
        partitions.
    :param sectors: Number of sectors to use in the disk geometry of
        partitions.
    :param cylinders: The number of cylinders to pass to sfdisk's -C argument.
        If None the -C argument is not passed.
    """
    if media.is_block_device:
        # Overwrite any existing partition tables with a fresh one.
        proc = cmd_runner.run(
            ['parted', '-s', media.path, 'mklabel', 'msdos'], as_root=True)
        proc.wait()

    if fat_size == 32:
        partition_type = '0x0C'
    else:
        partition_type = '0x0E'

    if board == 'mx51evk':
        # Create a one cylinder partition for fixed-offset bootloader data at
        # the beginning of the image (size is one cylinder, so 8224768 bytes
        # with the first sector for MBR).
        run_sfdisk_commands(',1,0xDA', heads, sectors, cylinders, media.path)

    # Create a VFAT or FAT16 partition of 9 cylinders (74027520 bytes, ~70
    # MiB), followed by a Linux-type partition containing the rest of the free
    # space.
    sfdisk_cmd = ',9,%s,*\n,,,-' % partition_type
    run_sfdisk_commands(sfdisk_cmd, heads, sectors, cylinders, media.path)

    # Sync and sleep to wait for the partition to settle.
    cmd_runner.run(['sync']).wait()
    # Sleeping just 1 second seems to be enough here, but if we start getting
    # errors because the disk is not partitioned then we should revisit this.
    time.sleep(1)


class Media(object):
    """A representation of the media where Linaro will be installed."""

    def __init__(self, path):
        self.path = path
        self.is_block_device = path.startswith('/dev/')


if __name__ == "__main__":
    (board, device, fat_size, image_size, bootfs_label, rootfs_label,
        rootfs_type, rootfs_uuid, should_create_partitions, bootfs_step,
        rootfs_step) = sys.argv[2:]
    out_file = sys.argv[1]
    fat_size = int(fat_size)
    should_format_bootfs = True
    should_format_rootfs = True
    if bootfs_step == "":
        should_format_bootfs = False
    if rootfs_step == "":
        should_format_rootfs = False
    boot, root = setup_partitions(
        board, Media(device), fat_size, image_size, bootfs_label,
        rootfs_label, rootfs_type, rootfs_uuid, should_create_partitions,
        should_format_bootfs, should_format_rootfs)
    # Write the boot/root partitions to the given out file to be later sourced
    # in the shell script.
    with open(out_file, 'w') as fd:
        fd.write("BOOTFS=%s ROOTFS=%s\n" % (boot, root))
