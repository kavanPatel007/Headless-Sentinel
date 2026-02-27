"""
Headless Sentinel - Setup Script
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / 'README.md'
long_description = readme_file.read_text(encoding='utf-8') if readme_file.exists() else ''

setup(
    name='headless-sentinel',
    version='1.0.0',
    description='Lightweight CLI-driven log aggregator for Windows environments',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Your Organization',
    author_email='security@yourcompany.com',
    url='https://github.com/yourorg/headless-sentinel',
    license='MIT',
    
    packages=find_packages(exclude=['tests', 'tests.*']),
    
    install_requires=[
        'pywinrm>=0.4.3',
        'duckdb>=0.9.2',
        'pandas>=2.0.0',
        'pyyaml>=6.0',
        'keyring>=24.0.0',
        'click>=8.1.0',
        'rich>=13.0.0',
        'aiohttp>=3.9.0',
        'python-dateutil>=2.8.2',
        'requests>=2.31.0',
        'cryptography>=41.0.0',
    ],
    
    extras_require={
        'dev': [
            'pytest>=7.4.0',
            'pytest-asyncio>=0.21.0',
            'black>=23.0.0',
            'flake8>=6.0.0',
            'mypy>=1.5.0',
        ]
    },
    
    entry_points={
        'console_scripts': [
            'sentinel=main:cli',
        ],
    },
    
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Information Technology',
        'License :: OSI Approved :: MIT License',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: System :: Monitoring',
        'Topic :: System :: Logging',
        'Topic :: Security',
    ],
    
    python_requires='>=3.8',
    
    keywords='windows logs siem security monitoring winrm eventlog',
    
    project_urls={
        'Bug Reports': 'https://github.com/yourorg/headless-sentinel/issues',
        'Source': 'https://github.com/yourorg/headless-sentinel',
        'Documentation': 'https://docs.yourcompany.com/sentinel',
    },
)
