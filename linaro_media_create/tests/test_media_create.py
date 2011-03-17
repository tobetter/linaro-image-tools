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
import stat
import string
import subprocess
import sys
import tempfile
import time
import types

from testtools import TestCase

from hwpack.testing import TestCaseWithFixtures

from linaro_media_create import (
    check_device,
    cmd_runner,
    boards,
    partitions,
    rootfs,
    utils,
    )
import linaro_media_create
from linaro_media_create.boards import (
    LOADER_MIN_SIZE_S,
    SECTOR_SIZE,
    align_up,
    align_partition,
    board_configs,
    make_flashable_env,
    install_mx5_boot_loader,
    install_omap_boot_loader,
    make_boot_script,
    make_uImage,
    make_uInitrd,
    _get_file_matching,
    _get_mlo_file,
    _run_mkimage,
    )
from linaro_media_create.hwpack import (
    copy_file,
    install_hwpack,
    install_hwpacks,
    mount_chroot_proc,
    run_local_atexit_funcs,
    temporarily_overwrite_file_on_dir,
    )
from linaro_media_create.partitions import (
    calculate_partition_size_and_offset,
    convert_size_to_bytes,
    create_partitions,
    ensure_partition_is_not_mounted,
    get_boot_and_root_loopback_devices,
    get_boot_and_root_partitions_for_media,
    Media,
    run_sfdisk_commands,
    setup_partitions,
    get_uuid,
    _parse_blkid_output,
    )
from linaro_media_create.populate_boot import populate_boot
from linaro_media_create.rootfs import (
    create_flash_kernel_config,
    has_space_left_for_swap,
    move_contents,
    populate_rootfs,
    write_data_to_protected_file,
    )
from linaro_media_create.unpack_binary_tarball import unpack_binary_tarball
from linaro_media_create.utils import (
    ensure_command,
    find_command,
    install_package_providing,
    UnableToFindPackageProvidingCommand,
    )

from linaro_media_create.tests.fixtures import (
    CreateTempDirFixture,
    CreateTarballFixture,
    MockCmdRunnerPopenFixture,
    MockSomethingFixture,
    MockRunSfdiskCommandsFixture,
    )


sudo_args = 'sudo -E'


def preferred_tools_dir():
    prefer_dir = None
    # running from bzr checkout?
    if not os.path.isabs(__file__):
        prefer_dir = os.getcwd()
    return prefer_dir


class TestEnsureCommand(TestCaseWithFixtures):

    install_pkg_providing_called = False

    def setUp(self):
        super(TestEnsureCommand, self).setUp()
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))

    def test_command_already_present(self):
        self.mock_install_package_providing()
        ensure_command('apt-get')
        self.assertFalse(self.install_pkg_providing_called)

    def test_command_not_present(self):
        self.mock_install_package_providing()
        ensure_command('apt-get-two-o')
        self.assertTrue(self.install_pkg_providing_called)

    def mock_install_package_providing(self):
        def mock_func(command):
            self.install_pkg_providing_called = True
        self.useFixture(MockSomethingFixture(
            utils, 'install_package_providing', mock_func))


class TestFindCommand(TestCaseWithFixtures):

    def test_preferred_dir(self):
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        lmc = 'linaro-media-create'
        path = os.path.join(tempdir, lmc)
        open(path, 'w').close()
        os.chmod(path, stat.S_IXUSR)
        self.assertEquals(path, find_command(lmc, tempdir))

    def test_existing_command(self):
        lmc = 'linaro-media-create'
        prefer_dir = preferred_tools_dir()
        if prefer_dir is None:
            expected, _ = cmd_runner.run(
                ['which', lmc, ],
                stdout=subprocess.PIPE).communicate()
            expected = expected.strip()
        else:
            expected = os.path.join(prefer_dir, lmc)
        self.assertEquals(expected, find_command(lmc))

    def test_nonexisting_command(self):
        self.assertEquals(find_command('linaro-moo'), None)


