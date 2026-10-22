import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
sfn = boto3.client("stepfunctions")


def to_json(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Not serializable: {type(obj)}")


def response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, default=to_json),
    }


def handler(event, context):
    method = event["httpMethod"]

    if method == "POST":
        data = json.loads(event.get("body") or "{}")
        item = {
            "orderId": str(uuid.uuid4()),
            "customerId": data.get("customerId", "anonymous"),
            "items": data.get("items", []),
            "status": "PENDING",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        table.put_item(Item=item)
        sfn.start_execution(
            stateMachineArn=os.environ["STATE_MACHINE_ARN"],
            input=json.dumps({"orderId": item["orderId"]}),
        )
        return response(201, item)

    if method == "GET":
        order_id = event["pathParameters"]["orderId"]
        result = table.get_item(Key={"orderId": order_id})
        if "Item" not in result:
            return response(404, {"message": "Order not found"})
        return response(200, result["Item"])

    return response(405, {"message": "Method not allowed"})
