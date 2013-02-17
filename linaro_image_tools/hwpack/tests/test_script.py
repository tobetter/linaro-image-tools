# Copyright (C) 2010, 2011 Linaro
#
# Author: James Westby <james.westby@linaro.org>
#
# This file is part of Linaro Image Tools.
#
# Linaro Image Tools is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Linaro Image Tools; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

import subprocess

from testtools.matchers import DocTestMatches

from linaro_image_tools.hwpack.hardwarepack import Metadata
from linaro_image_tools.hwpack.testing import (
    AptSourceFixture,
    ChdirToTempdirFixture,
    ConfigFileFixture,
    DummyFetchedPackage,
    IsHardwarePack,
)
from linaro_image_tools.hwpack.config import Config
from linaro_image_tools.testing import TestCaseWithFixtures
from linaro_image_tools.utils import find_command
import os
from StringIO import StringIO


class ScriptTests(TestCaseWithFixtures):
    """Tests that execute the linaro-hwpack-create script."""

    def setUp(self):
        super(ScriptTests, self).setUp()

        # Work out root of checkout.
        # We do this here because when running in PyCharm
        # the assumption in find_command that os.path.isabs(__file__) is
        # only true when not running from a Bazaar checkout is broken.
        # Thankfully find_command allows us to work around this by specifying
        # prefer_dir.
        dir = os.path.dirname(__file__)
        while True:
            path = os.path.join(dir, "linaro-hwpack-create")
            if dir == "/" or dir == "":
                # Didn't find linaro-media-create. Continue as if we haven't
                # tried to work out prefer_dir.
                dir = None
                break
            if os.path.exists(path) and os.access(path, os.X_OK):
                break
            dir = os.path.split(dir)[0]

        self.script_path = find_command("linaro-hwpack-create", prefer_dir=dir)
        self.useFixture(ChdirToTempdirFixture())

    def run_script(self, args, expected_returncode=0):
        cmdline = [self.script_path] + args
        proc = subprocess.Popen(
            cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout, stderr) = proc.communicate()
        self.assertEqual(
            expected_returncode, proc.returncode,
            "%s exited with code %d. stdout: %s\nstderr: %s\n"
            % (str(cmdline), proc.returncode, stdout, stderr))
        return stdout, stderr

    def test_errors_on_missing_configfile(self):
        stdout, stderr = self.run_script(
            ["nonexistant", "1.0"], expected_returncode=1)
        self.assertEqual("No such config file: 'nonexistant'\n", stderr)
        self.assertEqual("", stdout)

    def test_errors_on_missing_configfile_argument(self):
        stdout, stderr = self.run_script([], expected_returncode=2)
        self.assertEqual(
            "linaro-hwpack-create: error: too few arguments",
            stderr.splitlines()[-1])
        self.assertEqual("", stdout)

    def test_errors_on_missing_version_argument(self):
        stdout, stderr = self.run_script(["somefile"], expected_returncode=2)
        self.assertEqual(
            "linaro-hwpack-create: error: too few arguments",
            stderr.splitlines()[-1])
        self.assertEqual("", stdout)

    def test_builds_a_hwpack(self):
        package_name = 'foo'
        available_package = DummyFetchedPackage(
            package_name, "1.1", architecture="armel")
        source = self.useFixture(AptSourceFixture([available_package]))
        config = self.useFixture(ConfigFileFixture(
            '[hwpack]\nname=ahwpack\npackages=%s\narchitectures=armel\n'
            '\n[ubuntu]\nsources-entry=%s\n' % (
                package_name, source.sources_entry)))
        stdout, stderr = self.run_script([config.filename, "1.0"])
        metadata = Metadata("ahwpack", "1.0", "armel")
        self.assertThat(
            "hwpack_ahwpack_1.0_armel.tar.gz",
            IsHardwarePack(
                metadata, [available_package],
                {"ubuntu": source.sources_entry},
                package_spec=package_name))

    def test_builds_a_v3_hwpack_from_config_with_2_bootloaders(self):
        config_v3 = ("format: 3.0\n"
                     "name: ahwpack\n"
                     "architectures: armel\n"
                     "serial_tty: ttySAC1\n"
                     "partition_layout:\n"
                     " - bootfs_rootfs\n"
                     "boot_script: boot.scr\n"
                     "extra_serial_options:\n"
                     "  - console=tty0\n"
                     "  - console=ttyO2,115200n8\n"
                     "mmc_id: 0:1\n"
                     "kernel_file: boot/vmlinuz-*-linaro-omap\n"
                     "initrd_file: boot/initrd.img-*-linaro-omap\n"
                     "dtb_file: boot/dt-*-linaro-omap/omap4-panda.dtb\n"
                     "packages:\n"
                     " - %s\n"
                     " - %s\n")
        bootloader_config = ("  package: %s\n"
                             "  in_boot_part: %s\n"
                             "  extra_boot_options:\n"
                             "   - earlyprintk\n"
                             "   - fixrtc\n"
                             "   - nocompcache\n"
                             "   - vram=48M\n"
                             "   - omapfb.vram=0:24M\n"
                             "   - mem=456M@0x80000000\n"
                             "   - mem=512M@0xA0000000\n")

        config_v3 += ("bootloaders:\n"
                      " u_boot:\n" + bootloader_config +
                      " u_boot_2:\n" + bootloader_config)

        config_v3 += ("sources:\n"
                      " ubuntu: %s\n")

        package_names = ['foo', 'bar']
        available_packages = []
        for package_name in package_names:
            available_packages.append(
                DummyFetchedPackage(package_name, "1.1", architecture="armel"))
        source = self.useFixture(AptSourceFixture(available_packages))

        config_v3 = config_v3 % (package_names[0], package_names[1],
                                 package_names[0], "True",
                                 package_names[1], "False",
                                 source.sources_entry)

        config_file_fixture = self.useFixture(ConfigFileFixture(config_v3))
        self.run_script([config_file_fixture.filename, "1.0"])

        # We now need a real config object to test against the configuration
        # in the hardware pack we have created.
        config = Config(StringIO(config_v3))
        config.bootloader = "u_boot"
        metadata = Metadata.from_config(config, "1.0", "armel")
        self.assertThat(
            "hwpack_ahwpack_1.0_armel.tar.gz",
            IsHardwarePack(
                metadata, available_packages,
                {"ubuntu": source.sources_entry},
                package_spec=",".join(package_names),
                format="3.0"))

    def test_log_output(self):
        package_name = 'foo'
        architecture = 'armel'
        available_package = DummyFetchedPackage(
            package_name, "1.1", architecture=architecture)
        source = self.useFixture(AptSourceFixture([available_package]))
        config = self.useFixture(ConfigFileFixture(
            '[hwpack]\nname=ahwpack\npackages=%s\narchitectures=armel\n'
            '\n[ubuntu]\nsources-entry=%s\n' % (
                package_name, source.sources_entry)))
        stdout, stderr = self.run_script([config.filename, "1.0"])

        # XXX Adding in the format deprecation message below is just a hack
        # until the test can be fixed up to test a new format hwpack.

        self.assertThat(
            stderr,
            DocTestMatches(
                "Building for %(arch)s\nFetching packages\n"
                "The format '1.0' is deprecated, please update your hardware "
                "pack configuration.\n"
                "Wrote hwpack_ahwpack_1.0_%(arch)s.tar.gz"
                "\n" % dict(arch=architecture)))
