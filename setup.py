from setuptools import setup, find_packages
import os

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="nova-architect",
    version="2.0.0",
    description="Build AWS infrastructure from plain English — powered by Amazon Nova",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Nova Architect",
    url="https://github.com/nova-architect/nova-architect",
    license="MIT",
    packages=find_packages(),
    package_data={
        "nova_architect": ["frontend/**/*", "frontend/*", "backend/**/*", "backend/*"],
    },
    include_package_data=True,
    python_requires=">=3.11",
    install_requires=[
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.30.6",
        "python-multipart>=0.0.9",
        "websockets>=12.0",
        "boto3>=1.35.0",
        "botocore>=1.35.0",
        "python-dotenv>=1.0.1",
        "httpx>=0.27.0",
        "pillow>=10.4.0",
        "playwright>=1.54.0,<=1.56.0",
        "rich>=13.0.0",
        "click>=8.0.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "nova-architect=nova_architect.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Build Tools",
    ],
    keywords="aws cloud infrastructure ai bedrock nova automation",
)
