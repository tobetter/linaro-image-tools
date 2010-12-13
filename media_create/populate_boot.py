import glob
import sys

from media_create import cmd_runner


def _run_mkimage(img_type, load_addr, entry_point, name, img_data, img,
                 stdout=None, as_root=True):
    cmd = ['mkimage',
           '-A', 'arm',
           '-O', 'linux',
           '-T', img_type,
           '-C', 'none',
           '-a', load_addr,
           '-e', load_addr,
           '-n', name,
           '-d', img_data,
           img]
    proc = cmd_runner.run(cmd, as_root=as_root, stdout=stdout)
    proc.wait()
    return proc.returncode


def _get_file_matching(regex):
    """Return a file whose path matches the given regex.

    If zero or more than one files match, raise a ValueError.
    """
    files = glob.glob(regex)
    if len(files) == 1:
        return files[0]
    elif len(files) == 0:
        raise ValueError(
            "No files found matching '%s'; can't continue" % regex)
    else:
        # TODO: Could ask the user to chosse which file to use instead of
        # raising an exception.
        raise ValueError("Too many files matching '%s' found." % regex)


def make_uImage(load_addr, uboot_parts_dir, sub_arch, boot_disk):
    img_data = _get_file_matching(
        '%s/vmlinuz-*-%s' % (uboot_parts_dir, sub_arch))
    img = '%s/uImage' % boot_disk
    return _run_mkimage(
        'kernel', load_addr, load_addr, 'Linux', img_data, img)


def make_uInitrd(uboot_parts_dir, sub_arch, boot_disk):
    img_data = _get_file_matching(
        '%s/initrd.img-*-%s' % (uboot_parts_dir, sub_arch))
    img = '%s/uInitrd' % boot_disk
    return _run_mkimage('ramdisk', '0', '0', 'initramfs', img_data, img)


def make_boot_script(boot_script, tmp_dir):
    img_data = '%s/boot.cmd' % tmp_dir
    return _run_mkimage(
        'script', '0', '0', 'boot script', img_data, boot_script)


def install_mx51evk_boot_loader(imx_file, boot_device_or_file):
    proc = cmd_runner.run([
        "dd",
        "if=%s" % imx_file,
        "of=%s" % boot_device_or_file,
        "bs=1024",
        "seek=1",
        "conv=notrunc"], as_root=True)
    proc.wait()


def install_omap_boot_loader(mlo_file, boot_disk):
    cmd_runner.run(["cp", "-v", mlo_file, boot_disk], as_root=True).wait()
    # XXX: Is this really needed?
    cmd_runner.run(["sync"]).wait()


def make_boot_ini(boot_script, boot_disk):
    proc = cmd_runner.run(
        ["cp", "-v", boot_script, "%s/boot.ini" % boot_disk], as_root=True)
    proc.wait()


def populate_boot(board, sub_arch, load_addr, uboot_parts_dir, boot_disk,
                  tmp_dir, boot_script_name, boot_device_or_file):

    boot_script = "%(boot_disk)s/%(boot_script_name)s" % (
        dict(boot_disk=boot_disk, boot_script_name=boot_script_name))

    # TODO: Once linaro-media-create is fully ported to python, we should
    # split this into several board-specific functions that are defined
    # somewhere else and just called here.
    if board in ["beagle", "panda"]:
        mlo_file = "binary/usr/lib/x-loader-omap/MLO"
        if board == "panda":
            mlo_file = "binary/usr/lib/x-loader-omap4/MLO"
        install_omap_boot_loader(mlo_file, boot_disk)
        make_uImage(load_addr, uboot_parts_dir, sub_arch, boot_disk)
        make_uInitrd(uboot_parts_dir, sub_arch, boot_disk)
        make_boot_script(boot_script, tmp_dir)
        make_boot_ini(boot_script, boot_disk)

    elif board == "igep":
        make_uImage(load_addr, uboot_parts_dir, sub_arch, boot_disk)
        make_uInitrd(uboot_parts_dir, sub_arch, boot_disk)
        make_boot_script(boot_script, tmp_dir)
        make_boot_ini(boot_script, boot_disk)

    elif board == "ux500":
        make_uImage(load_addr, uboot_parts_dir, sub_arch, boot_disk)
        make_uInitrd(uboot_parts_dir, sub_arch, boot_disk)
        make_boot_script(boot_script, tmp_dir)

    elif board == "vexpress":
        make_uImage(load_addr, uboot_parts_dir, sub_arch, boot_disk)
        make_uInitrd(uboot_parts_dir, sub_arch, boot_disk)

    elif board == "mx51evk":
        install_mx51evk_boot_loader(
            "binary/usr/lib/u-boot/mx51evk/u-boot.imx", boot_device_or_file)
        make_uImage(load_addr, uboot_parts_dir, sub_arch, boot_disk)
        make_uInitrd(uboot_parts_dir, sub_arch, boot_disk)
        make_boot_script(boot_script, tmp_dir)

    else:
        raise AssertionError(
            "Internal error; missing support for board: %s" % board)


if __name__ == "__main__":
    sys.exit(populate_boot(*sys.argv[1:]))
