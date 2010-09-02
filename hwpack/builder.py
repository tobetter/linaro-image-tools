from hwpack.config import Config
from hwpack.hardwarepack import HardwarePack, Metadata
from hwpack.packages import PackageFetcher


class HardwarePackBuilder(object):

    def __init__(self, config_path, version):
        with open(config_path) as fp:
            self.config = Config(fp)
        self.config.validate()
        self.version = version

    def build(self):
        for architecture in self.config.architectures:
            metadata = Metadata.from_config(
                self.config, self.version, architecture)
            hwpack = HardwarePack(metadata)
            sources = self.config.sources
            hwpack.add_sources(sources)
            fetcher = PackageFetcher(
                sources.values(), architecture=architecture)
            with fetcher:
                packages = fetcher.fetch_packages(self.config.packages)
                hwpack.add_packages(packages)
                with open(hwpack.filename(), 'w') as f:
                    hwpack.to_file(f)
