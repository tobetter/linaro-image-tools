# Copyright (C) 2012 Linaro
#
# Author: Milo Casagrande <milo.casagrande@linaro.org>
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
# along with Linaro Image Tools.  If not, see <http://www.gnu.org/licenses/>.

import tarfile
from StringIO import StringIO
from linaro_image_tools.testing import TestCaseWithFixtures
from linaro_image_tools.tests.fixtures import (
    CreateTempDirFixture,
)

from linaro_image_tools.media_create.tests.fixtures import (
    CreateTarballFixture,
)

from linaro_image_tools.hwpack.hwpack_reader import (
    Hwpack,
    HwpackReader,
    HwpackReaderError,
)


class HwpackReaderTests(TestCaseWithFixtures):
    """Test class for the hwpack reader."""

    def setUp(self):
        super(HwpackReaderTests, self).setUp()
        self.metadata = ("format: 3.0\nversion: '1'\nname: test-hwpack\n"
                         "architecture: armel\norigin: Linaro")
        self.hwpack = Hwpack()
        self.hwpack.setname('test-hwpack')
        self.tar_dir_fixture = CreateTempDirFixture()
        self.useFixture(self.tar_dir_fixture)
        self.tarball_fixture = CreateTarballFixture(
            self.tar_dir_fixture.get_temp_dir())
        self.useFixture(self.tarball_fixture)

    def tearDown(self):
        super(HwpackReaderTests, self).tearDown()
        self.hwpack = None
        self.metadata = ""

    def add_to_tarball(self, files, tarball=None):
        if tarball is None:
            tarball = self.tarball_fixture.get_tarball()
        tar_file = tarfile.open(tarball, mode='w:gz')
        for filename, data in files:
            tarinfo = tarfile.TarInfo(filename)
            tarinfo.size = len(data)
            tar_file.addfile(tarinfo, StringIO(data))
        tar_file.close()
        return tarball

    def test_hwpack_class(self):
        hwpack = Hwpack()
        hwpack.setname('test-hwpack')
        hwpack.sethwpack('a_hwpack')
        self.hwpack.sethwpack('a_hwpack')
        self.assertEqual(self.hwpack, hwpack)

    def test_hwpack_class_not_equal(self):
        hwpack = Hwpack()
        hwpack.setname('test-hwpack')
        hwpack.sethwpack('a_hwpack')
        self.hwpack.sethwpack('b_hwpack')
        self.assertNotEqual(self.hwpack, hwpack)

    def test_hwpack_metadata_read(self):
        tarball = self.add_to_tarball([('metadata', self.metadata)])
        reader = HwpackReader([tarball])
        reader._read_hwpacks_metadata()
        self.hwpack.sethwpack(tarball)
        self.assertEqual(self.hwpack, reader.supported_elements[0])

    def test_raise_exception(self):
        new_metadata = ("format=2.0\nversion=4")
        tarball = self.add_to_tarball([('metadata', new_metadata)])
        reader = HwpackReader([tarball])
        self.assertRaises(HwpackReaderError, reader._read_hwpacks_metadata)

    def test_hwpack_metadata_read_with_boards(self):
        self.metadata += "\nboards:\n panda:\n  support: supported\n"
        tarball = self.add_to_tarball([('metadata', self.metadata)])
        reader = HwpackReader([tarball])
        reader._read_hwpacks_metadata()
        self.hwpack.sethwpack(tarball)
        self.hwpack.setboards({'panda': {'support': 'supported'}})
        self.assertEqual(self.hwpack, reader.supported_elements[0])

    def test_hwpack_metadata_read_with_bootloaders(self):
        self.metadata += ("\nboards:\n panda:\n  support: supported\n  "
                          "bootloaders:\n   u_boot:\n    file: a_file\n")
        tarball = self.add_to_tarball([('metadata', self.metadata)])
        reader = HwpackReader([tarball])
        reader._read_hwpacks_metadata()
        self.hwpack.sethwpack(tarball)
        self.hwpack.setboards({'panda': {'support': 'supported', 'bootloaders':
                              {'u_boot': {'file': 'a_file'}}}})
        self.assertEqual(self.hwpack, reader.supported_elements[0])
