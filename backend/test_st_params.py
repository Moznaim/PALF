import numpy as np
import cv2

# Synthetic directional texture simulating aligned PALF fiber bundle
np.random.seed(42)
h, w = 762, 1200
# Aligned vertical fibers with some noise
y_coords, x_coords = np.mgrid[0:h, 0:w]
freq = 0.2
fiber_pattern = np.sin(2 * np.pi * freq * x_coords) + 0.3 * np.random.randn(h, w)
fiber_pattern = ((fiber_pattern - fiber_pattern.min()) / (fiber_pattern.max() - fiber_pattern.min()) * 255).astype(np.uint8)

mask = np.ones((h, w), dtype=bool)

gray_f = fiber_pattern.astype(np.float64) / 255.0
Ix = cv2.Sobel(gray_f, cv2.CV_64F, 1, 0, ksize=3)
Iy = cv2.Sobel(gray_f, cv2.CV_64F, 0, 1, ksize=3)

Jxx = Ix * Ix
Jyy = Iy * Iy
Jxy = Ix * Iy

for sigma in [1.0, 1.5, 2.0, 2.5, 3.0]:
    for ksize in [(5, 5), (7, 7), (9, 9)]:
        Jxx_s = cv2.GaussianBlur(Jxx, ksize, sigma)
        Jyy_s = cv2.GaussianBlur(Jyy, ksize, sigma)
        Jxy_s = cv2.GaussianBlur(Jxy, ksize, sigma)
        
        coh = np.sqrt((Jxx_s - Jyy_s)**2 + 4 * Jxy_s**2) / (Jxx_s + Jyy_s + 1e-6)
        theta = 0.5 * np.arctan2(2 * Jxy_s, Jxx_s - Jyy_s)
        
        theta_m = theta[mask]
        C = np.mean(np.cos(2 * theta_m))
        S = np.mean(np.sin(2 * theta_m))
        R = np.sqrt(C**2 + S**2)
        spread = 0.5 * np.sqrt(-2 * np.log(max(R, 1e-6))) * (180.0 / np.pi)
        
        print(f"sigma={sigma}, ksize={ksize} -> coh_mean={coh.mean():.4f}, R={R:.4f}, spread={spread:.2f} deg")
        break
