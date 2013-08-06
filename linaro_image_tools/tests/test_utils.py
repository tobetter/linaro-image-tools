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
import logging
import tempfile
import tarfile
from StringIO import StringIO

from linaro_image_tools import cmd_runner, utils
from linaro_image_tools.testing import TestCaseWithFixtures
from linaro_image_tools.tests.fixtures import (
    CreateTempDirFixture,
    MockCmdRunnerPopenFixture,
    MockSomethingFixture,
)
from linaro_image_tools.utils import (
    IncompatibleOptions,
    InvalidHwpackFile,
    UnableToFindPackageProvidingCommand,
    additional_android_option_checks,
    additional_option_checks,
    android_hwpack_in_boot_tarball,
    check_file_integrity_and_log_errors,
    ensure_command,
    find_command,
    install_package_providing,
    path_in_tarfile_exists,
    preferred_tools_dir,
    prep_media_path,
    try_import,
    verify_file_integrity,
)


sudo_args = " ".join(cmd_runner.SUDO_ARGS)


class TestPathInTarfile(TestCaseWithFixtures):
    def setUp(self):
        super(TestPathInTarfile, self).setUp()
        tempdir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        self.tarfile_name = os.path.join(tempdir, 'test_tarfile.tar.gz')
        self.tempfile_added = self.createTempFileAsFixture()
        self.tempfile_unused = self.createTempFileAsFixture()
        with tarfile.open(self.tarfile_name, 'w:gz') as tar:
            tar.add(self.tempfile_added)

    def test_file_exists(self):
        self.assertTrue(path_in_tarfile_exists(self.tempfile_added[1:],
                                               self.tarfile_name))

    def test_file_does_not_exist(self):
        self.assertFalse(path_in_tarfile_exists(self.tempfile_unused[1:],
                                                self.tarfile_name))


