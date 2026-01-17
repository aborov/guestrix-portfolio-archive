#!/usr/bin/env python3
"""
Cleanup DynamoDB records that reference properties missing from BOTH Firestore databases
('(default)' and 'development').

By default, this is a dry run that prints counts. Pass --yes to actually delete.

Environment:
- Uses AWS_DEFAULT_REGION/AWS_REGION (default us-east-2)
- Uses CONVERSATIONS_TABLE_NAME (default 'Conversations')
- Optional CONNECTIONS_TABLE_NAME for WebSocket connections table
- Requires GOOGLE_APPLICATION_CREDENTIALS or default application credentials

Run (production credentials):
  DEPLOYMENT_ENV=production \
  GOOGLE_APPLICATION_CREDENTIALS=... \
  python3 scripts/cleanup_orphaned_dynamodb.py --yes
"""
import os
import sys
import json
import argparse
from typing import Dict, List, Optional, Tuple, Set

import boto3
import firebase_admin
from google.cloud import firestore_v1 as gc_firestore


def init_firestore_clients() -> Tuple[gc_firestore.Client, gc_firestore.Client]:
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    app = firebase_admin.get_app()
    creds = app.credential.get_credential()
    project_id = (
        app.project_id
        or os.getenv('FIREBASE_PROJECT_ID')
        or os.getenv('GOOGLE_CLOUD_PROJECT')
        or os.getenv('GOOGLE_CLOUD_PROJECT_ID')
    )
    fs_default = gc_firestore.Client(project=project_id, credentials=creds, database='(default)')
    fs_dev = gc_firestore.Client(project=project_id, credentials=creds, database='development')
    return fs_default, fs_dev


def init_dynamodb():
    region = os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION') or 'us-east-2'
    return boto3.resource('dynamodb', region_name=region)


def extract_property_id(item: Dict) -> Optional[str]:
    pid = item.get('PropertyId') or item.get('propertyId') or item.get('property_id')
    if not pid:
        pk = item.get('PK') or item.get('pk')
        if isinstance(pk, str) and pk.startswith('PROPERTY#'):
            pid = pk.split('#', 1)[1]
    return pid


def build_property_existence_map(property_ids: Set[str], fs_default: gc_firestore.Client, fs_dev: gc_firestore.Client) -> Tuple[Dict[str, bool], Dict[str, bool]]:
    exists_default: Dict[str, bool] = {}
    exists_dev: Dict[str, bool] = {}
    for pid in property_ids:
        exists_default[pid] = fs_default.collection('properties').document(pid).get().exists
        exists_dev[pid] = fs_dev.collection('properties').document(pid).get().exists
    return exists_default, exists_dev


def scan_conversations(table) -> List[Dict]:
    items: List[Dict] = []
    scan_kwargs = {
        'ProjectionExpression': 'PK, SK, PropertyId'
    }
    resp = table.scan(**scan_kwargs)
    items.extend(resp.get('Items', []))
    while 'LastEvaluatedKey' in resp:
        resp = table.scan(ExclusiveStartKey=resp['LastEvaluatedKey'], **scan_kwargs)
        items.extend(resp.get('Items', []))
    return items


def scan_connections(table) -> List[Dict]:
    items: List[Dict] = []
    scan_kwargs = {
        'ProjectionExpression': 'connectionId, propertyId, property_id'
    }
    resp = table.scan(**scan_kwargs)
    items.extend(resp.get('Items', []))
    while 'LastEvaluatedKey' in resp:
        resp = table.scan(ExclusiveStartKey=resp['LastEvaluatedKey'], **scan_kwargs)
        items.extend(resp.get('Items', []))
    return items


def delete_conversations(items: List[Dict], table) -> int:
    # BatchWrite: 25 per batch
    deleted = 0
    with table.batch_writer() as batch:
        for it in items:
            pk = it['PK']
            sk = it['SK']
            batch.delete_item(Key={'PK': pk, 'SK': sk})
            deleted += 1
    return deleted


def delete_connections(items: List[Dict], table) -> int:
    deleted = 0
    with table.batch_writer() as batch:
        for it in items:
            cid = it.get('connectionId')
            if cid:
                batch.delete_item(Key={'connectionId': cid})
                deleted += 1
    return deleted


def main():
    parser = argparse.ArgumentParser(description='Cleanup DynamoDB items referencing properties missing in both Firestore DBs')
    parser.add_argument('--yes', action='store_true', help='Actually perform deletions')
    args = parser.parse_args()

    fs_default, fs_dev = init_firestore_clients()
    dynamodb = init_dynamodb()

    convo_table_name = os.getenv('CONVERSATIONS_TABLE_NAME', 'Conversations')
    conversations = dynamodb.Table(convo_table_name)

    # Optional connections table
    connections = None
    connections_table_name = os.getenv('CONNECTIONS_TABLE_NAME')
    if connections_table_name:
        try:
            connections = dynamodb.Table(connections_table_name)
        except Exception:
            connections = None

    convo_items = scan_conversations(conversations)
    convo_pids: Set[str] = set()
    for it in convo_items:
        pid = extract_property_id(it)
        if pid:
            convo_pids.add(pid)

    exists_default, exists_dev = build_property_existence_map(convo_pids, fs_default, fs_dev)

    # Conversations to delete: property missing from both DBs
    convo_to_delete: List[Dict] = []
    for it in convo_items:
        pid = extract_property_id(it)
        if not pid:
            continue
        if not exists_default.get(pid, False) and not exists_dev.get(pid, False):
            convo_to_delete.append({'PK': it['PK'], 'SK': it['SK'], 'PropertyId': pid})

    # Connections cleanup (best-effort)
    conn_items = []
    conn_to_delete: List[Dict] = []
    if connections is not None:
        try:
            conn_items = scan_connections(connections)
            for it in conn_items:
                pid = it.get('propertyId') or it.get('property_id')
                if not pid:
                    continue
                if not exists_default.get(pid, False) and not exists_dev.get(pid, False):
                    cid = it.get('connectionId')
                    if cid:
                        conn_to_delete.append({'connectionId': cid, 'propertyId': pid})
        except Exception:
            pass

    result = {
        'conversations': {
            'scanned': len(convo_items),
            'unique_property_ids_seen': len(convo_pids),
            'to_delete_missing_in_both': len(convo_to_delete),
            'sample': convo_to_delete[:5],
        },
        'connections': {
            'scanned': len(conn_items),
            'to_delete_missing_in_both': len(conn_to_delete),
            'sample': conn_to_delete[:5],
            'table': connections_table_name or ''
        },
        'will_delete': args.yes,
        'tables': {
            'conversations': convo_table_name,
            'connections': connections_table_name or ''
        }
    }

    print(json.dumps(result, indent=2))

    if args.yes:
        deleted_convos = delete_conversations(convo_to_delete, conversations) if convo_to_delete else 0
        deleted_conns = delete_connections(conn_to_delete, connections) if (connections and conn_to_delete) else 0
        print(json.dumps({'deleted': {'conversations': deleted_convos, 'connections': deleted_conns}}, indent=2))


if __name__ == '__main__':
    sys.exit(main())


