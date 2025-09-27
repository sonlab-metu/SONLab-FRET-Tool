import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from scipy import ndimage
from matplotlib import rcParams
import warnings
from matplotlib.colors import ListedColormap
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.ticker as ticker
import tifffile
from skimage.measure import regionprops_table
import re

# Suppress specific warnings for cleaner output
warnings.filterwarnings('ignore')

def find_matching_files(directory):
    """Find all FRET efficiency and segmented label image pairs in the directory."""
    # Get all TIFF files
    tiff_files = [f for f in os.listdir(directory) if f.lower().endswith('.tif') or f.lower().endswith('.tiff')]
    
    # Separate into FRET and segmented files
    fret_files = [f for f in tiff_files if f.startswith('FRET Efficiency (%) of ') and 'segmented' not in f]
    segmented_files = [f for f in tiff_files if f.startswith('cellpose_segmented_') and f.endswith('_labels_efficiency.tif')]
    
    # Extract base names for matching
    base_names = {}
    for f in fret_files:
        base = f.replace('FRET Efficiency (%) of ', '').replace('.tif', '').replace('.tiff', '')
        base_names[base] = {'fret': f, 'segmented': None}
    
    # Match segmented files to FRET files
    for f in segmented_files:
        # Extract base name from segmented filename
        match = re.match(r'cellpose_segmented_(.+?)__labels_efficiency\.tif', f)
        if match:
            base = match.group(1)
            if base in base_names:
                base_names[base]['segmented'] = f
    
    # Only keep complete pairs
    matched_pairs = {k: v for k, v in base_names.items() 
                    if v['fret'] is not None and v['segmented'] is not None}
    
    return matched_pairs

def load_and_process_images(directory, file_pairs):
    """Load and process FRET and segmented label image pairs."""
    results = []
    all_pixel_values = []
    
    for base_name, files in file_pairs.items():
        fret_path = os.path.join(directory, files['fret'])
        seg_path = os.path.join(directory, files['segmented'])
        
        try:
            # Load images
            fret_img = tifffile.imread(fret_path).astype(np.float32)
            seg_img = tifffile.imread(seg_path)
            
            # Ensure label image is integer type
            if not np.issubdtype(seg_img.dtype, np.integer):
                seg_img = seg_img.astype(np.int32)
            
            # Get unique labels, excluding 0 (background)
            labels = np.unique(seg_img)
            labels = labels[labels > 0]
            
            # Process each ROI
            for label in labels:
                mask = (seg_img == label)
                pixels = fret_img[mask]
                # Exclude zero pixels
                non_zero_pixels = pixels[pixels > 0]
                
                if len(non_zero_pixels) > 0:  # Only process if ROI has non-zero pixels
                    results.append({
                        'image_name': base_name,
                        'roi_id': int(label),
                        'pixel_values': non_zero_pixels,
                        'mean_efficiency': np.mean(non_zero_pixels),
                        'pixel_count': len(non_zero_pixels)
                    })
                    all_pixel_values.extend(non_zero_pixels)
                    
        except Exception as e:
            print(f"Error processing {base_name}: {str(e)}")
    
    return results, np.array(all_pixel_values)

# Set up plot style for publication quality
def setup_plot_style():
    """Configure matplotlib with publication-quality settings matching fret_tab.py."""
    import seaborn as sns
    sns.set_style('whitegrid')

    
    # Base style parameters
    style_params = {
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'DejaVu Sans'],
        'font.size': 10,
        'axes.titlesize': 12,
        'axes.labelsize': 10,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'legend.fontsize': 9,
        'figure.titlesize': 12,
        'figure.dpi': 300,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.1,
        'lines.linewidth': 1.2,
        'lines.markersize': 3,
        'axes.linewidth': 0.8,
        'xtick.major.width': 0.8,
        'ytick.major.width': 0.8,
        'xtick.minor.width': 0.6,
        'ytick.minor.width': 0.6,
    }
    
    # Apply base style
    rcParams.update(style_params)
    
    # Set errorbar and boxplot styles directly in the plotting functions
    return style_params

