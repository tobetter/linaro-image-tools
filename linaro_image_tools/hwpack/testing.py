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

from contextlib import contextmanager
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from StringIO import StringIO
import tarfile
import time

from debian.deb822 import Packages

from testtools.matchers import Annotate, Equals, Matcher, Mismatch

from linaro_image_tools.hwpack.better_tarfile import writeable_tarfile
from linaro_image_tools.hwpack.tarfile_matchers import TarfileHasFile
from linaro_image_tools.hwpack.packages import (
    get_packages_file,
    FetchedPackage,
)


@contextmanager
def test_tarfile(contents=[], **kwargs):
    """Create a tarfile with the given contents, then re-open it for reading.

    This context manager creates a tarfile with the given contents, then
    reopens it for reading and yields it for use in a with block. When
    the block ends the tarfile will be closed.

    The contents can be specified as a list of tuples of (path, contents),
    where if the path ends with '/' it is considered to be a directory and
    the contents ignored.

    :param contents: the contents to put in the tarball, defaults to the
        empty list.
    :type contents: a list of tuples of (str, str)
    :param kwargs: keyword arguments for the better_tarfile.TarFile
        constructor.
    """
    backing_file = StringIO()
    with writeable_tarfile(backing_file, **kwargs) as tf:
        for path, content in contents:
            if path[-1] == "/":
                tf.create_dir(path)
            else:
                tf.create_file_from_string(path, content)
    if contents:
        backing_file.seek(0)
    tf = tarfile.TarFile.open(mode="r", fileobj=backing_file)
    try:
        yield tf
    finally:
        tf.close()


class DummyFetchedPackage(FetchedPackage):
    """A FetchedPackage with dummy information.

    See FetchedPackage for the instance variables.
    """

    def __init__(self, name, version, architecture="all", depends=None,
                 pre_depends=None, multi_arch=None, conflicts=None,
                 recommends=None, provides=None, replaces=None, breaks=None,
                 no_content=False, content=None):
        self.name = name
        self.version = version
        self.architecture = architecture
        self.depends = depends
        self.pre_depends = pre_depends
        self.multi_arch = multi_arch
        self.conflicts = conflicts
        self.recommends = recommends
        self.provides = provides
        self.replaces = replaces
        self.breaks = breaks
        self._no_content = no_content
        self._content = content
        self._file_path = None

    @property
    def filename(self):
        return "%s_%s_all.deb" % (self.name, self.version)

    def _content_str(self):
        return "Content of %s" % self.filename

    @property
    def content(self):
        if self._no_content:
            return None
        elif self._content is not None:
            return StringIO(self._content)
        return StringIO(self._content_str())

    @property
    def size(self):
        return len(self.content.read())

    @property
    def md5(self):
        md5sum = hashlib.md5()
        md5sum.update(self.content.read())
        return md5sum.hexdigest()


class AptSourceFixture(object):
    """A fixture that provides an apt source, with packages and indices.

    An apt source provides a set of package files, and a Packages file
    that allows apt to determine the contents of the source.

    :ivar sources_entry: the URI and suite to give to apt to view the
        source (i.e. a sources.list line without the "deb" prefix
    :type sources_entry: str
    """

    def __init__(self, packages, label=None):
        """Create an AptSourceFixture.

        :param packages: a list of packages to add to the source
            and index.
        :type packages: an iterable of FetchedPackages
        """
        self.packages = packages
        self.label = label

    def setUp(self):
        self.rootdir = tempfile.mkdtemp(prefix="hwpack-apt-source-")
        for package in self.packages:
            with open(os.path.join(self.rootdir, package.filename), 'wb') as f:
                f.write(package.content.read())
        with open(os.path.join(self.rootdir, "Packages"), 'wb') as f:
            f.write(get_packages_file(self.packages))
        if self.label is not None:
            subprocess.check_call(
                ['apt-ftparchive',
                 '-oAPT::FTPArchive::Release::Label=%s' % self.label,
                 'release',
                 self.rootdir],
                stdout=open(os.path.join(self.rootdir, 'Release'), 'w'))

    def tearDown(self):
        if os.path.exists(self.rootdir):
            shutil.rmtree(self.rootdir)

    @property
    def sources_entry(self):
        return "file:" + os.path.abspath(self.rootdir) + " ./"


class ConfigFileFixture(object):

    def __init__(self, contents):
        self.contents = contents
        self.filename = None

    def setUp(self):
        fh, self.filename = tempfile.mkstemp(prefix="hwpack-test-config-")
        with os.fdopen(fh, 'w') as f:
            f.write(self.contents)

    def tearDown(self):
        if self.filename is not None and os.path.exists(self.filename):
            os.unlink(self.filename)


