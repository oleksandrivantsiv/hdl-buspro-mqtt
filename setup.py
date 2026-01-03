from setuptools import setup

setup(
    name="hdl-buspro-mqtt",
    version="0.1.0",
    description="HDL Buspro to MQTT bridge",
    author="Oleksandr Ivantsiv",
    author_email="",
    py_modules=[
        "hdl_component",
        "hdl_ctl",
        "hdl_listener",
        "hdl_packets",
        "mqtt_client",
        "scheduler"
    ],
    install_requires=[
        "scapy==2.4.5",
        "click",
        "pyyaml",
        "paho-mqtt==1.5.1"
    ],
    python_requires=">=3.6",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
            "hdl-buspro-mqtt=hdl_ctl:main"
        ]
    },
    include_package_data=True,
    license="MIT",
    url="",
)