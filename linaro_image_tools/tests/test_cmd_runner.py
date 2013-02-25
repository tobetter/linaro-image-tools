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

from linaro_image_tools import cmd_runner
from linaro_image_tools.testing import TestCaseWithFixtures
from linaro_image_tools.tests.fixtures import (
    MockCmdRunnerPopenFixture,
    MockSomethingFixture,
)


sudo_args = " ".join(cmd_runner.SUDO_ARGS)
chroot_args = " ".join(cmd_runner.CHROOT_ARGS)


class TestSanitizePath(TestCaseWithFixtures):
    def setUp(self):
        super(TestSanitizePath, self).setUp()
        self.env = {}

    def test_path_unset(self):
        cmd_runner.sanitize_path(self.env)
        self.assertEqual(cmd_runner.DEFAULT_PATH, self.env['PATH'])

    def test_path_missing_dirs(self):
        path = '/bin:/sbin:/foo:/usr/local/sbin'
        self.env['PATH'] = path
        cmd_runner.sanitize_path(self.env)
        expected = '%s:/usr/local/bin:/usr/sbin:/usr/bin' % path
        self.assertEqual(expected, self.env['PATH'])

    def test_idempotent(self):
        self.env['PATH'] = cmd_runner.DEFAULT_PATH
        cmd_runner.sanitize_path(self.env)
        self.assertEqual(cmd_runner.DEFAULT_PATH, self.env['PATH'])


class TestCmdRunner(TestCaseWithFixtures):

    def test_run(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        proc = cmd_runner.run(['foo', 'bar', 'baz'])
        # Call wait or else MockCmdRunnerPopenFixture() raises an
        # AssertionError().
        proc.wait()
        self.assertEqual(0, proc.returncode)
        self.assertEqual(['foo bar baz'], fixture.mock.commands_executed)

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
        self.assertEqual(['foo bar'], fixture.mock.commands_executed)

    def test_tuple_with_sudo(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        self.useFixture(MockSomethingFixture(os, 'getuid', lambda: 1000))
        cmd_runner.run(('foo', 'bar',), as_root=True).wait()
        self.assertEqual(
            ['%s foo bar' % sudo_args], fixture.mock.commands_executed)

    def test_chrooted(self):
        fixture = self.useFixture(MockCmdRunnerPopenFixture())
        cmd_runner.run(['foo', 'bar'], chroot='chroot_dir').wait()
        self.assertEqual(
            ['%s %s chroot_dir foo bar' % (sudo_args, chroot_args)],
            fixture.mock.commands_executed)

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
