# Intensity / Densitometry

The **Intensity / Densitometry** tab performs object-based intensiometric analysis of segmented cells. It is designed to check whether a fluorophore-tagged protein localizes where it is expected — for example, whether a membrane-targeted construct is genuinely enriched at the cell membrane rather than in the cytoplasm.

Unlike the FRET tab, this module is **not tied to the FRET/Donor/Acceptor channel layout**. You declare your own frame layout in the tab's channel registry, so it works with any segmented stack — including single- or two-channel images from other experiments.

> This tab is independent of the FRET pipeline. Membrane-vs-whole-cell comparison for FRET efficiencies and bleed-through is planned for a later release.

---

## 1. Input images

The tab consumes segmented multi-frame stacks. The most convenient source is the Segmentation tab's **Segment both (membrane + whole-cell)** option, which writes a single stack laid out as:

```
[ outline (membrane) mask, filled (whole-cell) mask, ...raw channels ]
```

- Use **Add…** to load stacks, or send them directly from the Segmentation tab with the **Intensity** button (or the batch path).
- Assign an experimental **Group** label to selected images (e.g. *Control*, *Treated*) to drive the grouped plots and statistics.
- **Metadata** opens the acquisition metadata for the selected image.

---

## 2. Channel registry (frame layout)

Because segmented stacks can be laid out in different ways, you tell the tab what each frame is:

| Control | Meaning |
|---------|---------|
| **Outline (membrane) frame** | 0-based index of the membrane-band label mask. Set to **−1** if there is none. |
| **Whole-cell (filled) frame** | 0-based index of the filled label mask. |
| **Membrane source** | *From outline frame* uses the stored membrane band; *Erode whole-cell* derives the band by eroding the filled mask (works even for whole-cell-only stacks). |
| **Erosion width (px)** | Band width when the membrane is derived by erosion. |
| **Channels table** | One row per fluorophore channel to analyse: its 0-based **frame** index and a **label** (e.g. *GFP*, *RFP*). |

For a **Segment both** stack the defaults are: outline = 0, filled = 1, fluorophore channels from frame 2 onward. The registry is remembered between sessions.

> **Membrane definition.** The membrane is the band of pixels **inside** the cell, from the border inward by the outline thickness (or the erosion width). The interior is the rest of the cell, and the two together make up the whole cell. This keeps every membrane pixel inside the cell, so the enrichment read-outs are not diluted by background.

---

## 3. Preprocessing

Applied to each channel before measuring (never to the saved data):

- **Subtract background** — estimates a local-mean background level and subtracts it (the same method as the Bleed-Through tab). **BG kernel** sets the window size.
- **Gaussian blur** — optional smoothing to reduce pixel noise. **Blur sigma** sets the kernel width.

---

## 4. Measure and read out

Click **Measure Cells** to compute, for every cell and every registered channel, a full set of per-cell metrics across the **membrane**, **interior**, and **whole-cell** regions:

| Metric | Meaning |
|--------|---------|
| **Membrane enrichment (membrane / interior)** | Headline localization read-out. > 1 means the signal is enriched at the membrane. |
| **Membrane enrichment (membrane / whole-cell)** | Membrane mean relative to the whole-cell mean. |
| **Membrane fraction of total** | Fraction of the total cell signal that sits in the membrane band (Σmembrane / Σwhole). |
| **Mean / median / std intensity** | Per-region average, median, and spread. |
| **Area (px)** | Region size in pixels. |
| **Integrated density** | Sum of intensities in the region. |
| **CTCF** | Background-corrected total cell fluorescence (integrated density − area × background). |

Choose the **Metric** and **Channel** to plot; every metric is exported regardless of what is shown.

---

## 5. Plots and statistics

Four views, each with a publication-quality pop-out (300 DPI save) and a decoupled **Legend** window so crowded legends never overlap the plot:

- **Histogram** — per-cell distribution of the selected metric, one colour per group, with the group mean marked.
- **Box Plot** — per-group box plot with jittered per-cell points and **assumption-aware significance bars**: groups are screened for normality (Shapiro-Wilk) and the test family is chosen automatically (Welch's t-test / Welch ANOVA when normal; Mann-Whitney U / Kruskal-Wallis otherwise), with Holm-Bonferroni correction for multiple comparisons. **Stats info** shows the full report.
- **Scatter / Correlation** — any metric against any other (e.g. integrated density vs area), with a linear fit and Pearson's *r*.
- **Summary** — a per-group table plus the statistical report as text.

**Export CSV** writes every per-cell measurement (image, group, cell, channel, and all metrics) for downstream analysis.

---

## Typical workflow

1. In the **[[Segmentation]]** tab, tick **Segment both (membrane + whole-cell)**, segment your cells, and click **Intensity** (or batch-transfer) to send the stacks here.
2. Confirm the **channel registry** matches your stack and add your fluorophore channel(s).
3. Set preprocessing, assign **Group** labels, and click **Measure Cells**.
4. Pick a metric (e.g. *Membrane enrichment*) and compare groups in the **Box Plot**; read the significance report.
5. **Export CSV** and save publication figures from the pop-outs.

Continue to **[[Results and Visualization]]** for the shared plotting and statistics conventions.
