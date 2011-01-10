from contextlib import contextmanager
import atexit
import glob
import os
import random
import string
import subprocess
import sys
import time

from testtools import TestCase

from hwpack.testing import TestCaseWithFixtures

from media_create import check_device
from media_create import cmd_runner
from media_create import ensure_command
from media_create import populate_boot
from media_create import partitions
from media_create import rootfs
from media_create.hwpack import (
    copy_file,
    install_hwpack,
    install_hwpacks,
    mount_chroot_proc,
    run_local_atexit_funcs,
    temporarily_overwrite_file_on_dir,
    )
from media_create.partitions import (
    calculate_partition_size_and_offset,
    convert_size_to_bytes,
    create_partitions,
    ensure_partition_is_not_mounted,
    get_boot_and_root_loopback_devices,
    get_boot_and_root_partitions_for_media,
    Media,
    run_sfdisk_commands,
    setup_partitions,
    )
from media_create.populate_boot import (
    make_boot_script,
    make_uImage,
    make_uInitrd,
    _get_file_matching,
    _run_mkimage,
    )
from media_create.remove_binary_dir import remove_dir
from media_create.rootfs import (
    create_flash_kernel_config,
    has_space_left_for_swap,
    move_contents,
    populate_rootfs,
    write_data_to_protected_file,
    )
from media_create.unpack_binary_tarball import unpack_binary_tarball

