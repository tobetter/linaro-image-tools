"""Configuration for boards supported by linaro-media-create.

To add support for a new board, you need to create a subclass of
BoardConfig, set appropriate values for its variables and add it to
board_configs at the bottom of this file.
"""

import atexit
import glob
import os
import tempfile
import uuid

from linaro_media_create import cmd_runner

ROOTFS_UUID = str(uuid.uuid4())


class BoardConfig(object):
    """The configuration used when building an image for a board."""
    # These attributes may not need to be redefined on some subclasses.
    uboot_flavor = None
    mmc_option = '0:1'
    mmc_part_offset = 0
    fat_size = 32
    extra_serial_opts = ''
    live_serial_opts = ''
    extra_boot_args_options = None

    # These attributes must be defined on all subclasses.
    kernel_addr = None
    initrd_addr = None
    load_addr = None
    sub_arch = None
    boot_script = None

    @classmethod
    def _get_boot_cmd(cls, is_live, is_lowmem, consoles):
        """Get the boot command for this board.

        In general subclasses should not have to override this.
        """
        boot_args_options = 'rootwait ro'
        if cls.extra_boot_args_options is not None:
            boot_args_options += ' %s' % cls.extra_boot_args_options
        serial_opts = ''
        if consoles is not None:
            for console in consoles:
                serial_opts += ' console=%s' % console

            # XXX: I think this is not needed as we have board-specific
            # serial options for when is_live is true.
            if is_live:
                serial_opts += ' serialtty=ttyS2'

        serial_opts += ' %s' % cls.extra_serial_opts

        lowmem_opt = ''
        boot_snippet = 'root=UUID=%s' % ROOTFS_UUID
        if is_live:
            serial_opts += ' %s' % cls.live_serial_opts
            boot_snippet = 'boot=casper'
            if is_lowmem:
                lowmem_opt = 'only-ubiquity'

        replacements = dict(
            mmc_option=cls.mmc_option, kernel_addr=cls.kernel_addr,
            initrd_addr=cls.initrd_addr, serial_opts=serial_opts,
            lowmem_opt=lowmem_opt, boot_snippet=boot_snippet,
            boot_args_options=boot_args_options)
        return (
            "setenv bootcmd 'fatload mmc %(mmc_option)s %(kernel_addr)s "
                "uImage; fatload mmc %(mmc_option)s %(initrd_addr)s uInitrd; "
                "bootm %(kernel_addr)s %(initrd_addr)s'\n"
            "setenv bootargs '%(serial_opts)s %(lowmem_opt)s "
                "%(boot_snippet)s %(boot_args_options)s'\n"
            "boot" % replacements)

    @classmethod
    def make_boot_files(cls, uboot_parts_dir, is_live, is_lowmem, consoles,
                        root_dir, boot_dir, boot_script, boot_device_or_file):
        boot_cmd = cls._get_boot_cmd(is_live, is_lowmem, consoles)
        cls._make_boot_files(
            uboot_parts_dir, boot_cmd, root_dir, boot_dir, boot_script,
            boot_device_or_file)

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, root_dir, boot_dir,
                         boot_script, boot_device_or_file):
        """Make the necessary boot files for this board.

        This is usually board-specific so ought to be defined in every
        subclass.
        """
        raise NotImplementedError()


class BeagleConfig(BoardConfig):
    uboot_flavor = 'omap3_beagle'
    extra_serial_opts = 'console=tty0 console=ttyS2,115200n8'
    live_serial_opts = 'serialtty=ttyS2'
    kernel_addr = '0x80000000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    sub_arch = 'linaro-omap'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=12M omapfb.debug=y '
        'omapfb.mode=dvi:1280x720MR-16@60')

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script, boot_device_or_file):
        mlo_file = os.path.join(
            chroot_dir, 'usr', 'lib', 'x-loader-omap', 'MLO')
        install_omap_boot_loader(mlo_file, boot_dir)
        make_uImage(cls.load_addr, uboot_parts_dir, cls.sub_arch, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.sub_arch, boot_dir)
        make_boot_script(boot_cmd, boot_script)
        make_boot_ini(boot_script, boot_dir)


