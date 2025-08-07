import os

from setuptools import setup, find_packages

with open(
    os.path.join(os.path.abspath(os.path.dirname(__file__)), "statsig", "version.py"),
    encoding="utf-8",
) as f:
    exec(f.read())

with open(
    os.path.join(os.path.abspath(os.path.dirname(__file__)), "README.md"),
    encoding="utf-8",
) as r:
    README = r.read()

test_deps = ["requests", "user_agents", "semver"]
extras = {
    "test": test_deps,
}

setup(
    name="statsig",
    # pylint: disable=undefined-variable
    version=__version__,  # type: ignore
    description="Statsig Python Server SDK",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Tore Hanssen, Jiakan Wang",
    author_email="tore@statsig.com, jkw@statsig.com",
    url="https://github.com/statsig-io/python-sdk",
    license="ISC",
    classifiers=[
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries",
    ],
    install_requires=[
        "requests",
        "ua_parser",
        "ip3country",
        "grpcio",
        "protobuf",
        "ijson",
        "typing-extensions",
        "brotli",
    ],
    tests_require=test_deps,
    extras_require=extras,
    include_package_data=True,
    packages=find_packages(
        include=["statsig", "statsig.grpc", "statsig.grpc.generated"]
    ),
    python_requires=">=3.7",
)
