import os
from distutils.errors import CompileError
from setuptools import setup
from subprocess import call
from distutils.command.build import build

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'statsig', 'version.py')) as f:
    exec(f.read())  # pylint: disable=exec-used

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'README.md')) as r:
    README = r.read()

class StatsigBuild(build):
    def run(self):
        clean = [
            'make',
            '-C',
            'statsig/shared/',
            'clean',
        ]

        make = [
            'make',
            '-C',
            'statsig/shared/',
            'install',
        ]
        def compile():
            call(clean)
            out = call(make)
            if out != 0: 
                raise CompileError('Failed to build Statsig shared module.  Do you have Go installed?')

        self.execute(compile, [], 'Building statsig shared module')

        build.run(self)

setup(
    name='statsig',
    version=__version__, # pylint: disable=undefined-variable
    cmdclass={'build': StatsigBuild},
    description='Statsig Python Server SDK',
    long_description=README,
    long_description_content_type="text/markdown",
    author='Tore Hanssen, Jiakan Wang',
    author_email='tore@statsig.com, jkw@statsig.com',
    url='https://github.com/statsig-io/python-sdk',
    license='ISC',
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries'
    ],
    include_package_data=True,
    packages=['statsig']
)