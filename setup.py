__author__ = 'Igor Fernandes (Igorxp5)'
__email__ = 'rogixp5@gmail.com'
__copyright__ = 'Copyright 2019, Igor Fernandes'

__license__ = 'MIT'
__version__ = '1.0.5'


import setuptools

with open('README.md', 'r', encoding='utf-8') as fh:
    long_description = fh.read()

print(long_description)

setuptools.setup(
    name='window-terminal',
    version=__version__,
    author=__author__,
    author_email=__email__,
    description='Start new Terminal Windows with print and input control',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/Igorxp5/window-terminal',
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)