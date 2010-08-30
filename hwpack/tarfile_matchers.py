from testtools.matchers import Matcher, Mismatch


class TarfileMissingPathMismatch(Mismatch):

    def __init__(self, tarball, path):
        self.tarball = tarball
        self.path = path

    def describe(self):
        return '"%s" has no path "%s"' % (self.tarball, self.path)


class TarfileWrongValueMismatch(Mismatch):

    def __init__(self, attribute, tarball, path, expected, actual):
        self.attribute = attribute
        self.tarball = tarball
        self.path = path
        self.expected = expected
        self.actual = actual

    def describe(self):
        return 'The path "%s" in "%s" has %s %s, expected %s' % (
            self.path, self.tarball, self.attribute, self.actual,
            self.expected)


class TarfileHasFile(Matcher):

    def __init__(self, path, type=None, size=None, mtime=None, mode=None,
                 linkname=None, uid=None, gid=None, uname=None, gname=None,
                 content=None):
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
