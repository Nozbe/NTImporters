import pathlib

from setuptools import setup

HERE = pathlib.Path(__file__).parent
README = (HERE / "README.md").read_text()

setup(
    name="ntimporters",
    version="0.1",
    description="Set of migrators to import data from 3rd party apps to Nozbe",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/Nozbe/NTImporters",
    author="jsamelak",
    author_email="jarek@nozbe.com",
    license="MIT",
    install_requires=[
        "python_dateutil",
        "asana<4.0.0",
        "todoist-api-python",
        "todoist-python",
    ],
)
