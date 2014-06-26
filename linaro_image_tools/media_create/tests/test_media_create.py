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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import atexit
import glob
import os
import random
import string
import subprocess
import sys
import tempfile
import textwrap
import time
import types
import struct
import tarfile
import dbus
import shutil

from mock import MagicMock
from StringIO import StringIO
from testtools import TestCase

from linaro_image_tools import cmd_runner
from linaro_image_tools.hwpack.handler import HardwarepackHandler
from linaro_image_tools.hwpack.packages import PackageMaker
import linaro_image_tools.media_create
from linaro_image_tools.media_create import (
    android_boards,
    boards,
    check_device,
    partitions,
    rootfs,
)
from linaro_image_tools.media_create.boards import (
    SECTOR_SIZE,
    align_up,
    align_partition,
    get_plain_boot_script_contents,
    make_flashable_env,
    install_mx5_boot_loader,
    install_omap_boot_loader,
    make_boot_script,
    make_uImage,
    make_uInitrd,
    make_dtb,
    _get_file_matching,
    _get_mlo_file,
    _run_mkimage,
    BoardConfig,
    get_board_config,
)
from linaro_image_tools.media_create.android_boards import (
    AndroidSnowballEmmcConfig,
)
from linaro_image_tools.media_create.chroot_utils import (
    copy_file,
    install_hwpack,
    install_hwpacks,
    install_packages,
    mount_chroot_proc,
    prepare_chroot,
    run_local_atexit_funcs,
    temporarily_overwrite_file_on_dir,
)
from linaro_image_tools.media_create.partitions import (
    HEADS,
    MIN_IMAGE_SIZE,
    Media,
    SECTORS,
    _check_min_size,
    _get_device_file_for_partition_number,
    _parse_blkid_output,
    calculate_android_partition_size_and_offset,
    calculate_partition_size_and_offset,
    create_partitions,
    ensure_partition_is_not_mounted,
    get_android_loopback_devices,
    get_boot_and_root_loopback_devices,
    get_boot_and_root_partitions_for_media,
    get_partition_size_in_bytes,
    get_uuid,
    partition_mounted,
    run_sfdisk_commands,
    setup_partitions,
    wait_partition_to_settle,
)
from linaro_image_tools.media_create.rootfs import (
    append_to_fstab,
    create_flash_kernel_config,
    has_space_left_for_swap,
    move_contents,
    populate_rootfs,
    rootfs_mount_options,
    update_network_interfaces,
    write_data_to_protected_file,
)
from linaro_image_tools.media_create.tests.fixtures import (
    CreateTarballFixture,
    MockRunSfdiskCommandsFixture,
)
from linaro_image_tools.media_create.unpack_binary_tarball import (
    unpack_binary_tarball,
)
from linaro_image_tools.testing import TestCaseWithFixtures
from linaro_image_tools.tests.fixtures import (
    CreateTempDirFixture,
    MockCmdRunnerPopenFixture,
    MockSomethingFixture,
)
from linaro_image_tools.utils import find_command, preferred_tools_dir

from linaro_image_tools.hwpack.testing import ContextManagerFixture

chroot_args = " ".join(cmd_runner.CHROOT_ARGS)
sudo_args = " ".join(cmd_runner.SUDO_ARGS)


class TestHardwarepackHandler(TestCaseWithFixtures):
    def setUp(self):
        super(TestHardwarepackHandler, self).setUp()
        self.tar_dir_fixture = CreateTempDirFixture()
        self.useFixture(self.tar_dir_fixture)

        self.tarball_fixture = CreateTarballFixture(
            self.tar_dir_fixture.get_temp_dir())
        self.useFixture(self.tarball_fixture)

        self.metadata = (
            "NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\nORIGIN=linaro\n")

    def test_hardwarepack_bootloaders(self):
        metadata = ("format: 3.0\nname: ahwpack\nversion: 4\narchitecture: "
                    "armel\norigin: linaro\n")
        metadata += ("bootloaders:\n u_boot:\n  file: a_file\n uefi:\n  file: "
                     "b_file\n")
        data = '3.0'
        format = "%s\n" % data
        tarball = self.add_to_tarball(
            [('FORMAT', format), ('metadata', metadata)])
        hp = HardwarepackHandler([tarball], bootloader='u_boot')
        with hp:
            self.assertEquals(hp.get_field('bootloader_file')[0], 'a_file')

    def test_hardwarepack_boards(self):
        metadata = ("format: 3.0\nname: ahwpack\nversion: 4\narchitecture: "
                    "armel\norigin: linaro\n")
        metadata += ("bootloaders:\n u_boot:\n  file: a_file\n uefi:\n  file: "
                     "b_file\n")
        metadata += ("boards:\n panda:\n  bootloaders:\n   u_boot:\n    "
                     "file: panda_file")
        data = '3.0'
        format = "%s\n" % data
        tarball = self.add_to_tarball(
            [('FORMAT', format), ('metadata', metadata)])
        hp = HardwarepackHandler([tarball], board='panda')
        with hp:
            self.assertEquals(hp.get_field('bootloader_file')[0], 'panda_file')

    def test_hardwarepack_boards_and_bootloaders(self):
        metadata = ("format: 3.0\nname: ahwpack\nversion: 4\narchitecture: "
                    "armel\norigin: linaro\n")
        metadata += ("bootloaders:\n u_boot:\n  file: a_file\n uefi:\n  file: "
                     "b_file\n")
        metadata += ("boards:\n panda:\n  bootloaders:\n   u_boot:\n    "
                     "file: panda_file\n   uefi:\n    file: "
                     "uefi_panda_file\n")
        metadata += (" panda-lt:\n bootloaders:\n   u_boot:\n    "
                     "file: panda_lt_file")
        data = '3.0'
        format = "%s\n" % data
        tarball = self.add_to_tarball(
            [('FORMAT', format), ('metadata', metadata)])
        hp = HardwarepackHandler([tarball], board='panda', bootloader='uefi')
        with hp:
            self.assertEquals(hp.get_field('bootloader_file')[0],
                              'uefi_panda_file')

    def add_to_tarball(self, files, tarball=None):
        if tarball is None:
            tarball = self.tarball_fixture.get_tarball()
        tar_file = tarfile.open(tarball, mode='w:gz')
        for filename, data in files:
            tarinfo = tarfile.TarInfo(filename)
            tarinfo.size = len(data)
            tar_file.addfile(tarinfo, StringIO(data))
        tar_file.close()
        return tarball

    def test_get_format_1(self):
        data = HardwarepackHandler.FORMAT_1
        format = "%s\n" % data
        tarball = self.add_to_tarball(
            [('FORMAT', format), ('metadata', self.metadata)])
        hp = HardwarepackHandler([tarball])
        with hp:
            self.assertEquals(hp.get_format(), data)

    def test_get_format_2(self):
        data = '2.0'
        format = "%s\n" % data
        tarball = self.add_to_tarball(
            [('FORMAT', format), ('metadata', self.metadata)])
        hp = HardwarepackHandler([tarball])
        with hp:
            self.assertEquals(hp.get_format(), data)

    def test_get_unknown_format_raises(self):
        data = '9.9'
        format = "%s\n" % data
        tarball = self.add_to_tarball(
            [('FORMAT', format), ('metadata', self.metadata)])
        hp = HardwarepackHandler([tarball])
        with hp:
            self.assertRaises(AssertionError, hp.get_format)

    def test_mixed_formats(self):
        format1 = "%s\n" % HardwarepackHandler.FORMAT_1
        format2 = "%s\n" % HardwarepackHandler.FORMAT_2
        tarball1 = self.add_to_tarball(
            [('FORMAT', format1), ('metadata', self.metadata)],
            tarball=self.tarball_fixture.get_tarball())
        tarball_fixture2 = CreateTarballFixture(
            self.tar_dir_fixture.get_temp_dir(), reldir='tarfile2',
            filename='secondtarball.tar.gz')
        self.useFixture(tarball_fixture2)
        tarball2 = self.add_to_tarball(
            [('FORMAT', format2), ('metadata', self.metadata)],
            tarball=tarball_fixture2.get_tarball())
        hp = HardwarepackHandler([tarball2, tarball1])
        with hp:
            self.assertEquals(hp.get_format(), '1.0and2.0')

    def test_identical_formats_ok(self):
        format1 = "%s\n" % HardwarepackHandler.FORMAT_2
        format2 = "%s\n" % HardwarepackHandler.FORMAT_2
        tarball1 = self.add_to_tarball(
            [('FORMAT', format1), ('metadata', self.metadata)],
            tarball=self.tarball_fixture.get_tarball())
        tarball_fixture2 = CreateTarballFixture(
            self.tar_dir_fixture.get_temp_dir(), reldir='tarfile2',
            filename='secondtarball.tar.gz')
        self.useFixture(tarball_fixture2)
        tarball2 = self.add_to_tarball(
            [('FORMAT', format2), ('metadata', self.metadata)],
            tarball=tarball_fixture2.get_tarball())
        hp = HardwarepackHandler([tarball1, tarball2])
        with hp:
            self.assertEquals(hp.get_format(), '2.0')

    def test_get_metadata(self):
        data = 'data to test'
        metadata = self.metadata + "U_BOOT=%s\n" % data
        tarball = self.add_to_tarball(
            [('metadata', metadata)])
        hp = HardwarepackHandler([tarball])
        with hp:
            test_data, _ = hp.get_field('bootloader_file')
            self.assertEqual(test_data, data)

    def test_preserves_formatters(self):
        data = '%s%d'
        metadata = self.metadata + "U_BOOT=%s\n" % data
        tarball = self.add_to_tarball(
            [('metadata', metadata)])
        hp = HardwarepackHandler([tarball])
        with hp:
            test_data, _ = hp.get_field('bootloader_file')
            self.assertEqual(test_data, data)

    def test_creates_tempdir(self):
        tarball = self.add_to_tarball(
            [('metadata', self.metadata)])
        hp = HardwarepackHandler([tarball])
        with hp:
            self.assertTrue(os.path.exists(hp.tempdir))

    def test_tempfiles_are_removed(self):
        tempdir = None
        tarball = self.add_to_tarball(
            [('metadata', self.metadata)])
        hp = HardwarepackHandler([tarball])
        with hp:
            tempdir = hp.tempdir
        self.assertFalse(os.path.exists(tempdir))

    def test_get_file(self):
        data = 'test file contents\n'
        file_in_archive = 'testfile'
        metadata = self.metadata + "%s=%s\n" % ('U_BOOT', file_in_archive)
        tarball = self.add_to_tarball(
            [('metadata', metadata),
             (file_in_archive, data)])
        hp = HardwarepackHandler([tarball])
        with hp:
            test_file = hp.get_file('bootloader_file')
            self.assertEquals(data, open(test_file, 'r').read())

    def test_list_packages(self):
        metadata = ("format: 3.0\nname: ahwpack\nversion: 4\narchitecture: "
                    "armel\norigin: linaro\n")
        format = "3.0\n"
        tarball = self.add_to_tarball([
            ("FORMAT", format),
            ("metadata", metadata),
            ("pkgs/foo_1-1_all.deb", ''),
            ("pkgs/bar_1-1_all.deb", ''),
        ])

        hp = HardwarepackHandler([tarball], board='panda', bootloader='uefi')
        with hp:
            packages = hp.list_packages()
            names = [p[1] for p in packages]
            self.assertIn('pkgs/foo_1-1_all.deb', names)
            self.assertIn('pkgs/bar_1-1_all.deb', names)
            self.assertEqual(len(packages), 2)

    def test_find_package_for(self):
        metadata = ("format: 3.0\nname: ahwpack\nversion: 4\narchitecture: "
                    "armel\norigin: linaro\n")
        format = "3.0\n"
        tarball = self.add_to_tarball([
            ("FORMAT", format),
            ("metadata", metadata),
            ("pkgs/foo_1-3_all.deb", ''),
            ("pkgs/foo_2-5_arm.deb", ''),
            ("pkgs/bar_1-3_arm.deb", ''),
        ])

        hp = HardwarepackHandler([tarball], board='panda', bootloader='uefi')
        with hp:
            self.assertEqual(hp.find_package_for("foo")[1],
                             "pkgs/foo_1-3_all.deb")
            self.assertEqual(hp.find_package_for("bar")[1],
                             "pkgs/bar_1-3_arm.deb")
            self.assertEqual(hp.find_package_for("foo", version=2)[1],
                             "pkgs/foo_2-5_arm.deb")
            self.assertEqual(hp.find_package_for("foo", version=2,
                                                 revision=5)[1],
                             "pkgs/foo_2-5_arm.deb")
            self.assertEqual(hp.find_package_for("foo", version=2, revision=5,
                                                 architecture="arm")[1],
                             "pkgs/foo_2-5_arm.deb")
            self.assertEqual(hp.find_package_for("foo", architecture="arm")[1],
                             "pkgs/foo_2-5_arm.deb")
            self.assertEqual(hp.find_package_for("foo", architecture="all")[1],
                             "pkgs/foo_1-3_all.deb")

    def test_get_file_from_package(self):
        metadata = ("format: 3.0\nname: ahwpack\nversion: 4\narchitecture: "
                    "armel\norigin: linaro\n")
        format = "3.0\n"

        names = ['package0', 'package1', 'package2']
        files = {
            names[0]:
            ["usr/lib/u-boot/omap4_panda/u-boot.img",
             "usr/share/doc/u-boot-linaro-omap4-panda/copyright"],
            names[1]: ["usr/lib/u-boot/omap4_panda/u-boot2.img",
                       "foo/bar",
                       "flim/flam"],
            names[2]: ["some/path/config"]}

        # Generate some test packages
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))

        tarball_content = [("FORMAT", format), ("metadata", metadata)]

        package_names = []
        for package_name in names:
            # The files parameter to make_package is a list of files to create.
            # These files are text files containing package_name and their
            # path. Since package_name is different for each package, this
            # gives each file a unique content.
            deb_file_path = maker.make_package(package_name, '1.0', {},
                                               files=files[package_name])
            name = os.path.basename(deb_file_path)
            tarball_content.append((os.path.join("pkgs", name),
                                    open(deb_file_path).read()))
            package_names.append(name)

        tarball = self.add_to_tarball(tarball_content)

        hp = HardwarepackHandler([tarball], board='panda', bootloader='uefi')
        with hp:
            path = hp.get_file_from_package("some/path/config", "package2")
            self.assertTrue(path.endswith("some/path/config"))


