import os, platform

# Determine the project root directory (assuming this script is run from the project root)
project_root = os.path.dirname(os.path.abspath(__file__))

# Construct the path to the target file within the .venv directory
# Linux : backend-El-Switcher/.venv/lib/python3.10/site-packages/pytest_verbose_parametrize.py
# Windows : backend-El-Switcher/.venv/Lib/site-packages/pytest_verbose_parametrize.py

if platform.system() == "Windows":
    file_path = os.path.join(
        project_root,
        ".venv",
        "Lib",
        "site-packages",
        "pytest_verbose_parametrize.py",
    )
elif platform.system() == "Linux":
    file_path = os.path.join(
        project_root,
        ".venv",
        "lib",
        "python3.10",
        "site-packages",
        "pytest_verbose_parametrize.py",
    )
else:
    raise NotImplementedError(f"Unsupported platform: {platform.system()}")


# Read the file contents
with open(file_path, "r") as file:
    lines = file.readlines()


# Replace the specific line
new_lines = []
for line in lines:
    if "from collections import Iterable" in line:
        new_lines.append("from collections.abc import Iterable\n")
    else:
        new_lines.append(line)


# Write the modified contents back to the file
with open(file_path, "w") as file:
    file.writelines(new_lines)

print(
    f"Replaced 'from collections import Iterable' with 'from collections.abc import Iterable' in {file_path}"
)
