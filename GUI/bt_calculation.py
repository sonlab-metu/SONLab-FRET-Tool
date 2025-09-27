"""
FRET Analysis Core Functions
This module contains the core analysis functions for FRET data processing.
"""

import numpy as np
import tifffile as tiff
from scipy.ndimage import gaussian_filter
from scipy.ndimage import uniform_filter
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import warnings


def constant(x, a):
    return a

def linear(x, a, b):
    return a * x + b

def exponential(x, a, k, b):
    return a * np.exp(-k*x) + b

def apply_gaussian_blur(image, sigma=2):
    return gaussian_filter(image, sigma=sigma)

def subtract_background(image2, image, kernel_size=30):
    # Compute local means using a fast uniform filter
    local_means = uniform_filter(image, size=kernel_size, mode='reflect')
    
    # Find the minimum of all local means
    min_mean = np.min(local_means)
    
    # Subtract from image2
    bg_subtracted_image = image2 - min_mean
    bg_subtracted_image[bg_subtracted_image < 0] = 0
    return bg_subtracted_image

def process_donor_only_samples(donor_paths, sigma=2):
    """
    Process donor‐only samples using **segmented** TIFF stacks.
    
    Expected stack layout (frames):
        0 → segmentation mask (binary / labelled)
        1 → FRET channel
        2 → Donor channel (for donor-only samples)
        3 → *optional* Acceptor channel (ignored here)
    
    Parameters
    ----------
    donor_paths : list[str]
        List of donor-only TIFF paths.
    sigma : float, optional
        Gaussian kernel σ. Default is 2.
    
    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (donor intensities, S1 ratios) – both flattened arrays containing **only the
        pixels inside the segmentation mask**.
    """
    
    donor_intensity_accum = []
    fret_intensity_accum = []
    
    for donor_path in donor_paths:
        images = tiff.imread(donor_path)
        
        n_frames = images.shape[0]
        if n_frames not in (3, 4):
            raise ValueError(
                "Unsupported donor-only stack. Expected 3 or 4 frames (mask, FRET, Donor[ ,Acceptor])."
            )
        
        # Frame assignments
        mask_frame = images[0] > 0  # boolean mask of labelled pixels
        fret_raw = images[1].astype(float)
        donor_raw = images[2].astype(float)
        
        # Blur
        fret_blur = apply_gaussian_blur(fret_raw, sigma)
        donor_blur = apply_gaussian_blur(donor_raw, sigma)
        
        # Background subtraction (use pre-blur image for local mean estimation)
        fret_bg = subtract_background(fret_blur, fret_raw)
        donor_bg = subtract_background(donor_blur, donor_raw)
        
        # Apply segmentation mask BEFORE concatenation
        fret_masked = fret_bg[mask_frame]
        donor_masked = donor_bg[mask_frame]
        
        # Store
        fret_intensity_accum.append(fret_masked)
        donor_intensity_accum.append(donor_masked)
    
    donor_combined = np.concatenate(donor_intensity_accum, axis=None)
    fret_combined = np.concatenate(fret_intensity_accum, axis=None)
    
    # S1 ratio
    S1 = np.divide(
        fret_combined,
        donor_combined,
        out=np.zeros_like(fret_combined),
        where=donor_combined != 0,
    )
    
    # Discard unphysical (>1) values
    valid_mask = S1 < 1
    return donor_combined[valid_mask], S1[valid_mask]

