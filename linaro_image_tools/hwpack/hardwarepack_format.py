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

import logging


logger = logging.getLogger(__name__)


class HardwarePackFormat(object):
    def __init__(self):
        self.format_as_string = None
        self.is_deprecated = False
        self.is_supported = False
        self.has_v2_fields = False

    def __str__(self):
        if self.format_as_string is None:
            raise NotImplementedError()
        if self.is_deprecated:
            logger.warning("The format '%s' is deprecated, please update "
                           "your hardware pack configuration." %
                           self.format_as_string)
        return self.format_as_string


class HardwarePackFormatV1(HardwarePackFormat):
    def __init__(self):
        super(HardwarePackFormatV1, self).__init__()
        self.format_as_string = "1.0"
        self.is_supported = True
        self.is_deprecated = True


class HardwarePackFormatV2(HardwarePackFormat):
    def __init__(self):
        super(HardwarePackFormatV2, self).__init__()
        self.format_as_string = "2.0"
        self.is_supported = True
        self.is_deprecated = False
        self.has_v2_fields = True


class HardwarePackFormatV3(HardwarePackFormat):
    def __init__(self):
        super(HardwarePackFormatV3, self).__init__()
        self.format_as_string = "3.0"
        self.is_supported = True
        self.is_deprecated = False
        self.has_v2_fields = True
