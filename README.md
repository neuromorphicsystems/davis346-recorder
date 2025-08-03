- [Installation](#installation)
- [Usage](#usage)
- [Render event data](#render-event-data)
- [Render frames](#render-frames)

# Installation

> [!WARNING]
> The Python version that comes from Microsoft's Windows Store does not work with PySide6 (specifically, PySide6 complains that it cannot find qtquick2plugin.dll even though the file exists). Make sure to install Python from the official website https://www.python.org.

1. Create a virtual environment

    ```sh
    # Linux, macOS
    python3 -m venv .venv

    # Windows
    python -m venv .venv
    ```

2. Activate the virtual environment

    ```sh
    # Linux, macOS
    source .venv/bin/activate

    # Windows (cmd.exe)
    .venv\Scripts\Activate.ps1

    # Windows (PowerShell)
    .venv\Scripts\Activate.ps1
    ```

3. Install dependencies

    ```sh
    pip install neuromorphic-drivers faery PySide6 pillow
    ```

# Usage

1. Activate the virtual environment (skip this if you just went through the installation steps)

    ```sh
    # Linux, macOS
    source .venv/bin/activate

    # Windows (cmd.exe)
    .venv\Scripts\Activate.ps1

    # Windows (PowerShell)
    .venv\Scripts\Activate.ps1
    ```

2. Run the application

    ```sh
    python davis346_recorder.py
    ```

See https://docs.inivation.com/hardware/hardware-advanced-usage/biasing.html for a guide on bias tuning.

# Render event data

1. Create a directory called **recordings**

2. Move event files of interest (.csv) in the directory **recordings**

3. Run `faery init`

4. Faery cannot automatically tell the sensor width and height from a CSV file. In **faery_script.py** (created by the previous command), find all the calls to `faery.events_stream_from_file` and add the argument `dimensions_fallback=(346, 260)`. The modified called should look like the following:

    ```py
    faery.events_stream_from_file(input, dimensions_fallback=(346, 260))
    ```

5. Run `faery run`

See https://github.com/aestream/faery?tab=readme-ov-file#workflow for an example on how to generate a slow-motion video render.

# Render frames

The Davis346 ADC has a precision of 10 bits, hence the frame values are in the range [0, 1023].

Neuromorphic-drivers multiplies the raw values by 64, making the effective range [0, 65472], to avoid display issues (16 bits images look very dark if only the range [0, 1023] is used).

The frames' timestamps (same clock as the events) are stored in **frames_metadata.csv**. The raw frames (native endian u16) are stored in **frames/dddddd.raw**. They can be loaded in Python as follows.

```py
# read the frame as a numpy array
import numpy

with open("data/<recording name>/frames/000000.raw", "rb") as frame_file:
    array = numpy.frombuffer(frame_file.read(), dtype=numpy.uint16).reshape((260, 346))

# save the frame a 16-bit PNG image
import PIL.Image

PIL.Image.fromarray(array).save("test.png")
```