class PandaConfig(BoardConfig):
    uboot_flavor = 'omap4_panda'
    extra_serial_opts = 'console=tty0 console=ttyO2,115200n8'
    live_serial_opts = 'serialtty=ttyO2'
    kernel_addr = '0x80200000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    sub_arch = 'omap4'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=32M omapfb.debug=y '
        'omapfb.vram=0:8M mem=463M ip=none')

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script, boot_device_or_file):
        mlo_file = os.path.join(
            chroot_dir, 'usr', 'lib', 'x-loader-omap4', 'MLO')
        install_omap_boot_loader(mlo_file, boot_dir)
        make_uImage(cls.load_addr, uboot_parts_dir, cls.sub_arch, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.sub_arch, boot_dir)
        make_boot_script(boot_cmd, boot_script)
        make_boot_ini(boot_script, boot_dir)


class IgepConfig(BeagleConfig):
    uboot_flavor = None

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script, boot_device_or_file):
        make_uImage(cls.load_addr, uboot_parts_dir, cls.sub_arch, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.sub_arch, boot_dir)
        make_boot_script(boot_cmd, boot_script)
        make_boot_ini(boot_script, boot_dir)


class Ux500Config(BoardConfig):
    extra_serial_opts = 'console=tty0 console=ttyAMA2,115200n8'
    live_serial_opts = 'serialtty=ttyAMA2'
    kernel_addr = '0x00100000'
    initrd_addr = '0x08000000'
    load_addr = '0x00008000'
    sub_arch = 'ux500'
    boot_script = 'flash.scr'
    extra_boot_args_options = (
        'earlyprintk rootdelay=1 fixrtc nocompcache '
        'mem=96M@0 mem_modem=32M@96M mem=44M@128M pmem=22M@172M '
        'mem=30M@194M mem_mali=32M@224M pmem_hwb=54M@256M '
        'hwmem=48M@302M mem=152M@360M')
    mmc_option = '1:1'

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script, boot_device_or_file):
        make_uImage(cls.load_addr, uboot_parts_dir, cls.sub_arch, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.sub_arch, boot_dir)
        make_boot_script(boot_cmd, boot_script)


class Mx51evkConfig(BoardConfig):
    extra_serial_opts = 'console=tty0 console=ttymxc0,115200n8'
    live_serial_opts = 'serialtty=ttymxc0'
    kernel_addr = '0x90000000'
    initrd_addr = '0x90800000'
    load_addr = '0x90008000'
    sub_arch = 'linaro-mx51'
    boot_script = 'boot.scr'
    mmc_part_offset = 1
    mmc_option = '0:2'

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script, boot_device_or_file):
        uboot_file = os.path.join(
            chroot_dir, 'usr', 'lib', 'u-boot', 'mx51evk', 'u-boot.imx')
        install_mx51evk_boot_loader(uboot_file, boot_device_or_file)
        make_uImage(cls.load_addr, uboot_parts_dir, cls.sub_arch, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.sub_arch, boot_dir)
        make_boot_script(boot_cmd, boot_script)


class VexpressConfig(BoardConfig):
    uboot_flavor = 'ca9x4_ct_vxp'
    extra_serial_opts = 'console=tty0 console=ttyAMA0,38400n8'
    live_serial_opts = 'serialtty=ttyAMA0'
    kernel_addr = '0x60008000'
    initrd_addr = '0x81000000'
    load_addr = kernel_addr
    sub_arch = 'linaro-vexpress'
    boot_script = None
    # ARM Boot Monitor is used to load u-boot, uImage etc. into flash and
    # only allows for FAT16
    fat_size = 16

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_cmd, chroot_dir,
                         boot_dir, boot_script):
        make_uImage(cls.load_addr, uboot_parts_dir, cls.sub_arch, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.sub_arch, boot_dir)


board_configs = {
    'beagle': BeagleConfig,
    'igep': IgepConfig,
    'panda': PandaConfig,
    'vexpress': VexpressConfig,
    'ux500': Ux500Config,
    'mx51evk': Mx51evkConfig,
    }


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


def make_boot_script(boot_script_data, boot_script):
    # Need to save the boot script data into a file that will be passed to
    # mkimage.
    _, tmpfile = tempfile.mkstemp()
    atexit.register(os.unlink, tmpfile)
    with open(tmpfile, 'w') as fd:
        fd.write(boot_script_data)
    return _run_mkimage(
        'script', '0', '0', 'boot script', tmpfile, boot_script)


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
