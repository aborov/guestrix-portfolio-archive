# Image Optimization Guide

## Current Image Issues
Some images are very large and slow to load:
- `frustrated-host.png`: 1.8MB
- `happy-guest-family.png`: 5.0MB 
- `staycee-closeup.png`: 1.6MB
- `staycee-iphone.png`: 1.2MB
- `happy-host.png`: 1.3MB

## Optimization Strategies Implemented

### 1. Lazy Loading
- Added `loading="lazy"` attribute to all non-critical images
- Images load only when they're about to enter the viewport
- Reduces initial page load time

### 2. Image Preloading
- Added preload hints for critical images (logo, first visible image)
- Browser starts downloading these images immediately

### 3. CSS Optimizations
- Added smooth fade-in transitions for lazy-loaded images
- Responsive image sizing with `max-width: 100%`

### 4. JavaScript Enhancement
- Intersection Observer API for smooth lazy loading
- Fallback for older browsers

## Automated Image Optimization

### 🤖 CLI Tool Available!
We've created an automated optimization script that uses:
- **Squoosh CLI** (free, local processing)
- **TinyPNG API** (optional, requires API key)

### Usage:
```bash
# Dry run (see what would be optimized)
npm run optimize-images-dry

# Optimize images with Squoosh (free)
npm run optimize-images

# Optimize with TinyPNG API (requires key)
npm run optimize-images -- --tinypng-key YOUR_API_KEY
```

### Setup TinyPNG API (Optional):
1. Sign up at https://tinypng.com/developers
2. Get your free API key (500 compressions/month)
3. Run: `npm run optimize-images -- --tinypng-key YOUR_KEY`

## Manual Optimization Tools

### 1. Image Compression
Use tools like:
- **TinyPNG** (online): https://tinypng.com/
- **ImageOptim** (Mac): https://imageoptim.com/
- **Squoosh** (online): https://squoosh.app/

Target sizes:
- Hero images: < 500KB
- Section images: < 300KB
- Icons/logos: < 100KB

### 2. Modern Image Formats
Consider converting to:
- **WebP**: 25-35% smaller than PNG/JPEG
- **AVIF**: 50% smaller than JPEG (newer format)

### 3. Responsive Images
Use `srcset` for different screen sizes:
```html
<img src="image-800w.jpg" 
     srcset="image-400w.jpg 400w, 
             image-800w.jpg 800w, 
             image-1200w.jpg 1200w"
     sizes="(max-width: 600px) 400px, 
            (max-width: 1000px) 800px, 
            1200px"
     alt="Description">
```

### 4. CDN Implementation
Consider using a CDN like:
- Cloudflare Images
- AWS CloudFront
- Vercel Image Optimization

## Quick Wins
1. Compress existing PNG files to reduce size by 60-80%
2. Convert decorative images to WebP format
3. Add width/height attributes to prevent layout shift
