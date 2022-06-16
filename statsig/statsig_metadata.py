from .version import __version__


class _StatsigMetadata:
    @staticmethod
    def get():
        return {
            "sdkVersion": __version__,
            "sdkType": "py-server"
        }
