import subprocess
import time

from media_create import cmd_runner


# TODO: Merge this file with setup_partitions.py.
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
        cmd_runner.run(
            ['parted', '-s', media.path, 'mklabel', 'msdos'], as_root=True)
        # It sems to be necessary to sleep a bit here to avoid a race
        # condition with the sfdisk commands executed below.  Try removing it
        # and running the integration tests to see how it fails.
        time.sleep(0.5)

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
