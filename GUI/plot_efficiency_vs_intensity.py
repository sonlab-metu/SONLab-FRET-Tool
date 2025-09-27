import tifffile as tiff
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.optimize import curve_fit
import warnings
import argparse

# Suppress warnings that might come from curve fitting
warnings.filterwarnings('ignore')


# ------------------- Utility: Outlier Detection -------------------
def compute_outliers(arr):
    """Return boolean mask of outliers based on 1.5*IQR rule plus thresholds"""
    if arr.size == 0:
        return np.zeros_like(arr, dtype=bool), np.nan, np.nan
    q1 = np.percentile(arr, 25)
    q3 = np.percentile(arr, 75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return (arr < lower) | (arr > upper), lower, upper


def read_tiff_file(file_path):
    """Read a TIFF file and return its data as a numpy array."""
    try:
        return tiff.imread(file_path)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None


# Linear fit function for log-transformed intensities
def linear_func(x, a, b):
    return a * x + b


def fit_and_plot(x_data, y_data, outlier_mask, ax, color, label, xlabel):
    """Plot log-intensity vs efficiency, mark outliers, fit linear model to inliers."""
    # Sort data for plotting
    sort_idx = np.argsort(x_data)
    x_sorted = x_data[sort_idx]
    y_sorted = y_data[sort_idx]
    out_sorted = outlier_mask[sort_idx]

    # Plot inliers and outliers separately
    ax.scatter(x_sorted[~out_sorted], y_sorted[~out_sorted], alpha=0.4, color=color, s=12,
               label=f'{label} Inliers')
    ax.scatter(x_sorted[out_sorted], y_sorted[out_sorted], alpha=0.9, color='orange', marker='x', s=20,
               label=f'{label} Outliers')

    # Linear fit (ignore non-positive intensities)
    mask = (x_sorted > 0) & (~out_sorted)  # fit only on inlier points with positive intensity
    if np.any(mask):
        try:
            popt_lin, _ = curve_fit(linear_func, x_sorted[mask], y_sorted[mask])
            y_fit = linear_func(x_sorted[mask], *popt_lin)
            # Coefficient of determination (R^2)
            ss_res = np.sum((y_sorted[mask] - y_fit) ** 2)
            ss_tot = np.sum((y_sorted[mask] - np.mean(y_sorted[mask])) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot != 0 else np.nan

            ax.plot(x_sorted[mask], y_fit, '-', color='black', linewidth=2,
                    label=f'Linear Fit (slope={popt_lin[0]:.2e}, $R^2$={r2:.3f})')
        except RuntimeError:
            print(f"Could not fit linear curve for {label}")

    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel('FRET Efficiency', fontsize=12)
    ax.set_title(f'FRET Efficiency vs {label} Intensity', fontsize=14)
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)


# ------------------- Scaling Utility -------------------
def apply_scale(arr, scale):
    """Return intensity array scaled according to 'scale' option."""
    if scale == 'log10':
        return np.log10(arr + 1)
    elif scale == 'log2':
        return np.log2(arr + 1)
    else:
        return arr.astype(float)


def main():
    # ---------------- CLI argument parsing ----------------
    parser = argparse.ArgumentParser(description="Plot FRET efficiency vs intensity with scaling and outlier visualization")
    parser.add_argument('--scale', choices=['none', 'log10', 'log2'], default='none',
                        help='Intensity scaling to apply before plotting')
    parser.add_argument('--sample', type=int, default=0,
                        help='Randomly sample this many points for faster plotting (0 = no sampling)')
    args = parser.parse_args()
    scale_type = args.scale
    sample_n = args.sample

    # Base path and file names
    base_name = "outline_segmented_gap4391-20-01923_145856"
    base_dir = Path(".")  # Update this to your directory if needed

    # File paths
    efficiency_file = base_dir / f"{base_name}_efficiency.tif"
    donor_file = base_dir / f"{base_name}_donor.tif"
    acceptor_file = base_dir / f"{base_name}_acceptor.tif"

    # Read all TIFF files
    efficiency = read_tiff_file(efficiency_file).astype(float)
    donor = read_tiff_file(donor_file).astype(float)
    acceptor = read_tiff_file(acceptor_file).astype(float)

    if efficiency is None or donor is None or acceptor is None:
        print("Error: Could not read one or more input files")
        return

    # ---------------- Filtering Masks ----------------
    # 1) FRET efficiency between 0 and 50
    mask_eff = (efficiency > 0) & (efficiency <= 50)

    # 2) Valid donor/acceptor ratio between 1/100 and 100, and both intensities >0
    ratio_lower = 1 / 100
    ratio_upper = 100
    da_valid = (donor > 0) & (acceptor > 0) & (donor >= ratio_lower * acceptor) & (donor <= ratio_upper * acceptor)

    # Final mask combines both criteria
    mask = mask_eff & da_valid

    # Get the corresponding intensity and efficiency values
    donor_intensities = donor[mask].flatten()
    acceptor_intensities = acceptor[mask].flatten()
    efficiency_values = efficiency[mask].flatten()

    # Apply chosen scaling
    donor_scaled = apply_scale(donor_intensities, scale_type)
    acceptor_scaled = apply_scale(acceptor_intensities, scale_type)

    # Optional sampling
    if sample_n > 0 and donor_scaled.size > sample_n:
        idx = np.random.choice(donor_scaled.size, sample_n, replace=False)
        donor_scaled = donor_scaled[idx]
        acceptor_scaled = acceptor_scaled[idx]
        efficiency_values = efficiency_values[idx]

    # Axis label based on scale
    if scale_type == 'log10':
        xlab = 'log10 Intensity (a.u.)'
    elif scale_type == 'log2':
        xlab = 'log2 Intensity (a.u.)'
    else:
        xlab = 'Intensity (a.u.)'

    # ---------------- Outlier Detection ----------------
    donor_outliers, d_low, d_up = compute_outliers(donor_scaled)
    acceptor_outliers, a_low, a_up = compute_outliers(acceptor_scaled)
    eff_outliers, e_low, e_up = compute_outliers(efficiency_values)

    print("--- Outlier Summary (1.5*IQR rule) ---")
    print(
        f"Donor {xlab} outliers: {np.sum(donor_outliers)} / {donor_scaled.size} [lower={d_low:.2f}, upper={d_up:.2f}]")
    print(
        f"Acceptor {xlab} outliers: {np.sum(acceptor_outliers)} / {acceptor_scaled.size} [lower={a_low:.2f}, upper={a_up:.2f}]")
    print(
        f"Efficiency outliers: {np.sum(eff_outliers)} / {efficiency_values.size} [lower={e_low:.2f}, upper={e_up:.2f}]")

    # ---------------------------------------------------------
    # Report number of pixels with intensity < 100 (full image)
    donor_below_100 = np.sum(donor < 100)
    acceptor_below_100 = np.sum(acceptor < 100)
    total_pixels = donor.size  # same shape for all three arrays

    print(
        f"Pixels with donor intensity < 100 : {donor_below_100} / {total_pixels} ({donor_below_100 / total_pixels:.2%})")
    print(
        f"Pixels with acceptor intensity < 100 : {acceptor_below_100} / {total_pixels} ({acceptor_below_100 / total_pixels:.2%})")

    # Create figure with subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Plot donor data with fits
    fit_and_plot(donor_scaled, efficiency_values, eff_outliers, ax1, 'blue', 'Donor', xlab)

    # Plot acceptor data with fits
    fit_and_plot(acceptor_scaled, efficiency_values, eff_outliers, ax2, 'red', 'Acceptor', xlab)

    # Adjust layout
    plt.tight_layout()

    # Save the combined plot
    output_file = base_dir / f"{base_name}_efficiency_vs_intensity_with_fits.png"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Plot saved as {output_file}")

    # Save individual plots
    for label, color in [('donor', 'blue'), ('acceptor', 'red')]:
        fig, ax = plt.subplots(figsize=(8, 6))
        intensities = donor_scaled if label == 'donor' else acceptor_scaled
        fit_and_plot(intensities, efficiency_values, eff_outliers, ax, color, label.capitalize(), xlab)

        # Save individual plot
        individual_file = base_dir / f"{base_name}_efficiency_vs_{label}_intensity.png"
        plt.savefig(individual_file, dpi=300, bbox_inches='tight')
        print(f"Plot saved as {individual_file}")

    # -------------------- 3D Scatter Plot --------------------
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (needed for 3D projection)

    fig3d = plt.figure(figsize=(8, 6))
    ax3d = fig3d.add_subplot(111, projection='3d')

    # 3D scatter: inliers colored by efficiency, outliers in orange crosses
    sc = ax3d.scatter(donor_scaled[~eff_outliers], acceptor_scaled[~eff_outliers], efficiency_values[~eff_outliers],
                      c=efficiency_values[~eff_outliers], cmap='viridis', s=4, alpha=0.6)
    ax3d.scatter(donor_scaled[eff_outliers], acceptor_scaled[eff_outliers], efficiency_values[eff_outliers],
                 c='orange', marker='x', s=20, alpha=0.9)

    ax3d.set_xlabel(xlab.replace('Intensity','Donor Intensity'))
    ax3d.set_ylabel(xlab.replace('Intensity','Acceptor Intensity'))
    ax3d.set_zlabel('FRET Efficiency')
    ax3d.set_title('3D Scatter: Donor vs Acceptor vs Efficiency')
    fig3d.colorbar(sc, label='FRET Efficiency')

    # Save 3D plot
    plot3d_file = base_dir / f"{base_name}_3d_donor_acceptor_efficiency.png"
    plt.savefig(plot3d_file, dpi=300, bbox_inches='tight')
    print(f"3D plot saved as {plot3d_file}")

    # Show the plots
    plt.show()


if __name__ == "__main__":
    main()
