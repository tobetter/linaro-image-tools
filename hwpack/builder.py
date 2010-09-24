import errno

from hwpack.config import Config
from hwpack.hardwarepack import HardwarePack, Metadata
from hwpack.packages import PackageFetcher


class ConfigFileMissing(Exception):

    def __init__(self, filename):
        self.filename = filename
        super(ConfigFileMissing, self).__init__(
            "No such config file: '%s'" % self.filename)


class HardwarePackBuilder(object):

    def __init__(self, config_path, version):
        try:
            with open(config_path) as fp:
                self.config = Config(fp)
        except IOError, e:
            if e.errno == errno.ENOENT:
                raise ConfigFileMissing(config_path)
            raise
        self.config.validate()
        self.version = version

    def build(self):
        for architecture in self.config.architectures:
            metadata = Metadata.from_config(
                self.config, self.version, architecture)
            hwpack = HardwarePack(metadata)
            sources = self.config.sources
            hwpack.add_apt_sources(sources)
            fetcher = PackageFetcher(
                sources.values(), architecture=architecture)
            with fetcher:
                fetcher.ignore_packages(self.config.assume_installed)
                packages = fetcher.fetch_packages(
                    self.config.packages,
                    download_content=self.config.include_debs)
                hwpack.add_packages(packages)
                with open(hwpack.filename(), 'w') as f:
                    hwpack.to_file(f)
