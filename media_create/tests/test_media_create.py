from contextlib import contextmanager
import os
import random
import string
import subprocess
import sys

from testtools import TestCase

from hwpack.testing import TestCaseWithFixtures

from media_create import cmd_runner
from media_create import ensure_command
from media_create import populate_boot
from media_create import setup_partitions
from media_create.boot_cmd import create_boot_cmd
from media_create.create_partitions import (
    create_partitions,
    run_sfdisk_commands,
    )
from media_create.setup_partitions import (
    calculate_partition_size_and_offset,
    convert_size_to_bytes,
    get_boot_and_root_partitions_for_media,
    Media,
    )
from media_create.populate_boot import (
    make_boot_script,
    make_uImage,
    make_uInitrd,
    _get_file_matching,
    _run_mkimage,
    )
from media_create.remove_binary_dir import remove_binary_dir
from media_create.unpack_binary_tarball import unpack_binary_tarball

from media_create.tests.fixtures import (
    ChangeCurrentWorkingDirFixture,
    CreateTempDirFixture,
    CreateTarballFixture,
    MockCmdRunnerPopenFixture,
    MockSomethingFixture,
    MockRunSfdiskCommandsFixture,
    )


class TestEnsureCommand(TestCase):

    apt_get_called = False

    def test_command_already_present(self):
        with self.mock_apt_get_install():
            ensure_command.ensure_command('apt-get', 'apt')
        self.assertFalse(self.apt_get_called)

    def test_command_not_present(self):
        with self.mock_apt_get_install():
            ensure_command.ensure_command('apt-get-two-o', 'apt-2')
        self.assertTrue(self.apt_get_called)

    @contextmanager
    def mock_apt_get_install(self):
        def mock_apt_get_install(cmd, pkg):
            self.apt_get_called = True
        orig_func = ensure_command.apt_get_install
        ensure_command.apt_get_install = mock_apt_get_install
        yield
        ensure_command.apt_get_install = orig_func


class TestCreateBootCMD(TestCase):

    expected_boot_cmd = (
        "setenv bootcmd 'fatload mmc mmc_option kernel_addr uImage; "
        "fatload mmc mmc_option initrd_addr uInitrd; bootm kernel_addr "
        "initrd_addr'\nsetenv bootargs 'serial_opts splash_opts  "
        "root=UUID=root_uuid boot_args'\nboot")

    def test_create_boot_cmd(self):
        cmd = create_boot_cmd(
            is_live=False, is_lowmem=False, mmc_option='mmc_option',
            root_uuid='root_uuid', kernel_addr="kernel_addr",
            initrd_addr="initrd_addr", serial_opts="serial_opts",
            boot_args_options="boot_args", splash_opts="splash_opts")
        self.assertEqual(self.expected_boot_cmd, cmd)

    def test_create_boot_cmd_as_script(self):
        args = "%s -m media_create.boot_cmd " % sys.executable
        args += ("0 0 mmc_option root_uuid kernel_addr initrd_addr "
                 "serial_opts boot_args splash_opts")
        process = subprocess.Popen(
            args, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        self.assertEqual(self.expected_boot_cmd, stdout)


class TestRemoveBinaryDir(TestCaseWithFixtures):

    def setUp(self):
        super(TestRemoveBinaryDir, self).setUp()
        self.temp_dir_fixture = CreateTempDirFixture()
        self.useFixture(self.temp_dir_fixture)

    def test_remove_binary_dir(self):
        rc = remove_binary_dir(
            binary_dir=self.temp_dir_fixture.get_temp_dir(),
            as_root=False)
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(
            self.temp_dir_fixture.get_temp_dir()))


class TestUnpackBinaryTarball(TestCaseWithFixtures):

    def setUp(self):
        super(TestUnpackBinaryTarball, self).setUp()

        self.tar_dir_fixture = CreateTempDirFixture()
        self.useFixture(self.tar_dir_fixture)

        self.tarball_fixture = CreateTarballFixture(
            self.tar_dir_fixture.get_temp_dir())
        self.useFixture(self.tarball_fixture)

        self.unpack_dir_fixture = CreateTempDirFixture()
        self.useFixture(self.unpack_dir_fixture)

        self.useFixture(ChangeCurrentWorkingDirFixture(
            self.unpack_dir_fixture.get_temp_dir()))

    def test_unpack_binary_tarball(self):
        rc = unpack_binary_tarball(self.tarball_fixture.get_tarball(),
            as_root=False)
        self.assertEqual(rc, 0)


