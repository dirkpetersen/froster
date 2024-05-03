from setuptools import setup, find_packages

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name='froster',
    version='0.10.1',
    license='MIT',
    packages=find_packages(),
    install_requires=[
        'duckdb<1.0',
        'textual<0.60',
        'requests<2.40',
        'boto3<1.40',
        'psutil<6.0',
        'visidata',
        'inquirer'
    ],
    entry_points={
        'console_scripts': [
            'froster = froster.froster:main'
        ]
    },
    long_description=long_description,
    long_description_content_type='text/markdown',
)