class ContextManagerFixture(object):
    """Adapt a context manager to be a usable with `useFixture`."""

    def __init__(self, context_manager):
        self.manager = context_manager

    def setUp(self):
        self.manager.__enter__()

    def tearDown(self):
        # It might be nice to pass exc_type, exc_value, traceback in here in
        # the failure case, if that's possible.
        self.manager.__exit__(None, None, None)


class ChdirToTempdirFixture(object):

    def __init__(self):
        self._orig_dir = None
        self.tempdir = None

    def setUp(self):
        self.tearDown()
        self._orig_dir = os.getcwd()
        self.tempdir = tempfile.mkdtemp(prefix="hwpack-tests-")
        os.chdir(self.tempdir)

    def tearDown(self):
        if self._orig_dir is not None:
            os.chdir(self._orig_dir)
            self._orig_dir = None
        if self.tempdir is not None and os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)
            self.tempdir = None


class MismatchesAll(Mismatch):
    """A mismatch with many child mismatches."""

    def __init__(self, mismatches):
        self.mismatches = mismatches

    def describe(self):
        descriptions = ["Differences: ["]
        for mismatch in self.mismatches:
            descriptions.append(mismatch.describe())
        descriptions.append("]\n")
        return '\n'.join(descriptions)


class MatchesAll(object):

    def __init__(self, *matchers):
        self.matchers = matchers

    def __str__(self):
        return 'MatchesAll(%s)' % ', '.join(map(str, self.matchers))

    def match(self, matchee):
        results = []
        for matcher in self.matchers:
            mismatch = matcher.match(matchee)
            if mismatch is not None:
                results.append(mismatch)
        if results:
            return MismatchesAll(results)
        else:
            return None


class Not:
    """Inverts a matcher."""

    def __init__(self, matcher):
        self.matcher = matcher

    def __str__(self):
        return 'Not(%s)' % (self.matcher,)

    def match(self, other):
        mismatch = self.matcher.match(other)
        if mismatch is None:
            return MatchedUnexpectedly(self.matcher, other)
        else:
            return None


class MatchedUnexpectedly:
    """A thing matched when it wasn't supposed to."""

    def __init__(self, matcher, other):
        self.matcher = matcher
        self.other = other

    def describe(self):
        return "%r matches %s" % (self.other, self.matcher)


class HardwarePackHasFile(TarfileHasFile):
    """A subclass of TarfileHasFile specific to hardware packs.

    We default to a set of attributes expected for files in a hardware
    pack.
    """

    def __init__(self, path, **kwargs):
        """Create a HardwarePackHasFile matcher.

        The kwargs are the keyword arguments taken by TarfileHasFile.
        If they are not given then defaults will be checked:
            - The type should be a regular file
            - If the content is given then the size will be checked
                to ensure it indicates the length of the content
                correctly.
            - the mode is appropriate for the type. If the type is
                regular file this is 0644, otherwise if it is
                a directory then it is 0755.
            - the linkname should be the empty string.
            - the uid and gid should be 1000
            - the uname and gname should be "user" and "group"
                respectively.

        :param path: the path that should be present.
        :type path: str
        """
        kwargs.setdefault("type", tarfile.REGTYPE)
        if "content" in kwargs and kwargs['type'] != tarfile.DIRTYPE:
            kwargs.setdefault("size", len(kwargs["content"]))
        if kwargs["type"] == tarfile.DIRTYPE:
            kwargs.setdefault("mode", 0755)
        else:
            kwargs.setdefault("mode", 0644)
        kwargs.setdefault("linkname", "")
        kwargs.setdefault("uid", 1000)
        kwargs.setdefault("gid", 1000)
        kwargs.setdefault("uname", "user")
        kwargs.setdefault("gname", "group")
        kwargs.setdefault("mtime", time.time())
        # Enough that it won't fail if the test is slow to execute, but
        #  not enough that we can have a wildly wrong timestamp.
        kwargs.setdefault("mtime_skew", 100)
        super(HardwarePackHasFile, self).__init__(path, **kwargs)


