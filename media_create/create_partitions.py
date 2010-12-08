import subprocess
import sys

from media_create import cmd_runner


def run_sfdisk_commands(commands, heads, sectors, cylinders_arg, device,
                        as_root=True):
    """Run the given commands under sfdisk.

    :param commands: A string of sfdisk commands; each on a separate line.
    :return: A 2-tuple containing the subprocess' stdout and stderr.
    """
    args = ['sfdisk',
            '-D',
            '-H', str(heads),
            '-S', str(sectors)]
    if cylinders_arg:
        args.append(cylinders_arg)
    args.append(device)
    # XXX: There's some stuff duplicated here from cmd_runner.run() but I
    # don't see an easy way to consolidate them as a single function, so I'll
    # leave it for later.
    if as_root:
        args = args[:]
        args.insert(0, 'sudo')
    proc = subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate("%s\n" % commands)
    if proc.returncode != 0:
        raise cmd_runner.SubcommandNonZeroReturnValue(args, proc.returncode)
    return stdout, stderr


def create_partitions(board, device, fat_size, heads, sectors, cylinders_arg):
    """Partition the given device according to the board requirements.

    :param board: A string with the board type (e.g. beagle, panda, etc)
    :param device: A string containing the path to the device to partition.
    :param fat_size: The type of FATs used in the boot partition (16 or 32).
    :param heads: Number of heads to use in the disk geometry of
        partitions.
    :param sectors: Number of sectors to use in the disk geometry of
        partitions.
    :param cylinders_arg: A string of the form "-C NN" containing the number
        of cylinders to use in the disk geometry of partitions.
    """
    stdout = []
    stderr = []
    is_block_device = device.startswith('/dev/')
    if is_block_device:
        # Overwrite any existing partition tables with a fresh one.
        cmd_runner.run(
            ['parted', '-s', device, 'mklabel', 'msdos'], as_root=True)

    if fat_size == 32:
        partition_type = '0x0C'
    else:
        partition_type = '0x0E'

    if board == 'mx51evk':
        # Create a one cylinder partition for fixed-offset bootloader data at
        # the beginning of the image (size is one cylinder, so 8224768 bytes
        # with the first sector for MBR).
        out, err = run_sfdisk_commands(
            ',1,0xDA', heads, sectors, cylinders_arg, device)
        stdout.append(out)
        stderr.append(err)

    # Create a VFAT or FAT16 partition of 9 cylinders (74027520 bytes, ~70
    # MiB), followed by a Linux-type partition containing the rest of the free
    # space.
    sfdisk_cmd = ',9,%s,*\n,,,-' % partition_type
    out, err = run_sfdisk_commands(
        sfdisk_cmd, heads, sectors, cylinders_arg, device)
    stdout.append(out)
    stderr.append(err)
    return "\n".join(stdout), "\n".join(stderr)


if __name__ == "__main__":
    board, device, fat_size, heads, sectors, cylinders_arg = sys.argv[1:]
    fat_size = int(fat_size)
    heads = int(heads)
    sectors = int(sectors)
    stdout, stderr = create_partitions(
        board, device, fat_size, heads, sectors, cylinders_arg)
    print stdout
    print stderr
