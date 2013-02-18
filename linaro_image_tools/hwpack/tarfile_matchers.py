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

import tarfile

from testtools.matchers import Annotate, Equals, Matcher, Mismatch


class TarfileMissingPathMismatch(Mismatch):
    """A Mismatch indicating that a required path was missing from a tarfile.
    """

    def __init__(self, tarball, path):
        """Create a TarfileMissingPathMismatch Mismatch.

        :param tarball: the tarfile that was checked.
        :param path: the path that was expected to be present.
        """
        self.tarball = tarball
        self.path = path

    def describe(self):
        return '"%s" has no path "%s"' % (self.tarball, self.path)

    def __eq__(self, other):
        return self.tarball == other.tarball and self.path == other.path

    def __ne__(self, other):
        return not self.__eq__(other)


class TarfileWrongValueMismatch(Mismatch):
    """A Mismatch indicating that an entry in a tarfile was not as expected.
    """

    def __init__(self, attribute, tarball, path, expected, actual):
        """Create a TarfileWrongValueMismatch Mismatch.

        :param attribute: the attribute that was not as expected.
        :type attribute: str
        :param tarball: the tarfile that was checked.
        :param path: the path that was checked.
        :param expected: the expected value of the attribute.
        :param actual: the value that was found.
        """
        self.attribute = attribute
        self.tarball = tarball
        self.path = path
        self.expected = expected
        self.actual = actual

    def describe(self):
        return 'The path "%s" in "%s" has %s %s, expected %s' % (
            self.path, self.tarball, self.attribute, self.actual,
            self.expected)

    def __eq__(self, other):
        return (self.attribute == other.attribute
                and self.tarball == other.tarball
                and self.path == other.path
                and self.expected == other.expected
                and self.actual == other.actual)

    def __ne__(self, other):
        return not self.__eq__(other)


class TarfileHasFile(Matcher):
    """Check that a tarfile has an entry with certain values."""

    def __init__(self, path, type=None, size=None, mtime=None,
                 mtime_skew=None, mode=None, linkname=None, uid=None,
                 gid=None, uname=None, gname=None, content=None,
                 content_matcher=None):
        """Create a TarfileHasFile Matcher.

        :param path: the path that must be present.
        :type path: str
        :param type: the type of TarInfo that must be at `path`, or None
            to not check.
        :param size: the size that the entry at `path` must have, or None
            to not check.
        :param mtime: the mtime that the entry at `path` must have, or None
            to not check.
        :param mtime_skew: the number of seconds that the file mtime can
            be different to the required.
        :param mode: the mode that the entry at `path` must have, or None
            to not check.
        :param linkname: the linkname that the entry at `path` must have,
            or None to not check.
        :param uid: the user id that the entry at `path` must have, or None
            to not check.
        :param gid: the group id that the entry at `path` must have, or None
            to not check.
        :param uname: the username that the entry at `path` must have, or
            None to not check.
        :param gname: the group name that the entry at `path` must have, or
            None to not check.
        :param content: the content that `path` must have when extracted,
            or None to not check.
        :param content_matcher: a matcher to match the content that `path` has
            when extracted, or None to not check.  You can't specify both
            content_matcher and content.
        """
        self.path = path
        self.type = type
        self.size = size
        self.mtime = mtime
        self.mtime_skew = mtime_skew
        self.mode = mode
        self.linkname = linkname
        self.uid = uid
        self.gid = gid
        self.uname = uname
        self.gname = gname
        if content is not None:
            if content_matcher is not None:
                raise ValueError(
                    "doesn't make sense to specify content and "
                    "content_matcher")
            content_matcher = Equals(content)
        if content_matcher is not None:
            self.content_matcher = Annotate(
                'The content of path "%s" did not match' % path,
                content_matcher)
        else:
            self.content_matcher = None

    def match(self, tarball):
        """Match a tarfile.TarFile against the expected values."""
        if self.path not in tarball.getnames():
            return TarfileMissingPathMismatch(tarball, self.path)
        info = tarball.getmember(self.path)
        for attr in ("type", "size", "mode", "linkname",
                     "uid", "gid", "uname", "gname"):
            expected = getattr(self, attr, None)
            if expected is not None:
                actual = getattr(info, attr)
                if expected != actual:
                    return TarfileWrongValueMismatch(
                        attr, tarball, self.path, expected, actual)
        if self.mtime is not None:
            mtime_skew = self.mtime_skew or 0
            if abs(self.mtime - info.mtime) > mtime_skew:
                return TarfileWrongValueMismatch(
                    "mtime", tarball, self.path, self.mtime, info.mtime)
        if self.content_matcher is not None:
            if info.type == tarfile.DIRTYPE:
                contents = []
                path_frags = self.path.split('/')
                for name in tarball.getnames():
                    name_frags = name.split('/')
                    if (len(name_frags) == len(path_frags) + 1 and
                            name_frags[:-1] == path_frags):
                        contents.append(name_frags[-1])
                content_mismatch = self.content_matcher.match(contents)
                if content_mismatch:
                    return content_mismatch
            else:
                actual = tarball.extractfile(self.path).read()
                content_mismatch = self.content_matcher.match(actual)
                if content_mismatch:
                    return content_mismatch
        return None

    def __str__(self):
        return 'tarfile has file "%s"' % (self.path, )
