import subprocess
import sys
import os
import os.path

from testtools import TestCase

from media_create.boot_cmd import create_boot_cmd
from media_create.remove_binary_dir import remove_binary_dir


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

    TEST_DIR = 'binary_test_dir/'

    def test_remove_binary_dir(self):
        try:
            os.mkdir(TEST_DIR)
        except OSError:
            pass
            
        rc = remove_binary_dir(binary_dir=TEST_DIR, as_root=False)
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(TEST_DIR))
        