# Copyright (C) 2010, 2011, 2012 Linaro
#
# Author: Milo Casagrande <milo.casagrande@linaro.org>
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

import tempfile
from linaro_image_tools.testing import TestCaseWithFixtures
from linaro_image_tools.tests.fixtures import (
    CreateTempDirFixture,
    CreateTempFileFixture,
)

from linaro_image_tools.hwpack.hwpack_convert import (
    HwpackConverter,
    HwpackConverterException,
    check_and_validate_args,
)


class Args():
    """Defines the args for the command line options."""
    def __init__(self, input_file, output_file=None):
        self.CONFIG_FILE = input_file
        self.out = output_file


class HwpackConverterTests(TestCaseWithFixtures):
    """Test class for the hwpack converter."""

    def setUp(self):
        super(HwpackConverterTests, self).setUp()

    def test_wrong_input_file(self):
        """Pass a non-existing file."""
        input_file = '/tmp/foobaz'
        self.assertRaises(
            HwpackConverterException, check_and_validate_args,
            Args(input_file=input_file))

    def test_wrong_input_dir(self):
        """Pass a directory instead of file."""
        temp_file = tempfile.NamedTemporaryFile()
        temp_dir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        self.assertRaises(
            HwpackConverterException, check_and_validate_args,
            Args(input_file=temp_file.name, output_file=temp_dir))

    def test_same_input_output_file(self):
        """Pass the same existing file path to the two arguments."""
        temp_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        self.assertRaises(
            HwpackConverterException, check_and_validate_args,
            Args(input_file=temp_file, output_file=temp_file))

    def test_basic_parse(self):
        ini_format = '[hwpack]\nformat=2.0\nsupport=supported'
        output_format = "format: '3.0'\nsupport: supported\n"
        input_file = self.useFixture(
            CreateTempFileFixture(ini_format)).get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(output_format, str(converter))

    def test_architectures_section_creation(self):
        """Tests that we create the correct architectures list in the
        converted file.
        """
        ini_format = '[hwpack]\nformat=2.0\narchitectures=armhf armel'
        output_format = "format: '3.0'\narchitectures:\n- armhf\n- armel\n"
        input_file = self.useFixture(
            CreateTempFileFixture(ini_format)).get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(output_format, str(converter))

    def test_bootloaders(self):
        """Tests the correct creation of the bootloaders part."""
        ini_format = ("[hwpack]\nformat=2.0\nu_boot_package=a_package\n"
                      "u_boot_file=a_file\nu_boot_in_boot_part=Yes\n"
                      "u_boot_dd=33")
        out_format = ("format: '3.0'\nbootloaders:\n  u_boot:\n    dd: '33'"
                      "\n    file: a_file\n    in_boot_part: true\n"
                      "    package: a_package\n")
        input_file = self.useFixture(
            CreateTempFileFixture(ini_format)).get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(out_format, str(converter))

    def test_extra_boot_options(self):
        """Tests the correct creation of the extra_boot_options part."""
        ini_format = ("[hwpack]\nformat=2.0\nu_boot_package=a_package\n"
                      "extra_boot_options=opt1 opt2")
        out_format = ("format: '3.0'\nbootloaders:\n  u_boot:\n "
                      "   extra_boot_options:\n    - opt1\n    "
                      "- opt2\n    package: a_package\n")
        input_file = self.useFixture(
            CreateTempFileFixture(ini_format)).get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(out_format, str(converter))

    def test_extra_serial_options(self):
        """Tests the correct creation of the extra_serial_options part."""
        ini_format = ("[hwpack]\nformat=2.0\nextra_serial_options=opt1 opt2")
        out_format = ("format: '3.0'\nextra_serial_options:\n- opt1\n- opt2\n")
        input_file = self.useFixture(
            CreateTempFileFixture(ini_format)).get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(out_format, str(converter))

    def test_assume_installed(self):
        """Tests the correct creation of the extra_serial_options part."""
        ini_format = ("[hwpack]\nformat=2.0\nassume-installed=install1 "
                      "install2")
        out_format = ("format: '3.0'\nassume_installed:\n- install1\n- "
                      "install2\n")
        input_file = self.useFixture(
            CreateTempFileFixture(ini_format)).get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(out_format, str(converter))

    def test_include_debs(self):
        """Tests the correct creation of the extra_serial_options part."""
        ini_format = ("[hwpack]\nformat=2.0\ninclude-debs=yes")
        out_format = ("format: '3.0'\ninclude_debs: true\n")
        input_file = self.useFixture(
            CreateTempFileFixture(ini_format)).get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(out_format, str(converter))

    def test_dtb_file(self):
        """Test the dtb_file conversion."""
        ini_format = ("[hwpack]\nformat=2.0\ndtb_file=boot/a-*-path/file.dtb")
        out_format = ("format: '3.0'\ndtb_files:\n- board.dtb: "
                      "boot/a-*-path/file.dtb\n")
        input_file = self.useFixture(
            CreateTempFileFixture(ini_format)).get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(out_format, str(converter))

    def test_mmc_id(self):
        """Test correct handling of mmc_id field.

        The mmc_id field has to be quoted coming out from the converter
        otherwise when reading the yaml file the value is read as a number,
        not a string."""
        ini_format = ("[hwpack]\nformat=2.0\nmmc_id=1:1")
        out_format = ("format: '3.0'\nmmc_id: '1:1'\n")
        input_file = self.useFixture(
            CreateTempFileFixture(ini_format)).get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(out_format, str(converter))
