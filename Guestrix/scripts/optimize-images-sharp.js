#!/usr/bin/env node

/**
 * Image Optimization Script using Sharp
 * 
 * Sharp is a high-performance image processing library
 * that's very reliable and widely used.
 * 
 * Usage:
 * npm run optimize-images-sharp
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Configuration
const IMAGES_DIR = path.join(__dirname, '../images');
const BACKUP_DIR = path.join(__dirname, '../images-backup');
const SUPPORTED_FORMATS = ['.png', '.jpg', '.jpeg'];

function log(message) {
    console.log(`[IMAGE-OPT] ${message}`);
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function getFileSize(filePath) {
    const stats = fs.statSync(filePath);
    return stats.size;
}

function installSharp() {
    log('📦 Installing Sharp...');
    try {
        execSync('npm install sharp', { stdio: 'inherit' });
        log('✅ Sharp installed');
    } catch (error) {
        log('❌ Failed to install Sharp');
        process.exit(1);
    }
}

function createBackup() {
    if (!fs.existsSync(BACKUP_DIR)) {
        fs.mkdirSync(BACKUP_DIR, { recursive: true });
        log(`📁 Created backup directory: ${BACKUP_DIR}`);
    }
    
    const images = fs.readdirSync(IMAGES_DIR)
        .filter(file => SUPPORTED_FORMATS.includes(path.extname(file).toLowerCase()));
    
    images.forEach(image => {
        const sourcePath = path.join(IMAGES_DIR, image);
        const backupPath = path.join(BACKUP_DIR, image);
        
        if (!fs.existsSync(backupPath)) {
            fs.copyFileSync(sourcePath, backupPath);
        }
    });
    
    log(`✅ Backup complete (${images.length} images)`);
}

async function optimizeImage(imagePath, sharp) {
    const ext = path.extname(imagePath).toLowerCase();
    const originalSize = getFileSize(imagePath);
    
    try {
        let pipeline = sharp(imagePath);
        
        if (ext === '.png') {
            // PNG optimization
            await pipeline
                .png({ 
                    quality: 80,
                    compressionLevel: 9,
                    palette: true
                })
                .toFile(imagePath + '.tmp');
        } else if (ext === '.jpg' || ext === '.jpeg') {
            // JPEG optimization
            await pipeline
                .jpeg({ 
                    quality: 85,
                    progressive: true,
                    mozjpeg: true
                })
                .toFile(imagePath + '.tmp');
        }
        
        // Replace original with optimized
        const tempPath = imagePath + '.tmp';
        if (fs.existsSync(tempPath)) {
            const optimizedSize = getFileSize(tempPath);
            
            // Only replace if we actually saved space
            if (optimizedSize < originalSize) {
                fs.renameSync(tempPath, imagePath);
                const savings = originalSize - optimizedSize;
                const savingsPercent = ((savings / originalSize) * 100).toFixed(1);
                
                return {
                    success: true,
                    originalSize,
                    optimizedSize,
                    savings,
                    savingsPercent
                };
            } else {
                // Remove temp file if no savings
                fs.unlinkSync(tempPath);
                return {
                    success: false,
                    reason: 'No size reduction achieved'
                };
            }
        }
        
        return {
            success: false,
            reason: 'Optimization failed'
        };
        
    } catch (error) {
        // Clean up temp file if it exists
        const tempPath = imagePath + '.tmp';
        if (fs.existsSync(tempPath)) {
            fs.unlinkSync(tempPath);
        }
        
        return {
            success: false,
            reason: error.message
        };
    }
}

async function optimizeImages(specificFile = null) {
    log('🚀 Starting image optimization with Sharp...');
    
    // Install Sharp if needed
    let sharp;
    try {
        sharp = require('sharp');
    } catch (error) {
        installSharp();
        sharp = require('sharp');
    }
    
    // Create backup
    createBackup();
    
    // Get images to process
    let images;
    if (specificFile) {
        const specificPath = path.join(IMAGES_DIR, specificFile);
        if (fs.existsSync(specificPath) && SUPPORTED_FORMATS.includes(path.extname(specificFile).toLowerCase())) {
            images = [specificPath];
            log(`📸 Optimizing specific file: ${specificFile}`);
        } else {
            log(`❌ File not found or unsupported format: ${specificFile}`);
            return;
        }
    } else {
        images = fs.readdirSync(IMAGES_DIR)
            .filter(file => SUPPORTED_FORMATS.includes(path.extname(file).toLowerCase()))
            .map(file => path.join(IMAGES_DIR, file));
        log(`📸 Found ${images.length} images to optimize`);
    }
    
    let totalSavings = 0;
    const results = [];
    
    for (const imagePath of images) {
        const filename = path.basename(imagePath);
        const originalSize = getFileSize(imagePath);
        
        log(`\n🔄 Processing: ${filename} (${formatBytes(originalSize)})`);
        
        const result = await optimizeImage(imagePath, sharp);
        
        if (result.success) {
            totalSavings += result.savings;
            results.push({
                filename,
                ...result
            });
            
            log(`✅ ${filename}: ${formatBytes(result.originalSize)} → ${formatBytes(result.optimizedSize)} (${result.savingsPercent}% smaller)`);
        } else {
            log(`ℹ️  ${filename}: ${result.reason}`);
        }
    }
    
    // Summary
    log('\n📊 OPTIMIZATION SUMMARY');
    log('═'.repeat(50));
    
    if (results.length > 0) {
        results.forEach(result => {
            log(`${result.filename}: ${result.savingsPercent}% smaller`);
        });
        
        log(`\n💾 Total savings: ${formatBytes(totalSavings)}`);
        log(`📈 Average reduction: ${(results.reduce((sum, r) => sum + parseFloat(r.savingsPercent), 0) / results.length).toFixed(1)}%`);
        log(`📁 Original images backed up to: ${BACKUP_DIR}`);
    } else {
        log('ℹ️  No images were optimized (no size reduction achieved)');
    }
    
    log('\n✅ Optimization complete!');
}

// Run the optimization
if (require.main === module) {
    // Check for specific file argument
    const args = process.argv.slice(2);
    const specificFile = args.find(arg => !arg.startsWith('--'));
    
    optimizeImages(specificFile).catch(error => {
        console.error('❌ Optimization failed:', error);
        process.exit(1);
    });
}

module.exports = { optimizeImages };
