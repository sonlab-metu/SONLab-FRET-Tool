# Workflows and Data Flow

This page shows how the three tabs fit together and recommends an end-to-end workflow.

A detailed flow diagram for each stage is on its own page: **[[Segmentation]]**, **[[Bleed-Through Correction]]**, and **[[FRET Analysis]]**. The cross-tab pipeline is summarized below.

---

## The pipeline at a glance

```
 Raw images (.tif / .czi)
        │
        ▼
┌───────────────────────────┐
│ 1. Cellpose & Manual      │  segment cells → label mask
│    Segmentation           │  refine ROIs by hand
└───────────────────────────┘
        │  segmented stacks (mask + channels)
        ├──────────────► Send to Donor / Acceptor ──┐
        │                                            ▼
        │                              ┌───────────────────────────┐
        │                              │ 2. Bleed-Through          │  fit S1/S2 (+S3/S4)
        │                              │    Correction             │  → bt_params.json
        │                              └───────────────────────────┘
        │                                            │ coefficients
        ▼                                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. FRET Analysis                                                  │
│    apply correction → efficiency maps → stats & figures          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Recommended end-to-end workflow

1. **Segment your images** in the **[[Segmentation]]** tab.
   - Load raw `.tif`/`.czi` images, set the Cellpose parameters, and run segmentation.
   - Refine with the ROI Manager where needed.
   - Forward control images to the bleed-through channels using **Send to Donor** / **Send to Acceptor**, and experimental images to FRET using **Send to FRET** or **Batch Segment && Transfer**.

2. **Characterize bleed-through** in the **[[Bleed-Through Correction]]** tab.
   - For each channel (S1, S2, and optionally S3/S4), run the analysis, choose a fitting model, and **Confirm Fit**.
   - **Save Parameters** — the coefficients are written to `bt_params.json` (and copied next to your input images).

3. **Compute FRET** in the **[[FRET Analysis]]** tab.
   - Verify the Bleed-Through Parameters panel shows your confirmed coefficients.
   - Choose formulas, set thresholds and optional filters, assign groups.
   - **Run FRET Analysis** and review the **[[Results and Visualization]]**.
   - Export maps, statistics, and figures.

---

## How data moves between tabs

| Data | Produced in | Consumed in | Mechanism |
|------|-------------|-------------|-----------|
| **Segmented stacks** (mask + channels) | Segmentation | Bleed-Through, FRET | *Send to Donor/Acceptor*, *Send to FRET*, *Batch Segment && Transfer*, or saved files |
| **Bleed-through coefficients** | Bleed-Through | FRET | Confirmed fits, shown in the FRET *Bleed-Through Parameters* panel; persisted in `bt_params.json` |
| **Groups** | FRET (or set during batch transfer) | FRET statistics | Group tags drive aggregate comparisons |
| **Efficiency maps & stats** | FRET | external tools | Exported as TIFF / CSV / figures |

> The label mask travels **with** the image as frame 0 of every segmented stack, so each tab always knows which pixels belong to which cell. Raw channel intensities are preserved through saving, so corrections and efficiencies are computed on the original data.

---

## Sessions and reuse

- Save `bt_params.json` to reuse a bleed-through model across sessions or datasets; the tool offers to reload the last session's parameters on startup.
- Re-load saved segmented stacks at any time — they already contain the mask, so you can skip straight to bleed-through or FRET.

---

## Performance tips

- A CUDA-capable GPU greatly accelerates Cellpose segmentation.
- For large images or many cells, enable **Random Sampling** in the Bleed-Through tab.
- Use **Batch Segment && Transfer** to process many images in one pass.
- Close other memory-heavy applications when working with large datasets.
