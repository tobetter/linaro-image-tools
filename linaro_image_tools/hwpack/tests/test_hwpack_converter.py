#from StringIO import StringIO
import tempfile
#import os
#import os.path
#from testtools.matchers import Equals, MismatchError
from linaro_image_tools.testing import TestCaseWithFixtures
from linaro_image_tools.tests.fixtures import (
    CreateTempDirFixture,
    CreateTempFileFixture,
#    MockCmdRunnerPopenFixture,
#    MockSomethingFixture,
    )

from linaro_image_tools.hwpack.hwpack_convert import (
    HwpackConverter,
    HwpackConverterException,
    check_and_validate_args,
    create_yaml_dictionary,
    create_yaml_sequence,
    create_yaml_string,
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
        self.assertRaises(HwpackConverterException, check_and_validate_args,
                            Args(input_file=input_file))

    def test_wrong_input_dir(self):
        """Pass a directory instead of file."""
        temp_file = tempfile.NamedTemporaryFile()
        temp_dir = self.useFixture(CreateTempDirFixture()).get_temp_dir()
        self.assertRaises(HwpackConverterException, check_and_validate_args,
                            Args(input_file=temp_file.name,
                                output_file=temp_dir))

    def test_same_input_output_file(self):
        """Pass the same existing file path to the two arguments."""
        temp_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        self.assertRaises(HwpackConverterException, check_and_validate_args,
                            Args(input_file=temp_file, output_file=temp_file))

    def test_basic_parse(self):
        ini_format = '[hwpack]\nformat=2.0\nsupport=supported'
        output_format = 'support: supported\nformat: 2.0\n'
        input_file = self.useFixture(CreateTempFileFixture(ini_format)).\
                                                                get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(output_format, str(converter))

    def test_architectures_section_creation(self):
        """Tests that we create the correct architectures list in the
        converted file.
        """
        ini_format = '[hwpack]\nformat=2.0\narchitectures=armhf armel'
        output_format = 'format: 2.0\narchitectures:\n - armhf\n - armel\n'
        input_file = self.useFixture(CreateTempFileFixture(ini_format)).\
                                                                get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(output_format, str(converter))

    def test_yes_no_values_conversion(self):
        """Tests that Yes and No values are converted into True and False."""
        ini_format = '[hwpack]\nformat=2.0\nno_value=No\nyes_value=Yes'
        out_format = 'no_value: False\nyes_value: True\nformat: 2.0\n'
        input_file = self.useFixture(CreateTempFileFixture(ini_format)).\
                                                                get_file_name()
        output_file = self.useFixture(CreateTempFileFixture()).get_file_name()
        converter = HwpackConverter(input_file, output_file)
        converter._parse()
        self.assertEqual(out_format, str(converter))

    def test_create_yaml_dictionary_fron_list(self):
        false_dictionary = []
        self.assertRaises(HwpackConverterException, create_yaml_dictionary,
                            false_dictionary)

    def test_create_yaml_dictionary_fron_tuple(self):
        false_dictionary = ()
        self.assertRaises(HwpackConverterException, create_yaml_dictionary,
                            false_dictionary)

    def test_create_yaml_dictionary(self):
        dictionary = {'key1': 'value1', 'key2': 'value2'}
        expected_out = "key2: value2\nkey1: value1\n"
        received_out = create_yaml_dictionary(dictionary)
        self.assertEqual(expected_out, received_out)

    def test_create_yaml_dictionary_with_name(self):
        name = 'dictionary'
        dictionary = {'key1': 'value1', 'key2': 'value2'}
        expected_out = "dictionary:\n key2: value2\n key1: value1\n"
        received_out = create_yaml_dictionary(dictionary, name)
        self.assertEqual(expected_out, received_out)

    def test_create_yaml_sequence_from_dict(self):
        false_list = {}
        name = 'list'
        self.assertRaises(HwpackConverterException, create_yaml_sequence,
                            false_list, name)

    def test_create_yaml_sequence_from_tuple(self):
        false_list = ()
        name = 'list'
        self.assertRaises(HwpackConverterException, create_yaml_sequence,
                            false_list, name)

    def test_create_yaml_sequence(self):
        real_list = ['key1', 'key2']
        name = 'list'
        expected_out = "list:\n - key1\n - key2\n"
        received_out = create_yaml_sequence(real_list, name)
        self.assertEqual(expected_out, received_out)

    def test_create_yaml_string(self):
        key = "key"
        value = "value"
        expected_out = "key: value\n"
        received_out = create_yaml_string(key, value)
        self.assertEqual(expected_out, received_out)

    def test_create_yaml_string_negative(self):
        key = "key"
        value = "value"
        indent = -1
        self.assertRaises(HwpackConverterException, create_yaml_string, key,
                            value, indent)

    def test_create_yaml_string_no_value(self):
        key = "key"
        value = None
        indent = 0
        self.assertRaises(HwpackConverterException, create_yaml_string, key,
                            value, indent)