def process_image_data(results, all_pixel_values):
    """Process the loaded image data into a format suitable for plotting and analysis.
    
    Args:
        results: List of dictionaries containing ROI data
        all_pixel_values: Flat array of all non-zero pixel values across all ROIs
        
    Returns:
        tuple: (df, all_pixel_values) where df is a DataFrame with ROI statistics
               and all_pixel_values is the input array (unchanged)
    """
    # Convert to DataFrame for easier manipulation
    df_data = []
    for item in results:
        pixels = item['pixel_values']
        if len(pixels) > 0:  # Only include ROIs with non-zero pixels
            df_data.append({
                'image_name': item['image_name'],
                'roi_id': item['roi_id'],
                'mean_efficiency': item['mean_efficiency'],
                'pixel_count': len(pixels),
                'pixel_values': pixels
            })
    
    df = pd.DataFrame(df_data)
    return df, all_pixel_values

def create_fret_plots(df, all_pixel_values, output_dir):
    """Create publication-quality plots for FRET efficiency analysis.
    
    Args:
        df: DataFrame containing 'image_name', 'roi_id', 'mean_efficiency' columns
        all_pixel_values: Array of all pixel values across all ROIs
        output_dir: Directory to save the output figure
        
    Returns:
        tuple: (figure, result_dict) where result_dict contains analysis results
    """
    # Setup figure with three subplots (histogram, all ROIs box, per-image box)
    fig = Figure(figsize=(10, 12), dpi=300)
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 2, 2], hspace=0.5)
    ax1 = fig.add_subplot(gs[0])  # Histogram
    ax2 = fig.add_subplot(gs[1])   # All ROIs box plot
    ax3 = fig.add_subplot(gs[2])   # Per-image box plot
    
    # --- Histogram Plot ---
    # Match the binning from fret_tab.py
    lower_thr = 0.0  # Lower threshold
    upper_thr = 50.0  # Upper threshold (100% for FRET efficiency)
    n_bins = 256
    
    # Create bin edges and centers
    edges = np.linspace(lower_thr, upper_thr, n_bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    
    # Calculate histogram for all pixels across all ROIs
    hist, _ = np.histogram(all_pixel_values, bins=edges, density=False)
    
    # Convert to percentage of total pixels (matching fret_tab.py)
    hist_percent = (hist / hist.sum() * 100) if hist.sum() > 0 else hist
    
    # Calculate per-ROI histograms for mean and SEM
    roi_hists = []
    for _, row in df.iterrows():
        roi_hist, _ = np.histogram(row['pixel_values'], bins=edges, density=False)
        if roi_hist.sum() > 0:
            roi_hist = roi_hist / roi_hist.sum() * 100  # Normalize by ROI size
        roi_hists.append(roi_hist)
    
    if roi_hists:
        roi_hists = np.vstack(roi_hists)
        mean_hist = np.nanmean(roi_hists, axis=0)
        sem_hist = stats.sem(roi_hists, axis=0, nan_policy='omit')
    else:
        mean_hist = np.zeros_like(hist_percent)
        sem_hist = np.zeros_like(hist_percent)
    
    # Plot the mean histogram with error bars
    bin_width = edges[1] - edges[0]
    
    # Cap the y-axis at 10% to prevent outlier bars from squishing the rest of the data
    y_max = 10.0
    
    # Identify and mark bins that exceed the y-axis limit
    overflow_bins = mean_hist > y_max
    
    # Create the main histogram bars (clipped to max height)
    clipped_hist = np.minimum(mean_hist, y_max)
    bars = ax1.bar(centers, clipped_hist, width=bin_width * 0.9, 
                 color='steelblue', alpha=0.7, label='Mean ± SEM',
                 yerr=sem_hist, error_kw=dict(lw=1, capsize=2, capthick=1))
    
    # Add small triangles to indicate overflow bins
    if np.any(overflow_bins):
        overflow_centers = centers[overflow_bins]
        ax1.scatter(overflow_centers, [y_max] * len(overflow_centers), 
                   marker='^', color='red', s=30, zorder=5, 
                   label=f'Bins > {y_max:.1f}%')
        
        # Add text annotation for the first overflow bin
        first_overflow = np.where(overflow_bins)[0][0]
        ax1.annotate(f'{mean_hist[first_overflow]:.1f}%',
                    xy=(centers[first_overflow], y_max),
                    xytext=(0, 10), textcoords='offset points',
                    ha='center', va='bottom', color='red', fontsize=8)
    
    # Add labels and title
    ax1.set_xlabel('FRET Efficiency (%)', fontsize=10, labelpad=8)
    ax1.set_ylabel('Normalized Pixel Count (%)', fontsize=10, labelpad=8)
    ax1.set_title('FRET Efficiency Distribution', fontsize=12, pad=12)
    
    # Set x-axis limits to 0-50%
    ax1.set_xlim(0, 50)
    
    # Set y-axis limit to 10% and add indicator for out-of-bounds values
    ymax = 10.0
    ax1.set_ylim(0, ymax)
    
    # Find and mark bars that exceed the y-axis limit
    for bar in bars:
        height = bar.get_height()
        if height > ymax:
            # Add a marker at the top of the bar
            ax1.plot(bar.get_x() + bar.get_width()/2, ymax * 0.98, 
                    marker='^', color='red', markersize=8, clip_on=False)
            # Add a small text label
            ax1.text(bar.get_x() + bar.get_width()/2, ymax * 0.9, 
                    f'{height:.1f}%', ha='center', va='top', color='red', fontsize=8)
    
    # Add a note about the y-axis limit
    ax1.text(0.98, 0.95, 'y ≤ 10%', 
            transform=ax1.transAxes, ha='right', va='top',
            bbox=dict(facecolor='white', alpha=0.8, edgecolor='gray', boxstyle='round,pad=0.2'))
    ax1.grid(True, linestyle='--', alpha=0.3)
    
    # --- Box Plot 1: All ROIs Combined ---
    if not df.empty:
        # Get mean efficiency for all ROIs
        all_roi_means = df['mean_efficiency'].values
        
        # Calculate boxplot statistics
        box_stats = []
        positions = [1]
        
        # Calculate statistics for the box
        q1, q3 = np.percentile(all_roi_means, [25, 75])
        iqr = q3 - q1
        lower_whisker = q1 - 1.5 * iqr
        upper_whisker = q3 + 1.5 * iqr
        
        # Store stats for plotting
        box_stats.append({
            'med': np.median(all_roi_means),
            'q1': q1,
            'q3': q3,
            'whislo': max(np.min(all_roi_means[all_roi_means >= lower_whisker]), q1 - 1.5 * iqr),
            'whishi': min(np.max(all_roi_means[all_roi_means <= upper_whisker]), q3 + 1.5 * iqr),
            'mean': np.mean(all_roi_means),
            'fliers': all_roi_means[(all_roi_means < lower_whisker) | (all_roi_means > upper_whisker)]
        })
        
        # Create the boxplot
        box = ax2.bxp(box_stats, 
                     positions=positions,
                     widths=0.4,
                     patch_artist=True,
                     showfliers=False,  # We'll add outliers manually
                     boxprops=dict(
                         facecolor='lightblue',
                         color='steelblue',
                         linewidth=1.0,
                         alpha=0.8
                     ),
                     medianprops=dict(
                         color='crimson',
                         linewidth=1.5
                     ),
                     whiskerprops=dict(
                         color='steelblue',
                         linestyle='--',
                         linewidth=1.0
                     ),
                     capprops=dict(
                         color='steelblue',
                         linewidth=1.0
                     ))
        
        # Add individual data points with jitter and separate inliers/outliers
        jitter = 0.15
        x_jitter = np.random.uniform(1 - jitter, 1 + jitter, size=len(all_roi_means))
        
        # Separate inliers and outliers
        inliers = (all_roi_means >= lower_whisker) & (all_roi_means <= upper_whisker)
        outliers = ~inliers
        
        # Plot inliers with the same color as the box
        ax2.scatter(x_jitter[inliers], all_roi_means[inliers],
                   color='steelblue', s=25, alpha=0.9,
                   zorder=4, edgecolor='white', linewidth=0.8)
        
        # Plot outliers in red
        if np.any(outliers):
            ax2.scatter(x_jitter[outliers], all_roi_means[outliers],
                       color='red', s=30, alpha=0.7,
                       zorder=4, edgecolor='white', linewidth=0.8,
                       marker='o', label='Outliers')
    
    ax2.set_ylabel('Mean FRET Efficiency (%)', fontsize=10, labelpad=8)
    ax2.set_title('All ROIs Combined', fontsize=12, pad=12)
    ax2.set_ylim(0, df['mean_efficiency'].max() * 1.1)
    ax2.set_xticks([])  # Remove x-ticks since we only have one box
    ax2.grid(True, linestyle='--', alpha=0.3)
    
    # --- Box Plot 2: One Box per Image ---
    if not df.empty:
        # Group by image and get mean efficiency for each ROI
        image_roi_means = df.groupby('image_name')['mean_efficiency'].apply(list)
        
        # Calculate boxplot statistics for each image
        boxplot_stats = []
        positions = []
        position = 1
        
        for means in image_roi_means.values:
            if len(means) == 0:
                continue
                
            means = np.array(means)
            q1, q3 = np.percentile(means, [25, 75])
            iqr = q3 - q1
            lower_whisker = q1 - 1.5 * iqr
            upper_whisker = q3 + 1.5 * iqr
            
            boxplot_stats.append({
                'med': np.median(means),
                'q1': q1,
                'q3': q3,
                'whislo': max(np.min(means[means >= lower_whisker]), q1 - 1.5 * iqr),
                'whishi': min(np.max(means[means <= upper_whisker]), q3 + 1.5 * iqr),
                'mean': np.mean(means),
                'fliers': means[(means < lower_whisker) | (means > upper_whisker)]
            })
            positions.append(position)
            position += 1
        
        # Create the boxplot
        box = ax3.bxp(boxplot_stats, 
                     positions=positions,
                     widths=0.6,
                     patch_artist=True,
                     showfliers=False,  # We'll add outliers manually
                     boxprops=dict(
                         facecolor='lightgreen',
                         color='forestgreen',
                         linewidth=1.0,
                         alpha=0.8
                     ),
                     medianprops=dict(
                         color='crimson',
                         linewidth=1.5
                     ),
                     whiskerprops=dict(
                         color='forestgreen',
                         linestyle='--',
                         linewidth=1.0
                     ),
                     capprops=dict(
                         color='forestgreen',
                         linewidth=1.0
                     ))
        
        # Add individual data points with jitter and separate inliers/outliers
        jitter = 0.15
        for i, means in enumerate(image_roi_means.values, 1):
            if len(means) == 0:
                continue
                
            means = np.array(means)
            q1, q3 = np.percentile(means, [25, 75])
            iqr = q3 - q1
            lower_whisker = q1 - 1.5 * iqr
            upper_whisker = q3 + 1.5 * iqr
            
            x_jitter = np.random.uniform(i - jitter, i + jitter, size=len(means))
            inliers = (means >= lower_whisker) & (means <= upper_whisker)
            outliers = ~inliers
            
            # Plot inliers
            ax3.scatter(x_jitter[inliers], means[inliers],
                       color='forestgreen', s=25, alpha=0.9,
                       zorder=4, edgecolor='white', linewidth=0.8)
            
            # Plot outliers in red
            if np.any(outliers):
                ax3.scatter(x_jitter[outliers], means[outliers],
                           color='red', s=30, alpha=0.7,
                           zorder=4, edgecolor='white', linewidth=0.8,
                           marker='o')
        
        # Add legend for outliers if any
        if any(len(s['fliers']) > 0 for s in box_stats):
            ax3.scatter([], [], color='red', s=30, alpha=0.7,
                       edgecolor='white', linewidth=0.8, marker='o',
                       label='Outliers')
            ax3.legend(loc='upper right')
    
    ax3.set_xlabel('Image', fontsize=10, labelpad=8)
    ax3.set_ylabel('Mean FRET Efficiency (%)', fontsize=10, labelpad=8)
    ax3.set_title('FRET Efficiency by Image', fontsize=12, pad=12)
    ax3.set_ylim(0, df['mean_efficiency'].max() * 1.1)  # Same scale as first box plot
    if positions:  # Only set ticks if we have valid positions
        ax3.set_xticks(positions)
        ax3.set_xticklabels([f"{i}" for i in positions], rotation=45, fontsize=8, ha='right')
    ax3.grid(True, linestyle='--', alpha=0.3)
    
    # Add statistics
    if not df.empty:
        stats_text = (f"N = {len(df)} ROIs\n"
                     f"Mean = {df['mean_efficiency'].mean():.2f}%\n"
                     f"Median = {df['mean_efficiency'].median():.2f}%\n"
                     f"SD = {df['mean_efficiency'].std(ddof=1):.2f}")
        
        ax2.text(
            0.98, 0.98, stats_text,
            transform=ax2.transAxes,
            verticalalignment='top',
            horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8, 
                     edgecolor='lightgray', pad=0.5),
            fontsize=8
        )
    
    # Adjust layout to prevent label overlap
    fig.tight_layout()
    
    # Save figure
    output_path = os.path.join(output_dir, 'fret_efficiency_analysis.png')
    fig.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\nFigures saved to: {output_path}")
    
    # Calculate mean efficiency per image
    image_means = df.groupby('image_name')['mean_efficiency'].mean().to_dict()
    
    # Prepare return dictionary
    result_dict = {
        'bin_centers': centers,
        'mean_values': mean_hist,
        'sem_values': sem_hist,
        'roi_means': df.groupby('roi_id')['mean_efficiency'].mean().to_dict(),
        'image_means': image_means
    }
    
    return fig, result_dict

