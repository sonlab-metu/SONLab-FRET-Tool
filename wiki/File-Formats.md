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

## Notes

- The **label mask must be frame 0** of any stack you feed to the Bleed-Through or FRET tabs. If you build stacks outside the tool, follow the layout above.
- 3-frame stacks (mask, FRET, Donor/Acceptor) are sufficient for S1/S2; 4-frame stacks are required for S3/S4.
- See **[[Workflows and Data Flow]]** for how these files move between tabs.