class IsHardwarePack(Matcher):

    def __init__(self, metadata, packages, sources,
                 packages_without_content=None,
                 package_spec=None, format="1.0"):
        self.metadata = metadata
        self.packages = packages
        self.sources = sources
        self.packages_without_content = packages_without_content or []
        self.package_spec = package_spec
        self.format = format + "\n"

    def match(self, path):
        with tarfile.open(name=path, mode="r:gz") as tf:
            matchers = []
            matchers.append(HardwarePackHasFile("FORMAT", content=self.format))
            matchers.append(HardwarePackHasFile(
                "metadata", content=str(self.metadata)))
            manifest_lines = []
            for package in self.packages:
                manifest_lines.append(
                    "%s=%s" % (package.name, package.version))
            manifest_lines.append(
                "%s=%s" % (
                    'hwpack-' + self.metadata.name, self.metadata.version))
            matchers.append(
                HardwarePackHasFile(
                    "manifest",
                    content_matcher=AfterPreproccessing(
                        str.splitlines,
                        MatchesSetwise(*map(Equals, manifest_lines)))))
            matchers.append(HardwarePackHasFile("pkgs", type=tarfile.DIRTYPE))
            packages_with_content = [p for p in self.packages
                                     if p not in self.packages_without_content]
            for package in packages_with_content:
                matchers.append(HardwarePackHasFile(
                    "pkgs/%s" % package.filename,
                    content=package.content.read()))
            package_matchers = [
                MatchesPackage(p) for p in packages_with_content]
            dep_package_matcher = MatchesStructure(
                name=Equals('hwpack-' + self.metadata.name),
                version=Equals(self.metadata.version),
                architecture=Equals(self.metadata.architecture),
                filename=Equals('hwpack-%s_%s_%s.deb' % (
                    self.metadata.name, self.metadata.version,
                    self.metadata.architecture)))
            if self.package_spec:
                dep_package_matcher = dep_package_matcher.update(
                    depends=MatchesPackageRelationshipList(
                        [Equals(p.strip())
                         for p in self.package_spec.split(',')]))
            package_matchers.append(dep_package_matcher)
            matchers.append(HardwarePackHasFile(
                "pkgs/Packages",
                content_matcher=MatchesAsPackagesFile(
                    *package_matchers)))
            matchers.append(HardwarePackHasFile(
                "sources.list.d", type=tarfile.DIRTYPE))
            for source_id, sources_entry in self.sources.items():
                matchers.append(HardwarePackHasFile(
                    "sources.list.d/%s.list" % source_id,
                    content="deb " + sources_entry + "\n"))
            matchers.append(HardwarePackHasFile(
                "sources.list.d.gpg", type=tarfile.DIRTYPE))
            return MatchesAll(*matchers).match(tf)

    def __str__(self):
        return "Is a valid hardware pack."


class EachOf(object):
    """Matches if each matcher matches the corresponding value.

    More easily explained by example than in words:

    >>> EachOf([Equals(1)]).match([1])
    >>> EachOf([Equals(1), Equals(2)]).match([1, 2])
    >>> EachOf([Equals(1), Equals(2)]).match([2, 1]) #doctest: +ELLIPSIS
    <...Mismatch...>
    """

    def __init__(self, matchers):
        self.matchers = matchers

    def match(self, values):
        mismatches = []
        length_mismatch = Annotate(
            "Length mismatch", Equals(len(self.matchers))).match(len(values))
        if length_mismatch:
            mismatches.append(length_mismatch)
        for matcher, value in zip(self.matchers, values):
            mismatch = matcher.match(value)
            if mismatch:
                mismatches.append(mismatch)
        if mismatches:
            return MismatchesAll(mismatches)


class MatchesStructure(object):
    """Matcher that matches an object structurally.

    'Structurally' here means that attributes of the object being matched are
    compared against given matchers.

    `fromExample` allows the creation of a matcher from a prototype object and
    then modified versions can be created with `update`.
    """

    def __init__(self, **kwargs):
        self.kws = kwargs

    @classmethod
    def fromExample(cls, example, *attributes):
        kwargs = {}
        for attr in attributes:
            kwargs[attr] = Equals(getattr(example, attr))
        return cls(**kwargs)

    def update(self, **kws):
        new_kws = self.kws.copy()
        for attr, matcher in kws.iteritems():
            if matcher is None:
                new_kws.pop(attr, None)
            else:
                new_kws[attr] = matcher
        return type(self)(**new_kws)

    def match(self, value):
        matchers = []
        values = []
        for attr, matcher in self.kws.iteritems():
            matchers.append(Annotate(attr, matcher))
            values.append(getattr(value, attr))
        return EachOf(matchers).match(values)


def MatchesPackage(example):
    """Create a `MatchesStructure` object from a `FetchedPackage`."""
    return MatchesStructure.fromExample(
        example, *example._equality_attributes)


