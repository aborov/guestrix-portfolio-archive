const fs = require('fs');
const path = require('path');
const glob = require('glob');

console.log('Starting build script...');

// Create dist directory if it doesn't exist
if (!fs.existsSync('dist')) {
    console.log('Creating dist directory...');
    fs.mkdirSync('dist');
}

// Copy files
const patterns = ['*.html', '*.css', '*.js', 'images', 'scripts'];
console.log('Processing patterns:', patterns);

patterns.forEach(pattern => {
    console.log('Processing pattern:', pattern);
    if (pattern === 'images' || pattern === 'scripts') {
        // Handle directory
        if (fs.existsSync(pattern)) {
            console.log(`Found ${pattern} directory`);
            const dest = path.join('dist', pattern);
            if (!fs.existsSync(dest)) {
                fs.mkdirSync(dest, { recursive: true });
            }
            const files = fs.readdirSync(pattern);
            console.log(`Found files in ${pattern}:`, files);
            files.forEach(f => {
                const srcPath = path.join(pattern, f);
                const destPath = path.join(dest, f);
                if (fs.lstatSync(srcPath).isDirectory()) {
                    if (!fs.existsSync(destPath)) {
                        fs.mkdirSync(destPath, { recursive: true });
                    }
                } else {
                    fs.copyFileSync(srcPath, destPath);
                    console.log('Copied file:', srcPath, 'to', destPath);
                }
            });
        }
    } else {
        // Handle glob patterns
        const files = glob.sync(pattern);
        console.log('Found files matching pattern', pattern, ':', files);

        // Filter out disabled pages
        const excludedFiles = ['pricing.html', 'stories.html'];
        const filteredFiles = files.filter(file => {
            const basename = path.basename(file);
            return !excludedFiles.includes(basename);
        });

        console.log('Files after filtering:', filteredFiles);
        filteredFiles.forEach(file => {
            const dest = path.join('dist', path.basename(file));
            fs.copyFileSync(file, dest);
            console.log('Copied file:', file, 'to', dest);
        });
    }
});

console.log('Build script completed');