class TestSetMetadata(TestCaseWithFixtures):

    class MockHardwarepackHandler(HardwarepackHandler):
        metadata_dict = {}

        def __enter__(self):
            return self

        def get_field(self, field):
            try:
                return self.metadata_dict[field], None
            except:
                return None, None

        def get_format(self):
            return '2.0'

        def get_file(self, file_alias):
            return None

    def test_does_not_set_if_old_format(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(None, board_conf.kernel_addr)

    def test_sets_kernel_addr(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'kernel_addr'
        data_to_set = '0x8123ABCD'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, board_conf.kernel_addr)

    def test_sets_initrd_addr(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'initrd_addr'
        data_to_set = '0x8123ABCD'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, board_conf.initrd_addr)

    def test_sets_load_addr(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'load_addr'
        data_to_set = '0x8123ABCD'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, board_conf.load_addr)

    def test_sets_serial_tty(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'serial_tty'
        data_to_set = 'ttyAA'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, board_conf.serial_tty)

    def test_sets_wired_interfaces(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'wired_interfaces'
        data_to_set = 'eth0 eth1'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, board_conf.wired_interfaces)

    def test_sets_wireless_interfaces(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'wireless_interfaces'
        data_to_set = 'wlan0 wl1'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, board_conf.wireless_interfaces)

    def test_sets_mmc_id(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'mmc_id'
        data_to_set = '0:1'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, board_conf.mmc_option)
        self.assertEquals(0, board_conf.mmc_device_id)
        self.assertEquals(0, board_conf.mmc_part_offset)

    def test_sets_boot_min_size(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'boot_min_size'
        data_to_set = '100'
        expected = align_up(int(data_to_set) * 1024 * 1024,
                            SECTOR_SIZE) / SECTOR_SIZE
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(expected, board_conf.BOOT_MIN_SIZE_S)

    def test_sets_root_min_size(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'root_min_size'
        data_to_set = '3'
        expected = align_up(int(data_to_set) * 1024 * 1024,
                            SECTOR_SIZE) / SECTOR_SIZE
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(expected, board_conf.ROOT_MIN_SIZE_S)

    def test_sets_loader_min_size(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'loader_min_size'
        data_to_set = '2'
        expected = align_up(int(data_to_set) * 1024 * 1024,
                            SECTOR_SIZE) / SECTOR_SIZE
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(expected, board_conf.LOADER_MIN_SIZE_S)

    def test_sets_partition_layout_32(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'partition_layout'
        data_to_set = 'bootfs_rootfs'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(32, board_conf.fat_size)

    def test_sets_partition_layout_16(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'partition_layout'
        data_to_set = 'bootfs16_rootfs'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(16, board_conf.fat_size)

    def test_sets_partition_layout_raises(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'partition_layout'
        data_to_set = 'bootfs_bogus_rootfs'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        self.assertRaises(
            AssertionError, board_conf.set_metadata, 'ahwpack.tar.gz')

    def test_sets_copy_files(self):
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards, 'HardwarepackHandler',
            self.MockHardwarepackHandler))
        field_to_test = 'bootloader_copy_files'
        data_to_set = {'package':
                       [{"source1": "dest1"},
                        {"source2": "dest2"}]}
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
        }

        board_conf = BoardConfig()
        board_conf.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, board_conf.bootloader_copy_files)


class TestGetMLOFile(TestCaseWithFixtures):

    def test_mlo_from_new_xloader(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        path = os.path.join(
            tempdir, 'usr', 'lib', 'x-loader', 'omap3530beagle')
        os.makedirs(path)
        mlo_path = os.path.join(path, 'MLO')
        open(mlo_path, 'w').close()
        self.assertEquals(
            mlo_path, _get_mlo_file(tempdir))

    def test_mlo_from_old_xloader(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        path = os.path.join(tempdir, 'usr', 'lib', 'x-loader-omap4')
        os.makedirs(path)
        mlo_path = os.path.join(path, 'MLO')
        open(mlo_path, 'w').close()
        self.assertEquals(
            mlo_path, _get_mlo_file(tempdir))

    def test_no_mlo_found(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        self.assertRaises(
            AssertionError, _get_mlo_file, tempdir)

    def test_more_than_one_mlo_found(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        for directory in ['x-loader-omap4', 'x-loader-omap3']:
            path = os.path.join(tempdir, 'usr', 'lib', directory)
            os.makedirs(path)
            mlo_path = os.path.join(path, 'MLO')
            open(mlo_path, 'w').close()
        self.assertRaises(
            AssertionError, _get_mlo_file, tempdir)


def _create_uboot_dir(root, flavor):
    path = os.path.join(root, 'usr', 'lib', 'u-boot', flavor)
    os.makedirs(path)
    return path


class TestGetSMDKSPL(TestCaseWithFixtures):
    def setUp(self):
            super(TestGetSMDKSPL, self).setUp()
            self.config = boards.SMDKV310Config()
            self.config.hwpack_format = HardwarepackHandler.FORMAT_1

    def test_no_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        self.assertRaises(
            AssertionError, self.config._get_samsung_spl, tempdir)

    def test_old_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        path = _create_uboot_dir(tempdir, self.config.bootloader_flavor)
        spl_path = os.path.join(path, 'v310_mmc_spl.bin')
        open(spl_path, 'w').close()
        self.assertEquals(spl_path, self.config._get_samsung_spl(tempdir))

    def test_new_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        path = _create_uboot_dir(tempdir, self.config.bootloader_flavor)
        spl_path = os.path.join(path, 'u-boot-mmc-spl.bin')
        open(spl_path, 'w').close()
        self.assertEquals(spl_path, self.config._get_samsung_spl(tempdir))

    def test_prefers_old_path(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        path = _create_uboot_dir(tempdir, self.config.bootloader_flavor)
        old_spl_path = os.path.join(path, 'v310_mmc_spl.bin')
        new_spl_path = os.path.join(path, 'u-boot-mmc-spl.bin')
        open(old_spl_path, 'w').close()
        open(new_spl_path, 'w').close()
        self.assertEquals(old_spl_path, self.config._get_samsung_spl(tempdir))


class TestGetSMDKUboot(TestCaseWithFixtures):
    def setUp(self):
        super(TestGetSMDKUboot, self).setUp()
        self.config = boards.SMDKV310Config()
        self.config.hwpack_format = HardwarepackHandler.FORMAT_1

    def test_uses_uboot_flavour(self):
        chroot_dir = "chroot"
        uboot_file = os.path.join(chroot_dir, 'usr', 'lib', 'u-boot',
                                  self.config.bootloader_flavor, 'u-boot.bin')
        self.assertEquals(
            uboot_file, self.config._get_samsung_bootloader(chroot_dir))


class TestGetOrigenSPL(TestCaseWithFixtures):
    def setUp(self):
        super(TestGetOrigenSPL, self).setUp()
        self.config = boards.OrigenConfig()
        self.config.hwpack_format = HardwarepackHandler.FORMAT_1

    def test_no_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        self.assertRaises(
            AssertionError, self.config._get_samsung_spl, tempdir)

    def test_new_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        path = _create_uboot_dir(tempdir, self.config.bootloader_flavor)
        spl_path = os.path.join(path, 'u-boot-mmc-spl.bin')
        open(spl_path, 'w').close()
        self.assertEquals(spl_path, self.config._get_samsung_spl(tempdir))


class TestGetOrigenUboot(TestGetSMDKUboot):
    def setUp(self):
        super(TestGetOrigenUboot, self).setUp()
        self.config = boards.OrigenConfig()
        self.config.hwpack_format = HardwarepackHandler.FORMAT_1


class TestGetOrigenQuadSPL(TestCaseWithFixtures):
    def setUp(self):
        super(TestGetOrigenQuadSPL, self).setUp()
        self.config = boards.OrigenQuadConfig()
        self.config.hwpack_format = HardwarepackHandler.FORMAT_1

    def test_no_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        self.assertRaises(
            AssertionError, self.config._get_samsung_spl, tempdir)

    def test_new_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        path = _create_uboot_dir(tempdir, self.config.bootloader_flavor)
        spl_path = os.path.join(path, 'origen_quad-spl.bin')
        open(spl_path, 'w').close()
        self.assertEquals(spl_path, self.config._get_samsung_spl(tempdir))


class TestGetOrigenQuadUboot(TestGetSMDKUboot):
    def setUp(self):
        super(TestGetOrigenQuadUboot, self).setUp()
        self.config = boards.OrigenQuadConfig()
        self.config.hwpack_format = HardwarepackHandler.FORMAT_1


class TestGetArndaleSPL(TestCaseWithFixtures):
    def setUp(self):
        super(TestGetArndaleSPL, self).setUp()
        self.config = boards.ArndaleConfig()
        self.config.hwpack_format = HardwarepackHandler.FORMAT_1

    def test_no_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        self.assertRaises(
            AssertionError, self.config._get_samsung_spl, tempdir)

    def test_new_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        path = _create_uboot_dir(tempdir, self.config.bootloader_flavor)
        spl_path = os.path.join(path, 'smdk5250-spl.bin')
        open(spl_path, 'w').close()
        self.assertEquals(spl_path, self.config._get_samsung_spl(tempdir))


class TestGetArndaleUboot(TestGetSMDKUboot):
    config = boards.ArndaleConfig


class TestArndaleBootFiles(TestCaseWithFixtures):
    def test_arndale_make_boot_files_v2(self):
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        board_conf = boards.ArndaleConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        board_conf.load_addr = '0x40008000'
        board_conf.boot_script = None

        board_conf.hardwarepack_handler = (
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz'))

        self.tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        self.temp_bootdir_path = os.path.join(self.tempdir, 'boot')
        self.temp_bl0_path = os.path.join(self.tempdir,
                                          'lib', 'firmware', 'arndale')
        k_img_file = os.path.join(self.tempdir, 'vmlinuz-1-arndale')
        i_img_file = os.path.join(self.tempdir, 'initrd.img-1-arndale')
        bl0_file = os.path.join(self.temp_bl0_path, 'arndale-bl1.bin')
        os.makedirs(self.temp_bl0_path)
        open(bl0_file, 'w').close()

        boot_env = {'ethact': 'smc911x-0',
                    'initrd_high': '0xffffffff',
                    'ethaddr': '00:40:5c:26:0a:5b',
                    'fdt_high': '0xffffffff',
                    'bootcmd': 'fatload mmc 0:2 None uImage; bootm None',
                    'bootargs': 'root=UUID=test_boot_env_uuid rootwait ro'}

        board_conf._make_boot_files_v2(
            boot_env=boot_env,
            chroot_dir=self.tempdir,
            boot_dir=self.temp_bootdir_path,
            boot_device_or_file='boot_device_or_file',
            k_img_data=k_img_file,
            i_img_data=i_img_file,
            d_img_data=None)

        expected_commands = [
            ('sudo -E dd if=%s of=boot_device_or_file bs=512 conv=notrunc '
             'seek=1' % bl0_file),
            ('sudo -E mkimage -A arm -O linux -T kernel -C none -a %s -e %s '
             '-n Linux -d %s %s/uImage'
             % (board_conf.load_addr, board_conf.load_addr,
                k_img_file, self.temp_bootdir_path)),
            ('sudo -E mkimage -A arm -O linux -T ramdisk -C none -a 0 -e 0 '
             '-n initramfs -d %s %s/uInitrd'
             % (i_img_file, self.temp_bootdir_path))]
        self.assertEqual(expected_commands,
                         popen_fixture.mock.commands_executed)
        shutil.rmtree(self.tempdir)


class TestCreateToc(TestCaseWithFixtures):
    ''' Tests boards.SnowballEmmcConfig.create_toc()'''

    def setUp(self):
        ''' Create a temporary directory to work in'''
        super(TestCreateToc, self).setUp()
        self.tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        #Create the test's input data structures
        zero = '\x00\x00\x00\x00'
        line1 = zero + zero + zero + zero + zero + 'b' + zero + zero + \
            '\x00\x00\x00'
        maxint = '\xFF\xFF\xFF\x7F'
        minint = '\xFF\xFF\xFF\xFF'
        line2 = maxint + maxint + zero + minint + minint + \
            'hello' + zero + '\x00\x00\x00'
        line3 = '\x01\x00\x00\x00' '\x64\x00\x00\x00' + zero + \
            '\x05\x00\x00\x00' '\x05\x00\x00\x00' \
            'hello' + zero + '\x00\x00\x00'
        self.expected = line1 + line2 + line3
        self.board_conf = boards.SnowballEmmcConfig()

    def create_files_structure(self, src_data):
        ''' Creates the data structure that the tested function
            needs as input'''
        files = []
        for line in src_data:
            files.append({'section_name': line[5],
                          'filename': 'N/A',
                          'align': line[3],
                          'offset': line[0],
                          'size': line[1],
                          'load_adress': 'N/A'})
        return files

    def test_create_toc_normal_case(self):
        ''' Creates a toc file, and then reads the created
            file and compares it to precomputed data'''
        correct_data = [(0, 0, 0, 0, 0, 'b'),
                        (0x7FFFFFFF, 0x7FFFFFFF, 0x7FFFFFFF, -1, -1, 'hello'),
                        (1, 100, 1000, 5, 10, 'hello')]
        files = self.create_files_structure(correct_data)
        filename = os.path.join(self.tempdir, 'toc')
        with open(filename, 'w') as f:
            self.board_conf.create_toc(f, files)
        with open(filename, 'r') as f:
            actual = f.read()
        self.assertEquals(96, len(actual))
        for i in range(len(actual)):
            self.assertEquals(
                self.expected[i], actual[i], 'Mismatch at ix'
                ' %d, ref=%c, actual=%c' % (i, self.expected[i], actual[i]))

    def test_create_toc_error_too_large_section_name(self):
        '''Verify that trying to write past the end of the
           section name field raises an exception'''
        illegal_name_data = [(0, 0, 0, 0, 0, 'Too_longName')]
        files = self.create_files_structure(illegal_name_data)
        with open(os.path.join(self.tempdir, 'toc'), 'w') as f:
            self.assertRaises(AssertionError,
                              self.board_conf.create_toc,
                              f, files)

    def test_create_toc_error_negative_unsigned(self):
        '''Verify that trying to write a negative number to an unsigned
           field raises an exception'''
        illegal_unsigned_data = [(-3, 0, 0, 0, 0, 'xxx')]
        files = self.create_files_structure(illegal_unsigned_data)
        with open(os.path.join(self.tempdir, 'toc'), 'w') as f:
            self.assertRaises(struct.error,
                              self.board_conf.create_toc,
                              f, files)


class TestSnowballBootFiles(TestCaseWithFixtures):
    ''' Tests boards.SnowballEmmcConfig.install_snowball_boot_loader()'''
    ''' Tests boards.SnowballEmmcConfig._make_boot_files()'''
    ''' Tests boards.SnowballEmmcConfig.get_file_info()'''

    def setUp(self):
        ''' Create temporary directory to work in'''
        super(TestSnowballBootFiles, self).setUp()
        self.tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        self.temp_bootdir_path = os.path.join(self.tempdir, 'boot')
        self.temp_configdir_path = os.path.join(self.tempdir, 'startfiles')
        if not os.path.exists(self.temp_bootdir_path):
            os.makedirs(self.temp_bootdir_path)
        if not os.path.exists(self.temp_configdir_path):
            os.makedirs(self.temp_configdir_path)
        self.snowball_config = get_board_config('snowball_emmc')
        self.snowball_config.hwpack_format = HardwarepackHandler.FORMAT_1

    def setupFiles(self):
        return self.create_test_files(self.temp_bootdir_path)

    def setupAndroidFiles(self):
        return self.create_test_files(self.temp_configdir_path)

    def create_test_files(self, path):
        ''' Adds some files in the temp dir that the tested function
            can use as input:
            * A config file, which the tested function reads to
              discover which binary files should be written to
              the loader partition.
            * Test versions of the binary files themselves,
              containing dummy data.
            Returns the expected value that the tested function should
            return, given these input files.  '''
        src_data = [('ISSW', 'boot_image_issw.bin', -1, 0, '5'),
                    ('X-LOADER', 'boot_image_x-loader.bin', -1, 0, '6'),
                    ('MEM_INIT', 'mem_init.bin', 0, 0x160000, '7'),
                    ('PWR_MGT', 'power_management.bin', 0, 0x170000, '8'),
                    ('NORMAL', 'u-boot.bin', 0, 0xBA0000, '9'),
                    ('UBOOT_ENV', 'u-boot-env.bin', 0, 0x00C1F000, '10')]
        # Create a config file
        cfg_file = os.path.join(
            path, self.snowball_config.snowball_startup_files_config)
        with open(cfg_file, 'w') as f:
            for line in src_data:
                # Write comments, so we test that the parser can read them
                f.write('#Yet another comment\n')
                # Write whitespace, so we test that the parser can handle them
                f.write('   \n\t\n \t \t \n')
                f.write('%s %s %i %#x %s\n' % line)
        expected = []
        # Define dummy binary files, containing nothing but their own
        # section names.
        for line in src_data:
            with open(os.path.join(path, line[1]), 'w') as f:
                f.write(line[0])
        #define the expected values read from the config file
        expected = []
        ofs = [self.snowball_config.TOC_SIZE,
               self.snowball_config.TOC_SIZE + len('ISSW'), 0x160000,
               0x170000, 0xBA0000, 0xC1F000]
        size = [len('ISSW'), len('X-LOADER'), len('MEM_INIT'),
                len('PWR_MGT'), len('NORMAL'), len('UBOOT_ENV')]
        i = 0
        for line in src_data:
            filename = os.path.join(path, line[1])
            expected.append({'section_name': line[0],
                             'filename': filename,
                             'align': int(line[2]),
                             'offset': ofs[i],
                             'size': long(size[i]),
                             'load_adress': line[4]})
            i += 1
        return expected

    def test_get_file_info_relative_path(self):
        # Create a config file
        cfg_file = os.path.join(
            self.temp_bootdir_path,
            self.snowball_config.snowball_startup_files_config)
        uboot_file = 'u-boot.bin'
        with open(cfg_file, 'w') as f:
                f.write('%s %s %i %#x %s\n' % ('NORMAL', uboot_file, 0,
                                               0xBA0000, '9'))
        with open(os.path.join(self.temp_bootdir_path, uboot_file), 'w') as f:
            file_info = self.snowball_config.get_file_info(
                self.tempdir, self.temp_bootdir_path)
        self.assertEquals(file_info[0]['filename'],
                          os.path.join(self.temp_bootdir_path, uboot_file))

    def test_get_file_info_abs_path(self):
        # Create a config file
        cfg_file = os.path.join(
            self.temp_bootdir_path,
            self.snowball_config.snowball_startup_files_config)
        uboot_dir = tempfile.mkdtemp(dir=self.tempdir)
        uboot_file = os.path.join(uboot_dir, 'u-boot.bin')
        uboot_relative_file = uboot_file.replace(self.tempdir, '')
        with open(cfg_file, 'w') as f:
                f.write('%s %s %i %#x %s\n' % (
                        'NORMAL', uboot_relative_file, 0, 0xBA0000, '9'))
        with open(uboot_file, 'w') as f:
            file_info = self.snowball_config.get_file_info(
                self.tempdir, self.temp_bootdir_path)
        self.assertEquals(file_info[0]['filename'], uboot_file)

    def test_get_file_info_raises(self):
        # Create a config file
        cfg_file = os.path.join(
            self.temp_bootdir_path,
            self.snowball_config.snowball_startup_files_config)
        with open(cfg_file, 'w') as f:
                f.write('%s %s %i %#x %s\n' % ('NORMAL', 'u-boot.bin', 0,
                                               0xBA0000, '9'))
        self.assertRaises(
            AssertionError, self.snowball_config.get_file_info,
            self.tempdir, self.temp_bootdir_path)

    def test_file_name_size(self):
        ''' Test using a to large toc file '''
        _, toc_filename = tempfile.mkstemp()
        atexit.register(os.unlink, toc_filename)
        filedata = 'X'
        bytes = self.snowball_config.TOC_SIZE + 1
        tmpfile = open(toc_filename, 'wb')
        for n in xrange(bytes):
            tmpfile.write(filedata)
        tmpfile.close()
        files = self.setupFiles()
        self.assertRaises(
            AssertionError,
            self.snowball_config.install_snowball_boot_loader,
            toc_filename, files, "boot_device_or_file",
            self.snowball_config.SNOWBALL_LOADER_START_S)

    def test_install_snowball_boot_loader_toc_dont_delete(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        toc_filename = self.createTempFileAsFixture()
        files = self.setupFiles()
        self.snowball_config.install_snowball_boot_loader(
            toc_filename,
            files, "boot_device_or_file",
            self.snowball_config.SNOWBALL_LOADER_START_S)
        expected = [
            '%s dd if=%s of=boot_device_or_file bs=512 conv=notrunc'
            ' seek=%s' % (sudo_args, toc_filename,
                          self.snowball_config.SNOWBALL_LOADER_START_S),
            '%s dd if=%s/boot_image_issw.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=257' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/boot_image_x-loader.bin of=boot_device_or_file'
            ' bs=1 conv=notrunc seek=131588'
            % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/mem_init.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=3072' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/power_management.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=3200' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/u-boot.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=24064' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/u-boot-env.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=25080' % (sudo_args, self.temp_bootdir_path)]

        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_install_snowball_boot_loader_toc_delete(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        toc_filename = self.createTempFileAsFixture()
        files = self.setupFiles()
        self.snowball_config.install_snowball_boot_loader(
            toc_filename,
            files, "boot_device_or_file",
            self.snowball_config.SNOWBALL_LOADER_START_S, True)
        expected = [
            '%s dd if=%s of=boot_device_or_file bs=512 conv=notrunc'
            ' seek=%s' % (sudo_args, toc_filename,
                          self.snowball_config.SNOWBALL_LOADER_START_S),
            '%s dd if=%s/boot_image_issw.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=257' % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/boot_image_issw.bin' % (sudo_args,
                                              self.temp_bootdir_path),
            '%s dd if=%s/boot_image_x-loader.bin of=boot_device_or_file'
            ' bs=1 conv=notrunc seek=131588'
            % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/boot_image_x-loader.bin' % (sudo_args,
                                                  self.temp_bootdir_path),
            '%s dd if=%s/mem_init.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=3072' % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/mem_init.bin' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/power_management.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=3200' % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/power_management.bin' % (sudo_args,
                                               self.temp_bootdir_path),
            '%s dd if=%s/u-boot.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=24064' % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/u-boot.bin' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/u-boot-env.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=25080' % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/u-boot-env.bin' % (sudo_args, self.temp_bootdir_path)]

        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_install_snowball_boot_loader_toc_android(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        toc_filename = self.createTempFileAsFixture()
        files = self.setupFiles()
        board_conf = AndroidSnowballEmmcConfig()
        board_conf.install_snowball_boot_loader(
            toc_filename, files, "boot_device_or_file",
            board_conf.SNOWBALL_LOADER_START_S)
        expected = [
            '%s dd if=%s of=boot_device_or_file bs=512 conv=notrunc'
            ' seek=%s' % (sudo_args, toc_filename,
                          board_conf.SNOWBALL_LOADER_START_S),
            '%s dd if=%s/boot_image_issw.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=257' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/boot_image_x-loader.bin of=boot_device_or_file'
            ' bs=1 conv=notrunc seek=131588'
            % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/mem_init.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=3072' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/power_management.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=3200' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/u-boot.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=24064' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/u-boot-env.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=25080' % (sudo_args, self.temp_bootdir_path)]

        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_snowball_make_boot_files(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(
            MockSomethingFixture(tempfile, 'mkstemp',
                                 lambda:
                                 (-1, '/tmp/temp_snowball_make_boot_files')))
        self.setupFiles()
        k_img_file = os.path.join(self.tempdir, 'vmlinuz-1-ux500')
        i_img_file = os.path.join(self.tempdir, 'initrd.img-1-ux500')

        boot_env = self.snowball_config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=test_boot_env_uuid",
            i_img_data=None, d_img_data=None)
        self.snowball_config._make_boot_files(boot_env, self.tempdir,
                                              self.temp_bootdir_path,
                                              'boot_device_or_file',
                                              k_img_file, i_img_file, None)
        expected = [
            '%s mkimage -A arm -O linux -T kernel -C none -a 0x00008000 -e'
            ' 0x00008000 -n Linux -d %s %s/boot/uImage'
            % (sudo_args, k_img_file, self.tempdir),
            '%s cp /tmp/temp_snowball_make_boot_files %s/boot/boot.txt'
            % (sudo_args, self.tempdir),
            '%s mkimage -A arm -O linux -T script -C none -a 0 -e 0 -n boot'
            ' script -d %s/boot/boot.txt %s/boot/flash.scr'
            % (sudo_args, self.tempdir, self.tempdir),
            '%s dd if=/tmp/temp_snowball_make_boot_files'
            ' of=boot_device_or_file bs=512 conv=notrunc seek=256'
            % (sudo_args),
            '%s dd if=%s/boot/boot_image_issw.bin of=boot_device_or_file'
            ' bs=512 conv=notrunc seek=257' % (sudo_args, self.tempdir),
            '%s rm %s/boot_image_issw.bin' % (sudo_args,
                                              self.temp_bootdir_path),
            '%s dd if=%s/boot/boot_image_x-loader.bin of=boot_device_or_file'
            ' bs=1 conv=notrunc seek=131588' % (sudo_args, self.tempdir),
            '%s rm %s/boot_image_x-loader.bin' % (sudo_args,
                                                  self.temp_bootdir_path),
            '%s dd if=%s/boot/mem_init.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=3072' % (sudo_args, self.tempdir),
            '%s rm %s/mem_init.bin' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/boot/power_management.bin of=boot_device_or_file'
            ' bs=512 conv=notrunc seek=3200' % (sudo_args, self.tempdir),
            '%s rm %s/power_management.bin' % (sudo_args,
                                               self.temp_bootdir_path),
            '%s dd if=%s/boot/u-boot.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=24064' % (sudo_args, self.tempdir),
            '%s rm %s/u-boot.bin' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/boot/u-boot-env.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=25080' % (sudo_args, self.tempdir),
            '%s rm %s/u-boot-env.bin' % (sudo_args, self.temp_bootdir_path),
            '%s rm /tmp/temp_snowball_make_boot_files' % (sudo_args),
            '%s rm %s/startfiles.cfg' % (sudo_args, self.temp_bootdir_path)]

        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_missing_files(self):
        '''When the files cannot be read, an IOError should be raised'''
        self.assertRaises(IOError,
                          self.snowball_config.get_file_info,
                          self.tempdir, self.temp_bootdir_path)

    def test_normal_case(self):
        expected = self.setupFiles()
        actual = self.snowball_config.get_file_info(
            self.tempdir, self.temp_bootdir_path)
        self.assertEquals(expected, actual)


class TestBootSteps(TestCaseWithFixtures):

    def setUp(self):
        super(TestBootSteps, self).setUp()
        self.funcs_calls = []
        self.mock_all_boards_funcs()

    def mock_all_boards_funcs(self):
        """Mock functions of boards module with a call tracer."""

        def mock_func_creator(name):
            return lambda *args, **kwargs: self.funcs_calls.append(name)

        for name in dir(boards):
            attr = getattr(boards, name)
            if isinstance(attr, types.FunctionType):
                self.useFixture(MockSomethingFixture(
                    linaro_image_tools.media_create.boards, name,
                    mock_func_creator(name)))

    def mock_set_appropriate_serial_tty(self, config):

        def set_appropriate_serial_tty_mock(chroot_dir):
            config.serial_tty = config._serial_tty

        config.set_appropriate_serial_tty = MagicMock(
            side_effect=set_appropriate_serial_tty_mock)

    def make_boot_files(self, config):
        def _get_kflavor_files_mock(path):
            if config.dtb_name is None:
                return (path, path, None)
            return (path, path, path)

        config._get_kflavor_files = MagicMock(
            side_effect=_get_kflavor_files_mock)

        config.make_boot_files('', False, False, [], '', '', '', '')

    def test_vexpress_steps(self):
        board_conf = boards.VexpressConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.make_boot_files(board_conf)
        expected = ['make_uImage', 'make_uInitrd']
        self.assertEqual(expected, self.funcs_calls)

    def test_vexpress_a9_steps(self):
        board_conf = boards.VexpressA9Config()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.make_boot_files(board_conf)
        expected = ['make_uImage', 'make_uInitrd']
        self.assertEqual(expected, self.funcs_calls)

    def test_mx5_steps(self):
        board_conf = boards.Mx5Config()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        board_conf.bootloader_flavor = 'bootloader_flavor'
        board_conf.hardwarepack_handler = (
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz'))
        board_conf.hardwarepack_handler.get_format = (
            lambda: HardwarepackHandler.FORMAT_1)
        self.make_boot_files(board_conf)
        expected = [
            'install_mx5_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_dtb', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_smdkv310_steps(self):
        board_conf = boards.SMDKV310Config()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        board_conf.install_samsung_boot_loader = MagicMock()
        board_conf.install_samsung_boot_loader.return_value = \
            self.funcs_calls.append('install_samsung_boot_loader')
        self.useFixture(MockSomethingFixture(os.path, 'exists',
                                             lambda file: True))
        board_conf.hardwarepack_handler = (
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz'))
        board_conf.hardwarepack_handler.get_format = (
            lambda: HardwarepackHandler.FORMAT_1)
        self.make_boot_files(board_conf)
        expected = [
            'install_samsung_boot_loader', 'make_flashable_env', '_dd',
            'make_uImage', 'make_uInitrd', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_origen_steps(self):
        board_conf = boards.OrigenConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        board_conf.install_samsung_boot_loader = MagicMock()
        board_conf.install_samsung_boot_loader.return_value = \
            self.funcs_calls.append('install_samsung_boot_loader')
        self.useFixture(MockSomethingFixture(os.path, 'exists',
                                             lambda file: True))
        board_conf.hardwarepack_handler = (
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz'))
        board_conf.hardwarepack_handler.get_format = (
            lambda: HardwarepackHandler.FORMAT_1)
        self.make_boot_files(board_conf)
        expected = [
            'install_samsung_boot_loader', 'make_flashable_env', '_dd',
            'make_uImage', 'make_uInitrd', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_origen_quad_steps(self):
        board_conf = boards.OrigenQuadConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        board_conf.install_samsung_boot_loader = MagicMock()
        board_conf.install_samsung_boot_loader.return_value = \
            self.funcs_calls.append('install_samsung_boot_loader')

        self.useFixture(MockSomethingFixture(os.path, 'exists',
                                             lambda file: True))
        board_conf.hardwarepack_handler = (
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz'))
        board_conf.hardwarepack_handler.get_format = (
            lambda: HardwarepackHandler.FORMAT_1)
        self.make_boot_files(board_conf)
        expected = [
            'install_samsung_boot_loader', 'make_flashable_env', '_dd',
            'make_uImage', 'make_uInitrd', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_arndale_steps(self):
        board_conf = boards.ArndaleConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        board_conf.install_samsung_boot_loader = MagicMock()
        board_conf.install_samsung_boot_loader.return_value = \
            self.funcs_calls.append('install_samsung_boot_loader')

        self.useFixture(MockSomethingFixture(os.path, 'exists',
                                             lambda file: True))
        board_conf.hardwarepack_handler = (
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz'))
        board_conf.hardwarepack_handler.get_format = (
            lambda: '1.0')
        self.make_boot_files(board_conf)
        expected = [
            'install_samsung_boot_loader', 'make_flashable_env', '_dd',
            'make_uImage', 'make_uInitrd', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_ux500_steps(self):
        board_conf = boards.Ux500Config()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.make_boot_files(board_conf)
        expected = ['make_uImage', 'make_uInitrd', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_snowball_sd_steps(self):
        board_conf = boards.SnowballSdConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.make_boot_files(board_conf)
        expected = ['make_uImage', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_panda_steps(self):
        board_conf = boards.PandaConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.mock_set_appropriate_serial_tty(board_conf)
        self.make_boot_files(board_conf)
        expected = [
            'install_omap_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_dtb', 'make_boot_script', 'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_beagle_steps(self):
        board_conf = boards.BeagleConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.mock_set_appropriate_serial_tty(board_conf)
        self.make_boot_files(board_conf)
        expected = [
            'install_omap_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_dtb', 'make_boot_script', 'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_igep_steps(self):
        board_conf = boards.IgepConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.mock_set_appropriate_serial_tty(board_conf)
        self.make_boot_files(board_conf)
        expected = [
            'make_uImage', 'make_uInitrd', 'make_dtb', 'make_boot_script',
            'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_overo_steps(self):
        board_conf = boards.OveroConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.mock_set_appropriate_serial_tty(board_conf)
        self.make_boot_files(board_conf)
        expected = [
            'install_omap_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_dtb', 'make_boot_script', 'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_highbank_steps(self):
        board_conf = boards.HighBankConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_beaglbone_steps(self):
        board_conf = boards.BeagleBoneConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.mock_set_appropriate_serial_tty(board_conf)
        self.make_boot_files(board_conf)
        expected = [
            'install_omap_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_dtb', 'make_boot_script', 'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_aa9_steps(self):
        board_conf = boards.Aa9Config()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        expected = []
        self.assertEqual(expected, self.funcs_calls)


class TestPopulateRawPartition(TestCaseWithFixtures):

    def setUp(self):
        super(TestPopulateRawPartition, self).setUp()
        self.funcs_calls = []
        self.mock_all_boards_funcs()

    def mock_all_boards_funcs(self):
        """Mock functions of boards module with a call tracer."""

        def mock_func_creator(name):
            return lambda *args, **kwargs: self.funcs_calls.append(name)

        for name in dir(boards):
            attr = getattr(boards, name)
            if isinstance(attr, types.FunctionType):
                self.useFixture(MockSomethingFixture(
                    linaro_image_tools.media_create.boards, name,
                    mock_func_creator(name)))

    def populate_raw_partition(self, config):
        config.populate_raw_partition('', '')

    def test_snowball_config_raises(self):
        self.assertRaises(NotImplementedError,
                          boards.SnowballSdConfig().snowball_config, '')

    def test_beagle_raw(self):
        self.populate_raw_partition(android_boards.AndroidBeagleConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_panda_raw(self):
        self.populate_raw_partition(android_boards.AndroidPandaConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_snowball_sd_raw(self):
        self.populate_raw_partition(boards.SnowballSdConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_snowball_emmc_raw(self):
        def mock_func_creator(name):
            return classmethod(
                lambda *args, **kwargs: self.funcs_calls.append(name))

        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards.SnowballEmmcConfig,
            'get_file_info',
            mock_func_creator('get_file_info')))
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards.SnowballEmmcConfig,
            'create_toc',
            mock_func_creator('create_toc')))
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards.SnowballEmmcConfig,
            'install_snowball_boot_loader',
            mock_func_creator('install_snowball_boot_loader')))
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.boards.SnowballEmmcConfig,
            'delete_file',
            mock_func_creator('delete_file')))
        self.populate_raw_partition(boards.SnowballEmmcConfig())
        expected = ['get_file_info', 'create_toc',
                    'install_snowball_boot_loader', 'delete_file',
                    'delete_file']
        # Test that we run the Snowball populate_raw_partition() and
        # delete both the toc and startfiles.
        self.assertEqual(expected, self.funcs_calls)

    def test_smdkv310_raw(self):
        self.useFixture(MockSomethingFixture(os.path, 'getsize',
                                             lambda file: 1))

        self.populate_raw_partition(boards.SMDKV310Config())
        expected = ['_dd', '_dd', '_dd']
        self.assertEqual(expected, self.funcs_calls)

    def test_mx53loco_raw(self):
        self.populate_raw_partition(boards.Mx53LoCoConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_origen_raw(self):
        self.useFixture(MockSomethingFixture(os.path, 'getsize',
                                             lambda file: 1))

        self.populate_raw_partition(boards.OrigenConfig())
        expected = ['_dd', '_dd', '_dd']
        self.assertEqual(expected, self.funcs_calls)

    def test_origen_quad_raw(self):
        # Need to mock this since files do not exist here, and
        # an Exception is raised.
        self.useFixture(
            MockSomethingFixture(os.path, 'exists', lambda exists: True))

        self.populate_raw_partition(boards.OrigenQuadConfig())
        expected = ['_dd', '_dd', '_dd', '_dd', '_dd']
        self.assertEqual(expected, self.funcs_calls)

    def test_origen_quad_raises(self):
        board_conf = boards.OrigenQuadConfig()
        self.assertRaises(
            boards.BoardException, board_conf.populate_raw_partition, '', '')

    def test_arndale_raw(self):
        self.useFixture(MockSomethingFixture(os.path, 'getsize',
                                             lambda file: 1))

        self.populate_raw_partition(boards.ArndaleConfig())
        expected = ['_dd', '_dd', '_dd']
        self.assertEqual(expected, self.funcs_calls)

    def test_vexpress_a9_raw(self):
        self.populate_raw_partition(boards.VexpressA9Config())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_highbank_raw(self):
        self.populate_raw_partition(boards.HighBankConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_beaglebone_raw(self):
        self.populate_raw_partition(boards.BeagleBoneConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_aa9_raw(self):
        self.populate_raw_partition(boards.Aa9Config())
        expected = []
        self.assertEqual(expected, self.funcs_calls)


class TestPopulateRawPartitionAndroid(TestCaseWithFixtures):

    def setUp(self):
        super(TestPopulateRawPartitionAndroid, self).setUp()
        self.funcs_calls = []

    def populate_raw_partition(self, config):
        config.populate_raw_partition('', '')

    def test_beagle_raw(self):
        self.populate_raw_partition(android_boards.AndroidBeagleConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_panda_raw(self):
        self.populate_raw_partition(android_boards.AndroidPandaConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_snowball_sd_raw(self):
        self.populate_raw_partition(android_boards.AndroidSnowballSdConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_snowball_emmc_raw(self):
        def mock_func_creator(name):
            return classmethod(
                lambda *args, **kwargs: self.funcs_calls.append(name))

        self.useFixture(MockSomethingFixture(os.path, 'exists',
                                             lambda file: True))
        fixture = MockCmdRunnerPopenFixture()
        self.useFixture(fixture)
        expected_commands = ['sudo -E cp boot/u-boot.bin ./startupfiles']

        self.useFixture(MockSomethingFixture(
            android_boards.AndroidSnowballEmmcConfig,
            'get_file_info',
            mock_func_creator('get_file_info')))
        self.useFixture(MockSomethingFixture(
            android_boards.AndroidSnowballEmmcConfig,
            'create_toc',
            mock_func_creator('create_toc')))
        self.useFixture(MockSomethingFixture(
            android_boards.AndroidSnowballEmmcConfig,
            'install_snowball_boot_loader',
            mock_func_creator('install_snowball_boot_loader')))
        self.useFixture(MockSomethingFixture(
            android_boards.AndroidSnowballEmmcConfig,
            'delete_file',
            mock_func_creator('delete_file')))
        self.populate_raw_partition(android_boards.AndroidSnowballEmmcConfig())
        expected_calls = ['get_file_info', 'create_toc',
                          'install_snowball_boot_loader', 'delete_file']
        # Test that we copy the u-boot files to the local startupfiles dir.
        self.assertEqual(expected_commands, fixture.mock.commands_executed)
        # Test that we run the Snowball populate_raw_partition() and only
        # delete the toc.
        self.assertEqual(expected_calls, self.funcs_calls)

    def test_smdkv310_raw(self):
        fixture = MockCmdRunnerPopenFixture()
        self.useFixture(fixture)
        expected_commands = [
            'sudo -E dd if=/dev/zero of= bs=512 conv=notrunc count=32 seek=33',
            ('sudo -E dd if=boot/u-boot-mmc-spl.bin of= '
             'bs=512 conv=notrunc seek=1'),
            'sudo -E dd if=boot/u-boot.bin of= bs=512 conv=notrunc seek=65']
        self.useFixture(MockSomethingFixture(os.path, 'getsize',
                                             lambda file: 1))

        self.populate_raw_partition(android_boards.AndroidSMDKV310Config())
        expected_calls = []
        # Test that we dd the files
        self.assertEqual(expected_commands, fixture.mock.commands_executed)
        self.assertEqual(expected_calls, self.funcs_calls)

    def test_mx53loco_raw(self):
        self.populate_raw_partition(android_boards.AndroidMx53LoCoConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)

    def test_origen_raw(self):
        fixture = MockCmdRunnerPopenFixture()
        self.useFixture(fixture)
        expected_commands = [
            'sudo -E dd if=/dev/zero of= bs=512 conv=notrunc count=32 seek=33',
            ('sudo -E dd if=boot/u-boot-mmc-spl.bin of= bs=512 '
             'conv=notrunc seek=1'),
            'sudo -E dd if=boot/u-boot.bin of= bs=512 conv=notrunc seek=65']
        self.useFixture(MockSomethingFixture(os.path, 'getsize',
                                             lambda file: 1))

        self.populate_raw_partition(android_boards.AndroidOrigenConfig())
        expected = []
        # Test that we dd the files
        self.assertEqual(expected_commands, fixture.mock.commands_executed)
        self.assertEqual(expected, self.funcs_calls)

    def test_origen_quad_raw(self):
        fixture = MockCmdRunnerPopenFixture()
        self.useFixture(fixture)
        expected_commands = [
            ('sudo -E dd if=/dev/zero of= bs=512 conv=notrunc count=32 '
             'seek=1601'),
            ('sudo -E dd if=boot/origen_quad.bl1.bin of= bs=512 '
             'conv=notrunc seek=1'),
            ('sudo -E dd if=boot/origen_quad-spl.bin.signed of= bs=512 '
             'conv=notrunc seek=31'),
            ('sudo -E dd if=boot/u-boot.bin of= bs=512 conv=notrunc '
             'seek=63'),
            ('sudo -E dd if=boot/exynos4x12.tzsw.signed.img of= bs=512 '
             'conv=notrunc seek=761')
        ]

        self.useFixture(
            MockSomethingFixture(os.path, 'exists', lambda exists: True))

        self.populate_raw_partition(android_boards.AndroidOrigenQuadConfig())
        expected = []
        # Test that we dd the files
        self.assertEqual(expected_commands, fixture.mock.commands_executed)
        self.assertEqual(expected, self.funcs_calls)

    def test_vexpress_raw(self):
        self.populate_raw_partition(android_boards.AndroidVexpressConfig())
        expected = []
        self.assertEqual(expected, self.funcs_calls)


class TestAlignPartition(TestCase):

    def test_align_up_none(self):
        self.assertEqual(1024, align_up(1024, 1))

    def test_align_up_no_rounding(self):
        self.assertEqual(512, align_up(512, 512))

    def test_align_up_rounding(self):
        self.assertEqual(512, align_up(1, 512))

    def test_align_partition_4_mib_4_mib(self):
        expected = (4 * 1024 * 1024, 8 * 1024 * 1024 - 1, 4 * 1024 * 1024)
        self.assertEqual(expected,
                         align_partition(1, 1,
                                         4 * 1024 * 1024, 4 * 1024 * 1024))

    def test_align_partition_none_4_mib(self):
        expected = (1, 4 * 1024 * 1024 - 1, 4 * 1024 * 1024 - 1)
        self.assertEqual(expected,
                         align_partition(1, 1, 1, 4 * 1024 * 1024))


class TestFixForBug697824(TestCaseWithFixtures):

    def mock_set_appropriate_serial_tty(self, config):

        def set_appropriate_serial_tty_mock(arg):
            self.set_appropriate_serial_tty_called = True

        # Need to mock all the calls done from make_boot_files in order
        # to be able to correctly call it.
        config._get_kflavor_files = MagicMock(return_value=('', '', ''))
        config._get_boot_env = MagicMock(return_value=None)
        config._make_boot_files = MagicMock()
        config._make_boot_files_v2 = MagicMock()
        config.set_appropriate_serial_tty = MagicMock(
            side_effect=set_appropriate_serial_tty_mock)

    def test_omap_make_boot_files(self):
        self.set_appropriate_serial_tty_called = False

        board_conf = boards.BeagleConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.mock_set_appropriate_serial_tty(board_conf)
        # We don't need to worry about what's passed to make_boot_files()
        # because we mock the method which does the real work above and here
        # we're only interested in ensuring that OmapConfig.make_boot_files()
        # calls set_appropriate_serial_tty().
        board_conf.make_boot_files(
            None, None, None, None, None, None, None, None)
        self.assertTrue(
            self.set_appropriate_serial_tty_called,
            "make_boot_files didn't call set_appropriate_serial_tty")

    def test_omap_make_boot_files_v2(self):
        self.set_appropriate_serial_tty_called = False

        board_conf = boards.BeagleConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_2
        self.mock_set_appropriate_serial_tty(board_conf)
        # We don't need to worry about what's passed to make_boot_files()
        # because we mock the method which does the real work above and here
        # we're only interested in ensuring that OmapConfig.make_boot_files()
        # does not call set_appropriate_serial_tty().
        board_conf.make_boot_files(
            None, None, None, None, None, None, None, None)
        self.assertFalse(
            self.set_appropriate_serial_tty_called,
            "make_boot_files called set_appropriate_serial_tty")

    def test_set_appropriate_serial_tty_old_kernel(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        boot_dir = os.path.join(tempdir, 'boot')
        os.makedirs(boot_dir)
        open(os.path.join(boot_dir, 'vmlinuz-2.6.35-23-foo'), 'w').close()
        board_conf = boards.BeagleConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        board_conf.set_appropriate_serial_tty(tempdir)
        self.assertEquals('ttyS2', board_conf.serial_tty)

    def test_set_appropriate_serial_tty_new_kernel(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        boot_dir = os.path.join(tempdir, 'boot')
        os.makedirs(boot_dir)
        open(os.path.join(boot_dir, 'vmlinuz-2.6.36-13-foo'), 'w').close()
        board_conf = boards.BeagleConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        board_conf.set_appropriate_serial_tty(tempdir)
        self.assertEquals('ttyO2', board_conf.serial_tty)

    def test_set_appropriate_serial_tty_three_dot_oh_kernel(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        boot_dir = os.path.join(tempdir, 'boot')
        os.makedirs(boot_dir)
        open(os.path.join(boot_dir, 'vmlinuz-3.0-13-foo'), 'w').close()
        board_conf = boards.BeagleConfig()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        board_conf.set_appropriate_serial_tty(tempdir)
        self.assertEquals('ttyO2', board_conf.serial_tty)


class TestGetSfdiskCmd(TestCase):

    def set_up_config(self, config):
        config.hwpack_format = HardwarepackHandler.FORMAT_1

    def test_default(self):
        board_conf = BoardConfig()
        self.set_up_config(board_conf)
        self.assertEqual(
            '63,106432,0x0C,*\n106496,,,-', board_conf.get_sfdisk_cmd())

    def test_default_aligned(self):
        board_conf = BoardConfig()
        self.set_up_config(board_conf)
        self.assertEqual(
            '8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd(should_align_boot_part=True))

    def test_mx5(self):
        board_conf = boards.Mx5Config()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        self.assertEqual(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_snowball_sd(self):
        board_conf = boards.SnowballSdConfig()
        self.set_up_config(board_conf)
        self.assertEqual(
            '63,106432,0x0C,*\n106496,,,-', board_conf.get_sfdisk_cmd())

    def test_snowball_emmc(self):
        board_conf = boards.SnowballEmmcConfig()
        self.set_up_config(board_conf)
        self.assertEqual(
            '256,7936,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_smdkv310(self):
        board_conf = get_board_config('smdkv310')
        self.set_up_config(board_conf)
        self.assertEquals(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_origen(self):
        board_conf = get_board_config('origen')
        self.set_up_config(board_conf)
        self.assertEquals(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_origen_quad(self):
        board_conf = get_board_config('origen_quad')
        self.set_up_config(board_conf)
        self.assertEquals(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_arndale(self):
        board_conf = get_board_config('arndale')
        self.set_up_config(board_conf)
        self.assertEquals(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_highbank(self):
        board_conf = get_board_config('highbank')
        self.set_up_config(board_conf)
        self.assertEquals(
            '63,106432,0x83,*\n106496,,,-',
            board_conf.get_sfdisk_cmd())

    def test_beaglebone(self):
        board_conf = get_board_config('beaglebone')
        self.set_up_config(board_conf)
        self.assertEquals(
            '63,106432,0x0C,*\n106496,,,-',
            board_conf.get_sfdisk_cmd())

    def test_aa9(self):
        board_conf = get_board_config('aa9')
        self.set_up_config(board_conf)
        self.assertEquals(
            '63,106432,0x0C,*\n106496,,,-',
            board_conf.get_sfdisk_cmd())

    def test_panda_android(self):
        self.assertEqual(
            '63,270272,0x0C,*\n270336,1572864,L\n1843200,524288,L\n'
            '2367488,-,E\n2367488,1179648,L\n3547136,,,-',
            android_boards.AndroidPandaConfig().get_sfdisk_cmd())

    def test_origen_android(self):
        self.assertEqual(
            '1,8191,0xDA\n8253,270274,0x0C,*\n278528,1572864,L\n'
            '1851392,-,E\n1851392,524288,L\n2375680,1179648,L\n3555328,,,-',
            android_boards.AndroidOrigenConfig().get_sfdisk_cmd())

    def test_origen_quad_android(self):
        self.assertEqual(
            '1,8191,0xDA\n8253,270274,0x0C,*\n278528,1572864,L\n'
            '1851392,-,E\n1851392,524288,L\n2375680,1179648,L\n3555328,,,-',
            android_boards.AndroidOrigenQuadConfig().get_sfdisk_cmd())

    def test_snowball_emmc_android(self):
        self.assertEqual(
            '256,7936,0xDA\n8192,262144,0x0C,*\n270336,1572864,L\n'
            '1843200,-,E\n1843200,524288,L\n2367488,1179648,L\n3547136,,,-',
            android_boards.AndroidSnowballEmmcConfig().get_sfdisk_cmd())

    def test_vexpress_android(self):
        self.assertEqual(
            '63,270272,0x0E,*\n270336,1572864,L\n1843200,524288,L\n'
            '2367488,-,E\n2367488,1179648,L\n3547136,,,-',
            android_boards.AndroidVexpressConfig().get_sfdisk_cmd())

    def test_mx5_android(self):
        self.assertEqual(
            '1,8191,0xDA\n8192,262144,0x0C,*\n270336,1572864,L\n'
            '1843200,-,E\n1843200,524288,L\n2367488,1179648,L\n3547136,,,-',
            android_boards.AndroidMx53LoCoConfig().get_sfdisk_cmd())

    def test_mx6_android(self):
        self.assertEqual(
            '1,8191,0xDA\n8192,262144,0x0C,*\n270336,1572864,L\n'
            '1843200,-,E\n1843200,524288,L\n2367488,1179648,L\n3547136,,,-',
            android_boards.AndroidMx6QSabreliteConfig().get_sfdisk_cmd())


class TestGetSfdiskCmdV2(TestCase):

    def test_mx5(self):
        board_conf = boards.Mx5Config()
        board_conf.partition_layout = 'reserved_bootfs_rootfs'
        self.assertEqual(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_snowball_sd(self):
        board_conf = boards.SnowballSdConfig()
        board_conf.partition_layout = 'bootfs_rootfs'
        self.assertEqual(
            '63,106432,0x0C,*\n106496,,,-',
            board_conf.get_sfdisk_cmd())

    def test_snowball_emmc(self):
        board_conf = boards.SnowballEmmcConfig()
        board_conf.partition_layout = 'reserved_bootfs_rootfs'
        board_conf.loader_start_s = (128 * 1024) / SECTOR_SIZE
        self.assertEqual(
            '256,7936,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_smdkv310(self):
        board_conf = get_board_config('smdkv310')
        board_conf.partition_layout = 'reserved_bootfs_rootfs'
        board_conf.LOADER_MIN_SIZE_S = (
            board_conf.samsung_bl1_start +
            board_conf.samsung_bl1_len +
            board_conf.samsung_bl2_len +
            board_conf.samsung_env_len)
        self.assertEquals(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_origen(self):
        board_conf = get_board_config('origen')
        board_conf.partition_layout = 'reserved_bootfs_rootfs'
        board_conf.LOADER_MIN_SIZE_S = (
            board_conf.samsung_bl1_start +
            board_conf.samsung_bl1_len +
            board_conf.samsung_bl2_len +
            board_conf.samsung_env_len)
        self.assertEquals(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_origen_quad(self):
        board_conf = get_board_config('origen_quad')
        board_conf.partition_layout = 'reserved_bootfs_rootfs'
        board_conf.LOADER_MIN_SIZE_S = (
            board_conf.samsung_bl1_start +
            board_conf.samsung_bl1_len +
            board_conf.samsung_bl2_len +
            board_conf.samsung_env_len)
        self.assertEquals(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_arndale(self):
        board_conf = get_board_config('arndale')
        board_conf.partition_layout = 'reserved_bootfs_rootfs'
        board_conf.LOADER_MIN_SIZE_S = (
            board_conf.samsung_bl1_start +
            board_conf.samsung_bl1_len +
            board_conf.samsung_bl2_len +
            board_conf.samsung_env_len)
        self.assertEquals(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_conf.get_sfdisk_cmd())

    def test_highbank(self):
        board_conf = get_board_config('highbank')
        board_conf.partition_layout = 'bootfs_rootfs'
        self.assertEquals(
            '63,106432,0x83,*\n106496,,,-',
            board_conf.get_sfdisk_cmd())

    def test_beaglebone(self):
        board_conf = get_board_config('beaglebone')
        board_conf.partition_layout = 'bootfs_rootfs'
        self.assertEquals(
            '63,106432,0x0C,*\n106496,,,-',
            board_conf.get_sfdisk_cmd())

    def test_aa9(self):
        board_conf = get_board_config('aa9')
        board_conf.partition_layout = 'bootfs_rootfs'
        self.assertEquals(
            '63,106432,0x0C,*\n106496,,,-',
            board_conf.get_sfdisk_cmd())


class TestGetBootCmd(TestCase):

    def test_vexpress(self):
        board_conf = get_board_config('vexpress')
        boot_commands = board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=['ttyXXX'],
            rootfs_id="UUID=deadbeef", i_img_data="initrd", d_img_data=None)
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA0,38400n8 '
                        'console=ttyXXX  root=UUID=deadbeef rootwait ro',
            'bootcmd': 'fatload mmc 0:1 0x60000000 uImage; '
                       'fatload mmc 0:1 0x62000000 uInitrd; '
                       'bootm 0x60000000 0x62000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_vexpress_a9(self):
        board_conf = get_board_config('vexpress-a9')
        boot_commands = board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=['ttyXXX'],
            rootfs_id="UUID=deadbeef", i_img_data="initrd", d_img_data=None)
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA0,38400n8 '
                        'console=ttyXXX  root=UUID=deadbeef rootwait ro',
            'bootcmd': 'fatload mmc 0:1 0x60000000 uImage; '
                       'fatload mmc 0:1 0x62000000 uInitrd; '
                       'bootm 0x60000000 0x62000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_mx51(self):
        board_conf = boards.Mx51Config()
        boot_commands = board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd",
            d_img_data="mx51.dtb")
        expected = {
            'bootargs': 'console=tty0 console=ttymxc0,115200n8  '
                        'root=UUID=deadbeef rootwait ro',
            'bootcmd': 'fatload mmc 0:2 0x90000000 uImage; '
                       'fatload mmc 0:2 0x92000000 uInitrd; '
                       'fatload mmc 0:2 0x91ff0000 board.dtb; '
                       'bootm 0x90000000 0x92000000 0x91ff0000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_smdkv310(self):
        board_conf = get_board_config('smdkv310')
        boot_commands = board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd", d_img_data=None)
        expected = {
            'bootargs': 'console=ttySAC1,115200n8  root=UUID=deadbeef '
            'rootwait ro',
            'bootcmd': 'fatload mmc 0:2 0x40007000 uImage; '
            'fatload mmc 0:2 0x42000000 uInitrd; '
            'bootm 0x40007000 0x42000000',
            'ethact': 'smc911x-0',
            'ethaddr': '00:40:5c:26:0a:5b',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_origen(self):
        board_conf = get_board_config('origen')
        boot_commands = board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd", d_img_data=None)
        expected = {
            'bootargs': 'console=ttySAC2,115200n8  root=UUID=deadbeef '
            'rootwait ro',
            'bootcmd': 'fatload mmc 0:2 0x40007000 uImage; '
            'fatload mmc 0:2 0x42000000 uInitrd; '
            'bootm 0x40007000 0x42000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_origen_quad(self):
        board_conf = get_board_config('origen_quad')
        boot_commands = board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd", d_img_data=None)
        expected = {
            'bootargs': 'console=ttySAC2,115200n8  root=UUID=deadbeef '
                        'rootwait ro',
            'bootcmd': 'fatload mmc 0:2 0x40007000 uImage; '
            'fatload mmc 0:2 0x42000000 uInitrd; '
            'bootm 0x40007000 0x42000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_arndale(self):
        board_conf = get_board_config('arndale')
        boot_commands = board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd", d_img_data=None)
        expected = {
            'bootargs': 'root=UUID=deadbeef rootwait ro',
            'bootcmd': 'fatload mmc 0:2 None uImage; '
            'fatload mmc 0:2 None uInitrd; '
            'bootm None None',
            'ethact': 'smc911x-0',
            'ethaddr': '00:40:5c:26:0a:5b',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_ux500(self):
        board_conf = get_board_config('ux500')
        boot_commands = board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd", d_img_data=None)
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk '
                        'rootdelay=1 fixrtc nocompcache mem=96M@0 '
                        'mem_modem=32M@96M mem=44M@128M pmem=22M@172M '
                        'mem=30M@194M mem_mali=32M@224M pmem_hwb=54M@256M '
                        'hwmem=48M@302M mem=152M@360M',
            'bootcmd': 'fatload mmc 1:1 0x00100000 uImage; '
                       'fatload mmc 1:1 0x08000000 uInitrd; '
                       'bootm 0x00100000 0x08000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_snowball_emmc(self):
        board_conf = get_board_config('snowball_emmc')
        boot_commands = board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd", d_img_data=None)
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk '
                        'rootdelay=1 fixrtc nocompcache mem=96M@0 '
                        'mem_modem=32M@96M mem=44M@128M pmem=22M@172M '
                        'mem=30M@194M mem_mali=32M@224M pmem_hwb=54M@256M '
                        'hwmem=48M@302M mem=152M@360M',
            'bootcmd': 'fatload mmc 0:2 0x00100000 uImage; '
                       'fatload mmc 0:2 0x08000000 uInitrd; '
                       'bootm 0x00100000 0x08000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_panda(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = get_board_config('panda')
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd",
            d_img_data="panda.dtb")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=48M omapfb.vram=0:24M '
                        'mem=456M@0x80000000 mem=512M@0xA0000000',
            'bootcmd': 'fatload mmc 0:1 0x80200000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'fatload mmc 0:1 0x815f0000 board.dtb; '
                       'bootm 0x80200000 0x81600000 0x815f0000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_beagle(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = get_board_config('beagle')
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd",
            d_img_data="beagle.dtb")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=12M '
                        'omapfb.mode=dvi:1280x720MR-16@60 mpurate=${mpurate}',
            'bootcmd': 'fatload mmc 0:1 0x80000000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'fatload mmc 0:1 0x815f0000 board.dtb; '
                       'bootm 0x80000000 0x81600000 0x815f0000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_igep(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = boards.IgepConfig()
        config.serial_tty = config._serial_tty
        boot_cmd = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd",
            d_img_data="igep.dtb")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=12M '
                        'omapfb.mode=dvi:1280x720MR-16@60 mpurate=${mpurate}',
            'bootcmd': 'fatload mmc 0:1 0x80000000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'fatload mmc 0:1 0x815f0000 board.dtb; '
                       'bootm 0x80000000 0x81600000 0x815f0000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_cmd)

    def test_overo(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = get_board_config('overo')
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd",
            d_img_data="overo.dtb")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk '
                        'mpurate=${mpurate} vram=12M '
                        'omapdss.def_disp=${defaultdisplay} '
                        'omapfb.mode=dvi:${dvimode}',
            'bootcmd': 'fatload mmc 0:1 0x80000000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'fatload mmc 0:1 0x815f0000 board.dtb; '
                       'bootm 0x80000000 0x81600000 0x815f0000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_highbank(self):
        board_conf = get_board_config('highbank')
        boot_commands = board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd",
            d_img_data="board.dtb")
        expected = {
            'bootargs': 'root=UUID=deadbeef rootwait ro',
            'bootcmd': 'ext2load scsi 0:1 0x00800000 uImage; '
            'ext2load scsi 0:1 0x01000000 uInitrd; '
            'ext2load scsi 0:1 0x00001000 board.dtb; '
            'bootm 0x00800000 0x01000000 0x00001000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_beaglebone(self):
        config = get_board_config('beaglebone')
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd",
            d_img_data="board.dtb")
        expected = {
            'bootargs': 'console=ttyO0,115200n8  '
                        'root=UUID=deadbeef rootwait ro fixrtc',
            'bootcmd': 'fatload mmc 0:1 0x80200000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'fatload mmc 0:1 0x815f0000 board.dtb; '
                       'bootm 0x80200000 0x81600000 0x815f0000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)

    def test_aa9(self):
        config = get_board_config('aa9')
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_id="UUID=deadbeef", i_img_data="initrd",
            d_img_data="board.dtb")
        expected = {
            'bootargs': 'console=ttyS0,115200n8  '
                        'root=UUID=deadbeef rootwait ro',
            'bootcmd': 'fatload mmc 0:1 0x40000000 uImage; '
                       'fatload mmc 0:1 0x41100000 uInitrd; '
                       'fatload mmc 0:1 0x41000000 board.dtb; '
                       'bootm 0x40000000 0x41100000 0x41000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertEqual(expected, boot_commands)


class TestExtraBootCmd(TestCaseWithFixtures):

    def setUp(self):
        super(TestExtraBootCmd, self).setUp()
        self.board_conf = BoardConfig()

    def test_extra_boot_args_options_is_picked_by_get_boot_env(self):
        boot_args = 'whatever'

        self.board_conf.extra_boot_args_options = boot_args
        boot_commands = self.board_conf._get_boot_env(
            is_live=False, is_lowmem=False, consoles=['ttyXXX'],
            rootfs_id="UUID=deadbeef", i_img_data=None, d_img_data=None)
        expected = (
            'console=ttyXXX  root=UUID=deadbeef rootwait ro %s' % boot_args)
        self.assertEqual(expected, boot_commands['bootargs'])

    def test_passing_None_to_add_boot_args(self):
        boot_args = 'extra-args'

        self.board_conf.extra_boot_args_options = boot_args
        self.board_conf.add_boot_args(None)
        self.assertEqual(boot_args, self.board_conf.extra_boot_args_options)

    def test_passing_string_to_add_boot_args(self):
        boot_args = 'extra-args'
        extra_args = 'user-args'

        self.board_conf.extra_boot_args_options = boot_args
        self.board_conf.add_boot_args(extra_args)
        self.assertEqual(
            "%s %s" % (boot_args, extra_args),
            self.board_conf.extra_boot_args_options)

    def test_passing_string_to_add_boot_args_with_no_default_extra_args(self):
        extra_args = 'user-args'

        self.board_conf.add_boot_args(extra_args)
        self.assertEqual(extra_args, self.board_conf.extra_boot_args_options)

    def test_add_boot_args_from_file(self):
        boot_args = 'extra-args'
        extra_args = 'user-args'
        boot_arg_path = self.createTempFileAsFixture()
        with open(boot_arg_path, 'w') as boot_arg_file:
            boot_arg_file.write(extra_args)

        self.board_conf.extra_boot_args_options = boot_args
        self.board_conf.add_boot_args_from_file(boot_arg_path)
        self.assertEqual(
            "%s %s" % (boot_args, extra_args),
            self.board_conf.extra_boot_args_options)

    def test_passing_None_to_add_boot_args_from_file(self):
        boot_args = 'extra-args'

        self.board_conf.extra_boot_args_options = boot_args
        self.board_conf.add_boot_args_from_file(None)
        self.assertEqual(boot_args, self.board_conf.extra_boot_args_options)

    def test_add_boot_args_from_file_strips_whitespace_from_file(self):
        boot_args = 'extra-args'
        extra_args = 'user-args'
        boot_arg_path = self.createTempFileAsFixture()
        with open(boot_arg_path, 'w') as boot_arg_file:
            boot_arg_file.write('\n\n \t ' + extra_args + '  \n\n')

        self.board_conf.extra_boot_args_options = boot_args
        self.board_conf.add_boot_args_from_file(boot_arg_path)
        self.assertEqual(
            "%s %s" % (boot_args, extra_args),
            self.board_conf.extra_boot_args_options)


class TestUnpackBinaryTarball(TestCaseWithFixtures):

    def setUp(self):
        super(TestUnpackBinaryTarball, self).setUp()

        self.tar_dir_fixture = CreateTempDirFixture()
        self.useFixture(self.tar_dir_fixture)

        self.tarball_fixture = CreateTarballFixture(
            self.tar_dir_fixture.get_temp_dir())
        self.useFixture(self.tarball_fixture)

    def test_unpack_binary_tarball(self):
        tmp_dir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        rc = unpack_binary_tarball(
            self.tarball_fixture.get_tarball(), tmp_dir, as_root=False)
        self.assertEqual(rc, 0)


class TestGetUuid(TestCaseWithFixtures):

    def setUp(self):
        super(TestGetUuid, self).setUp()

    def test_get_uuid(self):
        fixture = MockCmdRunnerPopenFixture()
        self.useFixture(fixture)
        get_uuid("/dev/rootfs")
        self.assertEquals(
            ["%s blkid -o udev -p -c /dev/null /dev/rootfs" % sudo_args],
            fixture.mock.commands_executed)

    def test_parse_blkid_output(self):
        output = (
            "ID_FS_UUID=67d641db-ea7d-4acf-9f46-5f1f8275dce2\n"
            "ID_FS_UUID_ENC=67d641db-ea7d-4acf-9f46-5f1f8275dce2\n"
            "ID_FS_TYPE=ext4\n")
        uuid = _parse_blkid_output(output)
        self.assertEquals("67d641db-ea7d-4acf-9f46-5f1f8275dce2", uuid)


class TestBoards(TestCaseWithFixtures):

    def _mock_get_file_matching(self):
        self.useFixture(MockSomethingFixture(
            boards, '_get_file_matching',
            lambda regex: regex))

    def _mock_Popen(self):
        fixture = MockCmdRunnerPopenFixture()
        self.useFixture(fixture)
        return fixture

    def test_make_uImage(self):
        self._mock_get_file_matching()
        fixture = self._mock_Popen()
        make_uImage('load_addr', 'parts_dir/vmlinuz-*-sub_arch', 'boot_disk')
        expected = [
            '%s mkimage -A arm -O linux -T kernel -C none -a load_addr '
            '-e load_addr -n Linux -d parts_dir/vmlinuz-*-sub_arch '
            'boot_disk/uImage' % sudo_args]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_make_uInitrd(self):
        self._mock_get_file_matching()
        fixture = self._mock_Popen()
        make_uInitrd('parts_dir/initrd.img-*-sub_arch', 'boot_disk')
        expected = [
            '%s mkimage -A arm -O linux -T ramdisk -C none -a 0 -e 0 '
            '-n initramfs -d parts_dir/initrd.img-*-sub_arch '
            'boot_disk/uInitrd' % sudo_args]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_make_dtb(self):
        self._mock_get_file_matching()
        fixture = self._mock_Popen()
        make_dtb('parts_dir/dt-*-sub_arch/board_name.dtb', 'boot_disk')
        expected = [
            '%s cp parts_dir/dt-*-sub_arch/board_name.dtb '
            'boot_disk/board.dtb' % sudo_args]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_make_flashable_env_too_small_env(self):
        env = {'verylong': 'evenlonger'}
        self.assertRaises(AssertionError, make_flashable_env, env, 8)

    def test_make_flashable_env(self):
        env_file = self.createTempFileAsFixture()
        self.useFixture(MockSomethingFixture(
            tempfile, "mkstemp", lambda: (None, env_file)))
        env = {'a': 'b', 'x': 'y'}
        make_flashable_env(env, 12)
        with open(env_file, "r") as fd:
            self.assertEqual("\x80\x29\x2E\x89a=b\x00x=y\x00", fd.read())

    def test_install_mx5_boot_loader(self):
        fixture = self._mock_Popen()
        imx_file = self.createTempFileAsFixture()
        install_mx5_boot_loader(imx_file, "boot_device_or_file",
                                BoardConfig.LOADER_MIN_SIZE_S)
        expected = [
            '%s dd if=%s of=boot_device_or_file bs=512 '
            'conv=notrunc seek=2' % (sudo_args, imx_file)]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_install_mx5_boot_loader_too_large(self):
        self.useFixture(MockSomethingFixture(
            os.path, "getsize",
            lambda s: (BoardConfig.LOADER_MIN_SIZE_S - 1) * SECTOR_SIZE + 1))
        self.assertRaises(
            AssertionError,
            install_mx5_boot_loader, "imx_file", "boot_device_or_file",
            BoardConfig.LOADER_MIN_SIZE_S)

    def test_install_omap_boot_loader(self):
        fixture = self._mock_Popen()
        self.useFixture(MockSomethingFixture(
            boards, '_get_mlo_file',
            lambda chroot_dir: "%s/MLO" % chroot_dir))

        board_conf = BoardConfig()
        board_conf.set_metadata([])
        install_omap_boot_loader("chroot_dir", "boot_disk", board_conf)
        expected = [
            '%s cp -v chroot_dir/MLO boot_disk' % sudo_args, 'sync']
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_install_smdk_u_boot(self):
        fixture = self._mock_Popen()
        board_conf = boards.SMDKV310Config()
        bootloader_flavor = board_conf.bootloader_flavor
        self.useFixture(MockSomethingFixture(os.path, 'getsize',
                                             lambda file: 1))
        board_conf.install_samsung_boot_loader(
            "%s/%s/SPL" % ("chroot_dir", bootloader_flavor),
            "%s/%s/uboot" % ("chroot_dir", bootloader_flavor), "boot_disk")
        expected = [
            '%s dd if=chroot_dir/%s/SPL of=boot_disk bs=512 conv=notrunc '
            'seek=%d' % (sudo_args, bootloader_flavor,
                         board_conf.samsung_bl1_start),
            '%s dd if=chroot_dir/%s/uboot of=boot_disk bs=512 conv=notrunc '
            'seek=%d' % (sudo_args, bootloader_flavor,
                         board_conf.samsung_bl2_start)]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def _set_up_board_config(self, board_name):
        """Internal method to set-up correctly board config, with the
        appropriate mock objects.

        :param board_name: The name of the board to set-up.
        :return A 3-tuple: the config, the name of the bootloader, and the
        value of chroot_dir.
        """
        board_conf = get_board_config(board_name)
        bootloader_flavor = board_conf.bootloader_flavor
        # Made-up value to be used as the chroot directory.
        chroot_dir_value = 'chroot_dir'
        board_conf._get_samsung_spl = MagicMock()
        board_conf._get_samsung_spl.return_value = ("%s/%s/SPL" %
                                                    (chroot_dir_value,
                                                     bootloader_flavor))
        board_conf._get_samsung_bootloader = MagicMock()
        board_conf._get_samsung_bootloader.return_value = ("%s/%s/uboot" %
                                                           (chroot_dir_value,
                                                            bootloader_flavor))
        board_conf.hardwarepack_handler = (
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz'))
        board_conf.hardwarepack_handler.get_format = (
            lambda: HardwarepackHandler.FORMAT_1)
        return board_conf, bootloader_flavor, chroot_dir_value

    def test_install_origen_u_boot(self):
        fixture = self._mock_Popen()
        board_conf, bootloader_flavor, chroot_dir_value = \
            self._set_up_board_config('origen')
        self.useFixture(MockSomethingFixture(os.path, 'getsize',
                                             lambda file: 1))
        board_conf.install_samsung_boot_loader(
            board_conf._get_samsung_spl(chroot_dir_value),
            board_conf._get_samsung_bootloader(chroot_dir_value),
            "boot_disk")
        expected = [
            '%s dd if=chroot_dir/%s/SPL of=boot_disk bs=512 conv=notrunc '
            'seek=%d' % (sudo_args, bootloader_flavor,
                         board_conf.samsung_bl1_start),
            '%s dd if=chroot_dir/%s/uboot of=boot_disk bs=512 conv=notrunc '
            'seek=%d' % (sudo_args, bootloader_flavor,
                         board_conf.samsung_bl2_start)]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_install_origen_quad_u_boot(self):
        fixture = self._mock_Popen()
        board_conf, bootloader_flavor, chroot_dir_value = \
            self._set_up_board_config('origen_quad')
        self.useFixture(MockSomethingFixture(os.path, 'getsize',
                                             lambda file: 1))
        board_conf.install_samsung_boot_loader(
            board_conf._get_samsung_spl(chroot_dir_value),
            board_conf._get_samsung_bootloader(chroot_dir_value),
            "boot_disk")
        expected = [
            '%s dd if=chroot_dir/%s/SPL of=boot_disk bs=512 conv=notrunc '
            'seek=%d' % (sudo_args, bootloader_flavor,
                         board_conf.samsung_bl1_start),
            '%s dd if=chroot_dir/%s/uboot of=boot_disk bs=512 conv=notrunc '
            'seek=%d' % (sudo_args, bootloader_flavor,
                         board_conf.samsung_bl2_start)]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_install_arndale_u_boot(self):
        fixture = self._mock_Popen()
        board_conf, bootloader_flavor, chroot_dir_value = \
            self._set_up_board_config('arndale')
        self.useFixture(MockSomethingFixture(os.path, 'getsize',
                                             lambda file: 1))
        board_conf.install_samsung_boot_loader(
            board_conf._get_samsung_spl(chroot_dir_value),
            board_conf._get_samsung_bootloader(chroot_dir_value),
            "boot_disk")
        expected = [
            '%s dd if=chroot_dir/%s/SPL of=boot_disk bs=512 conv=notrunc '
            'seek=%d' % (sudo_args, bootloader_flavor,
                         board_conf.samsung_bl1_start),
            '%s dd if=chroot_dir/%s/uboot of=boot_disk bs=512 conv=notrunc '
            'seek=%d' % (sudo_args, bootloader_flavor,
                         board_conf.samsung_bl2_start)]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_get_plain_boot_script_contents(self):
        boot_env = {'bootargs': 'mybootargs', 'bootcmd': 'mybootcmd',
                    'initrd_high': '0xffffffff', 'fdt_high': '0xffffffff'}
        boot_script_data = get_plain_boot_script_contents(boot_env)
        self.assertEqual(textwrap.dedent("""\
            setenv initrd_high "0xffffffff"
            setenv fdt_high "0xffffffff"
            setenv bootcmd "mybootcmd"
            setenv bootargs "mybootargs"
            boot"""), boot_script_data)

    def test_make_boot_script(self):
        self.useFixture(MockSomethingFixture(
            tempfile, 'mkstemp', lambda: (-1, '/tmp/random-abxzr')))
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        self._mock_get_file_matching()
        fixture = self._mock_Popen()
        boot_script_path = os.path.join(tempdir, 'boot.scr')
        plain_boot_script_path = os.path.join(tempdir, 'boot.txt')
        boot_env = {'bootargs': 'mybootargs', 'bootcmd': 'mybootcmd',
                    'initrd_high': '0xffffffff', 'fdt_high': '0xffffffff'}
        make_boot_script(boot_env, boot_script_path)
        expected = [
            '%s cp /tmp/random-abxzr %s' % (
                sudo_args, plain_boot_script_path),
            '%s mkimage -A arm -O linux -T script -C none -a 0 -e 0 '
            '-n boot script -d %s %s' % (
                sudo_args, plain_boot_script_path, boot_script_path)]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_get_file_matching(self):
        prefix = ''.join(
            random.choice(string.ascii_lowercase) for x in range(5))
        file1 = self.createTempFileAsFixture(prefix)
        directory = os.path.dirname(file1)
        self.assertEqual(
            file1, _get_file_matching('%s/%s*' % (directory, prefix)))

    def test_get_file_matching_too_many_files_found(self):
        prefix = ''.join(
            random.choice(string.ascii_lowercase) for x in range(5))
        file1 = self.createTempFileAsFixture(prefix)
        file2 = self.createTempFileAsFixture(prefix)
        directory = os.path.dirname(file1)
        assert directory == os.path.dirname(file2), (
            "file1 and file2 should be in the same directory")
        self.assertRaises(
            ValueError, _get_file_matching, '%s/%s*' % (directory, prefix))

    def test_get_kflavor_files_more_specific(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        flavorx = 'flavorX'
        flavorxy = 'flavorXY'

        board_conf = BoardConfig()
        board_conf.kernel_flavors = [flavorx, flavorxy]
        for f in reversed(board_conf.kernel_flavors):
            kfile = os.path.join(tempdir, 'vmlinuz-1-%s' % f)
            ifile = os.path.join(tempdir, 'initrd.img-1-%s' % f)
            open(kfile, "w").close()
            open(ifile, "w").close()
        self.assertEqual(
            (kfile, ifile, None), board_conf._get_kflavor_files(tempdir))

    def test_get_dt_kflavor_files_more_specific(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        flavorx = 'flavorX'
        flavorxy = 'flavorXY'

        board_conf = BoardConfig()
        board_conf.kernel_flavors = [flavorx, flavorxy]
        board_conf.dtb_name = 'board_name.dtb'
        for f in reversed(board_conf.kernel_flavors):
            kfile = os.path.join(tempdir, 'vmlinuz-1-%s' % f)
            ifile = os.path.join(tempdir, 'initrd.img-1-%s' % f)
            dt = os.path.join(tempdir, 'dt-1-%s' % f)
            os.mkdir(dt)
            dfile = os.path.join(dt, board_conf.dtb_name)
            open(kfile, "w").close()
            open(ifile, "w").close()
            open(dfile, "w").close()
        self.assertEqual(
            (kfile, ifile, dfile), board_conf._get_kflavor_files(tempdir))

    def test_get_kflavor_files_later_in_flavors(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        flavor1 = 'flavorXY'
        flavor2 = 'flavorAA'

        board_conf = BoardConfig()
        board_conf.kernel_flavors = [flavor1, flavor2]
        kfile = os.path.join(tempdir, 'vmlinuz-1-%s' % flavor1)
        ifile = os.path.join(tempdir, 'initrd.img-1-%s' % flavor1)
        open(kfile, "w").close()
        open(ifile, "w").close()
        self.assertEqual(
            (kfile, ifile, None), board_conf._get_kflavor_files(tempdir))

    def test_get_dt_kflavor_files_later_in_flavors(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        flavor1 = 'flavorXY'
        flavor2 = 'flavorAA'

        board_conf = BoardConfig()
        board_conf.kernel_flavors = [flavor1, flavor2]
        board_conf.dtb_name = 'board_name.dtb'
        kfile = os.path.join(tempdir, 'vmlinuz-1-%s' % flavor1)
        ifile = os.path.join(tempdir, 'initrd.img-1-%s' % flavor1)
        dt = os.path.join(tempdir, 'dt-1-%s' % flavor1)
        os.mkdir(dt)
        dfile = os.path.join(dt, board_conf.dtb_name)
        open(kfile, "w").close()
        open(ifile, "w").close()
        open(dfile, "w").close()
        self.assertEqual(
            (kfile, ifile, dfile), board_conf._get_kflavor_files(tempdir))

    def test_get_kflavor_files_raises_when_no_match(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        flavor1 = 'flavorXY'
        flavor2 = 'flavorAA'

        board_conf = BoardConfig()
        board_conf.kernel_flavors = [flavor1, flavor2]
        self.assertRaises(ValueError, board_conf._get_kflavor_files, tempdir)

    def test_get_file_matching_no_files_found(self):
        self.assertEqual(
            None, _get_file_matching('/foo/bar/baz/*non-existent'))

    def test_run_mkimage(self):
        # Create a fake boot script.
        filename = self.createTempFileAsFixture()
        f = open(filename, 'w')
        f.write("setenv bootcmd 'fatload mmc 0:1 0x80000000 uImage;\nboot")
        f.close()

        img = self.createTempFileAsFixture()
        # Use that fake boot script to create a boot loader using mkimage.
        # Send stdout to /dev/null as mkimage will print to stdout and we
        # don't want that.
        retval = _run_mkimage(
            'script', '0', '0', 'boot script', filename, img,
            stdout=open('/dev/null', 'w'), as_root=False)

        self.assertEqual(0, retval)


class TestCreatePartitions(TestCaseWithFixtures):

    media = Media('/dev/xdz')

    def setUp(self):
        super(TestCreatePartitions, self).setUp()
        # Stub time.sleep() as create_partitions() use that.
        self.orig_sleep = time.sleep
        time.sleep = lambda s: None

    def tearDown(self):
        super(TestCreatePartitions, self).tearDown()
        time.sleep = self.orig_sleep

    def test_create_partitions_for_mx5(self):
        # For this board we create a one cylinder partition at the beginning.
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        board_conf = boards.Mx5Config()
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        create_partitions(board_conf, self.media, HEADS, SECTORS, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             '%s sfdisk -l %s' % (sudo_args, self.media.path),
             'sync',
             '%s sfdisk -l %s' % (sudo_args, self.media.path)],
            popen_fixture.mock.commands_executed)
        # Notice that we create all partitions in a single sfdisk run because
        # every time we run sfdisk it actually repartitions the device,
        # erasing any partitions created previously.
        self.assertEqual(
            [('1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-', HEADS, SECTORS,
              '', self.media.path)],
            sfdisk_fixture.mock.calls)

    def test_create_partitions_for_smdkv310(self):
        # For this board we create a one cylinder partition at the beginning.
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        board_conf = get_board_config('smdkv310')
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        create_partitions(board_conf, self.media, HEADS, SECTORS, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             '%s sfdisk -l %s' % (sudo_args, self.media.path),
             'sync',
             '%s sfdisk -l %s' % (sudo_args, self.media.path)],
            popen_fixture.mock.commands_executed)
        # Notice that we create all partitions in a single sfdisk run because
        # every time we run sfdisk it actually repartitions the device,
        # erasing any partitions created previously.
        self.assertEqual(
            [('1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-', HEADS,
              SECTORS, '', self.media.path)], sfdisk_fixture.mock.calls)

    def test_create_partitions_for_origen(self):
        # For this board we create a one cylinder partition at the beginning.
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        board_conf = get_board_config('origen')
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        create_partitions(board_conf, self.media, HEADS, SECTORS, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             '%s sfdisk -l %s' % (sudo_args, self.media.path),
             'sync',
             '%s sfdisk -l %s' % (sudo_args, self.media.path)],
            popen_fixture.mock.commands_executed)
        # Notice that we create all partitions in a single sfdisk run because
        # every time we run sfdisk it actually repartitions the device,
        # erasing any partitions created previously.
        self.assertEqual(
            [('1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-', HEADS,
              SECTORS, '', self.media.path)], sfdisk_fixture.mock.calls)

    def test_create_partitions_for_origen_quad(self):
        # For this board we create a one cylinder partition at the beginning.
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        board_conf = get_board_config('origen_quad')
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        create_partitions(
            board_conf, self.media, HEADS, SECTORS, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             '%s sfdisk -l %s' % (sudo_args, self.media.path),
             'sync',
             '%s sfdisk -l %s' % (sudo_args, self.media.path)],
            popen_fixture.mock.commands_executed)
        # Notice that we create all partitions in a single sfdisk run because
        # every time we run sfdisk it actually repartitions the device,
        # erasing any partitions created previously.
        self.assertEqual(
            [('1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-', HEADS,
              SECTORS, '', self.media.path)], sfdisk_fixture.mock.calls)

    def test_create_partitions_for_arndale(self):
        # For this board we create a one cylinder partition at the beginning.
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        board_conf = get_board_config('arndale')
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        create_partitions(
            board_conf, self.media, HEADS, SECTORS, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             '%s sfdisk -l %s' % (sudo_args, self.media.path),
             'sync',
             '%s sfdisk -l %s' % (sudo_args, self.media.path)],
            popen_fixture.mock.commands_executed)
        # Notice that we create all partitions in a single sfdisk run because
        # every time we run sfdisk it actually repartitions the device,
        # erasing any partitions created previously.
        self.assertEqual(
            [('1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-', HEADS,
              SECTORS, '', self.media.path)], sfdisk_fixture.mock.calls)

    def test_create_partitions_for_beagle(self):
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        board_conf = get_board_config('beagle')
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        create_partitions(board_conf, self.media, HEADS, SECTORS, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             '%s sfdisk -l %s' % (sudo_args, self.media.path),
             'sync',
             '%s sfdisk -l %s' % (sudo_args, self.media.path)],
            popen_fixture.mock.commands_executed)
        self.assertEqual(
            [('63,106432,0x0C,*\n106496,,,-', HEADS, SECTORS, '',
              self.media.path)],
            sfdisk_fixture.mock.calls)

    def test_create_partitions_with_img_file(self):
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        tmpfile = self.createTempFileAsFixture()
        board_conf = get_board_config('beagle')
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1
        create_partitions(board_conf, Media(tmpfile), HEADS, SECTORS, '')

        # Unlike the test for partitioning of a regular block device, in this
        # case parted was not called as there's no existing partition table
        # for us to overwrite on the image file.
        self.assertEqual(
            ['%s sfdisk -l %s' % (sudo_args, tmpfile),
             'sync',
             '%s sfdisk -l %s' % (sudo_args, tmpfile)],
            popen_fixture.mock.commands_executed)

        self.assertEqual(
            [('63,106432,0x0C,*\n106496,,,-', HEADS, SECTORS, '', tmpfile)],
            sfdisk_fixture.mock.calls)

    def test_run_sfdisk_commands(self):
        tmpfile = self.createTempFileAsFixture()
        proc = cmd_runner.run(
            ['dd', 'of=%s' % tmpfile, 'bs=1', 'seek=10M', 'count=0'],
            stderr=open('/dev/null', 'w'))
        proc.communicate()
        stdout, stderr = run_sfdisk_commands(
            '2,16063,0xDA', HEADS, SECTORS, '', tmpfile, as_root=False,
            stderr=subprocess.PIPE)
        self.assertIn('Successfully wrote the new partition table', stdout)

    def test_run_sfdisk_commands_raises_on_non_zero_returncode(self):
        tmpfile = self.createTempFileAsFixture()
        self.assertRaises(
            cmd_runner.SubcommandNonZeroReturnValue,
            run_sfdisk_commands,
            ',1,0xDA', HEADS, SECTORS, '', tmpfile, as_root=False,
            stderr=subprocess.PIPE)

    def test_wait_partitions_to_settle(self):
        class Namespace:
            pass

        ns = Namespace()
        ns.count = 0

        class MockCmdRunnerPopen(object):
            def __call__(self, cmd, *args, **kwargs):
                ns.count += 1
                self.returncode = 0
                if ns.count < 5:
                    raise cmd_runner.SubcommandNonZeroReturnValue(args, 1)
                else:
                    return self

            def communicate(self, input=None):
                self.wait()
                return '', ''

            def wait(self):
                return self.returncode

        self.useFixture(MockCmdRunnerPopenFixture())

        tmpfile = self.createTempFileAsFixture()
        media = Media(tmpfile)
        media.is_block_device = True

        self.assertEqual(0, wait_partition_to_settle(media, 'mbr'))

    def test_wait_partitions_to_settle_raises_SubcommandNonZeroReturnValue(
            self):
        def mock_run(args, as_root=False, chroot=None, stdin=None, stdout=None,
                     stderr=None, cwd=None):
            raise cmd_runner.SubcommandNonZeroReturnValue(args, 1)

        self.useFixture(MockSomethingFixture(
            cmd_runner, 'run',
            mock_run))

        tmpfile = self.createTempFileAsFixture()
        media = Media(tmpfile)
        media.is_block_device = True

        self.assertRaises(cmd_runner.SubcommandNonZeroReturnValue,
                          wait_partition_to_settle, media, 'mbr')


class TestPartitionSetup(TestCaseWithFixtures):

    def setUp(self):
        super(TestPartitionSetup, self).setUp()
        # Stub time.sleep() as create_partitions() use that.
        self.orig_sleep = time.sleep
        time.sleep = lambda s: None
        self.linux_image_size = 30 * 1024 ** 2
        self.linux_offsets_and_sizes = [
            (16384 * SECTOR_SIZE, 15746 * SECTOR_SIZE),
            (32768 * SECTOR_SIZE, (self.linux_image_size -
                                   32768 * SECTOR_SIZE))
        ]
        self.android_image_size = 256 * 1024 ** 2
        # Extended partition info takes 32 sectors from the first ext partition
        ext_part_size = 32
        self.android_offsets_and_sizes = [
            (63 * SECTOR_SIZE, 32768 * SECTOR_SIZE),
            (32831 * SECTOR_SIZE, 65536 * SECTOR_SIZE),
            (98367 * SECTOR_SIZE, 65536 * SECTOR_SIZE),
            ((294975 + ext_part_size) * SECTOR_SIZE,
             (131072 - ext_part_size) * SECTOR_SIZE),
            ((426047 + ext_part_size) * SECTOR_SIZE,
             self.android_image_size - (426047 + ext_part_size) * SECTOR_SIZE)
        ]

        self.android_snowball_offsets_and_sizes = [
            (8192 * SECTOR_SIZE, 24639 * SECTOR_SIZE),
            (32831 * SECTOR_SIZE, 65536 * SECTOR_SIZE),
            ((98367 + ext_part_size) * SECTOR_SIZE,
             (65536 - ext_part_size) * SECTOR_SIZE),
            (294975 * SECTOR_SIZE, 131072 * SECTOR_SIZE),
            ((426047 + ext_part_size) * SECTOR_SIZE,
             self.android_image_size - (426047 + ext_part_size) * SECTOR_SIZE)
        ]

    def tearDown(self):
        super(TestPartitionSetup, self).tearDown()
        time.sleep = self.orig_sleep

    def _create_tmpfile(self):
        # boot part at +8 MiB, root part at +16 MiB
        return self._create_qemu_img_with_partitions(
            '16384,15746,0x0C,*\n32768,,,-', '%s' % self.linux_image_size)

    def _create_android_tmpfile(self):
        # boot, system, cache, (extended), userdata and sdcard partitions
        return self._create_qemu_img_with_partitions(
            '63,32768,0x0C,*\n32831,65536,L\n98367,65536,L\n294975,-,E\n'
            '294975,131072,L\n426047,,,-', '%s' % self.android_image_size)

    def _create_snowball_android_tmpfile(self):
        # raw, boot, system, cache, (extended), userdata and sdcard partitions
        return self._create_qemu_img_with_partitions(
            '256,7936,0xDA\n8192,24639,0x0C,*\n32831,65536,L\n'
            '98367,-,E\n98367,65536,L\n294975,131072,L\n'
            '426047,,,-', '%s' % self.android_image_size)

    def test_check_min_size_small(self):
        """Check that we get back the minimum size as expeceted."""
        self.assertEqual(MIN_IMAGE_SIZE, _check_min_size(12345))

    def test_check_min_size_big(self):
        """Check that we get back the same value we pass."""
        self.assertEqual(MIN_IMAGE_SIZE * 3, _check_min_size(3145728))

    def test_convert_size_wrong_suffix(self):
        self.assertRaises(ValueError, get_partition_size_in_bytes, "123456H")

    def test_convert_size_no_suffix(self):
        self.assertEqual(2 ** 20, get_partition_size_in_bytes('123456'))

    def test_convert_size_one_mbyte(self):
        self.assertEqual(2 ** 20, get_partition_size_in_bytes('1M'))

    def test_convert_size_in_kbytes_to_bytes(self):
        self.assertEqual(2 * 2 ** 20, get_partition_size_in_bytes('2048K'))

    def test_convert_size_in_mbytes_to_bytes(self):
        self.assertEqual(100 * 2 ** 20, get_partition_size_in_bytes('100M'))

    def test_convert_size_in_gbytes_to_bytes(self):
        self.assertEqual(12 * 2 ** 30, get_partition_size_in_bytes('12G'))

    def test_convert_size_float_no_suffix(self):
        self.assertEqual(3 * 2 ** 20,
                         get_partition_size_in_bytes('2348576.91'))

    def test_convert_size_float_in_kbytes_to_bytes(self):
        self.assertEqual(3 * 2 ** 20, get_partition_size_in_bytes('2345.8K'))

    def test_convert_size_float_in_mbytes_to_bytes_double(self):
        self.assertEqual(2 * 2 ** 20,
                         get_partition_size_in_bytes('1.0000001M'))

    def test_convert_size_float_in_mbytes_to_bytes(self):
        self.assertEqual(877 * 2 ** 20,
                         get_partition_size_in_bytes('876.123M'))

    def test_convert_size_float_in_gbytes_to_bytes(self):
        self.assertEqual(1946 * 2 ** 20, get_partition_size_in_bytes('1.9G'))

    def test_calculate_partition_size_and_offset(self):
        tmpfile = self._create_tmpfile()
        vfat_size, vfat_offset, linux_size, linux_offset = (
            calculate_partition_size_and_offset(tmpfile))
        self.assertEqual(
            self.linux_offsets_and_sizes,
            [(vfat_offset, vfat_size), (linux_offset, linux_size)])

    def test_calculate_android_partition_size_and_offset(self):
        tmpfile = self._create_android_tmpfile()
        device_info = calculate_android_partition_size_and_offset(tmpfile)
        # We use map(None, ...) since it would catch if the lists are not of
        # equal length and zip() would not in all cases.
        for device_pair, expected_pair in map(None, device_info,
                                              self.android_offsets_and_sizes):
            self.assertEqual(device_pair, expected_pair)

    def test_calculate_snowball_android_partition_size_and_offset(self):
        tmpfile = self._create_snowball_android_tmpfile()
        device_info = calculate_android_partition_size_and_offset(tmpfile)
        # We use map(None, ...) since it would catch if the lists are not of
        # equal length and zip() would not in all cases.
        snowball_info = map(None, device_info,
                            self.android_snowball_offsets_and_sizes)
        for device_pair, expected_pair in snowball_info:
            self.assertEqual(device_pair, expected_pair)

    def test_partition_numbering(self):
        # another Linux partition at +24 MiB after the boot/root parts
        tmpfile = self._create_qemu_img_with_partitions(
            '16384,15746,0x0C,*\n32768,15427,,-\n49152,,,-',
            '%s' % self.linux_image_size)
        vfat_size, vfat_offset, linux_size, linux_offset = (
            calculate_partition_size_and_offset(tmpfile))
        # check that the linux partition offset starts at +16 MiB so that it's
        # the partition immediately following the vfat one
        self.assertEqual(linux_offset, 32768 * 512)

    def test_get_boot_and_root_partitions_for_media_beagle(self):
        self.useFixture(MockSomethingFixture(
            partitions, '_get_device_file_for_partition_number',
            lambda dev, partition: '%s%d' % (tmpfile, partition)))
        tmpfile = self.createTempFileAsFixture()
        media = Media(tmpfile)
        media.is_block_device = True
        self.assertEqual(
            ("%s%d" % (tmpfile, 1), "%s%d" % (tmpfile, 2)),
            get_boot_and_root_partitions_for_media(
                media, get_board_config('beagle')))

    def test_get_boot_and_root_partitions_for_media_mx5(self):
        self.useFixture(MockSomethingFixture(
            partitions, '_get_device_file_for_partition_number',
            lambda dev, partition: '%s%d' % (tmpfile, partition)))
        tmpfile = self.createTempFileAsFixture()
        media = Media(tmpfile)
        media.is_block_device = True
        self.assertEqual(
            ("%s%d" % (tmpfile, 2), "%s%d" % (tmpfile, 3)),
            get_boot_and_root_partitions_for_media(media, boards.Mx5Config()))

    def _create_qemu_img_with_partitions(self, sfdisk_commands, tempfile_size):
        tmpfile = self.createTempFileAsFixture()
        proc = cmd_runner.run(
            ['dd', 'of=%s' % tmpfile, 'bs=1', 'seek=%s' % tempfile_size,
             'count=0'],
            stderr=open('/dev/null', 'w'))
        proc.communicate()
        stdout, stderr = run_sfdisk_commands(
            sfdisk_commands, HEADS, SECTORS, '', tmpfile, as_root=False,
            # Throw away stderr as sfdisk complains a lot when operating on a
            # qemu image.
            stderr=subprocess.PIPE)
        self.assertIn('Successfully wrote the new partition table', stdout)
        return tmpfile

    def test_ensure_partition_is_not_mounted_for_mounted_partition(self):
        self.useFixture(MockSomethingFixture(
            partitions, 'is_partition_mounted', lambda part: True))
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        ensure_partition_is_not_mounted('/dev/whatever')
        self.assertEqual(
            ['%s umount /dev/whatever' % sudo_args],
            popen_fixture.mock.commands_executed)

    def test_ensure_partition_is_not_mounted_for_umounted_partition(self):
        self.useFixture(MockSomethingFixture(
            partitions, 'is_partition_mounted', lambda part: False))
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        ensure_partition_is_not_mounted('/dev/whatever')
        self.assertEqual(None, popen_fixture.mock.calls)

    def test_get_boot_and_root_loopback_devices(self):
        tmpfile = self._create_tmpfile()
        atexit_fixture = self.useFixture(MockSomethingFixture(
            atexit, 'register', AtExitRegister()))
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        # We can't test the return value of get_boot_and_root_loopback_devices
        # because it'd require running losetup as root, so we just make sure
        # it calls losetup correctly.
        get_boot_and_root_loopback_devices(tmpfile)
        self.assertEqual(
            ['%s losetup -f --show %s --offset %s --sizelimit %s'
                % (sudo_args, tmpfile, offset, size) for (offset, size) in
             self.linux_offsets_and_sizes],
            popen_fixture.mock.commands_executed)

        # get_boot_and_root_loopback_devices will also setup two exit handlers
        # to de-register the loopback devices set up above.
        self.assertEqual(2, len(atexit_fixture.mock.funcs))
        popen_fixture.mock.calls = []
        atexit_fixture.mock.run_funcs()
        # We did not really run losetup above (as it requires root) so here we
        # don't have a device to pass to 'losetup -d', but when a device is
        # setup it is passed to the atexit handler.
        self.assertEquals(
            ['%s losetup -d ' % sudo_args,
             '%s losetup -d ' % sudo_args],
            popen_fixture.mock.commands_executed)

    def test_get_android_loopback_devices(self):
        tmpfile = self._create_android_tmpfile()
        atexit_fixture = self.useFixture(MockSomethingFixture(
            atexit, 'register', AtExitRegister()))
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        # We can't test the return value of get_boot_and_root_loopback_devices
        # because it'd require running losetup as root, so we just make sure
        # it calls losetup correctly.
        get_android_loopback_devices(tmpfile)
        self.assertEqual(
            ['%s losetup -f --show %s --offset %s --sizelimit %s'
                % (sudo_args, tmpfile, offset, size) for (offset, size) in
             self.android_offsets_and_sizes],
            popen_fixture.mock.commands_executed)

        # get_boot_and_root_loopback_devices will also setup two exit handlers
        # to de-register the loopback devices set up above.
        self.assertEqual(5, len(atexit_fixture.mock.funcs))
        popen_fixture.mock.calls = []
        atexit_fixture.mock.run_funcs()
        # We did not really run losetup above (as it requires root) so here we
        # don't have a device to pass to 'losetup -d', but when a device is
        # setup it is passed to the atexit handler.
        self.assertEquals(
            ['%s losetup -d ' % sudo_args,
             '%s losetup -d ' % sudo_args,
             '%s losetup -d ' % sudo_args,
             '%s losetup -d ' % sudo_args,
             '%s losetup -d ' % sudo_args],
            popen_fixture.mock.commands_executed)

    def test_setup_partitions_for_image_file(self):
        # In practice we could pass an empty image file to setup_partitions,
        # but here we mock Popen() and thanks to that the image is not setup
        # (via dd) inside setup_partitions.  That's why we pass an
        # already setup image file.
        tmpfile = self._create_tmpfile()
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))

        def ensure_partition_not_mounted(part):
            raise AssertionError(
                "ensure_partition_is_not_mounted must not be called when "
                "generating image files. It makes no sense to do that and "
                "it depends on UDisks, thus making it hard to run on a "
                "chroot")
        self.useFixture(MockSomethingFixture(
            partitions,
            'ensure_partition_is_not_mounted', ensure_partition_not_mounted))
        self.useFixture(MockSomethingFixture(
            partitions, 'get_boot_and_root_loopback_devices',
            lambda image: ('/dev/loop99', '/dev/loop98')))

        board_conf = get_board_config('beagle')
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1

        bootfs_dev, rootfs_dev = setup_partitions(
            board_conf, Media(tmpfile), '2G', 'boot',
            'root', 'ext3', True, True, True)
        self.assertEqual(
            # This is the call that would create a 2 GiB image file.
            ['dd of=%s bs=1 seek=2147483648 count=0' % tmpfile,
             '%s sfdisk -l %s' % (sudo_args, tmpfile),
             # This call would partition the image file.
             '%s sfdisk --force -D -uS -H %s -S %s -C 1024 %s' % (
                 sudo_args, HEADS, SECTORS, tmpfile),
             # Make sure changes are written to disk.
             'sync',
             '%s sfdisk -l %s' % (sudo_args, tmpfile),
             '%s mkfs.vfat -F 32 %s -n boot' % (sudo_args, bootfs_dev),
             '%s mkfs.ext3 %s -L root' % (sudo_args, rootfs_dev)],
            popen_fixture.mock.commands_executed)

    def test_setup_partitions_for_block_device(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        # Pretend the partitions are mounted.
        self.useFixture(MockSomethingFixture(
            partitions, 'is_partition_mounted', lambda part: True))
        tmpfile = self._create_tmpfile()
        self.useFixture(MockSomethingFixture(
            partitions, '_get_device_file_for_partition_number',
            lambda dev, partition: '%s%d' % (tmpfile, partition)))
        media = Media(tmpfile)
        # Pretend our tmpfile is a block device.
        media.is_block_device = True
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())

        board_conf = get_board_config('beagle')
        board_conf.hwpack_format = HardwarepackHandler.FORMAT_1

        bootfs_dev, rootfs_dev = setup_partitions(
            board_conf, media, '2G', 'boot', 'root', 'ext3',
            True, True, True)
        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, tmpfile),
             '%s sfdisk -l %s' % (sudo_args, tmpfile),
             '%s sfdisk --force -D -uS -H %s -S %s %s' % (
                 sudo_args, HEADS, SECTORS, tmpfile),
             'sync',
             '%s sfdisk -l %s' % (sudo_args, tmpfile),
             # Since the partitions are mounted, setup_partitions will umount
             # them before running mkfs.
             '%s umount %s' % (sudo_args, bootfs_dev),
             '%s umount %s' % (sudo_args, rootfs_dev),
             '%s mkfs.vfat -F 32 %s -n boot' % (sudo_args, bootfs_dev),
             '%s mkfs.ext3 %s -L root' % (sudo_args, rootfs_dev)],
            popen_fixture.mock.commands_executed)

    def test_get_device_file_for_partition_number_raises_DBusException(self):
        def mock_get_udisks_device_path(d):
            raise dbus.exceptions.DBusException

        self.useFixture(MockSomethingFixture(
            partitions, '_get_udisks_device_path',
            mock_get_udisks_device_path))

        tmpfile = self.createTempFileAsFixture()
        partition = get_board_config('beagle').mmc_part_offset

        self.useFixture(MockSomethingFixture(
            glob, 'glob',
            lambda pathname: ['%s%d' % (tmpfile, partition)]))

        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))

        media = Media(tmpfile)
        media.is_block_device = True
        self.assertRaises(dbus.exceptions.DBusException,
                          _get_device_file_for_partition_number,
                          media.path, partition)

    def test_get_device_file_for_partition_number(self):
        class Namespace:
            pass
        ns = Namespace()
        ns.count = 0

        def mock_get_udisks_device_path(dev):
            ns.count += 1
            if ns.count < 5:
                raise dbus.exceptions.DBusException
            else:
                return '/abc/123'

        def mock_get_udisks_device_file(dev, part):
            if ns.count < 5:
                raise dbus.exceptions.DBusException
            else:
                return '/abc/123'

        self.useFixture(MockSomethingFixture(
            partitions, '_get_udisks_device_path',
            mock_get_udisks_device_path))

        self.useFixture(MockSomethingFixture(
            partitions, '_get_udisks_device_file',
            mock_get_udisks_device_file))

        tmpfile = self.createTempFileAsFixture()
        partition = get_board_config('beagle').mmc_part_offset

        self.useFixture(MockSomethingFixture(
            glob, 'glob',
            lambda pathname: ['%s%d' % (tmpfile, partition)]))

        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))

        media = Media(tmpfile)
        media.is_block_device = True
        self.assertIsNotNone(_get_device_file_for_partition_number(
            media.path, partition))


class TestException(Exception):
    """Just a test exception."""


class TestMountedPartitionContextManager(TestCaseWithFixtures):

    def test_basic(self):
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())

        def test_func():
            with partition_mounted('foo', 'bar', '-t', 'proc'):
                pass
        test_func()
        expected = ['%s mount foo bar -t proc' % sudo_args,
                    'sync',
                    '%s umount bar' % sudo_args]
        self.assertEqual(expected, popen_fixture.mock.commands_executed)

    def test_exception_raised_inside_with_block(self):
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())

        def test_func():
            with partition_mounted('foo', 'bar'):
                raise TestException('something')
        try:
            test_func()
        except TestException:
            pass
        expected = ['%s mount foo bar' % sudo_args,
                    'sync',
                    '%s umount bar' % sudo_args]
        self.assertEqual(expected, popen_fixture.mock.commands_executed)

    def test_umount_failure(self):
        # We ignore a SubcommandNonZeroReturnValue from umount because
        # otherwise it could shadow an exception raised inside the 'with'
        # block.
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())

        def failing_umount(path):
            raise cmd_runner.SubcommandNonZeroReturnValue('umount', 1)
        self.useFixture(MockSomethingFixture(
            partitions, 'umount', failing_umount))

        def test_func():
            with partition_mounted('foo', 'bar'):
                pass
        test_func()
        expected = ['sudo -E mount foo bar', 'sync']
        self.assertEqual(expected, popen_fixture.mock.commands_executed)


class TestPopulateBoot(TestCaseWithFixtures):

    expected_args = (
        'chroot_dir/boot', False, False, [], 'chroot_dir', 'rootfs_id',
        'boot_disk', 'boot_device_or_file')
    expected_args_live = (
        'chroot_dir/casper', True, False, [], 'chroot_dir', 'rootfs_id',
        'boot_disk', 'boot_device_or_file')
    expected_calls = [
        'mkdir -p boot_disk',
        '%s mount boot_partition boot_disk' % sudo_args,
        'sync',
        '%s umount boot_disk' % sudo_args]

    def save_args(self, *args):
        self.saved_args = args

    def prepare_config(self, config):
        self.config = config
        self.config.boot_script = 'boot_script'
        self.config.hardwarepack_handler = \
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz')
        self.config.hardwarepack_handler.get_format = \
            lambda: HardwarepackHandler.FORMAT_1
        self.popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(
            self.config, 'make_boot_files', self.save_args))
        self.config.hardwarepack_handler.get_file_from_package = \
            self.get_file_from_package
        self.config.bootloader_copy_files = None

    def get_file_from_package(self, source_path, source_package):
        if source_package in self.config.bootloader_copy_files:
            for file_info in self.config.bootloader_copy_files[source_package]:
                if source_path in file_info:
                    return source_path
        return None

    def prepare_config_v3(self, config):
        self.config = config
        self.config.boot_script = 'boot_script'
        self.config.hardwarepack_handler = \
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz')
        self.config.hardwarepack_handler.get_format = lambda: '3.0'
        self.config.hardwarepack_handler.get_file = \
            lambda file_alias: ['file1', 'file2']
        self.config.hardwarepack_handler.get_file_from_package = \
            self.get_file_from_package
        self.config.bootloader_copy_files = {
            "package1":
            [{"file1": "/boot/"},
             {"file2": "/boot/grub/renamed"}]}

        self.popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(
            self.config, 'make_boot_files', self.save_args))

    def call_populate_boot(self, config, is_live=False):
        config.populate_boot(
            'chroot_dir', 'rootfs_id', 'boot_partition', 'boot_disk',
            'boot_device_or_file', is_live, False, [])

    def test_populate_boot_live(self):
        self.prepare_config(BoardConfig())
        self.call_populate_boot(self.config, is_live=True)
        self.assertEquals(
            self.expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args_live, self.saved_args)

    def test_populate_boot_regular(self):
        self.prepare_config(BoardConfig())
        self.call_populate_boot(self.config)
        self.assertEquals(
            self.expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args, self.saved_args)

    def test_populate_boot_bootloader_flavor(self):
        self.prepare_config(BoardConfig())
        self.config.bootloader_flavor = "bootloader_flavor"
        self.call_populate_boot(self.config)
        self.assertEquals(
            self.expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args, self.saved_args)

    def test_populate_boot_bootloader_file_in_boot_part(self):
        self.prepare_config(BoardConfig())
        self.config.bootloader_flavor = "bootloader_flavor"
        self.config.bootloader_file_in_boot_part = True
        self.config.bootloader = "u_boot"
        self.call_populate_boot(self.config)
        expected_calls = self.expected_calls[:]
        expected_calls.insert(
            2,
            '%s cp -v chroot_dir/usr/lib/u-boot/bootloader_flavor/u-boot.bin '
            'boot_disk' % sudo_args)
        self.assertEquals(
            expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args, self.saved_args)

    def test_populate_boot_bootloader_file_in_boot_part_false(self):
        self.prepare_config(BoardConfig())
        self.config.bootloader_flavor = "bootloader_flavor"
        self.config.bootloader_file_in_boot_part = False
        self.call_populate_boot(self.config)
        expected_calls = self.expected_calls[:]
        self.assertEquals(
            expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args, self.saved_args)

    def test_populate_bootloader_copy_files(self):
        self.prepare_config_v3(BoardConfig())
        self.config.bootloader_flavor = "bootloader_flavor"
        # Test that copy_files works per spec (puts stuff in boot partition)
        # even if bootloader not in_boot_part.
        self.config.bootloader_file_in_boot_part = False
        self.call_populate_boot(self.config)
        expected_calls = self.expected_calls[:]
        expected_calls.insert(2, '%s mkdir -p boot_disk/boot' % sudo_args)
        expected_calls.insert(3,
                              '%s cp -v file1 '
                              'boot_disk/boot/' % sudo_args)
        expected_calls.insert(4, '%s mkdir -p boot_disk/boot/grub' % sudo_args)
        expected_calls.insert(5,
                              '%s cp -v file2 '
                              'boot_disk/boot/grub/renamed' % sudo_args)
        self.assertEquals(
            expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args, self.saved_args)

    def test_populate_bootloader_copy_files_bootloader_set(self):
        self.prepare_config_v3(BoardConfig())
        self.config.bootloader_flavor = "bootloader_flavor"
        # Test that copy_files works per spec (puts stuff in boot partition)
        # even if bootloader not in_boot_part.
        self.config.bootloader_file_in_boot_part = False
        self.config.bootloader = "u_boot"
        self.call_populate_boot(self.config)
        expected_calls = self.expected_calls[:]
        expected_calls.insert(2, '%s mkdir -p boot_disk/boot' % sudo_args)
        expected_calls.insert(3,
                              '%s cp -v file1 '
                              'boot_disk/boot/' % sudo_args)
        expected_calls.insert(4, '%s mkdir -p boot_disk/boot/grub' % sudo_args)
        expected_calls.insert(5,
                              '%s cp -v file2 '
                              'boot_disk/boot/grub/renamed' % sudo_args)
        self.assertEquals(
            expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args, self.saved_args)

    def test_populate_boot_no_bootloader_flavor(self):
        self.prepare_config(BoardConfig())
        self.config.bootloader_file_in_boot_part = True
        self.assertRaises(
            AssertionError, self.call_populate_boot, self.config)


class TestPopulateRootFS(TestCaseWithFixtures):

    lines_added_to_fstab = None
    create_flash_kernel_config_called = False

    def test_populate_rootfs(self):
        def fake_append_to_fstab(disk, additions):
            self.lines_added_to_fstab = additions

        def fake_create_flash_kernel_config(disk, mmc_device_id,
                                            partition_offset):
            self.create_flash_kernel_config_called = True

        # Mock stdout, cmd_runner.Popen(), append_to_fstab and
        # create_flash_kernel_config.
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        self.useFixture(MockSomethingFixture(
            rootfs, 'append_to_fstab', fake_append_to_fstab))
        self.useFixture(MockSomethingFixture(
            rootfs, 'create_flash_kernel_config',
            fake_create_flash_kernel_config))
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        # Store a dummy rootdisk and contents_dir in a tempdir.
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        root_disk = os.path.join(tempdir, 'rootdisk')
        contents_dir = os.path.join(tempdir, 'contents')
        contents_bin = os.path.join(contents_dir, 'bin')
        contents_etc = os.path.join(contents_dir, 'etc')
        os.makedirs(contents_bin)
        os.makedirs(contents_etc)

        # Must mock rootfs._list_files() because populate_rootfs() uses its
        # return value but since we mock cmd_runner.run() _list_files() would
        # return an invalid value.
        def mock_list_files(directory):
            return [contents_bin, contents_etc]
        self.useFixture(MockSomethingFixture(
            rootfs, '_list_files', mock_list_files))

        populate_rootfs(
            contents_dir, root_disk, partition='/dev/rootfs',
            rootfs_type='ext3', rootfs_id='UUID=uuid', should_create_swap=True,
            swap_size=100, mmc_device_id=0, partition_offset=0,
            os_release_id='ubuntu', board_config=None)

        self.assertEqual(
            ['UUID=uuid / ext3  errors=remount-ro 0 1',
             '/SWAP.swap  none  swap  sw  0 0'],
            self.lines_added_to_fstab)
        self.assertEqual(True, self.create_flash_kernel_config_called)
        swap_file = os.path.join(root_disk, 'SWAP.swap')
        expected = [
            '%s mount /dev/rootfs %s' % (sudo_args, root_disk),
            '%s mv %s %s %s' % (
                sudo_args, contents_bin, contents_etc, root_disk),
            '%s dd if=/dev/zero of=%s bs=1M count=100' % (
                sudo_args, swap_file),
            '%s mkswap %s' % (sudo_args, swap_file),
            'sync',
            '%s umount %s' % (sudo_args, root_disk)]
        self.assertEqual(expected, popen_fixture.mock.commands_executed)

    def test_create_flash_kernel_config(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir

        create_flash_kernel_config(tempdir, mmc_device_id=0,
                                   boot_partition_number=1)

        calls = fixture.mock.calls
        self.assertEqual(1, len(calls), calls)
        call = calls[0]
        # The call writes to a tmpfile and then moves it to the,
        # /etc/flash-kernel.conf, so the tmpfile is the next to last in the
        # list of arguments stored.
        tmpfile = call[-2]
        self.assertEqual(
            '%s mv -f %s %s/etc/flash-kernel.conf' % (
                sudo_args, tmpfile, tempdir),
            fixture.mock.commands_executed[0])
        self.assertEqual('UBOOT_PART=/dev/mmcblk0p1',
                         open(tmpfile).read().rstrip())

    def test_list_files(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        # We don't want to mock cmd_runner.run() because we're testing the
        # command that it runs, but we need to monkey-patch SUDO_ARGS because
        # we don't want to use 'sudo' in tests.
        orig_sudo_args = cmd_runner.SUDO_ARGS

        def restore_sudo_args():
            cmd_runner.SUDO_ARGS = orig_sudo_args
        self.addCleanup(restore_sudo_args)
        cmd_runner.SUDO_ARGS = []
        file1 = self.createTempFileAsFixture(dir=tempdir)
        self.assertEqual([file1], rootfs._list_files(tempdir))

    def test_move_contents(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        file1 = self.createTempFileAsFixture(dir=tempdir)

        def mock_list_files(directory):
            return [file1]
        self.useFixture(MockSomethingFixture(
            rootfs, '_list_files', mock_list_files))

        move_contents(tempdir, '/tmp/')

        self.assertEqual(['%s mv %s /tmp/' % (sudo_args, file1)],
                         popen_fixture.mock.commands_executed)

    def test_has_space_left_for_swap(self):
        statvfs = os.statvfs('/')
        space_left = statvfs.f_bavail * statvfs.f_bsize
        swap_size_in_megs = space_left / (1024 ** 2)
        self.assertTrue(
            has_space_left_for_swap('/', swap_size_in_megs))

    def test_has_no_space_left_for_swap(self):
        statvfs = os.statvfs('/')
        space_left = statvfs.f_bavail * statvfs.f_bsize
        swap_size_in_megs = (space_left / (1024 ** 2)) + 1
        self.assertFalse(
            has_space_left_for_swap('/', swap_size_in_megs))

    def mock_write_data_to_protected_file(self, path, data):
        # Duplicate of write_data_to_protected_file() but does not sudo.
        _, tmpfile = tempfile.mkstemp()
        with open(tmpfile, 'w') as fd:
            fd.write(data)
            cmd_runner.run(['mv', '-f', tmpfile, path], as_root=False).wait()

    def test_update_interfaces_no_interfaces_no_update(self):
        self.useFixture(MockSomethingFixture(
            rootfs, 'write_data_to_protected_file',
            self.mock_write_data_to_protected_file))
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        os.makedirs(os.path.join(tempdir, 'etc', 'network'))
        if_path = os.path.join(tempdir, 'etc', 'network', 'interfaces')

        update_network_interfaces(tempdir, BoardConfig())
        self.assertFalse(os.path.exists(if_path))

    def test_update_interfaces_creates_entry(self):
        self.useFixture(MockSomethingFixture(
            rootfs, 'write_data_to_protected_file',
            self.mock_write_data_to_protected_file))
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        os.makedirs(os.path.join(tempdir, 'etc', 'network'))
        if_path = os.path.join(tempdir, 'etc', 'network', 'interfaces')

        board_conf = BoardConfig()
        board_conf.wired_interfaces = ['eth0']

        expected = 'auto eth0\n' \
            'iface eth0 inet dhcp\n'
        update_network_interfaces(tempdir, board_conf)
        self.assertEqual(expected, open(if_path).read())

    def test_update_interfaces_creates_entries(self):
        self.useFixture(MockSomethingFixture(
            rootfs, 'write_data_to_protected_file',
            self.mock_write_data_to_protected_file))
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        os.makedirs(os.path.join(tempdir, 'etc', 'network'))
        if_path = os.path.join(tempdir, 'etc', 'network', 'interfaces')

        board_conf = BoardConfig()
        board_conf.wired_interfaces = ['eth0', 'eth1']
        board_conf.wireless_interfaces = ['wlan0']

        expected = 'auto %(if)s\n' \
            'iface %(if)s inet dhcp\n'

        update_network_interfaces(tempdir, board_conf)
        self.assertIn(expected % {'if': 'eth1'}, open(if_path).read())
        self.assertIn(expected % {'if': 'eth0'}, open(if_path).read())
        self.assertIn(expected % {'if': 'wlan0'}, open(if_path).read())

    def test_update_interfaces_leaves_original(self):
        self.useFixture(MockSomethingFixture(
            rootfs, 'write_data_to_protected_file',
            self.mock_write_data_to_protected_file))
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        os.makedirs(os.path.join(tempdir, 'etc', 'network'))
        if_path = os.path.join(tempdir, 'etc', 'network', 'interfaces')
        with open(if_path, 'w') as interfaces:
            interfaces.write('Original contents of file.\n')

        board_conf = BoardConfig()
        board_conf.wired_interfaces = ['eth0']

        expected = 'Original contents of file.\n' \
            'auto eth0\n' \
            'iface eth0 inet dhcp\n'
        update_network_interfaces(tempdir, board_conf)
        self.assertEqual(expected, open(if_path).read())

    def test_write_data_to_protected_file(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        data = 'foo'
        path = '/etc/nonexistant'

        write_data_to_protected_file(path, data)

        calls = fixture.mock.calls
        self.assertEqual(1, len(calls), calls)
        call = calls[0]
        # The call moves tmpfile to the given path, so tmpfile is the next to
        # last in the list of arguments stored.
        tmpfile = call[-2]
        self.assertEqual(['%s mv -f %s %s' % (sudo_args, tmpfile, path)],
                         fixture.mock.commands_executed)
        self.assertEqual(data, open(tmpfile).read())

    def test_rootfs_mount_options_for_btrfs(self):
        self.assertEqual("defaults", rootfs_mount_options('btrfs'))

    def test_rootfs_mount_options_for_ext4(self):
        self.assertEqual("errors=remount-ro", rootfs_mount_options('ext4'))

    def test_rootfs_mount_options_for_unknown(self):
        self.assertRaises(ValueError, rootfs_mount_options, 'unknown')

    def test_append_to_fstab(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        # we don't really need root (sudo) as we're not writing to a real
        # root owned /etc
        self.useFixture(MockSomethingFixture(os, 'getuid', lambda: 0))
        etc = os.path.join(tempdir, 'etc')
        os.mkdir(etc)
        fstab = os.path.join(etc, 'fstab')
        open(fstab, "w").close()
        append_to_fstab(tempdir, ['foo', 'bar'])
        f = open(fstab)
        contents = f.read()
        f.close()
        self.assertEquals("\nfoo\nbar\n", contents)


class TestCheckDevice(TestCaseWithFixtures):

    def _mock_does_device_exist_true(self):
        self.useFixture(MockSomethingFixture(
            check_device, '_does_device_exist', lambda device: True))

    def _mock_does_device_exist_false(self):
        self.useFixture(MockSomethingFixture(
            check_device, '_does_device_exist', lambda device: False))

    def _mock_print_devices(self):
        self.useFixture(MockSomethingFixture(
            check_device, '_print_devices', lambda: None))

    def _mock_select_device(self):
        self.useFixture(MockSomethingFixture(
            check_device, '_select_device', lambda device: True))

    def _mock_deselect_device(self):
        self.useFixture(MockSomethingFixture(
            check_device, '_select_device', lambda device: False))

    def _mock_sys_stdout(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open(os.devnull, 'w')))

    def setUp(self):
        super(TestCheckDevice, self).setUp()
        self._mock_sys_stdout()
        self._mock_print_devices()

    def test_ensure_device_partitions_not_mounted(self):
        partitions_umounted = []

        def ensure_partition_is_not_mounted_mock(part):
            partitions_umounted.append(part)
        self.useFixture(MockSomethingFixture(
            partitions, 'ensure_partition_is_not_mounted',
            ensure_partition_is_not_mounted_mock))
        self.useFixture(MockSomethingFixture(
            glob, 'glob', lambda pattern: ['/dev/sdz1', '/dev/sdz2']))
        check_device._ensure_device_partitions_not_mounted('/dev/sdz')
        self.assertEquals(['/dev/sdz1', '/dev/sdz2'], partitions_umounted)

    def test_check_device_and_select(self):
        self._mock_does_device_exist_true()
        self._mock_select_device()
        self.assertTrue(
            check_device.confirm_device_selection_and_ensure_it_is_ready(
                None))

    def test_check_device_and_deselect(self):
        self._mock_does_device_exist_true()
        self._mock_deselect_device()
        self.assertFalse(
            check_device.confirm_device_selection_and_ensure_it_is_ready(
                None))

    def test_check_device_not_found(self):
        self._mock_does_device_exist_false()
        self.assertFalse(
            check_device.confirm_device_selection_and_ensure_it_is_ready(
                None))


class AtExitRegister(object):

    funcs = None

    def __call__(self, func, *args, **kwargs):
        if self.funcs is None:
            self.funcs = []
        self.funcs.append((func, args, kwargs))

    def run_funcs(self):
        for func, args, kwargs in self.funcs:
            func(*args, **kwargs)


class TestInstallHWPack(TestCaseWithFixtures):
    def create_minimal_v3_hwpack(self, location, name, version, architecture):
        metadata = "\n".join([
            "name: " + name,
            "version: " + version,
            "architecture: " + architecture,
            "format: 3.0"
        ])
        print metadata
        tar_file = tarfile.open(location, mode='w:gz')
        tarinfo = tarfile.TarInfo("metadata")
        tarinfo.size = len(metadata)
        tar_file.addfile(tarinfo, StringIO(metadata))
        tar_file.close()

    def mock_prepare_chroot(self, chroot_dir, tmp_dir):
        def fake_prepare_chroot(chroot_dir, tmp_dir):
            cmd_runner.run(['prepare_chroot %s %s' % (chroot_dir, tmp_dir)],
                           as_root=True).wait()
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.chroot_utils, 'prepare_chroot',
            fake_prepare_chroot))

    def test_temporarily_overwrite_file_on_dir(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        temporarily_overwrite_file_on_dir('/path/to/file', '/dir', '/tmp/dir')
        self.assertEquals(
            ['%s cp /path/to/file /dir' % sudo_args],
            fixture.mock.commands_executed)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            ['%s rm -f /dir/file' % sudo_args],
            fixture.mock.commands_executed)

    def test_copy_file(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        copy_file('/path/to/file', '/dir')
        self.assertEquals(
            ['%s cp /path/to/file /dir' % sudo_args],
            fixture.mock.commands_executed)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            ['%s rm -f /dir/file' % sudo_args],
            fixture.mock.commands_executed)

    def test_mount_chroot_proc(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        mount_chroot_proc('chroot')
        self.assertEquals(
            ['%s mount proc chroot/proc -t proc' % sudo_args],
            fixture.mock.commands_executed)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            ['%s umount -v chroot/proc' % sudo_args],
            fixture.mock.commands_executed)

    def test_install_hwpack(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        chroot_dir = 'chroot_dir'
        hwpack_dir = tempfile.mkdtemp()
        hwpack_file_name = 'hwpack.tgz'
        hwpack_tgz_location = os.path.join(hwpack_dir, hwpack_file_name)
        hwpack_name = "foo"
        hwpack_version = "4"
        hwpack_architecture = "armel"
        extract_kpkgs = False
        self.create_minimal_v3_hwpack(hwpack_tgz_location, hwpack_name,
                                      hwpack_version, hwpack_architecture)
        force_yes = False
        install_hwpack(chroot_dir, hwpack_tgz_location,
                       extract_kpkgs, force_yes, 'linaro-hwpack-install')
        self.assertEquals(
            ['%s cp %s %s' % (sudo_args, hwpack_tgz_location, chroot_dir),
             '%s %s %s linaro-hwpack-install --hwpack-version %s '
             '--hwpack-arch %s --hwpack-name %s /%s'
                % (sudo_args, chroot_args, chroot_dir,
                   hwpack_version, hwpack_architecture, hwpack_name,
                   hwpack_file_name)],
            fixture.mock.commands_executed)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            ['%s rm -f %s/hwpack.tgz' % (sudo_args, chroot_dir)],
            fixture.mock.commands_executed)

    def test_install_hwpack_extract(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        chroot_dir = 'chroot_dir'
        hwpack_dir = tempfile.mkdtemp()
        hwpack_file_name = 'hwpack.tgz'
        hwpack_tgz_location = os.path.join(hwpack_dir, hwpack_file_name)
        hwpack_name = "foo"
        hwpack_version = "4"
        hwpack_architecture = "armel"
        extract_kpkgs = True
        self.create_minimal_v3_hwpack(hwpack_tgz_location, hwpack_name,
                                      hwpack_version, hwpack_architecture)
        force_yes = False
        install_hwpack(chroot_dir, hwpack_tgz_location,
                       extract_kpkgs, force_yes, 'linaro-hwpack-install')
        self.assertEquals(
            ['%s cp %s %s' % (sudo_args, hwpack_tgz_location, chroot_dir),
             '%s linaro-hwpack-install --hwpack-version %s '
             '--hwpack-arch %s --hwpack-name %s --extract-kernel-only %s/%s'
                % (sudo_args, hwpack_version, hwpack_architecture, hwpack_name,
                   chroot_dir, hwpack_file_name)],
            fixture.mock.commands_executed)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            ['%s rm -f %s/hwpack.tgz' % (sudo_args, chroot_dir)],
            fixture.mock.commands_executed)

    def test_install_hwpacks(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        chroot_dir = 'chroot_dir'
        tmp_dir = 'tmp_dir'
        self.mock_prepare_chroot(chroot_dir, tmp_dir)
        force_yes = True

        prefer_dir = preferred_tools_dir()

        hwpack_dir = tempfile.mkdtemp()
        hwpack_file_names = ['hwpack1.tgz', 'hwpack2.tgz']
        hwpack_tgz_locations = []
        hwpack_names = []
        extract_kpkgs = False
        for hwpack_file_name in hwpack_file_names:
            hwpack_tgz_location = os.path.join(hwpack_dir, hwpack_file_name)
            hwpack_tgz_locations.append(hwpack_tgz_location)
            hwpack_names.append(hwpack_file_name)
            hwpack_version = "4"
            hwpack_architecture = "armel"
            self.create_minimal_v3_hwpack(
                hwpack_tgz_location, hwpack_file_name, hwpack_version,
                hwpack_architecture)

        install_hwpacks(
            chroot_dir, tmp_dir, prefer_dir, force_yes, [], extract_kpkgs,
            hwpack_tgz_locations[0], hwpack_tgz_locations[1])
        linaro_hwpack_install = find_command(
            'linaro-hwpack-install', prefer_dir=prefer_dir)
        expected = [
            'prepare_chroot %(chroot_dir)s %(tmp_dir)s',
            'cp %(linaro_hwpack_install)s %(chroot_dir)s/usr/bin',
            'mount proc %(chroot_dir)s/proc -t proc',
            'chroot %(chroot_dir)s true',
            'cp %(hwpack1)s %(chroot_dir)s',
            ('%(chroot_args)s %(chroot_dir)s linaro-hwpack-install '
             '--hwpack-version %(hp_version)s '
             '--hwpack-arch %(hp_arch)s --hwpack-name %(hp_name1)s'
             ' --force-yes /hwpack1.tgz'),
            'cp %(hwpack2)s %(chroot_dir)s',
            ('%(chroot_args)s %(chroot_dir)s linaro-hwpack-install '
             '--hwpack-version %(hp_version)s '
             '--hwpack-arch %(hp_arch)s --hwpack-name %(hp_name2)s'
             ' --force-yes /hwpack2.tgz'),
            'rm -f %(chroot_dir)s/hwpack2.tgz',
            'rm -f %(chroot_dir)s/hwpack1.tgz',
            'umount -v %(chroot_dir)s/proc',
            'rm -f %(chroot_dir)s/usr/bin/linaro-hwpack-install']
        keywords = dict(
            chroot_dir=chroot_dir, tmp_dir=tmp_dir, chroot_args=chroot_args,
            linaro_hwpack_install=linaro_hwpack_install,
            hwpack1=hwpack_tgz_locations[0],
            hwpack2=hwpack_tgz_locations[1],
            hp_version=hwpack_version, hp_name1=hwpack_names[0],
            hp_name2=hwpack_names[1], hp_arch=hwpack_architecture)
        expected = [
            "%s %s" % (sudo_args, line % keywords) for line in expected]
        self.assertEquals(expected, fixture.mock.commands_executed)

    def test_install_packages(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        chroot_dir = 'chroot_dir'
        tmp_dir = 'tmp_dir'
        self.mock_prepare_chroot(chroot_dir, tmp_dir)

        install_packages(chroot_dir, tmp_dir, 'pkg1', 'pkg2')
        expected = [
            'prepare_chroot %(chroot_dir)s %(tmp_dir)s',
            'mount proc %(chroot_dir)s/proc -t proc',
            '%(chroot_args)s %(chroot_dir)s apt-get --yes install pkg1 pkg2',
            '%(chroot_args)s %(chroot_dir)s apt-get clean',
            'umount -v %(chroot_dir)s/proc']
        keywords = dict(
            chroot_dir=chroot_dir, tmp_dir=tmp_dir, chroot_args=chroot_args)
        expected = [
            "%s %s" % (sudo_args, line % keywords) for line in expected]
        self.assertEquals(expected, fixture.mock.commands_executed)

    def test_prepare_chroot(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        fixture = self.useFixture(MockCmdRunnerPopenFixture())

        prepare_chroot('chroot', '/tmp/dir')
        run_local_atexit_funcs()
        expected = [
            'cp /etc/resolv.conf chroot/etc',
            'cp /etc/hosts chroot/etc',
            'cp /usr/bin/qemu-armeb-static chroot/usr/bin',
            'cp /usr/bin/qemu-arm-static chroot/usr/bin',
            'cp /usr/bin/qemu-aarch64-static chroot/usr/bin',
            'rm -f chroot/usr/bin/qemu-aarch64-static',
            'rm -f chroot/usr/bin/qemu-arm-static',
            'rm -f chroot/usr/bin/qemu-armeb-static',
            'rm -f chroot/etc/hosts',
            'rm -f chroot/etc/resolv.conf']
        expected = [
            "%s %s" % (sudo_args, line) for line in expected]
        self.assertEquals(expected, fixture.mock.commands_executed)

    def test_run_local_atexit_funcs(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stderr', open('/dev/null', 'w')))
        self.call_order = []

        class TestException(Exception):
            pass

        def raising_func():
            self.call_order.append('raising_func')
            raise TestException()

        def behaving_func():
            self.call_order.append('behaving_func')
            self.behaving_func_called = True
        # run_local_atexit_funcs() runs the atexit handlers in LIFO order, but
        # even though the first function called (raising_func) will raise
        # an exception, the second one will still be called after it.
        linaro_image_tools.media_create.chroot_utils.local_atexit = [
            behaving_func, raising_func]
        # run_local_atexit_funcs() also propagates the last exception raised
        # by one of the functions.
        chroot_utils = linaro_image_tools.media_create.chroot_utils
        self.assertRaises(TestException, chroot_utils.run_local_atexit_funcs)
        self.assertEquals(
            ['raising_func', 'behaving_func'], self.call_order)

    def test_hwpack_atexit(self):
        self.run_local_atexit_functions_called = False

        def mock_run_local_atexit_functions():
            self.run_local_atexit_functions_called = True

        def mock_install_hwpack(p1, p2, p3, p4):
            raise Exception('hwpack mock exception')

        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.chroot_utils, 'install_hwpack',
            mock_install_hwpack))
        self.useFixture(MockSomethingFixture(
            linaro_image_tools.media_create.chroot_utils,
            'run_local_atexit_funcs',
            mock_run_local_atexit_functions))

        force_yes = True
        exception_caught = False
        extract_kpkgs = False
        try:
            install_hwpacks(
                'chroot', '/tmp/dir', preferred_tools_dir(), force_yes, [],
                extract_kpkgs, 'hwp.tgz', 'hwp2.tgz')
        except:
            exception_caught = True
        self.assertTrue(self.run_local_atexit_functions_called)
        self.assertTrue(exception_caught)

    def setUp(self):
        super(TestInstallHWPack, self).setUp()

        # Ensure the list of cleanup functions gets cleared to make sure tests
        # don't interfere with one another.

        def clear_atexits():
            linaro_image_tools.media_create.chroot_utils.local_atexit = []
        self.addCleanup(clear_atexits)