class TestInstallPackageProviding(TestCaseWithFixtures):

    def test_found_package(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        install_package_providing('mkfs.vfat')
        self.assertEqual(
            ['%s apt-get install dosfstools' % sudo_args],
            fixture.mock.commands_executed)

    def test_not_found_package(self):
        self.assertRaises(
            UnableToFindPackageProvidingCommand,
            install_package_providing, 'mkfs.lean')


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


class TestBootSteps(TestCaseWithFixtures):

    def setUp(self):
        super(TestBootSteps, self).setUp()
        self.funcs_calls = []
        self.mock_all_boards_funcs()

    def mock_all_boards_funcs(self):
        """Mock functions of linaro_media_create.boards with a call tracer."""

        def mock_func_creator(name):
            return lambda *args, **kwargs: self.funcs_calls.append(name)

        for name in dir(boards):
            attr = getattr(boards, name)
            if type(attr) == types.FunctionType:
                self.useFixture(MockSomethingFixture(
                    linaro_media_create.boards, name,
                    mock_func_creator(name)))

    def mock_set_appropriate_serial_tty(self, config):

        def set_appropriate_serial_tty_mock(cls, chroot_dir):
            cls.serial_tty = cls._serial_tty

        self.useFixture(MockSomethingFixture(
            config, 'set_appropriate_serial_tty',
            classmethod(set_appropriate_serial_tty_mock)))

    def make_boot_files(self, config):
        config.make_boot_files('', False, False, [], '', '', '', '', '')

    def test_vexpress_steps(self):
        self.make_boot_files(boards.VexpressConfig)
        expected = ['make_uImage', 'make_uInitrd']
        self.assertEqual(expected, self.funcs_calls)

    def test_mx5_steps(self):
        class SomeMx5Config(boards.Mx5Config):
            uboot_flavor = 'uboot_flavor'
        self.make_boot_files(SomeMx5Config)
        expected = [
            'install_mx5_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_smdkv310_steps(self):
        self.make_boot_files(boards.SMDKV310Config)
        expected = [
            'install_smdkv310_boot_loader', 'make_flashable_env',
            'install_smdkv310_boot_env', 'make_uImage',
            'install_smdkv310_uImage', 'make_uInitrd',
            'install_smdkv310_initrd']
        self.assertEqual(expected, self.funcs_calls)

    def test_ux500_steps(self):
        self.make_boot_files(boards.Ux500Config)
        expected = ['make_uImage', 'make_uInitrd', 'make_boot_script']
        self.assertEqual(expected, self.funcs_calls)

    def test_panda_steps(self):
        self.mock_set_appropriate_serial_tty(boards.PandaConfig)
        self.make_boot_files(boards.PandaConfig)
        expected = [
            'install_omap_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_boot_script', 'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_beagle_steps(self):
        self.mock_set_appropriate_serial_tty(boards.BeagleConfig)
        self.make_boot_files(boards.BeagleConfig)
        expected = [
            'install_omap_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_boot_script', 'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_igep_steps(self):
        self.mock_set_appropriate_serial_tty(boards.IgepConfig)
        self.make_boot_files(boards.IgepConfig)
        expected = [
            'make_uImage', 'make_uInitrd', 'make_boot_script',
            'make_boot_ini']
        self.assertEqual(expected, self.funcs_calls)

    def test_overo_steps(self):
        self.mock_set_appropriate_serial_tty(boards.OveroConfig)
        self.make_boot_files(boards.OveroConfig)
        expected = [
            'install_omap_boot_loader', 'make_uImage', 'make_uInitrd',
            'make_boot_script', 'make_boot_ini']
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
            None, None, None, None, None, None, None, None, None)
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

    def test_smdkv310(self):
        self.assertEquals(
            '1,221183,0xDA\n221184,106496,0x0C,*\n327680,,,-',
            board_configs['smdkv310'].get_sfdisk_cmd())


class TestGetBootCmd(TestCase):

    def test_vexpress(self):
        boot_commands = board_configs['vexpress']._get_boot_env(
            is_live=False, is_lowmem=False, consoles=['ttyXXX'],
            rootfs_uuid="deadbeef")
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA0,38400n8 '
                        'console=ttyXXX  root=UUID=deadbeef rootwait ro',
            'bootcmd': 'fatload mmc 0:1 0x60008000 uImage; '
                       'fatload mmc 0:1 0x81000000 uInitrd; '
                       'bootm 0x60008000 0x81000000'}
        self.assertEqual(expected, boot_commands)

    def test_mx5(self):
        boot_commands = boards.Mx5Config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef")
        expected = {
            'bootargs': 'console=tty0 console=ttymxc0,115200n8  '
                        'root=UUID=deadbeef rootwait ro',
            'bootcmd': 'fatload mmc 0:2 0x90000000 uImage; '
                       'fatload mmc 0:2 0x90800000 uInitrd; '
                       'bootm 0x90000000 0x90800000'}
        self.assertEqual(expected, boot_commands)

    def test_smdkv310(self):
        boot_commands = board_configs['smdkv310']._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef")
        expected = {
            'bootargs': 'console=ttySAC1,115200n8  root=UUID=deadbeef '
                        'rootwait ro',
             'bootcmd': 'movi read kernel 0x40007000; '
                        'movi read rootfs 0x41000000 0x1000000; '
                        'bootm 0x40007000 0x41000000',
             'ethact': 'smc911x-0',
             'ethaddr': '00:40:5c:26:0a:5b'}
        self.assertEqual(expected, boot_commands)

    def test_ux500(self):
        boot_commands = board_configs['ux500']._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef")
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
            rootfs_uuid="deadbeef")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=32M omapfb.vram=0:8M mem=463M '
                        'ip=none',
            'bootcmd': 'fatload mmc 0:1 0x80200000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'bootm 0x80200000 0x81600000'}
        self.assertEqual(expected, boot_commands)

    def test_beagle(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = board_configs['beagle']
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=12M '
                        'omapfb.mode=dvi:1280x720MR-16@60',
            'bootcmd': 'fatload mmc 0:1 0x80000000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'bootm 0x80000000 0x81600000'}
        self.assertEqual(expected, boot_commands)

    def test_igep(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = board_configs['igep']
        config.serial_tty = config._serial_tty
        boot_cmd = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=12M '
                        'omapfb.mode=dvi:1280x720MR-16@60',
            'bootcmd': 'fatload mmc 0:1 0x80000000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'bootm 0x80000000 0x81600000'}
        self.assertEqual(expected, boot_cmd)

    def test_overo(self):
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = board_configs['overo']
        config.serial_tty = config._serial_tty
        boot_commands = config._get_boot_env(
            is_live=False, is_lowmem=False, consoles=[],
            rootfs_uuid="deadbeef")
        expected = {
            'bootargs': 'console=tty0 console=ttyO2,115200n8  '
                        'root=UUID=deadbeef rootwait ro earlyprintk '
                        'mpurate=500 vram=12M '
                        'omapfb.mode=dvi:1024x768MR-16@60 '
                        'omapdss.def_disp=dvi',
            'bootcmd': 'fatload mmc 0:1 0x80000000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'bootm 0x80000000 0x81600000'}
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


class TestCmdRunner(TestCaseWithFixtures):

    def test_run(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        proc = cmd_runner.run(['foo', 'bar', 'baz'])
        # Call wait or else MockCmdRunnerPopenFixture() raises an
        # AssertionError().
        proc.wait()
        self.assertEqual(0, proc.returncode)
        self.assertEqual([['foo', 'bar', 'baz']], fixture.mock.calls)

    def test_run_as_root_with_sudo(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(os, 'getuid', lambda: 1000))
        cmd_runner.run(['foo', 'bar'], as_root=True).wait()
        self.assertEqual(
            ['%s foo bar' % sudo_args], fixture.mock.commands_executed)

    def test_run_as_root_as_root(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(os, 'getuid', lambda: 0))
        cmd_runner.run(['foo', 'bar'], as_root=True).wait()
        self.assertEqual([['foo', 'bar']], fixture.mock.calls)

    def test_run_succeeds_on_zero_return_code(self):
        proc = cmd_runner.run(['true'])
        # Need to wait() here as we're using the real Popen.
        proc.wait()
        self.assertEqual(0, proc.returncode)

    def test_run_raises_exception_on_non_zero_return_code(self):
        def run_and_wait():
            proc = cmd_runner.run(['false'])
            proc.wait()
        self.assertRaises(
            cmd_runner.SubcommandNonZeroReturnValue, run_and_wait)

    def test_run_must_be_given_list_as_args(self):
        self.assertRaises(AssertionError, cmd_runner.run, 'true')

    def test_Popen(self):
        proc = cmd_runner.Popen('true')
        returncode = proc.wait()
        self.assertEqual(0, returncode)


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
        make_uImage('load_addr', 'parts_dir', 'sub_arch', 'boot_disk')
        expected = [
            '%s mkimage -A arm -O linux -T kernel -C none -a load_addr '
            '-e load_addr -n Linux -d parts_dir/vmlinuz-*-sub_arch '
            'boot_disk/uImage' % sudo_args]
        self.assertEqual(expected, fixture.mock.commands_executed)

    def test_make_uInitrd(self):
        self._mock_get_file_matching()
        fixture = self._mock_Popen()
        make_uInitrd('parts_dir', 'sub_arch', 'boot_disk')
        expected = [
            '%s mkimage -A arm -O linux -T ramdisk -C none -a 0 -e 0 '
            '-n initramfs -d parts_dir/initrd.img-*-sub_arch '
            'boot_disk/uInitrd' % sudo_args]
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
        self.assertRaises(
            ValueError, _get_file_matching, '%s/%s*' % (directory, prefix))

    def test_get_file_matching_no_files_found(self):
        self.assertRaises(
            ValueError, _get_file_matching, '/foo/bar/baz/*non-existent')

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

        create_partitions(boards.Mx5Config, self.media, 128, 32, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             'sync'],
            popen_fixture.mock.commands_executed)
        # Notice that we create all partitions in a single sfdisk run because
        # every time we run sfdisk it actually repartitions the device,
        # erasing any partitions created previously.
        self.assertEqual(
            [('1,8191,0xDA\n8192,106496,0x0C,*\n114688,,,-', 128, 32, '',
              self.media.path)],
            sfdisk_fixture.mock.calls)

    def test_create_partitions_for_smdkv310(self):
        # For this board we create a one cylinder partition at the beginning.
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        create_partitions(
            board_configs['smdkv310'], self.media, 128, 32, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             'sync'],
            popen_fixture.mock.commands_executed)
        # Notice that we create all partitions in a single sfdisk run because
        # every time we run sfdisk it actually repartitions the device,
        # erasing any partitions created previously.
        self.assertEqual(
            [('1,221183,0xDA\n221184,106496,0x0C,*\n327680,,,-', 128, 32, '',
              self.media.path)], sfdisk_fixture.mock.calls)

    def test_create_partitions_for_beagle(self):
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        create_partitions(
            board_configs['beagle'], self.media, 128, 32, '')

        self.assertEqual(
            ['%s parted -s %s mklabel msdos' % (sudo_args, self.media.path),
             'sync'],
            popen_fixture.mock.commands_executed)
        self.assertEqual(
            [('63,106432,0x0C,*\n106496,,,-', 128, 32, '', self.media.path)],
            sfdisk_fixture.mock.calls)

    def test_create_partitions_with_img_file(self):
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        tmpfile = self.createTempFileAsFixture()
        create_partitions(
            board_configs['beagle'], Media(tmpfile), 128, 32, '')

        # Unlike the test for partitioning of a regular block device, in this
        # case parted was not called as there's no existing partition table
        # for us to overwrite on the image file.
        self.assertEqual(['sync'], popen_fixture.mock.commands_executed)

        self.assertEqual(
            [('63,106432,0x0C,*\n106496,,,-', 128, 32, '', tmpfile)],
            sfdisk_fixture.mock.calls)

    def test_run_sfdisk_commands(self):
        tmpfile = self.createTempFileAsFixture()
        proc = cmd_runner.run(
            ['qemu-img', 'create', '-f', 'raw', tmpfile, '10M'],
            stdout=subprocess.PIPE)
        proc.communicate()
        stdout, stderr = run_sfdisk_commands(
            '2,16063,0xDA', 128, 32, '', tmpfile, as_root=False,
            stderr=subprocess.PIPE)
        self.assertIn('Successfully wrote the new partition table', stdout)

    def test_run_sfdisk_commands_raises_on_non_zero_returncode(self):
        tmpfile = self.createTempFileAsFixture()
        self.assertRaises(
            cmd_runner.SubcommandNonZeroReturnValue,
            run_sfdisk_commands,
            ',1,0xDA', 128, 32, '', tmpfile, as_root=False,
            stderr=subprocess.PIPE)


class TestPartitionSetup(TestCaseWithFixtures):

    def setUp(self):
        super(TestPartitionSetup, self).setUp()
        # Stub time.sleep() as create_partitions() use that.
        self.orig_sleep = time.sleep
        time.sleep = lambda s: None

    def tearDown(self):
        super(TestPartitionSetup, self).tearDown()
        time.sleep = self.orig_sleep

    def _create_tmpfile(self):
        # boot part at +8 MiB, root part at +16 MiB
        return self._create_qemu_img_with_partitions(
            '16384,15746,0x0C,*\n32768,,,-')

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
            [8061952L, 8388608L, 14680064L, 16777216L],
            [vfat_size, vfat_offset, linux_size, linux_offset])

    def test_partition_numbering(self):
        # another Linux partition at +24 MiB after the boot/root parts
        tmpfile = self._create_qemu_img_with_partitions(
            '16384,15746,0x0C,*\n32768,15427,,-\n49152,,,-')
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

    def _create_qemu_img_with_partitions(self, sfdisk_commands):
        tmpfile = self.createTempFileAsFixture()
        proc = cmd_runner.run(
            ['qemu-img', 'create', '-f', 'raw', tmpfile, '30M'],
            stdout=subprocess.PIPE)
        proc.communicate()
        stdout, stderr = run_sfdisk_commands(
            sfdisk_commands, 128, 32, '', tmpfile, as_root=False,
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
            ['%s losetup -f --show %s --offset 8388608 --sizelimit 8061952'
                % (sudo_args, tmpfile),
             '%s losetup -f --show %s --offset 16777216 --sizelimit 14680064'
                % (sudo_args, tmpfile)],
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

    def test_setup_partitions_for_image_file(self):
        # In practice we could pass an empty image file to setup_partitions,
        # but here we mock Popen() and thanks to that the image is not setup
        # (via qemu-img) inside setup_partitions.  That's why we pass an
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
            ['qemu-img create -f raw %s 2147483648' % tmpfile,
             # This call would partition the image file.
             '%s sfdisk --force -D -uS -H 128 -S 32 -C 1024 %s' % (
                 sudo_args, tmpfile),
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
             '%s sfdisk --force -D -uS -H 128 -S 32 %s' % (
                 sudo_args, tmpfile),
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
        'boot_disk', 'boot_disk/boot_script', 'boot_device_or_file')
    expected_args_live = (
        'chroot_dir/casper', True, False, [], 'chroot_dir', 'rootfs_uuid',
        'boot_disk', 'boot_disk/boot_script', 'boot_device_or_file')
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
        self.popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(
            self.config, 'make_boot_files', self.save_args))

    def call_populate_boot(self, config, is_live=False):
        populate_boot(
            config, 'chroot_dir', 'rootfs_uuid', 'boot_partition',
            'boot_disk', 'boot_device_or_file', is_live, False, [])

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
            ['UUID=uuid / ext3  errors=remount-ro 0 1 ',
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
        force_yes = False
        install_hwpack('chroot', 'hwpack.tgz', force_yes)
        self.assertEquals(
            ['%s cp hwpack.tgz chroot' % sudo_args,
             '%s chroot chroot linaro-hwpack-install /hwpack.tgz'
                % sudo_args],
            fixture.mock.commands_executed)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            ['%s rm -f chroot/hwpack.tgz' % sudo_args],
            fixture.mock.commands_executed)

    def test_install_hwpacks(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        force_yes = True

        prefer_dir = preferred_tools_dir()

        install_hwpacks(
            'chroot', '/tmp/dir', prefer_dir, force_yes, 'hwpack1.tgz',
            'hwpack2.tgz')
        linaro_hwpack_install = find_command(
            'linaro-hwpack-install', prefer_dir=prefer_dir)
        expected = [
            'mv -f chroot/etc/resolv.conf /tmp/dir/resolv.conf',
            'cp /etc/resolv.conf chroot/etc',
            'mv -f chroot/etc/hosts /tmp/dir/hosts',
            'cp /etc/hosts chroot/etc',
            'cp /usr/bin/qemu-arm-static chroot/usr/bin',
            'cp %s chroot/usr/bin' % linaro_hwpack_install,
            'mount proc chroot/proc -t proc',
            'cp hwpack1.tgz chroot',
            'chroot chroot linaro-hwpack-install --force-yes /hwpack1.tgz',
            'cp hwpack2.tgz chroot',
            'chroot chroot linaro-hwpack-install --force-yes /hwpack2.tgz',
            'rm -f chroot/hwpack2.tgz',
            'rm -f chroot/hwpack1.tgz',
            'umount -v chroot/proc',
            'rm -f chroot/usr/bin/linaro-hwpack-install',
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
        linaro_media_create.hwpack.local_atexit = [
            behaving_func, raising_func]
        # run_local_atexit_funcs() also propagates the last exception raised
        # by one of the functions.
        self.assertRaises(
            TestException, linaro_media_create.hwpack.run_local_atexit_funcs)
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
            linaro_media_create.hwpack, 'install_hwpack',
            mock_install_hwpack))
        self.useFixture(MockSomethingFixture(
            linaro_media_create.hwpack, 'run_local_atexit_funcs',
            mock_run_local_atexit_functions))

        force_yes = True
        exception_caught = False
        try:
            install_hwpacks(
                'chroot', '/tmp/dir', preferred_tools_dir(), force_yes,
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
            linaro_media_create.hwpack.local_atexit = []
        self.addCleanup(clear_atexits)
