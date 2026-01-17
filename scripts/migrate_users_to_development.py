#!/usr/bin/env python3
"""
Migrate or copy users and their related data from '(default)' Firestore to 'development' Firestore within the same project.

Usage:
  DEPLOYMENT_ENV=production GOOGLE_APPLICATION_CREDENTIALS=...</n+  python3 scripts/migrate_users_to_development.py \
    --move cluoZcF1KhQgSgaQofnCnhgV6Xj2 pcvq4mDVmzYSZe6YWgJx3411gYX2 8LnLzt6W9JM3sGFsPWvbGoVTrS32 \
           BqVhdHwSbuhLfEsOJIRf4XLYl9T2 temp_magic_9daee134452a xmM4At4jH3eeNfq69WpBqPyMg952 \
           temp_magic_8c3c075d7be4 cRgVlcIfJreHClacLd3ZrbjHTXz1 \
    --copy L7wwaH3Mo7bsFMx5IO3QLXAdWP52 87XIELppuGTRaUbwskzWVEpfCuB2 rjosTon9T8fOlwB7tz1uAjUupGE2 jYiuQjA4L9gQIrmH8gty5lGSbA32 \
    --yes

Notes:
  - Reads from '(default)' DB and writes to 'development' DB.
  - --move: after successful write to development, deletes from default.
  - --copy: writes to development, keeps source intact.
  - Collections migrated: users, properties (by hostId), reservations (by propertyId), knowledge_sources (by propertyId), knowledge_items (by propertyId), and properties/{id}/knowledge subcollection if present.
"""

import os
import sys
import json
import argparse
from typing import List, Dict, Any, Set

from firebase_admin import firestore as admin_firestore
import firebase_admin
from google.cloud import firestore_v1 as gc_firestore


def get_project_and_credentials():
    app = firebase_admin.get_app()
    credentials_obj = app.credential.get_credential()
    project_id = (
        app.project_id
        or os.environ.get('FIREBASE_PROJECT_ID')
        or os.environ.get('GOOGLE_CLOUD_PROJECT')
        or os.environ.get('GOOGLE_CLOUD_PROJECT_ID')
    )
    if not project_id:
        raise RuntimeError("Unable to resolve GCP project ID")
    return project_id, credentials_obj


def get_clients():
    # Ensure Admin initialized in production (default DB)
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    project_id, creds = get_project_and_credentials()
    src = gc_firestore.Client(project=project_id, credentials=creds, database='(default)')
    dst = gc_firestore.Client(project=project_id, credentials=creds, database='development')
    return src, dst


def copy_document(src_doc_ref, dst_doc_ref):
    snap = src_doc_ref.get()
    if not snap.exists:
        return False
    dst_doc_ref.set(snap.to_dict())
    return True


def migrate_users(user_ids: List[str], src: gc_firestore.Client, dst: gc_firestore.Client, move: bool) -> Set[str]:
    migrated_users: Set[str] = set()
    for uid in user_ids:
        s_ref = src.collection('users').document(uid)
        d_ref = dst.collection('users').document(uid)
        if copy_document(s_ref, d_ref):
            migrated_users.add(uid)
            if move:
                s_ref.delete()
    return migrated_users


def list_properties_for_hosts(host_ids: Set[str], client: gc_firestore.Client) -> List[str]:
    props = []
    # Fetch all properties and filter; hostId field may vary
    for doc in client.collection('properties').stream():
        data = doc.to_dict() or {}
        host_id = data.get('hostId') or data.get('host_id')
        if host_id in host_ids:
            props.append(doc.id)
    return props


def migrate_properties(property_ids: List[str], src: gc_firestore.Client, dst: gc_firestore.Client, move: bool) -> Set[str]:
    migrated: Set[str] = set()
    for pid in property_ids:
        if copy_document(src.collection('properties').document(pid), dst.collection('properties').document(pid)):
            migrated.add(pid)
            # Also migrate subcollection properties/{id}/knowledge if present
            try:
                subcol = src.collection('properties').document(pid).collection('knowledge')
                for subdoc in subcol.stream():
                    dst.collection('properties').document(pid).collection('knowledge').document(subdoc.id).set(subdoc.to_dict())
            except Exception:
                pass
            if move:
                src.collection('properties').document(pid).delete()
    return migrated


def migrate_collection_by_property(collection_name: str, property_ids: Set[str], src: gc_firestore.Client, dst: gc_firestore.Client, move: bool) -> int:
    count = 0
    col = src.collection(collection_name)
    # Scan all and filter by propertyId (schema variations accounted)
    for doc in col.stream():
        data = doc.to_dict() or {}
        prop_id = data.get('propertyId') or data.get('property_id')
        if prop_id in property_ids:
            dst.collection(collection_name).document(doc.id).set(data)
            count += 1
            if move:
                col.document(doc.id).delete()
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--move', nargs='*', default=[], help='User IDs to move (delete from default after copying)')
    parser.add_argument('--copy', nargs='*', default=[], help='User IDs to copy (keep in default)')
    parser.add_argument('--yes', action='store_true', help='Proceed without interactive confirmation')
    args = parser.parse_args()

    if not args.move and not args.copy:
        print('Provide at least one user ID via --move/--copy')
        sys.exit(2)

    # Ensure we are initialized (reads from production default via Admin)
    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    src, dst = get_clients()

    users_to_move = list(dict.fromkeys(args.move))
    users_to_copy = list(dict.fromkeys(args.copy))
    print('Plan:')
    print(f'  Move: {len(users_to_move)} users')
    print(f'  Copy: {len(users_to_copy)} users')
    if not args.yes:
        print('Aborting: --yes not provided')
        sys.exit(3)

    # Migrate users
    moved_users = migrate_users(users_to_move, src, dst, move=True)
    copied_users = migrate_users(users_to_copy, src, dst, move=False)
    all_user_ids = set(moved_users) | set(copied_users)
    print(f'Migrated users: {len(all_user_ids)}')

    # Properties for those users (hosts)
    property_ids = list_properties_for_hosts(all_user_ids, src)
    print(f'Found properties for users: {len(property_ids)}')
    migrated_props = migrate_properties(property_ids, src, dst, move=bool(users_to_move))
    print(f'Migrated properties: {len(migrated_props)}')

    # Related collections by propertyId
    for col in ['reservations', 'knowledge_sources', 'knowledge_items']:
        cnt = migrate_collection_by_property(col, set(migrated_props), src, dst, move=bool(users_to_move))
        print(f'Migrated {cnt} from {col}')

    print('Done')


if __name__ == '__main__':
    main()




