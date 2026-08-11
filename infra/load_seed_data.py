"""Create the sahayogi-programs DynamoDB table (if missing) and load seed data.

Usage:
    uv run python infra/load_seed_data.py

Requires valid AWS credentials with dynamodb:CreateTable / BatchWriteItem in
the target region (defaults to the CLI-configured region).
"""

import json
from decimal import Decimal
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = "sahayogi-programs"
SEED_FILE = Path(__file__).parent / "seed-data" / "programs.json"


def ensure_table(dynamodb) -> None:
    try:
        dynamodb.meta.client.describe_table(TableName=TABLE_NAME)
        print(f"Table {TABLE_NAME} already exists.")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    print(f"Creating table {TABLE_NAME} ...")
    table = dynamodb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "program_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "program_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    print("Table created.")


def load_seed(dynamodb) -> None:
    items = json.loads(SEED_FILE.read_text(encoding="utf-8"), parse_float=Decimal)
    table = dynamodb.Table(TABLE_NAME)
    with table.batch_writer(overwrite_by_pkeys=["program_id"]) as batch:
        for item in items:
            batch.put_item(Item=item)
    print(f"Loaded {len(items)} programs into {TABLE_NAME}.")


def main() -> None:
    dynamodb = boto3.resource("dynamodb")
    ensure_table(dynamodb)
    load_seed(dynamodb)


if __name__ == "__main__":
    main()