from media_create.tests.fixtures import (
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


# TODO: Must test this on the board config
# class TestCreateBootCMD(TestCase):
# 
#     expected_boot_cmd = (
#         "setenv bootcmd 'fatload mmc mmc_option kernel_addr uImage; "
#         "fatload mmc mmc_option initrd_addr uInitrd; bootm kernel_addr "
#         "initrd_addr'\nsetenv bootargs 'serial_opts  root=UUID=root_uuid "
#         "boot_args'\nboot")
# 
#     def test_create_boot_cmd(self):
#         cmd = create_boot_cmd(
#             is_live=False, is_lowmem=False, mmc_option='mmc_option',
#             root_uuid='root_uuid', kernel_addr="kernel_addr",
#             initrd_addr="initrd_addr", serial_opts="serial_opts",
#             boot_args_options="boot_args")
#         self.assertEqual(self.expected_boot_cmd, cmd)
# 
#     def test_create_boot_cmd_as_script(self):
#         args = "%s -m media_create.boot_cmd " % sys.executable
#         args += ("0 0 mmc_option root_uuid kernel_addr initrd_addr "
#                  "serial_opts boot_args")
#         process = subprocess.Popen(
#             args, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#         stdout, stderr = process.communicate()
#         self.assertEqual(self.expected_boot_cmd, stdout)


class TestRemoveBinaryDir(TestCaseWithFixtures):

    def setUp(self):
        super(TestRemoveBinaryDir, self).setUp()
        self.temp_dir_fixture = CreateTempDirFixture()
        self.useFixture(self.temp_dir_fixture)

    def test_remove_dir(self):
        rc = remove_dir(
            self.temp_dir_fixture.get_temp_dir(), as_root=False)
        self.assertEqual(rc, 0)
        self.assertFalse(
            os.path.exists(self.temp_dir_fixture.get_temp_dir()))


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
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        make_boot_script('boot script data', tempdir, 'boot_script')
        expected = [
            'sudo', 'mkimage', '-A', 'arm', '-O', 'linux', '-T', 'script',
            '-C', 'none', '-a', '0', '-e', '0', '-n', 'boot script',
            '-d', '%s/boot.cmd' % tempdir, 'boot_script']
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

    def setUp(self):
        super(TestPartitionSetup, self).setUp()
        # Stub time.sleep() as create_partitions() use that.
        self.orig_sleep = time.sleep
        time.sleep = lambda s: None

    def tearDown(self):
        super(TestPartitionSetup, self).tearDown()
        time.sleep = self.orig_sleep

    def test_convert_size_in_kbytes_to_bytes(self):
        self.assertEqual(512 * 1024, convert_size_to_bytes('512K'))

    def test_convert_size_in_mbytes_to_bytes(self):
        self.assertEqual(100 * 1024**2, convert_size_to_bytes('100M'))

    def test_convert_size_in_gbytes_to_bytes(self):
        self.assertEqual(12 * 1024**3, convert_size_to_bytes('12G'))

    def test_convert_size_in_kbytes_to_bytes_rounds_to_256k_multiple(self):
        # See comment in convert_size_to_bytes as to why we need to do this.
        self.assertEqual(
            3891 * (1024 * 256), convert_size_to_bytes('1000537K'))

    def test_calculate_partition_size_and_offset(self):
        tempfile = self._create_qemu_img_with_partitions(',1,0x0C,*\n,,,-')
        vfat_size, vfat_offset, linux_size, linux_offset = (
            calculate_partition_size_and_offset(tempfile))
        self.assertEqual(
            [129024L, 32256L, 10321920L, 161280L],
            [vfat_size, vfat_offset, linux_size, linux_offset])

    def test_get_boot_and_root_partitions_for_media_with_2_partitions(self):
        self.useFixture(MockSomethingFixture(
            partitions, '_get_partition_count', lambda media: 2))
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
            partitions, '_get_partition_count', lambda media: 3))
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

    def test_ensure_partition_is_not_mounted_for_mounted_partition(self):
        self.useFixture(MockSomethingFixture(
            partitions, 'is_partition_mounted', lambda part: True))
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        ensure_partition_is_not_mounted('/dev/whatever')
        self.assertEqual(
            [['sudo', 'umount', '/dev/whatever']], popen_fixture.mock.calls)

    def test_ensure_partition_is_not_mounted_for_umounted_partition(self):
        self.useFixture(MockSomethingFixture(
            partitions, 'is_partition_mounted', lambda part: False))
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        ensure_partition_is_not_mounted('/dev/whatever')
        self.assertEqual(None, popen_fixture.mock.calls)

    def test_get_boot_and_root_loopback_devices(self):
        tempfile = self._create_qemu_img_with_partitions(',1,0x0C,*\n,,,-')
        atexit_fixture = self.useFixture(MockSomethingFixture(
            atexit, 'register', AtExitRegister()))
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        # We can't test the return value of get_boot_and_root_loopback_devices
        # because it'd require running losetup as root, so we just make sure
        # it calls losetup correctly.
        get_boot_and_root_loopback_devices(tempfile)
        self.assertEqual(
            [['sudo', 'losetup', '-f', '--show', tempfile, '--offset',
              '32256', '--sizelimit', '129024'],
             ['sudo', 'losetup', '-f', '--show', tempfile, '--offset',
              '161280', '--sizelimit', '10321920']],
            popen_fixture.mock.calls)

        # get_boot_and_root_loopback_devices will also setup two exit handlers
        # to de-register the loopback devices set up above.
        self.assertEqual(2, len(atexit_fixture.mock.funcs))
        popen_fixture.mock.calls = []
        atexit_fixture.mock.run_funcs()
        # We did not really run losetup above (as it requires root) so here we
        # don't have a device to pass to 'losetup -d', but when a device is
        # setup it is passed to the atexit handler.
        self.assertEquals(
            [['sudo', 'losetup', '-d', ''], ['sudo', 'losetup', '-d', '']],
            popen_fixture.mock.calls)

    def test_setup_partitions_for_image_file(self):
        # In practice we could pass an empty image file to setup_partitions,
        # but here we mock Popen() and thanks to that the image is not setup
        # (via qemu-img) inside setup_partitions.  That's why we pass an
        # already setup image file.
        tempfile = self._create_qemu_img_with_partitions(',1,0x0C,*\n,,,-')
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        self.useFixture(MockSomethingFixture(
            partitions, 'is_partition_mounted', lambda part: False))
        self.useFixture(MockSomethingFixture(
            partitions, 'get_boot_and_root_loopback_devices',
            lambda image: ('/dev/loop99', '/dev/loop98')))
        uuid = '2e82008e-1af3-4699-8521-3bf5bac1e67a'
        bootfs, rootfs = setup_partitions(
            'beagle', Media(tempfile), 32, '2G', 'boot', 'root', 'ext3',
            uuid, True, True, True)
        self.assertEqual(
             # This is the call that would create the image file.
            [['qemu-img', 'create', '-f', 'raw', tempfile, '2G'],
             # This call would partition the image file.
             ['sudo', 'sfdisk', '-D', '-H', '255', '-S', '63', '-C', '261',
              tempfile],
             # Make sure changes are written to disk.
             ['sync'],
             ['sudo', 'mkfs.vfat', '-F', '32', bootfs, '-n', 'boot'],
             ['sudo', 'mkfs.ext3', '-U', uuid, rootfs, '-L', 'root']],
            popen_fixture.mock.calls)

    def test_setup_partitions_for_block_device(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        self.useFixture(MockSomethingFixture(
            partitions, '_get_partition_count', lambda media: 2))
        # Pretend the partitions are mounted.
        self.useFixture(MockSomethingFixture(
            partitions, 'is_partition_mounted', lambda part: True))
        tempfile = self._create_qemu_img_with_partitions(',1,0x0C,*\n,,,-')
        media = Media(tempfile)
        # Pretend our tempfile is a block device.
        media.is_block_device = True
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        uuid = '2e82008e-1af3-4699-8521-3bf5bac1e67a'
        bootfs, rootfs = setup_partitions(
            'beagle', media, 32, '2G', 'boot', 'root', 'ext3', uuid, True,
            True, True)
        self.assertEqual(
            [['sudo', 'parted', '-s', tempfile, 'mklabel', 'msdos'],
             ['sudo', 'sfdisk', '-D', '-H', '255', '-S', '63', tempfile],
             ['sync'],
             # Since the partitions are mounted, setup_partitions will umount
             # them before running mkfs.
             ['sudo', 'umount', bootfs],
             ['sudo', 'mkfs.vfat', '-F', '32', bootfs, '-n', 'boot'],
             ['sudo', 'umount', rootfs],
             ['sudo', 'mkfs.ext3', '-U', uuid, rootfs, '-L', 'root']],
            popen_fixture.mock.calls)


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
            ['sudo', 'mount', '/dev/rootfs', root_disk],
            ['sudo', 'mv', contents_bin, contents_etc, root_disk],
            ['sudo', 'dd', 'if=/dev/zero', 'of=%s' % swap_file, 'bs=1M',
             'count=100'],
            ['sudo', 'mkswap', swap_file],
            ['sync'],
            ['sudo', 'umount', root_disk]]
        self.assertEqual(expected, popen_fixture.mock.calls)

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
            ['sudo', 'mv', '-f', tmpfile,
             '%s/etc/flash-kernel.conf' % tempdir],
            call)
        self.assertEqual('UBOOT_PART=/dev/mmcblk0p1', open(tmpfile).read())

    def test_move_contents(self):
        tempdir = self.useFixture(CreateTempDirFixture()).tempdir
        popen_fixture = self.useFixture(MockCmdRunnerPopenFixture())
        file1 = self.createTempFileAsFixture(dir=tempdir)

        move_contents(tempdir, '/tmp/')

        self.assertEqual([['sudo', 'mv', file1, '/tmp/']],
                         popen_fixture.mock.calls)

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
        self.assertEqual(['sudo', 'mv', '-f', tmpfile, path], call)
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
            [['sudo', 'mv', '-f', '/dir/file', '/tmp/dir/file'],
             ['sudo', 'cp', '/path/to/file', '/dir']],
            fixture.mock.calls)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            [['sudo', 'mv', '-f', '/tmp/dir/file', '/dir']],
            fixture.mock.calls)

    def test_copy_file(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        copy_file('/path/to/file', '/dir')
        self.assertEquals(
            [['sudo', 'cp', '/path/to/file', '/dir']],
            fixture.mock.calls)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            [['sudo', 'rm', '-f', '/dir/file']], fixture.mock.calls)

    def test_mount_chroot_proc(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        mount_chroot_proc('chroot')
        self.assertEquals(
            [['sudo', 'mount', 'proc', 'chroot/proc', '-t', 'proc']],
            fixture.mock.calls)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            [['sudo', 'umount', '-v', 'chroot/proc']], fixture.mock.calls)

    def test_install_hwpack(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        force_yes = False
        install_hwpack('chroot', 'hwpack.tgz', force_yes)
        self.assertEquals(
            [['sudo', 'cp', 'hwpack.tgz', 'chroot'],
             ['sudo', 'chroot', 'chroot', 'linaro-hwpack-install',
              '/hwpack.tgz']],
            fixture.mock.calls)

        fixture.mock.calls = []
        run_local_atexit_funcs()
        self.assertEquals(
            [['sudo', 'rm', '-f', 'chroot/hwpack.tgz']], fixture.mock.calls)

    def test_install_hwpacks(self):
        self.useFixture(MockSomethingFixture(
            sys, 'stdout', open('/dev/null', 'w')))
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        force_yes = True
        install_hwpacks(
            'chroot', '/tmp/dir', force_yes, 'hwpack1.tgz', 'hwpack2.tgz')
        self.assertEquals(
            [['sudo', 'mv', '-f', 'chroot/etc/resolv.conf',
              '/tmp/dir/resolv.conf'],
             ['sudo', 'cp', '/etc/resolv.conf', 'chroot/etc'],
             ['sudo', 'mv', '-f', 'chroot/etc/hosts', '/tmp/dir/hosts'],
             ['sudo', 'cp', '/etc/hosts', 'chroot/etc'],
             ['sudo', 'cp', '/usr/bin/qemu-arm-static', 'chroot/usr/bin'],
             ['sudo', 'cp', 'media_create/../linaro-hwpack-install',
              'chroot/usr/bin'],
             ['sudo', 'mount', 'proc', 'chroot/proc', '-t', 'proc'],
             ['sudo', 'cp', 'hwpack1.tgz', 'chroot'],
             ['sudo', 'chroot', 'chroot', 'linaro-hwpack-install',
              '--force-yes', '/hwpack1.tgz'],
             ['sudo', 'cp', 'hwpack2.tgz', 'chroot'],
             ['sudo', 'chroot', 'chroot', 'linaro-hwpack-install',
              '--force-yes', '/hwpack2.tgz'],
             ['sudo', 'rm', '-f', 'chroot/hwpack2.tgz'],
             ['sudo', 'rm', '-f', 'chroot/hwpack1.tgz'],
             ['sudo', 'umount', '-v', 'chroot/proc'],
             ['sudo', 'rm', '-f', 'chroot/usr/bin/linaro-hwpack-install'],
             ['sudo', 'rm', '-f', 'chroot/usr/bin/qemu-arm-static'],
             ['sudo', 'mv', '-f', '/tmp/dir/hosts', 'chroot/etc'],
             ['sudo', 'mv', '-f', '/tmp/dir/resolv.conf', 'chroot/etc']],
            fixture.mock.calls)
