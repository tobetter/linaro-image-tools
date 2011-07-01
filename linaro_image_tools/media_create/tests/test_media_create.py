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

from StringIO import StringIO
from testtools import TestCase

from linaro_image_tools import cmd_runner
import linaro_image_tools.media_create
from linaro_image_tools.media_create import (
    check_device,
    boards,
    partitions,
    rootfs,
    android_boards,
    )
from linaro_image_tools.media_create.boards import (
    LOADER_MIN_SIZE_S,
    SAMSUNG_V310_BL1_START,
    SAMSUNG_V310_BL2_START,
    SECTOR_SIZE,
    align_up,
    align_partition,
    board_configs,
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
    HardwarepackHandler,
    BoardConfig,
    )
from linaro_image_tools.media_create.android_boards import (
    android_board_configs,
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
    SECTORS,
    calculate_partition_size_and_offset,
    calculate_android_partition_size_and_offset,
    convert_size_to_bytes,
    create_partitions,
    ensure_partition_is_not_mounted,
    get_boot_and_root_loopback_devices,
    get_android_loopback_devices,
    get_boot_and_root_partitions_for_media,
    Media,
    run_sfdisk_commands,
    setup_partitions,
    get_uuid,
    _parse_blkid_output,
    )
from linaro_image_tools.media_create.rootfs import (
    append_to_fstab,
    create_flash_kernel_config,
    has_space_left_for_swap,
    move_contents,
    populate_rootfs,
    rootfs_mount_options,
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
        data = '1.0'
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
        format1 = "%s\n" % '1.0'
        format2 = "%s\n" % '2.0'
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
        format1 = "%s\n" % '2.0'
        format2 = "%s\n" % '2.0'
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
        metadata = self.metadata + "TEST=%s\n" % data
        tarball = self.add_to_tarball(
            [('metadata', metadata)])
        hp = HardwarepackHandler([tarball])
        with hp:
            test_data, _ = hp.get_field(hp.main_section, 'test')
            self.assertEqual(test_data, data)

    def test_preserves_formatters(self):
        data = '%s%d'
        metadata = self.metadata + "TEST=%s\n" % data
        tarball = self.add_to_tarball(
            [('metadata', metadata)])
        hp = HardwarepackHandler([tarball])
        with hp:
            test_data, _ = hp.get_field(hp.main_section, 'test')
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
        metadata_file = 'TESTFILE'
        file_in_archive = 'testfile'
        metadata = self.metadata + "%s=%s\n" % (metadata_file, file_in_archive)
        tarball = self.add_to_tarball(
            [('metadata', metadata),
             (file_in_archive, data)])
        hp = HardwarepackHandler([tarball])
        with hp:
            test_file = hp.get_file(metadata_file)
            self.assertEquals(data, open(test_file, 'r').read())
        

class TestSetMetadata(TestCaseWithFixtures):

    class MockHardwarepackHandler(HardwarepackHandler):
        metadata_dict = {}

        def __enter__(self):
            return self

        def get_field(self, section, field):
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

        class config(BoardConfig):
            pass
        config.set_metadata('ahwpack.tar.gz')
        self.assertEquals(None, config.kernel_addr)

    def test_sets_kernel_addr(self):
        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards, 'HardwarepackHandler',
                self.MockHardwarepackHandler))
        field_to_test = 'kernel_addr'
        data_to_set = '0x8123ABCD'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
            }
        class config(BoardConfig):
            pass
        config.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, config.kernel_addr)

    def test_sets_initrd_addr(self):
        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards, 'HardwarepackHandler',
                self.MockHardwarepackHandler))
        field_to_test = 'initrd_addr'
        data_to_set = '0x8123ABCD'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
            }
        class config(BoardConfig):
            pass
        config.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, config.initrd_addr)

    def test_sets_load_addr(self):
        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards, 'HardwarepackHandler',
                self.MockHardwarepackHandler))
        field_to_test = 'load_addr'
        data_to_set = '0x8123ABCD'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
            }
        class config(BoardConfig):
            pass
        config.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, config.load_addr)

    def test_sets_serial_tty(self):
        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards, 'HardwarepackHandler',
                self.MockHardwarepackHandler))
        field_to_test = 'serial_tty'
        data_to_set = 'ttyAA'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
            }
        class config(BoardConfig):
            pass
        config.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, config.serial_tty)

    def test_sets_wired_interfaces(self):
        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards, 'HardwarepackHandler',
                self.MockHardwarepackHandler))
        field_to_test = 'wired_interfaces'
        data_to_set = 'eth0 eth1'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
            }
        class config(BoardConfig):
            pass
        config.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, config.wired_interfaces)

    def test_sets_wireless_interfaces(self):
        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards, 'HardwarepackHandler',
                self.MockHardwarepackHandler))
        field_to_test = 'wireless_interfaces'
        data_to_set = 'wlan0 wl1'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
            }
        class config(BoardConfig):
            pass
        config.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, config.wireless_interfaces)

    def test_sets_mmc_id(self):
        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards, 'HardwarepackHandler',
                self.MockHardwarepackHandler))
        field_to_test = 'mmc_id'
        data_to_set = '1'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
            }
        class config(BoardConfig):
            pass
        config.set_metadata('ahwpack.tar.gz')
        self.assertEquals(data_to_set, config.mmc_id)

    def test_sets_partition_layout_32(self):
        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards, 'HardwarepackHandler',
                self.MockHardwarepackHandler))
        field_to_test = 'partition_layout'
        data_to_set = 'bootfs_rootfs'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
            }
        class config(BoardConfig):
            pass
        config.set_metadata('ahwpack.tar.gz')
        self.assertEquals(32, config.fat_size)

    def test_sets_partition_layout_16(self):
        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards, 'HardwarepackHandler',
                self.MockHardwarepackHandler))
        field_to_test = 'partition_layout'
        data_to_set = 'bootfs16_rootfs'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
            }
        class config(BoardConfig):
            pass
        config.set_metadata('ahwpack.tar.gz')
        self.assertEquals(16, config.fat_size)

    def test_sets_partition_layout_raises(self):
        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards, 'HardwarepackHandler',
                self.MockHardwarepackHandler))
        field_to_test = 'partition_layout'
        data_to_set = 'bootfs_bogus_rootfs'
        self.MockHardwarepackHandler.metadata_dict = {
            field_to_test: data_to_set,
            }
        class config(BoardConfig):
            pass
        self.assertRaises(AssertionError, config.set_metadata, 'ahwpack.tar.gz')


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


