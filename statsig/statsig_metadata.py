from platform import python_version
import uuid
from .version import __version__


class _StatsigMetadata:
    @staticmethod
    def get():
        return {
            "sdkVersion": __version__,
            "sdkType": "py-server",
            "languageVersion": python_version(),
            "sessionID": str(uuid.uuid4())
        }