class MatchesSetwise(object):
    """Matches if all the matchers match elements of the value being matched.

    The difference compared to `EachOf` is that the order of the matchings
    does not matter.
    """

    def __init__(self, *matchers):
        self.matchers = matchers

    def match(self, observed):
        remaining_matchers = set(self.matchers)
        not_matched = []
        for value in observed:
            for matcher in remaining_matchers:
                if matcher.match(value) is None:
                    remaining_matchers.remove(matcher)
                    break
            else:
                not_matched.append(value)
        if not_matched or remaining_matchers:
            remaining_matchers = list(remaining_matchers)
            # There are various cases that all should be reported somewhat
            # differently.

            # There are two trivial cases:
            # 1) There are just some matchers left over.
            # 2) There are just some values left over.

            # Then there are three more interesting cases:
            # 3) There are the same number of matchers and values left over.
            # 4) There are more matchers left over than values.
            # 5) There are more values left over than matchers.

            if len(not_matched) == 0:
                if len(remaining_matchers) > 1:
                    msg = "There were %s matchers left over: " % (
                        len(remaining_matchers),)
                else:
                    msg = "There was 1 matcher left over: "
                msg += ', '.join(map(str, remaining_matchers))
                return Mismatch(msg)
            elif len(remaining_matchers) == 0:
                if len(not_matched) > 1:
                    return Mismatch(
                        "There were %s values left over: %s" % (
                            len(not_matched), not_matched))
                else:
                    return Mismatch(
                        "There was 1 value left over: %s" % (
                            not_matched, ))
            else:
                common_length = min(len(remaining_matchers), len(not_matched))
                if common_length == 0:
                    raise AssertionError("common_length can't be 0 here")
                if common_length > 1:
                    msg = "There were %s mismatches" % (common_length,)
                else:
                    msg = "There was 1 mismatch"
                if len(remaining_matchers) > len(not_matched):
                    extra_matchers = remaining_matchers[common_length:]
                    msg += " and %s extra matcher" % (len(extra_matchers), )
                    if len(extra_matchers) > 1:
                        msg += "s"
                    msg += ': ' + ', '.join(map(str, extra_matchers))
                elif len(not_matched) > len(remaining_matchers):
                    extra_values = not_matched[common_length:]
                    msg += " and %s extra value" % (len(extra_values), )
                    if len(extra_values) > 1:
                        msg += "s"
                    msg += ': ' + str(extra_values)
                return Annotate(
                    msg, EachOf(remaining_matchers[:common_length])
                ).match(not_matched[:common_length])


def parse_packages_file_content(file_content):
    packages = []
    for para in Packages.iter_paragraphs(StringIO(file_content)):
        args = {}
        for key, value in para.iteritems():
            key = key.lower()
            if key == 'md5sum':
                key = 'md5'
            elif key == 'package':
                key = 'name'
            elif key == 'size':
                value = int(value)
            if key in FetchedPackage._equality_attributes:
                args[key] = value
        packages.append(FetchedPackage(**args))
    return packages


class AfterPreproccessing(object):
    """Matches if the value matches after passing through a function."""

    def __init__(self, preprocessor, matcher):
        self.preprocessor = preprocessor
        self.matcher = matcher

    def __str__(self):
        return "AfterPreproccessing(%s, %s)" % (
            self.preprocessor, self.matcher)

    def match(self, value):
        value = self.preprocessor(value)
        return self.matcher.match(value)


def MatchesAsPackagesFile(*package_matchers):
    """Matches the contents of a Packages file against the given matchers.

    The contents of the Packages file is turned into a list of FetchedPackages
    using `parse_packages_file_content` above.
    """
    return AfterPreproccessing(
        parse_packages_file_content, MatchesSetwise(*package_matchers))


def MatchesAsPackageContent(package_matcher):
    """Match a package on disk against `package_matcher`."""

    def load_from_disk(content):
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, content)
            os.close(fd)
            return FetchedPackage.from_deb(path)
        finally:
            os.remove(path)
    return AfterPreproccessing(load_from_disk, package_matcher)


class DoesNotStartWith(Mismatch):

    def __init__(self, matchee, expected):
        """Create a DoesNotStartWith Mismatch.

        :param matchee: the string that did not match.
        :param expected: the string that `matchee` was expected to start
            with.
        """
        self.matchee = matchee
        self.expected = expected

    def describe(self):
        return "'%s' does not start with '%s'." % (
            self.matchee, self.expected)


class StartsWith(Matcher):
    """Checks whether one string starts with another."""

    def __init__(self, expected):
        """Create a StartsWith Matcher.

        :param expected: the string that matchees should start with.
        """
        self.expected = expected

    def __str__(self):
        return "Starts with '%s'." % self.expected

    def match(self, matchee):
        if not matchee.startswith(self.expected):
            return DoesNotStartWith(matchee, self.expected)
        return None


def MatchesPackageRelationshipList(relationship_matchers):
    """Matches a set of matchers against a package relationship specification.

    >>> MatchesPackageRelationshipList(
    ...     [Equals('foo'), StartsWith('bar (')]).match('bar (= 1.0), foo')
    >>>
    """
    def process(relationships):
        if relationships is None:
            return []
        return [rel.strip() for rel in relationships.split(',')]
    return AfterPreproccessing(
        process, MatchesSetwise(*relationship_matchers))


class AppendingHandler(logging.Handler):
    """A logging handler that simply appends messages to a list."""

    def __init__(self):
        logging.Handler.__init__(self)
        self.messages = []

    def emit(self, message):
        self.messages.append(message)
