import subprocess
import sys
import os
import os.path
import shutil

from testtools import TestCase

from media_create.boot_cmd import create_boot_cmd
from media_create.remove_binary_dir import remove_binary_dir
from media_create.unpack_binary_tarball import unpack_binary_tarball


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


class TestRemoveBinaryDir(TestCase):

    def test_remove_binary_dir(self):
        TEST_DIR = 'binary_test_dir/'
        try:
            os.mkdir(TEST_DIR)
        except OSError:
            pass

        rc = remove_binary_dir(binary_dir=TEST_DIR, as_root=False)
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(TEST_DIR))

        if os.path.exists(TEST_DIR):
            os.rmdir(TEST_DIR)


class TestUnpackBinaryTarball(TestCase):

    def test_unpack_binary_tarball(self):
        TEST_DIR = 'binary_test_dir/'
        TARBALL = TEST_DIR + '.tar.gz'
        try:
            os.mkdir(TEST_DIR)
        except OSError:
            pass

        cmd = 'tar -czf %s %s' % (TARBALL, TEST_DIR)
        proc = subprocess.Popen(cmd, shell=True)
        proc.wait()
        rc = unpack_binary_tarball(TARBALL, as_root=False)
        self.assertEqual(rc, 0)

        if os.path.exists(TEST_DIR):            
            shutil.rmtree(TEST_DIR)
        if os.path.exists(TARBALL):
            os.remove(TARBALL)