class TestGetSMDKSPL(TestCaseWithFixtures):

    def test_no_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        uboot_flavor = "some_uboot_flavour"
        self.assertRaises(
            AssertionError, boards.SMDKV310Config._get_smdk_spl, tempdir,
            uboot_flavor)

    def test_old_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        uboot_flavor = "some_uboot_flavour"
        path = os.path.join(tempdir, 'usr', 'lib', 'u-boot', uboot_flavor)
        os.makedirs(path)
        spl_path = os.path.join(path, 'v310_mmc_spl.bin')
        open(spl_path, 'w').close()
        self.assertEquals(spl_path, boards.SMDKV310Config._get_smdk_spl(
                tempdir, uboot_flavor))

    def test_new_file_present(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        uboot_flavor = "some_uboot_flavour"
        path = os.path.join(tempdir, 'usr', 'lib', 'u-boot', uboot_flavor)
        os.makedirs(path)
        spl_path = os.path.join(path, 'u-boot-mmc-spl.bin')
        open(spl_path, 'w').close()
        self.assertEquals(spl_path, boards.SMDKV310Config._get_smdk_spl(
                tempdir, uboot_flavor))

    def test_prefers_old_path(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        uboot_flavor = "some_uboot_flavour"
        path = os.path.join(tempdir, 'usr', 'lib', 'u-boot', uboot_flavor)
        os.makedirs(path)
        old_spl_path = os.path.join(path, 'v310_mmc_spl.bin')
        new_spl_path = os.path.join(path, 'u-boot-mmc-spl.bin')
        open(old_spl_path, 'w').close()
        open(new_spl_path, 'w').close()
        self.assertEquals(old_spl_path, boards.SMDKV310Config._get_smdk_spl(
                tempdir, uboot_flavor))


class TestGetSMDKUboot(TestCaseWithFixtures):

    def test_uses_uboot_flavour(self):
        chroot_dir = "chroot"
        uboot_flavor = "some_uboot_flavour"
        uboot_file = os.path.join(chroot_dir, 'usr', 'lib', 'u-boot', uboot_flavor,
            'u-boot.bin')
        self.assertEquals(uboot_file, boards.SMDKV310Config._get_smdk_uboot(
                chroot_dir, uboot_flavor))


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
            boards.SnowballEmmcConfig.create_toc(f, files)
        with open(filename, 'r') as f:
            actual = f.read()
        self.assertEquals(96, len(actual))
        for i in range(len(actual)):
            self.assertEquals(self.expected[i], actual[i], 'Mismatch at ix' \
                ' %d, ref=%c, actual=%c' % (i, self.expected[i], actual[i]))

    def test_create_toc_error_too_large_section_name(self):
        '''Verify that trying to write past the end of the
           section name field raises an exception'''
        illegal_name_data = [(0, 0, 0, 0, 0, 'Too_longName')]
        files = self.create_files_structure(illegal_name_data)
        with open(os.path.join(self.tempdir, 'toc'), 'w') as f:
            self.assertRaises(AssertionError,
                              boards.SnowballEmmcConfig.create_toc,
                              f, files)

    def test_create_toc_error_negative_unsigned(self):
        '''Verify that trying to write a negative number to an unsigned
           field raises an exception'''
        illegal_unsigned_data = [(-3, 0, 0, 0, 0, 'xxx')]
        files = self.create_files_structure(illegal_unsigned_data)
        with open(os.path.join(self.tempdir, 'toc'), 'w') as f:
            self.assertRaises(struct.error,
                              boards.SnowballEmmcConfig.create_toc,
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
        if not os.path.exists(self.temp_bootdir_path):
            os.makedirs(self.temp_bootdir_path)

    def setupFiles(self):
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
        cfg_file = os.path.join(self.temp_bootdir_path,
        boards.SnowballEmmcConfig.SNOWBALL_STARTUP_FILES_CONFIG)
        with open(cfg_file, 'w') as f:
            for line in src_data:
                # Write comments, so we test that the parser can read them
                f.write('#Yet another comment\n')
                f.write('%s %s %i %#x %s\n' % line)
        expected = []
        # Define dummy binary files, containing nothing but their own
        # section names.
        for line in src_data:
            with open(os.path.join(self.temp_bootdir_path, line[1]), 'w') as f:
                f.write(line[0])
        #define the expected values read from the config file
        expected = []
        ofs = [boards.SnowballEmmcConfig.TOC_SIZE,
               boards.SnowballEmmcConfig.TOC_SIZE + len('ISSW'), 0x160000,
               0x170000, 0xBA0000, 0xC1F000]
        size = [len('ISSW'), len('X-LOADER'), len('MEM_INIT'), \
                len('PWR_MGT'), len('NORMAL'), len('UBOOT_ENV')]
        i = 0
        for line in src_data:
            filename = os.path.join(self.temp_bootdir_path, line[1])
            expected.append({'section_name': line[0],
                             'filename': filename,
                             'align': int(line[2]),
                             'offset': ofs[i],
                             'size': long(size[i]),
                             'load_adress': line[4]})
            i += 1
        return expected

    def test_file_name_size(self):
        ''' Test using a to large toc file '''
        _, toc_filename = tempfile.mkstemp()
        atexit.register(os.unlink, toc_filename)
        filedata = 'X'
        bytes = boards.SnowballEmmcConfig.TOC_SIZE + 1
        tmpfile = open(toc_filename, 'wb')
        for n in xrange(bytes):
            tmpfile.write(filedata)
        tmpfile.close()
        files = self.setupFiles()
        self.assertRaises(AssertionError,
            boards.SnowballEmmcConfig.install_snowball_boot_loader,
            toc_filename, files, "boot_device_or_file",
            boards.SnowballEmmcConfig.SNOWBALL_LOADER_START_S)

    def test_install_snowball_boot_loader_toc(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        toc_filename = self.createTempFileAsFixture()
        files = self.setupFiles()
        boards.SnowballEmmcConfig.install_snowball_boot_loader(toc_filename,
            files, "boot_device_or_file",
            boards.SnowballEmmcConfig.SNOWBALL_LOADER_START_S)
        expected = [
            '%s dd if=%s of=boot_device_or_file bs=512 conv=notrunc' \
            ' seek=%s' % (sudo_args, toc_filename,
            boards.SnowballEmmcConfig.SNOWBALL_LOADER_START_S),
            '%s dd if=%s/boot_image_issw.bin of=boot_device_or_file bs=512' \
            ' conv=notrunc seek=257' % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/boot_image_issw.bin' % (sudo_args,
            self.temp_bootdir_path),
            '%s dd if=%s/boot_image_x-loader.bin of=boot_device_or_file' \
            ' bs=1 conv=notrunc seek=131588'
            % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/boot_image_x-loader.bin' % (sudo_args,
            self.temp_bootdir_path),
            '%s dd if=%s/mem_init.bin of=boot_device_or_file bs=512' \
            ' conv=notrunc seek=3072' % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/mem_init.bin' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/power_management.bin of=boot_device_or_file bs=512' \
            ' conv=notrunc seek=3200' % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/power_management.bin' % (sudo_args,
            self.temp_bootdir_path),
            '%s dd if=%s/u-boot.bin of=boot_device_or_file bs=512' \
            ' conv=notrunc seek=24064' % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/u-boot.bin' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/u-boot-env.bin of=boot_device_or_file bs=512'
            ' conv=notrunc seek=25080' % (sudo_args, self.temp_bootdir_path),
            '%s rm %s/u-boot-env.bin' % (sudo_args, self.temp_bootdir_path)]

        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_snowball_make_boot_files(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(tempfile, 'mkstemp',
            lambda: (-1, '/tmp/temp_snowball_make_boot_files')))
        self.setupFiles()
        k_img_file = os.path.join(self.tempdir, 'vmlinuz-1-ux500')
        i_img_file = os.path.join(self.tempdir, 'initrd.img-1-ux500')

        boot_env = board_configs['snowball_emmc']._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="test_boot_env_uuid", d_img_data=None)
        boards.SnowballEmmcConfig._make_boot_files(boot_env, self.tempdir,
            self.temp_bootdir_path, 'boot_device_or_file', k_img_file,
            i_img_file, None)
        expected = [
            '%s mkimage -A arm -O linux -T kernel -C none -a 0x00008000 -e' \
            ' 0x00008000 -n Linux -d %s %s/boot/uImage' % (sudo_args,
            k_img_file, self.tempdir),
            '%s cp /tmp/temp_snowball_make_boot_files %s/boot/boot.txt'
            % (sudo_args, self.tempdir),
            '%s mkimage -A arm -O linux -T script -C none -a 0 -e 0 -n boot' \
            ' script -d %s/boot/boot.txt %s/boot/flash.scr'
            % (sudo_args, self.tempdir, self.tempdir),
            '%s dd if=/tmp/temp_snowball_make_boot_files' \
            ' of=boot_device_or_file bs=512 conv=notrunc seek=256'
            % (sudo_args),
            '%s dd if=%s/boot/boot_image_issw.bin of=boot_device_or_file' \
            ' bs=512 conv=notrunc seek=257' % (sudo_args, self.tempdir),
            '%s rm %s/boot_image_issw.bin' % (sudo_args,
            self.temp_bootdir_path),
            '%s dd if=%s/boot/boot_image_x-loader.bin of=boot_device_or_file' \
            ' bs=1 conv=notrunc seek=131588' % (sudo_args, self.tempdir),
            '%s rm %s/boot_image_x-loader.bin' % (sudo_args,
            self.temp_bootdir_path),
            '%s dd if=%s/boot/mem_init.bin of=boot_device_or_file bs=512' \
            ' conv=notrunc seek=3072' % (sudo_args, self.tempdir),
            '%s rm %s/mem_init.bin' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/boot/power_management.bin of=boot_device_or_file' \
            ' bs=512 conv=notrunc seek=3200' % (sudo_args, self.tempdir),
            '%s rm %s/power_management.bin' % (sudo_args,
            self.temp_bootdir_path),
            '%s dd if=%s/boot/u-boot.bin of=boot_device_or_file bs=512' \
            ' conv=notrunc seek=24064' % (sudo_args, self.tempdir),
            '%s rm %s/u-boot.bin' % (sudo_args, self.temp_bootdir_path),
            '%s dd if=%s/boot/u-boot-env.bin of=boot_device_or_file bs=512' \
            ' conv=notrunc seek=25080' % (sudo_args, self.tempdir),
            '%s rm %s/u-boot-env.bin' % (sudo_args, self.temp_bootdir_path),
            '%s rm /tmp/temp_snowball_make_boot_files' % (sudo_args),
            '%s rm %s/startfiles.cfg' % (sudo_args, self.temp_bootdir_path)]

        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_missing_files(self):
        '''When the files cannot be read, an IOError should be raised'''
        self.assertRaises(IOError,
                          boards.SnowballEmmcConfig.get_file_info,
                          self.tempdir)

    def test_normal_case(self):
        expected = self.setupFiles()
        actual = boards.SnowballEmmcConfig.get_file_info(
            self.temp_bootdir_path)
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
            if type(attr) == types.FunctionType:
                self.useFixture(MockSomethingFixture(
                    linaro_image_tools.media_create.boards, name,
                    mock_func_creator(name)))

    def mock_set_appropriate_serial_tty(self, config):

        def set_appropriate_serial_tty_mock(cls, chroot_dir):
            cls.serial_tty = cls._serial_tty

        self.useFixture(MockSomethingFixture(
            config, 'set_appropriate_serial_tty',
            classmethod(set_appropriate_serial_tty_mock)))

    def make_boot_files(self, config):
        def _get_kflavor_files_mock(cls, path):
            if cls.dtb_name is None:
                return (path, path, None)
            return (path, path, path)

        self.useFixture(MockSomethingFixture(
            config, '_get_kflavor_files',
            classmethod(_get_kflavor_files_mock)))

        config.make_boot_files('', False, False, [], '', '', '', '')

    def test_vexpress_steps(self):
        self.make_boot_files(boards.VexpressConfig)
        expected = ['make_uImage', 'make_uInitrd']
        self.assertEqual(expected, self.funcs_calls)

    def test_mx5_steps(self):
        class SomeMx5Config(boards.Mx5Config):
            uboot_flavor = 'uboot_flavor'
        SomeMx5Config.hardwarepack_handler = (
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz'))
        SomeMx5Config.hardwarepack_handler.get_format = (
            lambda: '1.0')
        self.make_boot_files(SomeMx5Config)
        expected = [
            'install_mx5_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_dtb', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_smdkv310_steps(self):
        def mock_func_creator(name):
            return classmethod(
                lambda *args, **kwargs: self.funcs_calls.append(name))

        self.useFixture(MockSomethingFixture(
                linaro_image_tools.media_create.boards.SMDKV310Config,
                'install_smdk_boot_loader',
                mock_func_creator('install_smdk_boot_loader')))
        boards.SMDKV310Config.hardwarepack_handler = (
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz'))
        boards.SMDKV310Config.hardwarepack_handler.get_format = (
            lambda: '1.0')
        self.make_boot_files(boards.SMDKV310Config)
        expected = [
            'install_smdk_boot_loader', 'make_flashable_env', '_dd', 'make_uImage',
            'make_uInitrd', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_ux500_steps(self):
        self.make_boot_files(boards.Ux500Config)
        expected = ['make_uImage', 'make_uInitrd', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_snowball_sd_steps(self):
        self.make_boot_files(boards.SnowballSdConfig)
        expected = ['make_uImage', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_panda_steps(self):
        self.mock_set_appropriate_serial_tty(boards.PandaConfig)
        self.make_boot_files(boards.PandaConfig)
        expected = [
            'install_omap_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_dtb', 'make_boot_script', 'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_beagle_steps(self):
        self.mock_set_appropriate_serial_tty(boards.BeagleConfig)
        self.make_boot_files(boards.BeagleConfig)
        expected = [
            'install_omap_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_dtb', 'make_boot_script', 'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_igep_steps(self):
        self.mock_set_appropriate_serial_tty(boards.IgepConfig)
        self.make_boot_files(boards.IgepConfig)
        expected = [
            'make_uImage', 'make_uInitrd', 'make_dtb', 'make_boot_script',
            'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_overo_steps(self):
        self.mock_set_appropriate_serial_tty(boards.OveroConfig)
        self.make_boot_files(boards.OveroConfig)
        expected = [
            'install_omap_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_dtb', 'make_boot_script', 'make_boot_ini']
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
            align_partition(1, 1, 4 * 1024 * 1024, 4 * 1024 * 1024))

    def test_align_partition_none_4_mib(self):
        expected = (1, 4 * 1024 * 1024 - 1, 4 * 1024 * 1024 - 1)
        self.assertEqual(expected,
            align_partition(1, 1, 1, 4 * 1024 * 1024))


class TestFixForBug697824(TestCaseWithFixtures):

    def mock_set_appropriate_serial_tty(self, config):

        def set_appropriate_serial_tty_mock(cls, chroot_dir):
            self.set_appropriate_serial_tty_called = True
            cls.serial_tty = cls._serial_tty

        self.useFixture(MockSomethingFixture(
            config, 'set_appropriate_serial_tty',
            classmethod(set_appropriate_serial_tty_mock)))

    def test_omap_make_boot_files(self):
        self.set_appropriate_serial_tty_called = False
        self.mock_set_appropriate_serial_tty(board_configs['beagle'])
        self.useFixture(MockSomethingFixture(
            boards.BoardConfig, 'make_boot_files',
            classmethod(lambda *args: None)))
        # We don't need to worry about what's passed to make_boot_files()
        # because we mock the method which does the real work above and here
        # we're only interested in ensuring that OmapConfig.make_boot_files()
        # calls set_appropriate_serial_tty().
        board_configs['beagle'].make_boot_files(
            None, None, None, None, None, None, None, None)
        self.assertTrue(
            self.set_appropriate_serial_tty_called,
            "make_boot_files didn't call set_appropriate_serial_tty")

    def test_set_appropriate_serial_tty_old_kernel(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        boot_dir = os.path.join(tempdir, 'boot')
        os.makedirs(boot_dir)
        open(os.path.join(boot_dir, 'vmlinuz-2.6.35-23-foo'), 'w').close()
        boards.BeagleConfig.set_appropriate_serial_tty(tempdir)
        self.assertEquals('ttyS2', boards.BeagleConfig.serial_tty)

    def test_set_appropriate_serial_tty_new_kernel(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        boot_dir = os.path.join(tempdir, 'boot')
        os.makedirs(boot_dir)
        open(os.path.join(boot_dir, 'vmlinuz-2.6.36-13-foo'), 'w').close()
        boards.BeagleConfig.set_appropriate_serial_tty(tempdir)
        self.assertEquals('ttyO2', boards.BeagleConfig.serial_tty)


class TestGetSfdiskCmd(TestCase):

    def test_default(self):
        self.assertEqual(
            '63,106432,0x0C,*\n106496,,,-',
            boards.BoardConfig.get_sfdisk_cmd())

    def test_default_aligned(self):
        self.assertEqual(
            '8192,106496,0x0C,*\n114688,,,-',
            boards.BoardConfig.get_sfdisk_cmd(should_align_boot_part=True))

    def test_mx5(self):
        self.assertEqual(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            boards.Mx5Config.get_sfdisk_cmd())

    def test_snowball_sd(self):
        self.assertEqual(
            '63,106432,0x0C,*\n106496,,,-',
            boards.SnowballSdConfig.get_sfdisk_cmd())

    def test_snowball_emmc(self):
        self.assertEqual(
            '256,7936,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            boards.SnowballEmmcConfig.get_sfdisk_cmd())

    def test_smdkv310(self):
        self.assertEquals(
            '1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-',
            board_configs['smdkv310'].get_sfdisk_cmd())

    def test_panda_android(self):
        self.assertEqual(
            '63,270272,0x0C,*\n270336,524288,L\n794624,524288,L\n' \
                '1318912,-,E\n1318912,1048576,L\n2367488,,,-', 
                android_boards.AndroidPandaConfig.get_sfdisk_cmd())

    def test_snowball_emmc_android(self):
        self.assertEqual(
            '256,7936,0xDA\n8192,262144,0x0C,*\n270336,524288,L\n' \
                '794624,-,E\n794624,524288,L\n1318912,1048576,L\n2367488,,,-', 
                android_boards.AndroidSnowballEmmcConfig.get_sfdisk_cmd())


class TestGetBootCmd(TestCase):

    def test_vexpress(self):
        boot_commands = board_configs['vexpress']._get_boot_env(
            is_live=False, is_lowmem=False, consoles=['ttyXXX'],
            rootfs_uuid="deadbeef", d_img_data=None)
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA0,38400n8 '
                        'console=ttyXXX  root=UUID=deadbeef rootwait ro',
            'bootcmd': 'fatload mmc 0:1 0x60008000 uImage; '
                       'fatload mmc 0:1 0x81000000 uInitrd; '
                       'bootm 0x60008000 0x81000000'}
        self.assertEqual(expected, boot_commands)

    def test_mx51(self):
        boot_commands = boards.Mx51Config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef", d_img_data="mx51.dtb")
        expected = {
            'bootargs': 'console=tty0 console=ttymxc0,115200n8  '
                        'root=UUID=deadbeef rootwait ro',
            'bootcmd': 'fatload mmc 0:2 0x90000000 uImage; '
                       'fatload mmc 0:2 0x92000000 uInitrd; '
                       'fatload mmc 0:2 0x91ff0000 board.dtb; '
                       'bootm 0x90000000 0x92000000 0x91ff0000'}
        self.assertEqual(expected, boot_commands)

    def test_smdkv310(self):
        boot_commands = board_configs['smdkv310']._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef", d_img_data=None)
        expected = {
            'bootargs': 'console=ttySAC1,115200n8  root=UUID=deadbeef '
                        'rootwait ro',
             'bootcmd': 'fatload mmc 0:2 0x40007000 uImage; '
                        'fatload mmc 0:2 0x42000000 uInitrd; '
                        'bootm 0x40007000 0x42000000',
             'ethact': 'smc911x-0',
             'ethaddr': '00:40:5c:26:0a:5b'}
        self.assertEqual(expected, boot_commands)

    def test_ux500(self):
        boot_commands = board_configs['ux500']._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef", d_img_data=None)
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk '
                        'rootdelay=1 fixrtc nocompcache mem=96M@0 '
                        'mem_modem=32M@96M mem=44M@128M pmem=22M@172M '
                        'mem=30M@194M mem_mali=32M@224M pmem_hwb=54M@256M '
                        'hwmem=48M@302M mem=152M@360M',
            'bootcmd': 'fatload mmc 1:1 0x00100000 uImage; '
                       'fatload mmc 1:1 0x08000000 uInitrd; '
                       'bootm 0x00100000 0x08000000'}
        self.assertEqual(expected, boot_commands)

    def test_snowball_emmc(self):
        boot_commands = board_configs['snowball_emmc']._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef", d_img_data=None)
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk '
                        'rootdelay=1 fixrtc nocompcache mem=96M@0 '
                        'mem_modem=32M@96M mem=44M@128M pmem=22M@172M '
                        'mem=30M@194M mem_mali=32M@224M pmem_hwb=54M@256M '
                        'hwmem=48M@302M mem=152M@360M',
            'bootcmd': 'fatload mmc 1:1 0x00100000 uImage; '
                       'fatload mmc 1:1 0x08000000 uInitrd; '
                       'bootm 0x00100000 0x08000000'}
        self.assertEqual(expected, boot_commands)


    def test_panda(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = board_configs['panda']
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef", d_img_data="panda.dtb")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=48M omapfb.vram=0:24M '
                        'mem=456M@0x80000000 mem=512M@0xA0000000',
            'bootcmd': 'fatload mmc 0:1 0x80200000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'fatload mmc 0:1 0x815f0000 board.dtb; '
                       'bootm 0x80200000 0x81600000 0x815f0000'}
        self.assertEqual(expected, boot_commands)

    def test_beagle(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = board_configs['beagle']
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef", d_img_data="beagle.dtb")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=12M '
                        'omapfb.mode=dvi:1280x720MR-16@60 mpurate=${mpurate}',
            'bootcmd': 'fatload mmc 0:1 0x80000000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'fatload mmc 0:1 0x815f0000 board.dtb; '
                       'bootm 0x80000000 0x81600000 0x815f0000'}
        self.assertEqual(expected, boot_commands)

    def test_igep(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = boards.IgepConfig
        config.serial_tty = config._serial_tty
        boot_cmd = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef", d_img_data="igep.dtb")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=12M '
                        'omapfb.mode=dvi:1280x720MR-16@60 mpurate=${mpurate}',
            'bootcmd': 'fatload mmc 0:1 0x80000000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'fatload mmc 0:1 0x815f0000 board.dtb; '
                       'bootm 0x80000000 0x81600000 0x815f0000'}
        self.assertEqual(expected, boot_cmd)

    def test_overo(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = board_configs['overo']
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef", d_img_data="overo.dtb")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk '
                        'mpurate=${mpurate} vram=12M',
            'bootcmd': 'fatload mmc 0:1 0x80000000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'fatload mmc 0:1 0x815f0000 board.dtb; '
                       'bootm 0x80000000 0x81600000 0x815f0000'}
        self.assertEqual(expected, boot_commands)


class TestGetBootCmdAndroid(TestCase):
    def test_panda(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = android_board_configs['panda']
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(consoles=[])
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8 '
                        'rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=48M omapfb.vram=0:24M,1:24M '
                        'mem=456M@0x80000000 mem=512M@0xA0000000 '
                        'init=/init androidboot.console=ttyO2',
            'bootcmd': 'fatload mmc 0:1 0x80200000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'bootm 0x80200000 0x81600000'}
        self.assertEqual(expected, boot_commands)
	
    def test_android_snowball_emmc(self):
        boot_commands = (android_boards.AndroidSnowballEmmcConfig.
                         _get_boot_env(consoles=[]))
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA2,115200n8 '
                        'rootwait ro earlyprintk '
                        'rootdelay=1 fixrtc nocompcache '
                        'mem=128M@0 mali.mali_mem=64M@128M mem=24M@192M '
                        'hwmem=167M@216M mem_issw=1M@383M mem=640M@384M '
                        'vmalloc=256M init=/init androidboot.console=ttyAMA2',
            'bootcmd': 'fatload mmc 1:1 0x00100000 uImage; '
                       'fatload mmc 1:1 0x08000000 uInitrd; '
                       'bootm 0x00100000 0x08000000'}
        self.assertEqual(expected, boot_commands)


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
        install_mx5_boot_loader(imx_file, "boot_device_or_file")
        expected = [
            '%s dd if=%s of=boot_device_or_file bs=512 '
            'conv=notrunc seek=2' % (sudo_args, imx_file)]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_install_mx5_boot_loader_too_large(self):
        self.useFixture(MockSomethingFixture(
            os.path, "getsize",
            lambda s: (LOADER_MIN_SIZE_S - 1) * SECTOR_SIZE + 1))
        self.assertRaises(AssertionError,
            install_mx5_boot_loader, "imx_file", "boot_device_or_file")

    def test_install_omap_boot_loader(self):
        fixture = self._mock_Popen()
        self.useFixture(MockSomethingFixture(
            boards, '_get_mlo_file',
            lambda chroot_dir: "%s/MLO" % chroot_dir))
        install_omap_boot_loader("chroot_dir", "boot_disk")
        expected = [
            '%s cp -v chroot_dir/MLO boot_disk' % sudo_args, 'sync']
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_install_smdk_u_boot(self):
        fixture = self._mock_Popen()
        uboot_flavor = "some_u_boot_flavour"
        self.useFixture(MockSomethingFixture(
            boards.SMDKV310Config, '_get_smdk_spl',
            classmethod(lambda cls, chroot_dir, uboot_flavor: "%s/%s/SPL" % (
                        chroot_dir, uboot_flavor))))
        self.useFixture(MockSomethingFixture(
            boards.SMDKV310Config, '_get_smdk_uboot',
            classmethod(lambda cls, chroot_dir, uboot_flavor: "%s/%s/uboot" % (
                        chroot_dir, uboot_flavor))))
        boards.SMDKV310Config.hardwarepack_handler = (
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz'))
        boards.SMDKV310Config.hardwarepack_handler.get_format = (
            lambda: '1.0')
        self.useFixture(MockSomethingFixture(os.path, 'getsize',
                                             lambda file: 1))
        boards.SMDKV310Config.install_smdk_boot_loader(
            "chroot_dir", "boot_disk", uboot_flavor)
        expected = [
            '%s dd if=chroot_dir/%s/SPL of=boot_disk bs=512 conv=notrunc '
            'seek=%d' % (sudo_args, uboot_flavor, SAMSUNG_V310_BL1_START),
            '%s dd if=chroot_dir/%s/uboot of=boot_disk bs=512 conv=notrunc '
            'seek=%d' % (sudo_args, uboot_flavor, SAMSUNG_V310_BL2_START)]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_get_plain_boot_script_contents(self):
        boot_env = {'bootargs': 'mybootargs', 'bootcmd': 'mybootcmd'}
        boot_script_data = get_plain_boot_script_contents(boot_env)
        self.assertEqual(textwrap.dedent("""\
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
        boot_env = {'bootargs': 'mybootargs', 'bootcmd': 'mybootcmd'}
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
        class config(boards.BoardConfig):
            kernel_flavors = [flavorx, flavorxy]
        for f in reversed(config.kernel_flavors):
            kfile = os.path.join(tempdir, 'vmlinuz-1-%s' % f)
            ifile = os.path.join(tempdir, 'initrd.img-1-%s' % f)
            open(kfile, "w").close()
            open(ifile, "w").close()
        self.assertEqual(
            (kfile, ifile, None), config._get_kflavor_files(tempdir))

    def test_get_dt_kflavor_files_more_specific(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        flavorx = 'flavorX'
        flavorxy = 'flavorXY'
        class config(boards.BoardConfig):
            kernel_flavors = [flavorx, flavorxy]
            dtb_name = 'board_name.dtb'
        for f in reversed(config.kernel_flavors):
            kfile = os.path.join(tempdir, 'vmlinuz-1-%s' % f)
            ifile = os.path.join(tempdir, 'initrd.img-1-%s' % f)
            dt = os.path.join(tempdir, 'dt-1-%s' % f)
            os.mkdir(dt)
            dfile = os.path.join(dt, config.dtb_name)
            open(kfile, "w").close()
            open(ifile, "w").close()
            open(dfile, "w").close()
        self.assertEqual(
            (kfile, ifile, dfile), config._get_kflavor_files(tempdir))

    def test_get_kflavor_files_later_in_flavors(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        flavor1 = 'flavorXY'
        flavor2 = 'flavorAA'
        class config(boards.BoardConfig):
            kernel_flavors = [flavor1, flavor2]
        kfile = os.path.join(tempdir, 'vmlinuz-1-%s' % flavor1)
        ifile = os.path.join(tempdir, 'initrd.img-1-%s' % flavor1)
        open(kfile, "w").close()
        open(ifile, "w").close()
        self.assertEqual(
            (kfile, ifile, None), config._get_kflavor_files(tempdir))

    def test_get_dt_kflavor_files_later_in_flavors(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        flavor1 = 'flavorXY'
        flavor2 = 'flavorAA'
        class config(boards.BoardConfig):
            kernel_flavors = [flavor1, flavor2]
            dtb_name = 'board_name.dtb'
        kfile = os.path.join(tempdir, 'vmlinuz-1-%s' % flavor1)
        ifile = os.path.join(tempdir, 'initrd.img-1-%s' % flavor1)
        dt = os.path.join(tempdir, 'dt-1-%s' % flavor1)
        os.mkdir(dt)
        dfile = os.path.join(dt, config.dtb_name)
        open(kfile, "w").close()
        open(ifile, "w").close()
        open(dfile, "w").close()
        self.assertEqual(
            (kfile, ifile, dfile), config._get_kflavor_files(tempdir))

    def test_get_kflavor_files_raises_when_no_match(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        flavor1 = 'flavorXY'
        flavor2 = 'flavorAA'
        class config(boards.BoardConfig):
            kernel_flavors = [flavor1, flavor2]
        self.assertRaises(ValueError, config._get_kflavor_files, tempdir)

    def test_get_file_matching_no_files_found(self):
        self.assertEqual(None, _get_file_matching('/foo/bar/baz/*non-existent'))

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

        create_partitions(boards.Mx5Config, self.media, HEADS, SECTORS, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             'sync'],
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

        create_partitions(
            board_configs['smdkv310'], self.media, HEADS, SECTORS, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             'sync'],
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

        create_partitions(
            board_configs['beagle'], self.media, HEADS, SECTORS, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             'sync'],
            popen_fixture.mock.commands_executed)
        self.assertEqual(
            [('63,106432,0x0C,*\n106496,,,-', HEADS, SECTORS, '',
              self.media.path)],
            sfdisk_fixture.mock.calls)

    def test_create_partitions_with_img_file(self):
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        tmpfile = self.createTempFileAsFixture()
        create_partitions(
            board_configs['beagle'], Media(tmpfile), HEADS, SECTORS, '')

        # Unlike the test for partitioning of a regular block device, in this
        # case parted was not called as there's no existing partition table
        # for us to overwrite on the image file.
        self.assertEqual(['sync'], popen_fixture.mock.commands_executed)

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


class TestPartitionSetup(TestCaseWithFixtures):

    def setUp(self):
        super(TestPartitionSetup, self).setUp()
        # Stub time.sleep() as create_partitions() use that.
        self.orig_sleep = time.sleep
        time.sleep = lambda s: None
        self.linux_image_size = 30 * 1024**2
        self.linux_offsets_and_sizes = [
            (16384 * SECTOR_SIZE, 15746 * SECTOR_SIZE),
            (32768 * SECTOR_SIZE, (self.linux_image_size - 
                                        32768 * SECTOR_SIZE))
            ]
        self.android_image_size = 256 * 1024**2
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
            ((98367  + ext_part_size)* SECTOR_SIZE, 
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
            '63,32768,0x0C,*\n32831,65536,L\n98367,65536,L\n294975,-,E\n' \
                '294975,131072,L\n426047,,,-', '%s' % self.android_image_size)

    def _create_snowball_android_tmpfile(self):
        # raw, boot, system, cache, (extended), userdata and sdcard partitions
        return self._create_qemu_img_with_partitions(
            '256,7936,0xDA\n8192,24639,0x0C,*\n32831,65536,L\n' \
            '98367,-,E\n98367,65536,L\n294975,131072,L\n' \
            '426047,,,-', '%s' % self.android_image_size)

    def test_convert_size_no_suffix(self):
        self.assertEqual(524288, convert_size_to_bytes('524288'))

    def test_convert_size_in_kbytes_to_bytes(self):
        self.assertEqual(512 * 1024, convert_size_to_bytes('512K'))

    def test_convert_size_in_mbytes_to_bytes(self):
        self.assertEqual(100 * 1024**2, convert_size_to_bytes('100M'))

    def test_convert_size_in_gbytes_to_bytes(self):
        self.assertEqual(12 * 1024**3, convert_size_to_bytes('12G'))

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
        for device_pair, expected_pair in map(None, device_info,
                                              self.android_snowball_offsets_and_sizes):
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
                media, board_configs['beagle']))

    def test_get_boot_and_root_partitions_for_media_mx5(self):
        self.useFixture(MockSomethingFixture(
            partitions, '_get_device_file_for_partition_number',
            lambda dev, partition: '%s%d' % (tmpfile, partition)))
        tmpfile = self.createTempFileAsFixture()
        media = Media(tmpfile)
        media.is_block_device = True
        self.assertEqual(
            ("%s%d" % (tmpfile, 2), "%s%d" % (tmpfile, 3)),
            get_boot_and_root_partitions_for_media(media, boards.Mx5Config))

    def _create_qemu_img_with_partitions(self, sfdisk_commands, tempfile_size):
        tmpfile = self.createTempFileAsFixture()
        proc = cmd_runner.run(
            ['dd', 'of=%s' % tmpfile, 'bs=1', 'seek=%s' % tempfile_size, 'count=0'],
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
        bootfs_dev, rootfs_dev = setup_partitions(
            board_configs['beagle'], Media(tmpfile), '2G', 'boot',
            'root', 'ext3', True, True, True)
        self.assertEqual(
             # This is the call that would create a 2 GiB image file.
            ['dd of=%s bs=1 seek=2147483648 count=0' % tmpfile,
             # This call would partition the image file.
             '%s sfdisk --force -D -uS -H %s -S %s -C 1024 %s' % (
                 sudo_args, HEADS, SECTORS, tmpfile),
             # Make sure changes are written to disk.
             'sync',
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
        bootfs_dev, rootfs_dev = setup_partitions(
            board_configs['beagle'], media, '2G', 'boot', 'root', 'ext3',
            True, True, True)
        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, tmpfile),
             '%s sfdisk --force -D -uS -H %s -S %s %s' % (
                 sudo_args, HEADS, SECTORS, tmpfile),
             'sync',
             # Since the partitions are mounted, setup_partitions will umount
             # them before running mkfs.
             '%s umount %s' % (sudo_args, bootfs_dev),
             '%s umount %s' % (sudo_args, rootfs_dev),
             '%s mkfs.vfat -F 32 %s -n boot' % (sudo_args, bootfs_dev),
             '%s mkfs.ext3 %s -L root' % (sudo_args, rootfs_dev)],
            popen_fixture.mock.commands_executed)


class TestPopulateBoot(TestCaseWithFixtures):

    expected_args = (
        'chroot_dir/boot', False, False, [], 'chroot_dir', 'rootfs_uuid',
        'boot_disk', 'boot_device_or_file')
    expected_args_live = (
        'chroot_dir/casper', True, False, [], 'chroot_dir', 'rootfs_uuid',
        'boot_disk', 'boot_device_or_file')
    expected_calls = [
        'mkdir -p boot_disk',
        '%s mount boot_partition boot_disk' % sudo_args,
        'sync',
        '%s umount boot_disk' % sudo_args]

    def save_args(self, *args):
        self.saved_args = args

    def prepare_config(self, config):
        class c(config):
            pass

        self.config = c
        self.config.boot_script = 'boot_script'
        self.config.hardwarepack_handler = \
            TestSetMetadata.MockHardwarepackHandler('ahwpack.tar.gz')
        self.config.hardwarepack_handler.get_format = lambda: '1.0'
        self.popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(
            self.config, 'make_boot_files', self.save_args))

    def call_populate_boot(self, config, is_live=False):
        config.populate_boot(
            'chroot_dir', 'rootfs_uuid', 'boot_partition', 'boot_disk',
            'boot_device_or_file', is_live, False, [])

    def test_populate_boot_live(self):
        self.prepare_config(boards.BoardConfig)
        self.call_populate_boot(self.config, is_live=True)
        self.assertEquals(
            self.expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args_live, self.saved_args)

    def test_populate_boot_regular(self):
        self.prepare_config(boards.BoardConfig)
        self.call_populate_boot(self.config)
        self.assertEquals(
            self.expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args, self.saved_args)

    def test_populate_boot_uboot_flavor(self):
        self.prepare_config(boards.BoardConfig)
        self.config.uboot_flavor = "uboot_flavor"
        self.call_populate_boot(self.config)
        self.assertEquals(
            self.expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args, self.saved_args)

    def test_populate_boot_uboot_in_boot_part(self):
        self.prepare_config(boards.BoardConfig)
        self.config.uboot_flavor = "uboot_flavor"
        self.config.uboot_in_boot_part = True
        self.call_populate_boot(self.config)
        expected_calls = self.expected_calls[:]
        expected_calls.insert(2,
            '%s cp -v chroot_dir/usr/lib/u-boot/uboot_flavor/u-boot.bin '
            'boot_disk' % sudo_args)
        self.assertEquals(
            expected_calls, self.popen_fixture.mock.commands_executed)
        self.assertEquals(self.expected_args, self.saved_args)

    def test_populate_boot_no_uboot_flavor(self):
        self.prepare_config(boards.BoardConfig)
        self.config.uboot_in_boot_part = True
        self.assertRaises(
            AssertionError, self.call_populate_boot, self.config)


class TestPopulateRootFS(TestCaseWithFixtures):

    lines_added_to_fstab = None
    create_flash_kernel_config_called = False

    def test_populate_rootfs(self):
        def fake_append_to_fstab(disk, additions):
            self.lines_added_to_fstab = additions

        def fake_create_flash_kernel_config(disk, partition_offset):
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

        populate_rootfs(
            contents_dir, root_disk, partition='/dev/rootfs',
            rootfs_type='ext3', rootfs_uuid='uuid', should_create_swap=True,
            swap_size=100, partition_offset=0)

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

        create_flash_kernel_config(tempdir, boot_partition_number=1)

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
        self.assertEqual('UBOOT_PART=/dev/mmcblk0p1', open(tmpfile).read())

    def test_move_contents(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        file1 = self.createTempFileAsFixture(dir=tempdir)

        move_contents(tempdir, '/tmp/')

        self.assertEqual(['%s mv %s /tmp/' % (sudo_args, file1)],
                         popen_fixture.mock.commands_executed)

    def test_has_space_left_for_swap(self):
        statvfs = os.statvfs('/')
        space_left = statvfs.f_bavail * statvfs.f_bsize
        swap_size_in_megs = space_left / (1024**2)
        self.assertTrue(
            has_space_left_for_swap('/', swap_size_in_megs))

    def test_has_no_space_left_for_swap(self):
        statvfs = os.statvfs('/')
        space_left = statvfs.f_bavail * statvfs.f_bsize
        swap_size_in_megs = (space_left / (1024**2)) + 1
        self.assertFalse(
            has_space_left_for_swap('/', swap_size_in_megs))

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
            ['%s mv -f /dir/file /tmp/dir/file' % sudo_args,
             '%s cp /path/to/file /dir' % sudo_args],
            fixture.mock.commands_executed)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            ['%s mv -f /tmp/dir/file /dir' % sudo_args],
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
        force_yes = False
        install_hwpack(chroot_dir, 'hwpack.tgz', force_yes)
        self.assertEquals(
            ['%s cp hwpack.tgz %s' % (sudo_args, chroot_dir),
             '%s %s %s linaro-hwpack-install /hwpack.tgz'
                % (sudo_args, chroot_args, chroot_dir)],
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

        install_hwpacks(
            chroot_dir, tmp_dir, prefer_dir, force_yes, [], 'hwpack1.tgz',
            'hwpack2.tgz')
        linaro_hwpack_install = find_command(
            'linaro-hwpack-install', prefer_dir=prefer_dir)
        expected = [
            'prepare_chroot %(chroot_dir)s %(tmp_dir)s',
            'cp %(linaro_hwpack_install)s %(chroot_dir)s/usr/bin',
            'mount proc %(chroot_dir)s/proc -t proc',
            'cp hwpack1.tgz %(chroot_dir)s',
            ('%(chroot_args)s %(chroot_dir)s linaro-hwpack-install '
             '--force-yes /hwpack1.tgz'),
            'cp hwpack2.tgz %(chroot_dir)s',
            ('%(chroot_args)s %(chroot_dir)s linaro-hwpack-install '
             '--force-yes /hwpack2.tgz'),
            'rm -f %(chroot_dir)s/hwpack2.tgz',
            'rm -f %(chroot_dir)s/hwpack1.tgz',
            'umount -v %(chroot_dir)s/proc',
            'rm -f %(chroot_dir)s/usr/bin/linaro-hwpack-install']
        keywords = dict(
            chroot_dir=chroot_dir, tmp_dir=tmp_dir, chroot_args=chroot_args,
            linaro_hwpack_install=linaro_hwpack_install)
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
            'mv -f chroot/etc/resolv.conf /tmp/dir/resolv.conf',
            'cp /etc/resolv.conf chroot/etc',
            'mv -f chroot/etc/hosts /tmp/dir/hosts',
            'cp /etc/hosts chroot/etc',
            'cp /usr/bin/qemu-arm-static chroot/usr/bin',
            'rm -f chroot/usr/bin/qemu-arm-static',
            'mv -f /tmp/dir/hosts chroot/etc',
            'mv -f /tmp/dir/resolv.conf chroot/etc']
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

        def mock_install_hwpack(p1, p2, p3):
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
        try:
            install_hwpacks(
                'chroot', '/tmp/dir', preferred_tools_dir(), force_yes, [],
                'hwp.tgz', 'hwp2.tgz')
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
