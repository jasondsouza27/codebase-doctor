from setuptools import setup, find_packages

setup(
    name="codebase-doctor",
    version="1.0.0",
    description="AI Codebase Doctor: Understand legacy codebases, blast radiuses, risks, and auto-generate tests.",
    packages=find_packages(),
    install_requires=[
        "networkx>=3.0",
        "rich>=13.0",
        "click>=8.0",
        "pytest>=8.0",
        "httpx>=0.25.0",
        "streamlit>=1.30.0",
    ],
    entry_points={
        "console_scripts": [
            "codebase-doctor=codebase_doctor.cli:main",
        ],
    },
    python_requires=">=3.9",
)