class TestVerifyFileIntegrity(TestCaseWithFixtures):

    filenames_in_shafile = ['verified-file1', 'verified-file2']

    class MockCmdRunnerPopen(object):
        def __call__(self, cmd, *args, **kwargs):
            self.returncode = 0
            return self

        def communicate(self, input=None):
            self.wait()
            return ': OK\n'.join(
                TestVerifyFileIntegrity.filenames_in_shafile) + ': OK\n', ''

        def wait(self):
            return self.returncode

    class MockCmdRunnerPopen_sha1sum_fail(object):
        def __call__(self, cmd, *args, **kwargs):
            self.returncode = 0
            return self

        def communicate(self, input=None):
            self.wait()
            return ': ERROR\n'.join(
                TestVerifyFileIntegrity.filenames_in_shafile) + ': ERROR\n', ''

        def wait(self):
            return self.returncode

    class MockCmdRunnerPopen_wait_fails(object):
        def __call__(self, cmd, *args, **kwargs):
            self.returncode = 0
            return self

        def communicate(self, input=None):
            self.wait()
            return ': OK\n'.join(
                TestVerifyFileIntegrity.filenames_in_shafile) + ': OK\n', ''

        def wait(self):
            stdout = ': OK\n'.join(
                TestVerifyFileIntegrity.filenames_in_shafile) + ': OK\n'
            raise cmd_runner.SubcommandNonZeroReturnValue([], 1, stdout, None)

    class FakeTempFile():
        name = "/tmp/1"

        def close(self):
            pass

        def read(self):
            return ""

    def test_verify_files(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(tempfile, 'NamedTemporaryFile',
                                             self.FakeTempFile))
        hash_filename = "dummy-file.txt"
        signature_filename = hash_filename + ".asc"
        verify_file_integrity([signature_filename])
        self.assertEqual(
            ['gpg --status-file=%s --verify %s' % (self.FakeTempFile.name,
                                                   signature_filename),
             'sha1sum -c %s' % hash_filename],
            fixture.mock.commands_executed)

    def test_verify_files_returns_files(self):
        self.useFixture(MockSomethingFixture(cmd_runner, 'Popen',
                                             self.MockCmdRunnerPopen()))
        hash_filename = "dummy-file.txt"
        signature_filename = hash_filename + ".asc"
        verified_files, _, _ = verify_file_integrity([signature_filename])
        self.assertEqual(self.filenames_in_shafile, verified_files)

    def test_check_file_integrity_and_print_errors(self):
        self.useFixture(MockSomethingFixture(cmd_runner, 'Popen',
                                             self.MockCmdRunnerPopen()))
        hash_filename = "dummy-file.txt"
        signature_filename = hash_filename + ".asc"
        result, verified_files = check_file_integrity_and_log_errors(
            [signature_filename],
            self.filenames_in_shafile[0],
            [self.filenames_in_shafile[1]])
        self.assertEqual(self.filenames_in_shafile, verified_files)

        # The sha1sums are faked as passing and all commands return 0, so
        # it should look like GPG passed
        self.assertTrue(result)

    def test_check_file_integrity_and_print_errors_fail_sha1sum(self):
        logging.getLogger().setLevel(100)  # Disable logging messages to screen
        self.useFixture(MockSomethingFixture(
            cmd_runner, 'Popen', self.MockCmdRunnerPopen_sha1sum_fail()))
        hash_filename = "dummy-file.txt"
        signature_filename = hash_filename + ".asc"
        result, verified_files = check_file_integrity_and_log_errors(
            [signature_filename],
            self.filenames_in_shafile[0],
            [self.filenames_in_shafile[1]])
        self.assertEqual([], verified_files)

        # The sha1sums are faked as failing and all commands return 0, so
        # it should look like GPG passed
        self.assertFalse(result)
        logging.getLogger().setLevel(logging.WARNING)

    def test_check_file_integrity_and_print_errors_fail_gpg(self):
        logging.getLogger().setLevel(100)  # Disable logging messages to screen
        self.useFixture(MockSomethingFixture(
            cmd_runner, 'Popen', self.MockCmdRunnerPopen_wait_fails()))
        hash_filename = "dummy-file.txt"
        signature_filename = hash_filename + ".asc"
        result, verified_files = check_file_integrity_and_log_errors(
            [signature_filename],
            self.filenames_in_shafile[0],
            [self.filenames_in_shafile[1]])
        self.assertEqual([], verified_files)

        # The sha1sums are faked as passing and all commands return 1, so
        # it should look like GPG failed
        self.assertFalse(result)
        logging.getLogger().setLevel(logging.WARNING)


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

    # This is the package we need to fake the installation of, it is a
    # slightly changed version of 'apt-get -s install' output.
    # It is used as an argument to MockCmdRunnerPopenFixture in order to
    # pass a string that should be expected as output from the command that
    # is being executed.
    output_string = 'Inst dosfstools (3.0.12-1ubuntu1 Ubuntu:12.04)'

    def test_package_installation_accepted(self):
        self.useFixture(MockSomethingFixture(sys,
                                             'stdout',
                                             open('/dev/null', 'w')))
        # We need this since we are getting user input via raw_input
        # and we need a 'Y' to proceed with the operations.
        self.useFixture(MockSomethingFixture(sys,
                                             'stdin',
                                             StringIO('Y')))
        fixture = self.useFixture(
            MockCmdRunnerPopenFixture(self.output_string))

        try:
            install_package_providing('mkfs.vfat')
        except UnableToFindPackageProvidingCommand as inst:
            self.assertEqual("CommandNotFound python module does not exist.",
                             inst.args[0])
        else:
            self.assertEqual(
                ['apt-get -s install dosfstools',
                 '%s apt-get --yes install dosfstools' % sudo_args],
                fixture.mock.commands_executed)

    def test_package_installation_refused(self):
        self.useFixture(MockSomethingFixture(sys,
                                             'stdout',
                                             open('/dev/null', 'w')))
        # We need this since we are getting user input via raw_input
        # and we need a 'n' to mimic a refused package installation.
        self.useFixture(MockSomethingFixture(sys,
                                             'stdin',
                                             StringIO('n')))
        self.useFixture(MockCmdRunnerPopenFixture(self.output_string))

        CommandNotFound = try_import('CommandNotFound.CommandNotFound')

        if CommandNotFound is None:
            self.assertRaises(UnableToFindPackageProvidingCommand,
                              install_package_providing, 'mkfs.vfat')
        else:
            self.assertRaises(SystemExit, install_package_providing,
                              'mkfs.vfat')

    def test_not_found_package(self):
        self.assertRaises(UnableToFindPackageProvidingCommand,
                          install_package_providing, 'mkfs.lean')


