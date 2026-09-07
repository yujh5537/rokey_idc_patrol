# SLAM map drop-in directory

Frontend-only preview works without map files.

When SLAM output is available, place the pair here as:

- `map.pgm`
- `map.yaml`

`MapView` will automatically detect them, parse the PGM occupancy image, apply the dark IDC style, and position robot/rack markers using `resolution` and `origin` from the YAML file.
