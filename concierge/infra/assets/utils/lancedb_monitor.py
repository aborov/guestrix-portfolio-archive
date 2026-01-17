#!/usr/bin/env python3
"""
LanceDB S3 Usage Monitor

This script helps monitor and analyze LanceDB S3 usage to identify optimization opportunities.
It provides functions to:
1. Check current LanceDB connection settings
2. Analyze query patterns
3. Provide recommendations for reducing S3 costs
"""

import os
import sys
import time
import logging
import argparse
import boto3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Default S3 bucket from environment
DEFAULT_S3_BUCKET = os.environ.get('LANCEDB_S3_BUCKET', 'guestrix-lancedb-storage')
DEFAULT_S3_PREFIX = 'lancedb'

def get_s3_request_metrics(bucket_name: str, days: int = 7) -> Dict[str, Any]:
    """
    Get S3 request metrics for the specified bucket over the last N days.

    Args:
        bucket_name: The S3 bucket name
        days: Number of days to analyze

    Returns:
        Dictionary with request metrics
    """
    try:
        # Create CloudWatch client
        cloudwatch = boto3.client('cloudwatch')

        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        # Define metrics to retrieve
        metrics = [
            'GetRequests',
            'PutRequests',
            'HeadRequests',
            'ListRequests',
            'BytesDownloaded',
            'BytesUploaded'
        ]

        results = {}

        # Get metrics for each request type
        for metric_name in metrics:
            response = cloudwatch.get_metric_statistics(
                Namespace='AWS/S3',
                MetricName=metric_name,
                Dimensions=[
                    {
                        'Name': 'BucketName',
                        'Value': bucket_name
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,  # Daily statistics
                Statistics=['Sum']
            )

            # Extract and store the data
            datapoints = response.get('Datapoints', [])
            if datapoints:
                # Sort by timestamp
                datapoints.sort(key=lambda x: x['Timestamp'])

                # Store the data
                results[metric_name] = {
                    'total': sum(point['Sum'] for point in datapoints),
                    'daily': [(point['Timestamp'].strftime('%Y-%m-%d'), point['Sum']) for point in datapoints]
                }
            else:
                results[metric_name] = {'total': 0, 'daily': []}

        return results

    except Exception as e:
        logging.error(f"Error getting S3 metrics: {e}")
        return {}

def analyze_s3_usage(metrics: Dict[str, Any]) -> List[str]:
    """
    Analyze S3 usage patterns and provide optimization recommendations.

    Args:
        metrics: S3 request metrics from get_s3_request_metrics()

    Returns:
        List of recommendations
    """
    recommendations = []

    # Check if we have metrics data
    if not metrics:
        recommendations.append("No S3 metrics data available. Make sure you have proper permissions.")
        return recommendations

    # Analyze GET requests (most expensive for LanceDB)
    get_requests = metrics.get('GetRequests', {}).get('total', 0)
    if get_requests > 1000:
        recommendations.append(f"High number of GET requests ({get_requests}). Consider increasing cache size and TTL.")

    # Analyze HEAD requests (metadata checks)
    head_requests = metrics.get('HeadRequests', {}).get('total', 0)
    if head_requests > 500:
        recommendations.append(f"High number of HEAD requests ({head_requests}). Consider caching table schemas.")

    # Analyze LIST requests (directory listings)
    list_requests = metrics.get('ListRequests', {}).get('total', 0)
    if list_requests > 100:
        recommendations.append(f"High number of LIST requests ({list_requests}). Consider caching table names.")

    # Analyze data transfer
    bytes_downloaded = metrics.get('BytesDownloaded', {}).get('total', 0)
    if bytes_downloaded > 1_000_000_000:  # 1 GB
        recommendations.append(f"High data transfer ({bytes_downloaded/1_000_000_000:.2f} GB). Consider batching queries and limiting result sizes.")

    # General recommendations
    recommendations.append("General recommendations:")
    recommendations.append("1. Use connection pooling to reuse LanceDB connections")
    recommendations.append("2. Increase cache TTL to at least 30 minutes for stable data")
    recommendations.append("3. Batch similar queries together to reduce S3 requests")
    recommendations.append("4. Cache table schemas to avoid repeated metadata lookups")
    recommendations.append("5. Consider setting LANCEDB_CACHE_SIZE=200 and LANCEDB_CACHE_TTL=1800 environment variables")

    return recommendations

def check_lancedb_settings() -> Dict[str, Any]:
    """
    Check current LanceDB settings and configuration.

    Returns:
        Dictionary with LanceDB settings
    """
    settings = {}

    # Check environment variables
    settings['LANCEDB_S3_URI'] = os.environ.get('LANCEDB_S3_URI')
    settings['LANCEDB_S3_BUCKET'] = os.environ.get('LANCEDB_S3_BUCKET')
    settings['LANCEDB_TABLE_NAME'] = os.environ.get('LANCEDB_TABLE_NAME')
    settings['LANCEDB_PATH'] = os.environ.get('LANCEDB_PATH')
    settings['LANCEDB_CACHE_SIZE'] = os.environ.get('LANCEDB_CACHE_SIZE')
    settings['LANCEDB_CACHE_TTL'] = os.environ.get('LANCEDB_CACHE_TTL')

    # Check if we can import LanceDB
    try:
        import lancedb
        settings['lancedb_version'] = getattr(lancedb, '__version__', 'unknown')
        settings['lancedb_available'] = True
    except ImportError:
        settings['lancedb_available'] = False

    # Check if we can import cache helpers
    try:
        try:
            from utils.cache_helpers import lancedb_cache
        except ImportError:
            from concierge.utils.cache_helpers import lancedb_cache

        if lancedb_cache:
            settings['cache_stats'] = lancedb_cache.get_stats()
            settings['cache_available'] = True
        else:
            settings['cache_available'] = False
    except ImportError:
        settings['cache_available'] = False

    return settings

def main():
    """Main function to run the LanceDB monitor."""
    parser = argparse.ArgumentParser(description='LanceDB S3 Usage Monitor')
    parser.add_argument('--bucket', type=str, help='S3 bucket name')
    parser.add_argument('--days', type=int, default=7, help='Number of days to analyze')
    parser.add_argument('--check-settings', action='store_true', help='Check LanceDB settings')
    parser.add_argument('--analyze', action='store_true', help='Analyze S3 usage and provide recommendations')

    args = parser.parse_args()

    # Determine bucket name
    bucket_name = args.bucket or DEFAULT_S3_BUCKET

    # Print header
    print("\n===== LanceDB S3 Usage Monitor =====\n")

    # Check LanceDB settings
    if args.check_settings:
        print("Checking LanceDB settings...")
        settings = check_lancedb_settings()

        print("\nLanceDB Configuration:")
        print(f"- LANCEDB_S3_URI: {settings.get('LANCEDB_S3_URI', 'Not set')}")
        print(f"- LANCEDB_S3_BUCKET: {settings.get('LANCEDB_S3_BUCKET', 'Not set')}")
        print(f"- LANCEDB_TABLE_NAME: {settings.get('LANCEDB_TABLE_NAME', 'Not set')}")
        print(f"- LANCEDB_PATH: {settings.get('LANCEDB_PATH', 'Not set')}")
        print(f"- LANCEDB_CACHE_SIZE: {settings.get('LANCEDB_CACHE_SIZE', 'Not set')}")
        print(f"- LANCEDB_CACHE_TTL: {settings.get('LANCEDB_CACHE_TTL', 'Not set')}")

        print("\nLanceDB Status:")
        print(f"- LanceDB available: {settings.get('lancedb_available', False)}")
        if settings.get('lancedb_available'):
            print(f"- LanceDB version: {settings.get('lancedb_version', 'unknown')}")

        print("\nCache Status:")
        print(f"- Cache available: {settings.get('cache_available', False)}")
        if settings.get('cache_available') and settings.get('cache_stats'):
            stats = settings.get('cache_stats', {})
            print(f"- Cache size: {stats.get('cache_size', 0)}/{stats.get('max_cache_size', 0)}")
            print(f"- Cache hit rate: {stats.get('hit_rate_percent', 0):.2f}%")
            print(f"- Cache hits: {stats.get('hits', 0)}")
            print(f"- Cache misses: {stats.get('misses', 0)}")
            print(f"- Cache TTL: {stats.get('ttl_seconds', 0)} seconds")
            print(f"- Cache enabled: {stats.get('enabled', False)}")

    # Analyze S3 usage
    if args.analyze:
        print(f"\nAnalyzing S3 usage for bucket '{bucket_name}' over the last {args.days} days...")
        metrics = get_s3_request_metrics(bucket_name, args.days)

        if metrics:
            print("\nS3 Request Metrics:")
            for metric_name, data in metrics.items():
                print(f"- {metric_name}: {data['total']}")

                # Print daily breakdown
                if data['daily']:
                    print("  Daily breakdown:")
                    for date, value in data['daily']:
                        print(f"  - {date}: {value}")

            print("\nRecommendations:")
            recommendations = analyze_s3_usage(metrics)
            for i, recommendation in enumerate(recommendations, 1):
                print(f"{recommendation}")
        else:
            print("No S3 metrics available. Make sure you have proper permissions.")

    # If no specific action requested, show help
    if not args.check_settings and not args.analyze:
        parser.print_help()

    print("\n===== End of Report =====\n")

if __name__ == "__main__":
    main()
