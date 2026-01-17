#!/usr/bin/env node

/**
 * Image Optimization Script
 * 
 * This script optimizes images using:
 * 1. Squoosh CLI (free, local processing)
 * 2. TinyPNG API (optional, requires API key)
 * 
 * Usage:
 * npm run optimize-images
 * npm run optimize-images -- --tinypng-key YOUR_API_KEY
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Configuration
const IMAGES_DIR = path.join(__dirname, '../images');
const BACKUP_DIR = path.join(__dirname, '../images-backup');
const SUPPORTED_FORMATS = ['.png', '.jpg', '.jpeg'];

// Parse command line arguments
const args = process.argv.slice(2);
const tinypngKey = args.find(arg => arg.startsWith('--tinypng-key='))?.split('=')[1];
const dryRun = args.includes('--dry-run');
const verbose = args.includes('--verbose');

function log(message) {
    console.log(`[IMAGE-OPT] ${message}`);
}

function checkDependencies() {
    try {
        execSync('npx @squoosh/cli --version', { stdio: 'ignore' });
        log('✅ Squoosh CLI available');
    } catch (error) {
        log('❌ Squoosh CLI not found. Installing...');
        try {
            execSync('npm install -g @squoosh/cli', { stdio: 'inherit' });
            log('✅ Squoosh CLI installed');
        } catch (installError) {
            log('❌ Failed to install Squoosh CLI. Please install manually: npm install -g @squoosh/cli');
            process.exit(1);
        }
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
            if (verbose) log(`📋 Backed up: ${image}`);
        }
    });
    
    log(`✅ Backup complete (${images.length} images)`);
}

function getFileSize(filePath) {
    const stats = fs.statSync(filePath);
    return stats.size;
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

async function optimizeWithSquoosh(imagePath) {
    const ext = path.extname(imagePath).toLowerCase();
    const outputPath = imagePath.replace(ext, '_optimized' + ext);
    
    try {
        let command;
        if (ext === '.png') {
            // PNG optimization
            command = `npx @squoosh/cli --oxipng '{"level":3}' "${imagePath}" -d "${path.dirname(imagePath)}"`;
        } else {
            // JPEG optimization
            command = `npx @squoosh/cli --mozjpeg '{"quality":85}' "${imagePath}" -d "${path.dirname(imagePath)}"`;
        }
        
        if (verbose) log(`🔧 Running: ${command}`);
        
        if (!dryRun) {
            execSync(command, { stdio: verbose ? 'inherit' : 'ignore' });
            
            // Check if optimized file was created
            const optimizedPath = imagePath.replace(ext, ext);
            if (fs.existsSync(optimizedPath)) {
                return optimizedPath;
            }
        }
        
        return imagePath;
    } catch (error) {
        log(`❌ Squoosh failed for ${path.basename(imagePath)}: ${error.message}`);
        return imagePath;
    }
}

async function optimizeWithTinyPNG(imagePath, apiKey) {
    if (!apiKey) return imagePath;
    
    try {
        const tinify = require('tinify');
        tinify.key = apiKey;
        
        const source = tinify.fromFile(imagePath);
        const outputPath = imagePath.replace(path.extname(imagePath), '_tiny' + path.extname(imagePath));
        
        if (!dryRun) {
            await source.toFile(outputPath);
            return outputPath;
        }
        
        return imagePath;
    } catch (error) {
        log(`❌ TinyPNG failed for ${path.basename(imagePath)}: ${error.message}`);
        return imagePath;
    }
}

async function optimizeImages() {
    log('🚀 Starting image optimization...');
    
    if (dryRun) {
        log('🔍 DRY RUN MODE - No files will be modified');
    }
    
    // Check dependencies
    checkDependencies();
    
    // Create backup
    if (!dryRun) {
        createBackup();
    }
    
    // Get all images
    const images = fs.readdirSync(IMAGES_DIR)
        .filter(file => SUPPORTED_FORMATS.includes(path.extname(file).toLowerCase()))
        .map(file => path.join(IMAGES_DIR, file));
    
    log(`📸 Found ${images.length} images to optimize`);
    
    let totalSavings = 0;
    const results = [];
    
    for (const imagePath of images) {
        const originalSize = getFileSize(imagePath);
        const filename = path.basename(imagePath);
        
        log(`\n🔄 Processing: ${filename} (${formatBytes(originalSize)})`);
        
        try {
            // Try Squoosh first (free)
            let optimizedPath = await optimizeWithSquoosh(imagePath);
            
            // Try TinyPNG if API key provided
            if (tinypngKey && !dryRun) {
                optimizedPath = await optimizeWithTinyPNG(optimizedPath, tinypngKey);
            }
            
            if (!dryRun && optimizedPath !== imagePath) {
                const optimizedSize = getFileSize(optimizedPath);
                const savings = originalSize - optimizedSize;
                const savingsPercent = ((savings / originalSize) * 100).toFixed(1);
                
                // Replace original with optimized
                fs.renameSync(optimizedPath, imagePath);
                
                totalSavings += savings;
                results.push({
                    filename,
                    originalSize,
                    optimizedSize,
                    savings,
                    savingsPercent
                });
                
                log(`✅ ${filename}: ${formatBytes(originalSize)} → ${formatBytes(optimizedSize)} (${savingsPercent}% smaller)`);
            } else if (dryRun) {
                log(`🔍 Would optimize: ${filename}`);
            }
        } catch (error) {
            log(`❌ Failed to optimize ${filename}: ${error.message}`);
        }
    }
    
    // Summary
    log('\n📊 OPTIMIZATION SUMMARY');
    log('═'.repeat(50));
    
    if (!dryRun && results.length > 0) {
        results.forEach(result => {
            log(`${result.filename}: ${result.savingsPercent}% smaller`);
        });
        
        log(`\n💾 Total savings: ${formatBytes(totalSavings)}`);
        log(`📈 Average reduction: ${(results.reduce((sum, r) => sum + parseFloat(r.savingsPercent), 0) / results.length).toFixed(1)}%`);
    }
    
    log(`\n✅ Optimization complete!`);
    if (!dryRun) {
        log(`📁 Original images backed up to: ${BACKUP_DIR}`);
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
