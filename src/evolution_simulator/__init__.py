"""Evolution simulator."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("evolution-simulator")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0.0.0"
