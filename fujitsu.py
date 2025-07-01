import os
from pathlib import Path
import subprocess

# Set your input and output folder paths
input_folder = Path('../compiler-test-suite/Fortran')
output_folder = Path('/mnt/c/Temp/fujitsu_fortran')

# Find all .f90 files in the input folder (recursive search)
f90_files = list(input_folder.rglob('*.f90'))

# Compute relative paths and corresponding output paths
relative_paths = [f.relative_to(input_folder).with_suffix(".json") for f in f90_files]
output_paths = [output_folder / rel_path for rel_path in relative_paths]

total_files = len(relative_paths)
print("Found " + str(total_files) + " files")

# Example: printing the mappings
counter = 1
errors = []
timeouts = []
success = 0

for f90_file in f90_files:
    relative_path = f90_file.relative_to(input_folder).with_suffix(".json")
    out = output_folder / relative_path
    cmd = ["flang-20", "-fc1", "-load", "./build/DumpASTPlugin.so", "-plugin", "dump-ast", str(f90_file)]
    print("(" + str(counter) + "/" + str(total_files) + ") " + " ".join(cmd))
    try:
        result = subprocess.run(cmd, timeout=5, capture_output=True, text=True)
    except subprocess.TimeoutExpired as e:
        timeouts.append(f90_file)

    if result.returncode == 0:
      success += 1
      out.parent.mkdir(parents=True, exist_ok=True)
      with open(out, "w") as f:
        f.write(result.stdout);
    else:
      print("Error: " + result.stderr)
      errors.append(f90_file)
    

    counter += 1


# Print stats
with open("stats.txt", "w") as f:

   f.write("Errors:\n")
   for f90_file in errors:
     f.write(str(f90_file) + "\n")

   f.write("Timeouts:\n")
   for f90_file in timeouts:
      f.write(str(f90_file) + "\n")

   f.write("\n#Errors: " + str(len(errors)))
   f.write("\n#Timeouts: " + str(len(timeouts)))
   f.write("\n#Successes: " + str(success))
   f.write("\nTotal: " + str(counter))
