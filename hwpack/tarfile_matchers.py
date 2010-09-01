from testtools.matchers import Matcher, Mismatch


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

    def __hash__(self):
        return hash((self.tarball, self.path))


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

    def __hash__(self):
        return hash(
            (self.attribute, self.tarball, self.path, self.expected,
             self.actual))


class TarfileHasFile(Matcher):
    """Check that a tarfile has an entry with certain values."""

    def __init__(self, path, type=None, size=None, mtime=None, mode=None,
                 linkname=None, uid=None, gid=None, uname=None, gname=None,
                 content=None):
        """Create a TarfileHasFile Matcher.

        :param path: the path that must be present.
        :type path: str
        :param type: the type of TarInfo that must be at `path`, or None
            to not check.
        :param size: the size that the entry at `path` must have, or None
            to not check.
        :param mtime: the mtime that the entry at `path` must have, or None
            to not check.
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
        """
        self.path = path
        self.type = type
        self.size = size
        self.mtime = mtime
        self.mode = mode
        self.linkname = linkname
        self.uid = uid
        self.gid = gid
        self.uname = uname
        self.gname = gname
        self.content = content

    def match(self, tarball):
        """Match a tarfile.TarFile against the expected values."""
        if self.path not in tarball.getnames():
            return TarfileMissingPathMismatch(tarball, self.path)
        info = tarball.getmember(self.path)
        for attr in (
            "type", "size", "mtime", "mode", "linkname", "uid", "gid",
            "uname", "gname"):
            expected = getattr(self, attr, None)
            if expected is not None:
                actual = getattr(info, attr)
                if expected != actual:
                    return TarfileWrongValueMismatch(
                        attr, tarball, self.path, expected, actual)
        if self.content is not None:
            actual = tarball.extractfile(self.path).read()
            if actual != self.content:
                return TarfileWrongValueMismatch(
                    "content", tarball, self.path, self.content, actual)
        return None

    def __str__(self):
        return 'tarfile has file "%s"' % (self.path, )
