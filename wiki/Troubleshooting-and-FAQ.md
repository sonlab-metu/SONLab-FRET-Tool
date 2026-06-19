# Troubleshooting and FAQ

If your problem isn't covered here, open an issue on the project's GitHub repository or email `sonlab@metu.edu.tr`.

---

## Installation & startup

| Problem | Solution |
|---------|----------|
| **Python not found** | Install **Python 3.10** and ensure it is on your system PATH. Newer versions are not supported. |
| **Missing dependencies / import errors** | Activate the virtual environment and reinstall: `pip install -r installers/requirements.txt`. Install PyTorch with the command matching your hardware (see **[[Installation]]**). |
| **GPU not detected** | Verify your CUDA/ROCm version matches the PyTorch build you installed. The tool still runs on CPU, just slower. |
| **macOS blocks the app** | Right-click the app, choose **Open**, and confirm. |

---

## Segmentation

| Problem | Solution |
|---------|----------|
| Cells merged together | Lower **Cell Diameter** or **Flow Threshold**. |
| Cells split into pieces | Increase **Cell Diameter**. |
| Debris segmented as cells | Increase **Min Cell Size**. |
| Faint cells missed | Lower **Cell Prob. Threshold**. |
| Too many false detections | Raise **Cell Prob. Threshold**, lower **Flow Threshold**. |
| Polygon ROI won't complete | Ensure at least 3 vertices and that the polygon is closed. |
| Segmentation is slow | Use a CUDA-capable GPU; reduce image size or batch size. |

---

## Bleed-Through

| Problem | Solution |
|---------|----------|
| Poor fit | Try a different model (Constant / Linear / Exponential) or adjust the Gaussian Blur Sigma. |
| Slow performance | Enable **Random Sampling** with a smaller **Sample Size**. |
| No data points | Confirm the images are single-label controls in the correct channel and contain a segmentation mask. |
| Plot/fit not updating | Use the toolbar **Home**, threshold **Update Plot**, or re-run the analysis. |
| "S3 requires 4-frame images" | Provide 4-frame stacks (mask, FRET, Donor, Acceptor). |
| Loading parameters changed my fit | Loading re-draws the **saved** coefficients without re-fitting; if values look wrong, re-confirm the fit and save again. |

---

## FRET Analysis

| Problem | Solution |
|---------|----------|
| BT parameters show *N/A* | Confirm and save the fits in the Bleed-Through tab first. |
| DFRET won't run | Enter a positive **E (photobleaching)** value, or compute **C1** from a fusion image. |
| Maps appear empty | Check the Lower/Upper thresholds and that the stack has a mask in frame 0. |
| All cells excluded | Loosen or disable the **Cell Efficiency Threshold**. |
| Non-zero and thresholded averages look identical | They differ only when cells contain pixels outside the threshold range; widen the range or check your data. |
| Significance bars disappeared | For >2 groups, post-hoc bars appear only when the omnibus test is significant — see **[[Results and Visualization]]**. |

---

## General

| Problem | Solution |
|---------|----------|
| The plot still shows a removed image | Removing the **last** image returns the view to an empty state; if a stale plot lingers, re-select an image or use **Reset Tab**. |
| Mouse wheel won't change a dropdown/spin box | This is intentional — scrolling never edits values. Click the field and type, or use the arrows. |
| Out-of-memory on large datasets | Process fewer images at once, enable random sampling, and close other applications. |
| Unexpected efficiency values | Verify the input frame order (mask, FRET, Donor, Acceptor) — see **[[File Formats]]**. |

---

## Frequently asked questions

**Which images go into the Bleed-Through tab?**
Single-label controls: donor-only samples for S1/S3 and acceptor-only samples for S2/S4. Send them there from the Segmentation tab.

**Do I have to segment before FRET?**
Yes — the segmentation mask (frame 0) tells the FRET calculation which pixels belong to which cell. Use the Segmentation tab or load stacks that already contain a mask.

**Can I reuse a bleed-through model across experiments?**
Yes. Save `bt_params.json` and load it later. A copy is also stored next to your input images.

**Which FRET formula should I use?**
That depends on your assay and references; the tool lets you compute several at once and compare. DFRET additionally requires a photobleaching calibration.

**Where are my results saved?**
Efficiency maps go to a `FRET_Analysis_Results/` folder; statistics export to CSV; figures save wherever you choose from each plot's Save button. See **[[File Formats]]**.
