# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2021 Scipp contributors (https://github.com/scipp)
# @author Neil Vaytet

import os
import argparse
import shutil
import subprocess
import multiprocessing
import sys

parser = argparse.ArgumentParser(description='Build C++ library and run tests')
parser.add_argument('--prefix', default='')
parser.add_argument('--source_dir', default='..')
parser.add_argument('--build_dir', default='build')


def run_command(cmd, shell):
    """
    Run a command (supplied as a list) using subprocess.check_call
    """
    os.write(1, "{}\n".format(' '.join(cmd)).encode())
    return subprocess.check_call(cmd, stderr=subprocess.STDOUT, shell=shell)


def main(prefix='', build_dir=''):
    """
    Platform-independent function to run cmake, build, install and C++ tests.
    """

    # Get the platform name: 'linux', 'darwin' (osx), or 'win32'.
    platform = sys.platform

    # Default options
    shell = False
    ncores = str(multiprocessing.cpu_count())
    parallel_flag = '-j'
    build_config = ''

    # Some flags use a syntax with a space separator instead of '='
    use_space = ['-G', '-A']

    # Default cmake flags
    cmake_flags = {
        '-G': 'Ninja',
        '-DPYTHON_EXECUTABLE': shutil.which("python"),
        '-DCMAKE_INSTALL_PREFIX': prefix,
        '-DWITH_CTEST': 'OFF',
        '-DCMAKE_INTERPROCEDURAL_OPTIMIZATION': 'OFF'
    }

    if platform == 'linux':
        cmake_flags.update({'-DCMAKE_INTERPROCEDURAL_OPTIMIZATION': 'ON'})

    if platform == 'darwin':
        osxversion = os.environ.get('OSX_VERSION')
        if osxversion is not None:
            cmake_flags.update({
                '-DCMAKE_OSX_DEPLOYMENT_TARGET':
                osxversion,
                '-DCMAKE_OSX_SYSROOT':
                os.path.join('/Applications', 'Xcode.app', 'Contents',
                             'Developer', 'Platforms', 'MacOSX.platform',
                             'Developer', 'SDKs',
                             'MacOSX{}.sdk'.format(osxversion))
            })

    if platform == 'win32':
        cmake_flags.update({
            '-G': 'Visual Studio 16 2019',
            '-A': 'x64',
            '-DCMAKE_CXX_STANDARD': '20'
        })
        shell = True
        parallel_flag = '-- /m:'
        build_config = 'Release'

    # Additional flags for --build commands
    build_flags = []
    if len(build_config) > 0:
        build_flags += ['--config', build_config]
    build_flags += [parallel_flag + ncores]

    # Parse cmake flags
    flags_list = []
    for key, value in cmake_flags.items():
        if key in use_space:
            flags_list += [key, value]
        else:
            flags_list.append('{}={}'.format(key, value))

    if not os.path.exists(build_dir):
        os.makedirs(build_dir)
    os.chdir(build_dir)

    # Run cmake
    run_command(['cmake'] + flags_list + [args.source_dir], shell=shell)

    # Show cmake settings
    run_command(['cmake', '-B', '.', '-S', '..', '-LA'], shell=shell)

    # Compile benchmarks
    run_command(['cmake', '--build', '.', '--target', 'all-benchmarks'] +
                build_flags,
                shell=shell)

    # Compile C++ tests
    run_command(['cmake', '--build', '.', '--target', 'all-tests'] +
                build_flags,
                shell=shell)

    # Compile Python library
    run_command(['cmake', '--build', '.', '--target', 'install'] + build_flags,
                shell=shell)

    # Run C++ tests
    run_command([os.path.join('bin', build_config, 'scippneutron-test')],
                shell=shell)


if __name__ == '__main__':
    args = parser.parse_args()
    main(prefix=args.prefix, build_dir=args.build_dir)
