# data/

Default data folder of BraggFlow. Everything inside it is **ignored by git**
(only this README and the `.gitkeep` files are versioned), so real
measurements never end up in the repository.

The commands look for the data folder in this order: the `--data-dir` option,
the `BRAGGFLOW_DATA_DIR` environment variable, and `./data` in the directory
where you run them. Missing subfolders are created automatically.

| Subfolder    | What goes there                                                                 |
|--------------|---------------------------------------------------------------------------------|
| `raw/`       | Interrogator exports and spectra you copy here yourself (`.asc`, `.txt`, `.dat`…) |
| `uploads/`   | Files imported through the web app ("Escolher no computador" / drag and drop)  |
| `processed/` | Processed CSVs and their JSON provenance; the web app keeps one subfolder per project |
| `projects/`  | Projects saved by the web app (JSON: files, sensors, steps, markers, figure style) |
| `setups/`    | Sensor setups saved by the web app (channel name and allowed band)            |
| `styles/`    | Figure styles saved in the Visualização tab                                     |
| `figures/`   | Exported figures                                                                |

The formats of these files are described in [`docs/data-formats.md`](../docs/data-formats.md).
