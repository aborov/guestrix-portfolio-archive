#!/usr/bin/env node

/**
 * Simple Image Optimization Script using imagemin
 * 
 * This script optimizes images using imagemin with plugins:
 * - imagemin-mozjpeg for JPEG compression
 * - imagemin-pngquant for PNG compression
 * 
 * Usage:
 * npm run optimize-images-simple
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Configuration
const IMAGES_DIR = path.join(__dirname, '../images');
const BACKUP_DIR = path.join(__dirname, '../images-backup');

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

function installDependencies() {
    const packages = [
        'imagemin',
        'imagemin-mozjpeg',
        'imagemin-pngquant'
    ];
    
    log('📦 Installing optimization dependencies...');
    try {
        execSync(`npm install ${packages.join(' ')}`, { stdio: 'inherit' });
        log('✅ Dependencies installed');
    } catch (error) {
        log('❌ Failed to install dependencies');
        process.exit(1);
    }
}

function createBackup() {
    if (!fs.existsSync(BACKUP_DIR)) {
        fs.mkdirSync(BACKUP_DIR, { recursive: true });
        log(`📁 Created backup directory: ${BACKUP_DIR}`);
    }
    
    const images = fs.readdirSync(IMAGES_DIR)
        .filter(file => ['.png', '.jpg', '.jpeg'].includes(path.extname(file).toLowerCase()));
    
    images.forEach(image => {
        const sourcePath = path.join(IMAGES_DIR, image);
        const backupPath = path.join(BACKUP_DIR, image);
        
        if (!fs.existsSync(backupPath)) {
            fs.copyFileSync(sourcePath, backupPath);
        }
    });
    
    log(`✅ Backup complete (${images.length} images)`);
}

async function optimizeImages() {
    log('🚀 Starting image optimization...');
    
    // Install dependencies if needed
    try {
        require('imagemin');
    } catch (error) {
        installDependencies();
    }
    
    const imagemin = require('imagemin');
    const imageminMozjpeg = require('imagemin-mozjpeg').default || require('imagemin-mozjpeg');
    const imageminPngquant = require('imagemin-pngquant').default || require('imagemin-pngquant');
    
    // Create backup
    createBackup();
    
    // Get current images and sizes
    const images = fs.readdirSync(IMAGES_DIR)
        .filter(file => ['.png', '.jpg', '.jpeg'].includes(path.extname(file).toLowerCase()));
    
    log(`📸 Found ${images.length} images to optimize`);
    
    const beforeSizes = {};
    images.forEach(image => {
        beforeSizes[image] = getFileSize(path.join(IMAGES_DIR, image));
    });
    
    // Optimize images
    try {
        const files = await imagemin([`${IMAGES_DIR}/*.{jpg,jpeg,png}`], {
            destination: IMAGES_DIR,
            plugins: [
                imageminMozjpeg({ quality: 85 }),
                imageminPngquant({ quality: [0.6, 0.8] })
            ]
        });
        
        log(`✅ Optimized ${files.length} images`);
        
        // Calculate savings
        let totalSavings = 0;
        const results = [];
        
        images.forEach(image => {
            const imagePath = path.join(IMAGES_DIR, image);
            if (fs.existsSync(imagePath)) {
                const beforeSize = beforeSizes[image];
                const afterSize = getFileSize(imagePath);
                const savings = beforeSize - afterSize;
                const savingsPercent = ((savings / beforeSize) * 100).toFixed(1);
                
                if (savings > 0) {
                    totalSavings += savings;
                    results.push({
                        filename: image,
                        beforeSize,
                        afterSize,
                        savings,
                        savingsPercent
                    });
                    
                    log(`✅ ${image}: ${formatBytes(beforeSize)} → ${formatBytes(afterSize)} (${savingsPercent}% smaller)`);
                }
            }
        });
        
        // Summary
        log('\n📊 OPTIMIZATION SUMMARY');
        log('═'.repeat(50));
        
        if (results.length > 0) {
            log(`💾 Total savings: ${formatBytes(totalSavings)}`);
            log(`📈 Average reduction: ${(results.reduce((sum, r) => sum + parseFloat(r.savingsPercent), 0) / results.length).toFixed(1)}%`);
            log(`📁 Original images backed up to: ${BACKUP_DIR}`);
        } else {
            log('ℹ️  No significant compression achieved');
        }
        
        log('\n✅ Optimization complete!');
        
    } catch (error) {
        log(`❌ Optimization failed: ${error.message}`);
        process.exit(1);
    }
}

// Run the optimization
if (require.main === module) {
    optimizeImages().catch(error => {
        console.error('❌ Optimization failed:', error);
        process.exit(1);
    });
}

module.exports = { optimizeImages };
