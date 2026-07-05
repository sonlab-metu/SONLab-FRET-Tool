# File Formats

This page documents the input and output file structures the tool uses. Understanding the **frame layout** of the multi-frame TIFF stacks is the key to using the tool's outputs correctly.

---

## Input images

| Type | Extension | Notes |
|------|-----------|-------|
| Multi-frame TIFF | `.tif`, `.tiff` | Contains the FRET, Donor, and Acceptor channels as separate frames. |
| Zeiss CZI | `.czi` | Converted automatically on load to a multi-frame TIFF. |

### CZI conversion

When a `.czi` file is loaded, the tool extracts the channels into a 3-frame TIFF (**FRET, Donor, Acceptor**) and preserves the original raw intensity values (no rescaling). A 4th channel is included when present for S3/S4 calculations.

---

## Segmented stacks (Segmentation output)

Saved into a `segmented/` folder next to the source image, named:

```
outline_segmented_<name>.tif      # when "Generate outlines only" is on
whole-cell_segmented_<name>.tif   # when filled masks are used
```

**Frame layout:**

| Frame | Content |
|-------|---------|
| 0 | Segmentation **label mask** (0 = background, 1..N = cell labels) |
| 1 | FRET channel |
| 2 | Donor channel |
| 3 | Acceptor channel *(present for 4-frame data)* |

This is exactly the layout the Bleed-Through and FRET tabs expect. Raw intensities of every channel are preserved so downstream calculations are accurate.

### Membrane + whole-cell stacks (*Segment both*)

When **Segment both (membrane + whole-cell)** is enabled, the file is prefixed `both_segmented_` and uses a different layout intended for the **[[Intensity and Densitometry]]** tab:

| Frame | Content |
|-------|---------|
| 0 | **Outline** (membrane) label mask — a band drawn inward from each cell border |
| 1 | **Filled** (whole-cell) label mask |
| 2…N | Raw image channels, in their **original input order** (not reordered) |

Both masks share the same label ids, so each cell's membrane band and whole-cell body correspond. The Intensity tab's channel registry lets you declare which frame is which. These stacks are **not** meant for the Bleed-Through or FRET tabs.

---

## Bleed-through parameters (`bt_params.json`)

Written by **Save Parameters** in the Bleed-Through tab to the default location **and** copied into each input image directory. Structure:

```json
{
  "s3_s4_enabled": false,
  "donor_params":    { "...": "model type, coefficients, sigma, sampling, selected_fit_model, fit_results" },
  "acceptor_params": { "..." },
  "s3_params":       { "..." },
  "s4_params":       { "..." }
}
```

Each channel block records the fitting model, its coefficients, the processing settings, and the selected model so the fit can be restored exactly. Load it with **Load Parameters**.

---

## FRET outputs

| Output | Format | Location / how |
|--------|--------|----------------|
| Efficiency maps (one per formula) | 32-bit float TIFF | `FRET_Analysis_Results/<name>_<formula>_efficiency.tif`, when efficiency saving is enabled |
| Aggregate statistics | CSV | Exported from the aggregate statistics table |
| Figures (maps, histograms, box plots) | PNG / PDF | **Save** button on any plot or its pop-out window |

Efficiency maps store percentage values (0–100%) as floating-point pixels, with background and excluded pixels set to 0.

---

## Intensity / Densitometry outputs

| Output | Format | Location / how |
|--------|--------|----------------|
| Per-cell measurements | CSV | **Export CSV** — one row per cell × channel with columns `image, group, cell, channel` and every metric (membrane/interior/whole mean, area, integrated density, CTCF, membrane enrichment, membrane fraction) |
| Figures (histogram, box plot, scatter, legend) | PNG / TIFF / PDF / SVG | **Save Plot (300 DPI)** in any plot pop-out |

---

## Notes

- The **label mask must be frame 0** of any stack you feed to the Bleed-Through or FRET tabs. If you build stacks outside the tool, follow the layout above.
- 3-frame stacks (mask, FRET, Donor/Acceptor) are sufficient for S1/S2; 4-frame stacks are required for S3/S4.
- See **[[Workflows and Data Flow]]** for how these files move between tabs.