def main():
    try:
        # Set up plot style
        setup_plot_style()
        
        # Get the directory of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        print("Finding and processing image files...")
        # Find all matching file pairs
        file_pairs = find_matching_files(script_dir)
        
        if not file_pairs:
            print("No matching FRET and segmented image pairs found.")
            return None
            
        print(f"Found {len(file_pairs)} image pairs to process")
        
        # Load and process all images
        results, all_pixel_values = load_and_process_images(script_dir, file_pairs)
        
        if not results:
            print("No valid ROIs found in the images.")
            return None
            
        print(f"Processed {len(results)} ROIs with {len(all_pixel_values)} total pixels")
        
        # Process the image data
        df, all_pixel_values = process_image_data(results, all_pixel_values)
        
        # Create output directory if it doesn't exist
        output_dir = script_dir
        os.makedirs(output_dir, exist_ok=True)
        
        print("\nGenerating plots...")
        fig, results = create_fret_plots(df, all_pixel_values, output_dir)
        
        # Save the results to CSV for reference
        output_csv = os.path.join(output_dir, 'fret_efficiency_analysis_results.csv')
        df[['image_name', 'roi_id', 'mean_efficiency']].to_csv(output_csv, index=False)
        print(f"\nResults saved to: {output_csv}")
        
        # Show the plot (if running interactively)
        try:
            plt.show()
        except Exception as e:
            print(f"Note: Could not display plot: {str(e)}")
            
        return results
        
    except Exception as e:
        import traceback
        print(f"Error: {str(e)}")
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()
