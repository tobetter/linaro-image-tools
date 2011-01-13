import errno
import os

from linaro_media_create import cmd_runner


def populate_boot(board_config, chroot_dir, boot_partition, boot_disk,
                  boot_device_or_file, is_live, is_lowmem, consoles):

    parts_dir = 'boot'
    if is_live:
        parts_dir = 'casper'
    uboot_parts_dir = os.path.join(chroot_dir, parts_dir)

    try:
        os.makedirs(boot_disk)
    except OSError, exc:
        if exc.errno == errno.EEXIST:
            pass
        else:
            raise
    cmd_runner.run(['mount', boot_partition, boot_disk], as_root=True).wait()

    uboot_flavor = board_config.uboot_flavor
    if uboot_flavor is not None:
        uboot_bin = os.path.join(
            chroot_dir, 'usr', 'lib', 'u-boot', uboot_flavor, 'u-boot.bin')
        cmd_runner.run(
            ['cp', '-v', uboot_bin, boot_disk], as_root=True).wait()

    boot_script = "%(boot_disk)s/%(boot_script_name)s" % (
        dict(boot_disk=boot_disk,
             boot_script_name=board_config.boot_script))

    board_config.make_boot_files(
        uboot_parts_dir, is_live, is_lowmem, consoles, chroot_dir, boot_disk,
        boot_script, boot_device_or_file)

    cmd_runner.run(['sync']).wait()
    try:
        cmd_runner.run(['umount', boot_disk], as_root=True).wait()
    except cmd_runner.SubcommandNonZeroReturnValue:
        pass