class TestCmdRunner(TestCaseWithFixtures):

    def test_run(self):
        fixture = MockCmdRunnerPopenFixture()
        self.useFixture(fixture)
        proc = cmd_runner.run(['foo', 'bar', 'baz'])
        self.assertEqual(0, proc.returncode)
        self.assertEqual([['foo', 'bar', 'baz']], fixture.mock.calls)

    def test_run_as_root(self):
        fixture = MockCmdRunnerPopenFixture()
        self.useFixture(fixture)
        cmd_runner.run(['foo', 'bar'], as_root=True)
        self.assertEqual([['sudo', 'foo', 'bar']], fixture.mock.calls)

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


class TestPopulateBoot(TestCaseWithFixtures):

    def _mock_get_file_matching(self):
        self.useFixture(MockSomethingFixture(
            populate_boot, '_get_file_matching',
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
            'sudo', 'mkimage', '-A', 'arm', '-O', 'linux', '-T', 'kernel',
            '-C', 'none', '-a', 'load_addr', '-e', 'load_addr', '-n', 'Linux',
            '-d', 'parts_dir/vmlinuz-*-sub_arch', 'boot_disk/uImage']
        self.assertEqual([expected], fixture.mock.calls)

    def test_make_uInitrd(self):
        self._mock_get_file_matching()
        fixture = self._mock_Popen()
        make_uInitrd('parts_dir', 'sub_arch', 'boot_disk')
        expected = [
            'sudo', 'mkimage', '-A', 'arm', '-O', 'linux', '-T', 'ramdisk',
            '-C', 'none', '-a', '0', '-e', '0', '-n', 'initramfs',
            '-d', 'parts_dir/initrd.img-*-sub_arch', 'boot_disk/uInitrd']
        self.assertEqual([expected], fixture.mock.calls)

    def test_make_boot_script(self):
        self._mock_get_file_matching()
        fixture = self._mock_Popen()
        make_boot_script('boot_script', 'tmp_dir')
        expected = [
            'sudo', 'mkimage', '-A', 'arm', '-O', 'linux', '-T', 'script',
            '-C', 'none', '-a', '0', '-e', '0', '-n', 'boot script',
            '-d', 'tmp_dir/boot.cmd', 'boot_script']
        self.assertEqual([expected], fixture.mock.calls)

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
        # Send stdout to file as mkimage will print to stdout and we don't
        # want that.
        retval = _run_mkimage(
            'script', '0', '0', 'boot script', filename, img,
            stdout=open(self.createTempFileAsFixture(), 'w'),
            as_root=False)

        self.assertEqual(0, retval)


class TestCreatePartitions(TestCaseWithFixtures):

    media = Media('/dev/xdz')

    def test_create_partitions_for_mx51evk(self):
        # For this board we create a one cylinder partition at the beginning.
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        create_partitions('mx51evk', self.media, 32, 255, 63, '')

        self.assertEqual(
            [['sudo', 'parted', '-s', self.media.path, 'mklabel', 'msdos'],
             ['sync']],
            popen_fixture.mock.calls)
        self.assertEqual(
            [(',1,0xDA', 255, 63, '', self.media.path),
             (',9,0x0C,*\n,,,-', 255, 63, '', self.media.path)],
            sfdisk_fixture.mock.calls)

    def test_create_partitions_for_beagle(self):
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        create_partitions('beagle', self.media, 32, 255, 63, '')

        self.assertEqual(
            [['sudo', 'parted', '-s', self.media.path, 'mklabel', 'msdos'],
             ['sync']],
            popen_fixture.mock.calls)
        self.assertEqual(
            [(',9,0x0C,*\n,,,-', 255, 63, '', self.media.path)],
            sfdisk_fixture.mock.calls)

    def test_create_partitions_with_img_file(self):
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        sfdisk_fixture = self.useFixture(MockRunSfdiskCommandsFixture())

        tempfile = self.createTempFileAsFixture()
        create_partitions('beagle', Media(tempfile), 32, 255, 63, '')

        # Unlike the test for partitioning of a regular block device, in this
        # case parted was not called as there's no existing partition table
        # for us to overwrite on the image file.
        self.assertEqual([['sync']], popen_fixture.mock.calls)

        self.assertEqual(
            [(',9,0x0C,*\n,,,-', 255, 63, '', tempfile)],
            sfdisk_fixture.mock.calls)

    def test_run_sfdisk_commands(self):
        tempfile = self.createTempFileAsFixture()
        proc = cmd_runner.run(
            ['qemu-img', 'create', '-f', 'raw', tempfile, '10M'],
            stdout=subprocess.PIPE)
        proc.communicate()
        stdout, stderr = run_sfdisk_commands(
            ',1,0xDA', 5, 63, '', tempfile, as_root=False,
            stderr=subprocess.PIPE)
        self.assertIn('Successfully wrote the new partition table', stdout)

    def test_run_sfdisk_commands_raises_on_non_zero_returncode(self):
        tempfile = self.createTempFileAsFixture()
        self.assertRaises(
            cmd_runner.SubcommandNonZeroReturnValue,
            run_sfdisk_commands,
            ',1,0xDA', 5, 63, '', tempfile, as_root=False,
            stderr=subprocess.PIPE)


class TestPartitionSetup(TestCaseWithFixtures):

    def test_convert_size_in_kbytes_to_bytes(self):
        self.assertEqual(10 * 1024, convert_size_to_bytes('10K'))

    def test_convert_size_in_mbytes_to_bytes(self):
        self.assertEqual(11 * 1024 * 1024, convert_size_to_bytes('11M'))

    def test_convert_size_in_gbytes_to_bytes(self):
        self.assertEqual(
            12 * 1024 * 1024 * 1024, convert_size_to_bytes('12G'))

    def test_calculate_partition_size_and_offset(self):
        tempfile = self._create_qemu_img_with_partitions(',1,0x0C,*\n,,,-')
        vfat_size, vfat_offset, linux_size, linux_offset = (
            calculate_partition_size_and_offset(tempfile))
        self.assertEqual(
            [129024L, 32256L, 10321920L, 161280L],
            [vfat_size, vfat_offset, linux_size, linux_offset])

    def test_get_boot_and_root_partitions_for_media_with_2_partitions(self):
        self.useFixture(MockSomethingFixture(
            setup_partitions, '_get_partition_count', lambda media: 2))
        tempfile = self._create_qemu_img_with_partitions(',1,0x0C,*\n,,,-')
        media = Media(tempfile)
        # Pretend the image file is a block device, or else
        # get_boot_and_root_partitions_for_media will choke.
        media.is_block_device = True
        self.assertEqual(
            ("%s%d" % (tempfile, 1), "%s%d" % (tempfile, 2)),
            get_boot_and_root_partitions_for_media(media))

    def test_get_boot_and_root_partitions_for_media_with_3_partitions(self):
        self.useFixture(MockSomethingFixture(
            setup_partitions, '_get_partition_count', lambda media: 3))
        tempfile = self._create_qemu_img_with_partitions(
            ',1,0xDA\n,1,0x0C,*\n,,,-')
        media = Media(tempfile)
        # Pretend the image file is a block device, or else
        # get_boot_and_root_partitions_for_media will choke.
        media.is_block_device = True
        self.assertEqual(
            ("%s%d" % (tempfile, 2), "%s%d" % (tempfile, 3)),
            get_boot_and_root_partitions_for_media(media))

    def _create_qemu_img_with_partitions(self, sfdisk_commands):
        tempfile = self.createTempFileAsFixture()
        proc = cmd_runner.run(
            ['qemu-img', 'create', '-f', 'raw', tempfile, '10M'],
            stdout=subprocess.PIPE)
        proc.communicate()
        stdout, stderr = run_sfdisk_commands(
            sfdisk_commands, 5, 63, '', tempfile, as_root=False,
            # Throw away stderr as sfdisk complains a lot when operating on a
            # qemu image.
            stderr=subprocess.PIPE)
        self.assertIn('Successfully wrote the new partition table', stdout)
        return tempfile