def process_acceptor_only_samples(acceptor_paths, sigma=2):
    """
    Process acceptor‐only samples with the new **segmented** stack format.
    
    Expected stack layout (frames):
        0 → segmentation mask (binary / labelled)
        1 → FRET channel
        2 → Donor channel (ignored here) *or* Acceptor channel (if only 3 frames)
        3 → Acceptor channel (for 4-frame stacks)
    
    The function auto-detects the correct Acceptor channel frame.
    All calculations use only the pixels inside the segmentation mask.
    """
    
    acceptor_intensity_accum = []
    fret_intensity_accum = []
    
    for acceptor_path in acceptor_paths:
        images = tiff.imread(acceptor_path)
        
        n_frames = images.shape[0]
        if n_frames == 3:
            # mask, FRET, Acceptor
            mask_frame = images[0] > 0
            fret_raw = images[1].astype(float)
            acceptor_raw = images[2].astype(float)
        elif n_frames == 4:
            # mask, FRET, Donor, Acceptor
            mask_frame = images[0] > 0
            fret_raw = images[1].astype(float)
            acceptor_raw = images[3].astype(float)
        else:
            raise ValueError(
                "Unsupported acceptor-only stack. Expected 3 or 4 frames (mask, FRET, [Donor,] Acceptor)."
            )
        
        # Blur
        fret_blur = apply_gaussian_blur(fret_raw, sigma)
        acceptor_blur = apply_gaussian_blur(acceptor_raw, sigma)
        
        # Background subtraction
        fret_bg = subtract_background(fret_blur, fret_raw)
        acceptor_bg = subtract_background(acceptor_blur, acceptor_raw)
        
        # Apply segmentation mask
        fret_masked = fret_bg[mask_frame]
        acceptor_masked = acceptor_bg[mask_frame]
        
        fret_intensity_accum.append(fret_masked)
        acceptor_intensity_accum.append(acceptor_masked)
    
    acceptor_combined = np.concatenate(acceptor_intensity_accum, axis=None)
    fret_combined = np.concatenate(fret_intensity_accum, axis=None)
    
    S2 = np.divide(
        fret_combined,
        acceptor_combined,
        out=np.zeros_like(fret_combined),
        where=acceptor_combined != 0,
    )
    
    valid_mask = S2 < 1
    return acceptor_combined[valid_mask], S2[valid_mask]

def fit_and_plot(x_data, y_data, x_label, y_label, title, ax, use_sampling, sample_size):
    """
    Fit and plot data with optional sampling for visualization.
    
    Parameters:
    x_data : array-like
        The x-axis data
    y_data : array-like
        The y-axis data
    x_label : str
        Label for x-axis
    y_label : str
        Label for y-axis
    title : str
        Plot title
    ax : matplotlib.axes.Axes
        The axes object to plot on
    use_sampling : bool
        Whether to use sampling for plotting
    sample_size : int
        Number of points to sample for plotting
    """
    
    mask4 = y_data > 0 
    non_zero4 = y_data[mask4]
    # print(f'{ylabel}: {np.mean(non_zero4)}')

    # Create a combined mask where both x_data and y_data are > 0
    mask = (x_data > 0) & (y_data > 0)
    x_data = x_data[mask]
    y_data = y_data[mask]

    # Create a copy of the data for plotting
    x_plot = x_data.copy()
    y_plot = y_data.copy()
    
    # Apply sampling if enabled – this should affect BOTH plotting and fitting.
    if use_sampling and len(x_data) > sample_size:
        np.random.seed(42)
        sample_indices = np.random.choice(len(x_data), size=sample_size, replace=False)
        x_data = x_data[sample_indices]
        y_data = y_data[sample_indices]
        # Use the same subset for plotting
        x_plot = x_data
        y_plot = y_data

    ax.scatter(x_plot, y_plot, label='Data', alpha=0.5, color='red', s=1)
    x_fit = np.linspace(x_data.min(), x_data.max(), 400)

    coeffs = {}
    fit_lines = {}

    # Calculate constant model as the average of y_data
    avg_y = np.mean(y_data)
    fit_lines['Constant'] = np.full_like(x_fit, avg_y)
    coeffs['Constant'] = avg_y

    # Fit linear model
    try:
        popt_linear, _ = curve_fit(linear, x_data, y_data)
        fit_lines['Linear'] = linear(x_fit, *popt_linear)
        coeffs['Linear'] = popt_linear
    except Exception as e:
        coeffs['Linear'] = None
        print(f"Linear fit failed: {e}")

    # Fit exponential model
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', RuntimeWarning)
            popt_exponential, _ = curve_fit(
                exponential,
                x_data,
                y_data,
                p0=(1, 0.005, 0),
                bounds=([0, 0, 0], [np.inf, np.inf, 1]),  # ensure physically meaningful (a,k,b >=0, b<=1)
                maxfev=5000,
            )
            # Additional sanity check – reject if any parameter is nan or k is very small (flat curve)
            if (
                np.any(~np.isfinite(popt_exponential))
                or popt_exponential[1] <= 0
                or popt_exponential[0] <= 0
            ):
                raise RuntimeError("Unphysical exponential parameters")
            fit_lines['Exponential'] = exponential(x_fit, *popt_exponential)
            coeffs['Exponential'] = popt_exponential
    except Exception as e:
        coeffs['Exponential'] = None
        print(f"Exponential fit failed: {e}")

    # Plot all models
    for model, line_data in fit_lines.items():
        if line_data is not None:
            ax.plot(x_fit, line_data, label=model)

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.legend()
    ax.grid(True)

    return coeffs
