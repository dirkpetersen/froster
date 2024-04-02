from setuptools import setup, find_packages

setup(
    name='froster',
    version='0.0.1',
    license='MIT',
    packages=find_packages(),
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