class Args():
    def __init__(self, directory, device, board):
        self.directory = directory
        self.device = device
        self.board = board


class TestPrepMediaPath(TestCaseWithFixtures):

    def test_prep_media_path(self):
        self.useFixture(MockSomethingFixture(os.path, 'abspath', lambda x: x))
        self.useFixture(MockSomethingFixture(os, "makedirs", lambda x: x))

        self.assertEqual("testdevice",
                         prep_media_path(Args(directory=None,
                                              device="testdevice",
                                              board="testboard")))

        self.assertEqual("/foo/bar/testdevice",
                         prep_media_path(Args(directory="/foo/bar",
                                              device="testdevice",
                                              board="testboard")))


class TestAdditionalOptionChecks(TestCaseWithFixtures):

    def test_additional_option_checks(self):
        self.useFixture(MockSomethingFixture(os.path, 'abspath', lambda x: x))
        self.useFixture(MockSomethingFixture(os, "makedirs", lambda x: x))

        self.assertRaises(IncompatibleOptions, additional_option_checks,
                          Args(directory="/foo/bar",
                               device="/testdevice",
                               board="testboard"))

        sys.argv.append("--mmc")
        self.assertRaises(IncompatibleOptions, additional_option_checks,
                          Args(directory="/foo/bar",
                               device="testdevice",
                               board="testboard"))
        sys.argv.remove("--mmc")


class TestAndroidOptionChecks(TestCaseWithFixtures):

    def test_hwpack_is_file(self):
        class HwPacksArgs:
            def __init__(self, hwpack):
                self.hwpack = hwpack

        try:
            tmpdir = tempfile.mkdtemp()
            self.assertRaises(InvalidHwpackFile,
                              additional_android_option_checks,
                              HwPacksArgs(tmpdir))
        finally:
            os.rmdir(tmpdir)

    def test_android_hwpack_in_boot(self):
        """Test presence of config file in boot directory."""
        try:
            tmpdir = tempfile.mkdtemp()
            boot_dir = os.path.join(tmpdir, "boot")
            os.mkdir(boot_dir)
            config_file = os.path.join(boot_dir, "config")
            expected = (True, config_file)
            with open(config_file, "w"):
                self.assertEqual(expected,
                                 android_hwpack_in_boot_tarball(tmpdir))
        finally:
            os.unlink(config_file)
            os.removedirs(boot_dir)

    def test_android_hwpack_not_in_boot(self):
        """Test missing config file."""
        try:
            tmpdir = tempfile.mkdtemp()
            boot_dir = os.path.join(tmpdir, "boot")
            os.mkdir(boot_dir)
            config_file = os.path.join(boot_dir, "config")
            expected = (False, config_file)
            self.assertEqual(expected, android_hwpack_in_boot_tarball(tmpdir))
        finally:
            os.removedirs(boot_dir)


class TestHwpackIsFile(TestCaseWithFixtures):

    """Testing '--hwpack' option only allows regular files."""

    def test_hwpack_is_file(self):
        class HwPackArgs:
            def __init__(self, hwpack):
                self.hwpacks = [hwpack]
                self.directory = None

        try:
            tmpdir = tempfile.mkdtemp()
            self.assertRaises(InvalidHwpackFile, additional_option_checks,
                              HwPackArgs(hwpack=tmpdir))
        finally:
            os.rmdir(tmpdir)

    def test_hwpacks_are_files(self):

        """
        Tests that multiple hwpacks are regular files.

        Tests against a file and a directory, to avoid circumstances in which
        'additional_option_checks' is tweaked.
        """

        class HwPacksArgs:
            def __init__(self, hwpacks):
                self.hwpacks = hwpacks
                self.directory = None

        try:
            tmpdir = tempfile.mkdtemp()
            _, tmpfile = tempfile.mkstemp()
            self.assertRaises(InvalidHwpackFile, additional_option_checks,
                              HwPacksArgs([tmpfile, tmpdir]))
        finally:
            os.rmdir(tmpdir)
            os.remove(tmpfile)
