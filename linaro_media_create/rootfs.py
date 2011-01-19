import glob
import os
import tempfile

from linaro_media_create import cmd_runner


def populate_rootfs(content_dir, root_disk, partition, rootfs_type,
                    rootfs_uuid, should_create_swap, swap_size,
                    partition_offset):
    """Populate the rootfs and make the necessary tweaks to make it usable.

    This consists of:
      1. Create a directory on the path specified by root_disk
      2. Mount the given partition onto the created directory.
      3. Move the contents of content_dir to that directory.
      4. If should_create_swap, then create it with the given size.
      5. Add fstab entries for the / filesystem and swap (if created).
      6. Create a /etc/flash-kernel.conf containing the target's boot device.
      7. Unmount the partition we mounted on step 2.
    """
    print "\nPopulating rootfs partition"
    print "Be patient, this may take a few minutes\n"
    # Create a directory to mount the rootfs partition.
    os.makedirs(root_disk)

    cmd_runner.run(['mount', partition, root_disk], as_root=True).wait()

    move_contents(content_dir, root_disk)

    fstab_additions = ["UUID=%s / %s  errors=remount-ro 0 1 " % (
            rootfs_uuid, rootfs_type)]
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

    print "\nCreating /etc/flash-kernel.conf\n"
    create_flash_kernel_config(root_disk, 1 + partition_offset)

    cmd_runner.run(['sync']).wait()
    # The old code used to ignore failures here, but I don't think that's
    # desirable so I'm using cmd_runner.run()'s standard behaviour, which will
    # fail on a non-zero return value.
    cmd_runner.run(['umount', root_disk], as_root=True).wait()


def create_flash_kernel_config(root_disk, boot_partition_number):
    """Create a flash-kernel.conf file under root_disk/etc.

    Uses the given partition number to figure out the boot partition.
    """
    target_boot_dev = '/dev/mmcblk0p%s' % boot_partition_number
    flash_kernel = os.path.join(root_disk, 'etc', 'flash-kernel.conf')
    write_data_to_protected_file(
        flash_kernel, "UBOOT_PART=%s" % target_boot_dev)


def move_contents(from_, root_disk):
    """Move everything under from_ to the given root disk.

    Uses sudo for moving.
    """
    assert os.path.isdir(from_), "%s is not a directory" % from_
    files = glob.glob(os.path.join(from_, '*'))
    mv_cmd = ['mv']
    mv_cmd.extend(sorted(files))
    mv_cmd.append(root_disk)
    cmd_runner.run(mv_cmd, as_root=True).wait()


def has_space_left_for_swap(root_disk, swap_size_in_mega_bytes):
    """Is there enough space for a swap file in the given root disk?"""
    statvfs = os.statvfs(root_disk)
    free_space = statvfs.f_bavail * statvfs.f_bsize
    swap_size_in_bytes = int(swap_size_in_mega_bytes) * 1024**2
    if free_space >= swap_size_in_bytes:
        return True
    return False


def append_to_fstab(root_disk, fstab_additions):
    fstab = os.path.join(root_disk, 'etc', 'fstab')
    data = open(fstab).read() + '\n' + '\n'.join(fstab_additions)
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
