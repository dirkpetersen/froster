from setuptools import setup, find_packages

with open('README.md', 'r') as f:
    long_description = f.read()

with open('requirements.txt') as f:
    requirements = f.read().splitlines()


setup(
    name='froster',
    version='0.10.4',
    license='MIT',
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'froster = froster.froster:main'
        ]
    },
    long_description=long_description,
    long_description_content_type='text/markdown',
)
