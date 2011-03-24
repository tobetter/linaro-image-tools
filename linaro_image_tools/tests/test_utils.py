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

import os
import stat
import subprocess
import sys

from linaro_image_tools import utils

from linaro_image_tools.hwpack.testing import TestCaseWithFixtures

from linaro_image_tools.media_create import cmd_runner

from linaro_image_tools.media_create.tests.fixtures import (
    CreateTempDirFixture,
    MockCmdRunnerPopenFixture,
    MockSomethingFixture,
    )

from linaro_image_tools.utils import (
    ensure_command,
    find_command,
    install_package_providing,
    UnableToFindPackageProvidingCommand,
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

