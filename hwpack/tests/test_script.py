import os
import subprocess

from hwpack.hardwarepack import Metadata
from hwpack.testing import (
    AptSourceFixture,
    ChdirToTempdirFixture,
    ConfigFileFixture,
    DummyFetchedPackage,
    IsHardwarePack,
    TestCaseWithFixtures,
    )


class ScriptTests(TestCaseWithFixtures):
    """Tests that execute the linaro-hwpack-create script."""

    def setUp(self):
        super(ScriptTests, self).setUp()
        self.script_path = self.find_script()
        self.useFixture(ChdirToTempdirFixture())

    def find_script(self):
        script_name = "linaro-hwpack-create"
        this_path = os.path.abspath(__file__)
        parent_path = this_path
        for i in range(3):
            parent_path = os.path.dirname(parent_path)
        possible_paths = [
            os.path.join(parent_path, script_name),
            os.path.join("usr", "local", "bin", script_name),
            os.path.join("usr", "bin", script_name),
        ]
        for script_path in possible_paths:
            if os.path.exists(script_path):
                return script_path
        raise AssertionError(
            "Could not find linaro-hwpack-create script to test.")

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
            "usage: linaro-hwpack-create [-h] CONFIG_FILE VERSION\n"
            "linaro-hwpack-create: error: too few arguments\n", stderr)
        self.assertEqual("", stdout)

    def test_errors_on_missing_version_argument(self):
        stdout, stderr = self.run_script(["somefile"], expected_returncode=2)
        self.assertEqual(
            "usage: linaro-hwpack-create [-h] CONFIG_FILE VERSION\n"
            "linaro-hwpack-create: error: too few arguments\n", stderr)
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
