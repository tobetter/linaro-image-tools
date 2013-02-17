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

from linaro_image_tools.hwpack.handler import HardwarepackHandler
from linaro_image_tools.hwpack.hwpack_fields import (
    FORMAT_FIELD,
    NAME_FIELD,
    BOARDS_FIELD,
    BOOTLOADERS_FIELD,
)

from os import linesep as LINE_SEP

# Fields necessary for the string representation of the hardware pack supported
# boards and bootlaoders.
HALF_SEPARATOR = '+--------------------------------------'
ENDING = '+'
SEPARATOR = HALF_SEPARATOR * 2 + ENDING
FORMAT = '{:<80}'
CENTER_ALIGN = '{:^80}'
ELEMENT_FORMAT = '{:<39}| {:<39}'


class HwpackReaderError(Exception):
    """General error raised by HwpackReader."""
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class Hwpack(object):
    """A simple representation of an hardware pack and its value."""
    def __init__(self):
        self._hwpack = None
        self._boards = None
        self._bootloaders = None
        self._name = None

    @property
    def hwpack(self):
        """The hardware pack it refers to."""
        return self._hwpack

    def sethwpack(self, value):
        """Sets the hwpack field."""
        self._hwpack = value

    @property
    def boards(self):
        """The boards field of this hardware pack."""
        return self._boards

    def setboards(self, value):
        """Sets the boards field."""
        self._boards = value

    @property
    def name(self):
        """The name field of this hardware pack."""
        return self._name

    def setname(self, value):
        """Sets the name field."""
        self._name = value

    @property
    def bootloaders(self):
        """The bootlaoders field of this hardware pack."""
        return self._bootloaders

    def setbootloaders(self, value):
        """Sets the bootlaoders field."""
        self._bootloaders = value

    def __eq__(self, other):
        """Equality method."""
        equal = False
        if isinstance(other, Hwpack):
            equal = (self.name == other.name and
                     self.boards == other.boards and
                     self.hwpack == other.hwpack and
                     self.bootloaders == other.bootloaders)
        return equal

    def __hash__(self):
        return hash(frozenset(self.bootloaders), frozenset(self.boards),
                    self.name, self.hwpack)

    def __str__(self):
        """String representation of this hwapack supported elements."""
        string = FORMAT.format("Read hardware pack: %s" % self.hwpack)
        string += LINE_SEP
        string += FORMAT.format(SEPARATOR)
        string += LINE_SEP
        string += ELEMENT_FORMAT.format("Supported boards",
                                        "Supported bootloaders")
        string += LINE_SEP
        string += FORMAT.format(SEPARATOR)
        string += LINE_SEP

        if self.boards:
            for key, value in self.boards.iteritems():
                if value.get(BOOTLOADERS_FIELD, None) is not None:
                    bootloaders = value.get(BOOTLOADERS_FIELD)
                    supported_bootloaders = bootloaders.keys()
                else:
                    supported_bootloaders = self.bootloaders.keys()
                string += ELEMENT_FORMAT.format(
                    key, ",".join(supported_bootloaders))
                string += LINE_SEP
        else:
            # If we pass a converted file with just a single board, we do not
            # have the boards section, and we default to the name of the hwpack
            if self.bootloaders:
                supported_bootloaders = self.bootloaders.keys()
                string += ELEMENT_FORMAT.format(
                    self.name, ",".join(supported_bootloaders))
                string += LINE_SEP
            else:
                string += CENTER_ALIGN.format("No supported boards and "
                                              "bootloaders")
                string += LINE_SEP
        string += FORMAT.format(SEPARATOR)
        return string + LINE_SEP


class HwpackReader(object):
    """Reads the information contained in a hwpack """
    def __init__(self, hwpacks):
        """Create a new instance.

        :param hwpacks: The list of hardware packs to read from."""
        self.hwpacks = hwpacks
        # Where we store all the info from the hwpack.
        self._supported_elements = []

    @property
    def supported_elements(self):
        """Gets the supported elements of by all the hardwapare packs."""
        return self._supported_elements

    def _read_hwpacks_metadata(self):
        """Reads the hardware pack metadata file, and prints information about
        the supported boards and bootloaders."""
        for tarball in self.hwpacks:
            with HardwarepackHandler([tarball]) as handler:
                hwpack_format = handler.get_field(FORMAT_FIELD)[0]
                if hwpack_format.format_as_string == "3.0":
                    local_hwpack = Hwpack()
                    local_hwpack.sethwpack(tarball)
                    local_hwpack.setname(handler.get_field(NAME_FIELD)[0])
                    local_hwpack.setboards(handler.get_field(BOARDS_FIELD)[0])
                    local_hwpack.setbootloaders(
                        handler.get_field(BOOTLOADERS_FIELD)[0])
                    self.supported_elements.append(local_hwpack)
                else:
                    raise HwpackReaderError("Hardwarepack '%s' cannot be "
                                            "read, unsupported format." %
                                            (tarball))

    def get_supported_boards(self):
        """Prints the necessary information.

        :return A string representation of the information."""
        self._read_hwpacks_metadata()
        return str(self)

    def __str__(self):
        """The string representation of this reader. It is a printable
        representation of the necessary information."""
        hwpack_reader = ""
        for element in self.supported_elements:
            hwpack_reader += str(element)
        return hwpack_reader
