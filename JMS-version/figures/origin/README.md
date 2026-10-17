# Origin Gantt figure sources

`build_origin_gantt.ps1` reconstructs the four representative resource-view
Gantt charts from the frozen experiment SVGs. It creates an editable Origin
project and exports PDF, SVG, TIFF (600 dpi), and PNG files without changing
the existing `_nature` figures.

Rebuild with Origin 2026b SR1 installed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\JMS-version\figures\origin\build_origin_gantt.ps1
```

The plotted horizon ends when the final product wafer returns to an LP. Tasks
that start after that boundary, including terminal cleaning with no subsequent
production, are intentionally excluded from the Cmax/WPH figure horizon.
