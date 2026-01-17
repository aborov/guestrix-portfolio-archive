# Script to reset the waitlist function and storage
# Usage: .\reset-function.ps1
#
# This script automates the removal of the waitlist function and storage.
# After running this script, you will need to manually recreate the resources.
#
# MANUAL STEPS AFTER RUNNING THIS SCRIPT:
# 1. Add Storage (DynamoDB):
#    - Run: amplify add storage
#    - Select: NoSQL Database
#    - Table name: WaitList
#    - Partition key: id (string)
#    - No sort key needed
#    - Add columns:
#      * firstName (string)
#      * lastName (string)
#      * email (string)
#      * createdAt (string)
#
# 2. Add Function:
#    - Run: amplify add function
#    - Select: Lambda function
#    - Name: waitlistapi
#    - Runtime: nodejs
#    - Template: serverless-express
#    - Advanced settings: yes
#    - Environment variables: no
#    - Lambda trigger: no
#
# 3. Restore Function Code:
#    - Copy the contents from the backup directory (shown in script output)
#    - Paste into amplify/backend/function/waitlistapi/src/
#
# 4. Push Changes:
#    - Run: amplify push --yes

# Set error action preference
$ErrorActionPreference = "Stop"

# Get the project root directory
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Split-Path -Parent $projectRoot

# Set working directory
Set-Location $projectRoot

# Create backup directory if it doesn't exist
$backupDir = Join-Path $projectRoot "amplify/backups"
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

# Create timestamp for backup
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $backupDir "waitlistapi-backup-$timestamp"

# Backup current function and storage
Write-Host "Backing up current function and storage..."
if (Test-Path "amplify/backend/function/waitlistapi") {
    Copy-Item -Path "amplify/backend/function/waitlistapi" -Destination $backupPath -Recurse
    Write-Host "Backup created at: $backupPath"
}

# Remove function
Write-Host "Removing function..."
amplify remove function --yes

# Remove storage
Write-Host "Removing storage..."
amplify remove storage --yes

Write-Host "`nAutomated removal complete! Please follow the manual steps documented above to recreate the resources."
Write-Host "Backup location: $backupPath" 