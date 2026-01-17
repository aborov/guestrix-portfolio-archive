#!/usr/bin/env python3
import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Generate a QR code for a property's magic link")
    parser.add_argument('--property-id', required=True, help='Property ID in Firestore')
    parser.add_argument('--domain', default='guestrix.ai', help='Base domain to use (default: guestrix.ai)')
    parser.add_argument('--output', default=None, help='Output PNG path (default: ./qr_<property_id>.png)')
    parser.add_argument('--token', default=None, help='Explicit magic link token to use (optional)')
    args = parser.parse_args()

    try:
        # Lazy import to ensure repo path is on sys.path
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        from concierge.utils.firestore_client import (
            get_property,
            get_property_magic_link_token,
            create_property_magic_link,
        )
    except Exception as e:
        print(f"Failed to import Firestore client: {e}", file=sys.stderr)
        sys.exit(1)

    property_id = args.property_id

    # Resolve magic link token
    token = args.token
    if not token:
        try:
            token = get_property_magic_link_token(property_id)
        except Exception:
            token = None
        if not token:
            try:
                token = create_property_magic_link(property_id)
            except Exception as e:
                print(f"Failed to get or create magic link token: {e}", file=sys.stderr)
                sys.exit(1)

    if not token:
        print("No magic link token available for property.", file=sys.stderr)
        sys.exit(1)

    magic_url = f"https://{args.domain}/magic/{token}"

    # Generate QR code
    try:
        import qrcode
    except ImportError:
        print("The 'qrcode' package is required. Install with: pip install qrcode[pil]", file=sys.stderr)
        sys.exit(1)

    img = qrcode.make(magic_url)
    output_path = args.output or os.path.abspath(f"qr_{property_id}.png")
    img.save(output_path)

    # Optional: print basic property info
    try:
        prop = get_property(property_id)
    except Exception:
        prop = None

    print("QR code generated")
    print(f"URL: {magic_url}")
    print(f"Saved: {output_path}")
    if prop:
        name = prop.get('name') or prop.get('title') or ''
        address = prop.get('address') or ''
        print(f"Property: {name} | {address}")


if __name__ == '__main__':
    main()



