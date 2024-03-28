import platform
import subprocess

from setuptools import setup, find_packages


def compile_pwalk():

    # Check the user's architecture
    arch = platform.machine()

    # Compile the C tool accordingly
    if arch in ['x86_64', 'amd64']:
        subprocess.check_call(['gcc', '-w', '-pthread', 'filesystem-reporting-tools/pwalk.c',
                              'filesystem-reporting-tools/exclude.c', 'filesystem-reporting-tools/fileProcess.c', '-o', 'pwalk'])

    elif arch in ['arm', 'arm64', 'aarch64']:
        subprocess.check_call(['gcc', '-w', '-pthread', 'filesystem-reporting-tools/pwalk.c', 'filesystem-reporting-tools/exclude.c',
                              'filesystem-reporting-tools/fileProcess.c', '-o', 'pwalk', '-march=armv7-a'])

    # Add more elif statements for other architectures
    else:
        raise Exception('Unsupported architecture')


# compilte pwalk before setup
compile_pwalk()


setup(
    name='froster',
    version='0.0.1',
    license='MIT',
    packages=find_packages(),
    data_files=[('tools', ['pwalk'])],
    install_requires=[
        'duckdb<1.0',
        'textual<0.60',
        'requests<2.40',
        'boto3<1.40',
        'psutil<6.0',
        'visidata',
        'inquirer',
    ],
    entry_points={
        'console_scripts': [
            'froster = froster.froster:main'
        ]
    }
)

# Clean up the compiled C tool
subprocess.check_call(['rm', 'pwalk'])
