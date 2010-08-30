from testtools.matchers import Matcher, Mismatch


class TarfileMissingPathMismatch(Mismatch):

    def __init__(self, tarball, path):
        self.tarball = tarball
        self.path = path

    def describe(self):
        return '"%s" has no path "%s"' % (self.tarball, self.path)


class TarfileWrongTypeMismatch(Mismatch):

    def __init__(self, tarball, path, expected_type, actual_type):
        self.tarball = tarball
        self.path = path
        self.expected_type = expected_type
        self.actual_type = actual_type

    def describe(self):
        return 'The path "%s" in "%s" has type %s, not type %s' % (
            self.path, self.tarball, self.actual_type, self.expected_type)


class TarfileHasFile(Matcher):

    def __init__(self, path, type=None):
        self.path = path
        self.type = type

    def match(self, tarball):
        if self.path not in tarball.getnames():
            return TarfileMissingPathMismatch(tarball, self.path)
        info = tarball.getmember(self.path)
        if self.type is not None:
            if info.type != self.type:
                return TarfileWrongTypeMismatch(
                    tarball, self.path, self.type, info.type)
        return None

    def __str__(self):
        return 'tarfile has file "%s"' % (self.path, )
