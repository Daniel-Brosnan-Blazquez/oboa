"""
Setup configuration for the oboa application.
"""

from setuptools import find_packages, setup


setup(
    name="oboa",
    version="0.1.0",
    description="Orchestrator for Business Operations Analysis",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "oboa.config": ["*.json", "*.xml"],
        "oboa.datamodel": ["*.dbm", "*.sql"],
        "oboa.schemas": ["*.xsd"],
        "oboa.scripts": ["*.sh"],
    },
    python_requires=">=3",
    install_requires=[
        "aboa==0.1.0",
        "sqlalchemy==1.3.22",
        "psycopg2-binary==2.9.11",
        "python-dateutil==2.9.0.post0",
        "lxml==6.0.2",
    ],
    extras_require={
        "tests": [
            "pytest==8.4.2",
            "pytest-cov==7.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "oboa_init.py=oboa.scripts.oboa_init:main",
            "oboa_configure.py=oboa.scripts.oboa_configure:main",
            "oboa_orchestrate.py=oboa.scripts.oboa_orchestrate:main",
            "oboa_poll.py=oboa.scripts.oboa_poll:main",
            "oboa_daemon.py=oboa.scripts.oboa_daemon:main",
            "oboa_query.py=oboa.scripts.oboa_query:main",
        ]
    },
)
