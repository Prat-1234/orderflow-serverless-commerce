import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
orders = dynamodb.Table(os.environ["ORDERS_TABLE"])
inventory = dynamodb.Table(os.environ["INVENTORY_TABLE"])


class OutOfStock(Exception):
    pass


class PaymentDeclined(Exception):
    pass


def release_items(items):
    for line in items:
        inventory.update_item(
            Key={"sku": line["sku"]},
            UpdateExpression="SET qtyOnHand = qtyOnHand + :q",
            ExpressionAttributeValues={":q": int(line["qty"])},
        )


def reserve(event, context):
    order = orders.get_item(Key={"orderId": event["orderId"]}, ConsistentRead=True)["Item"]
    reserved = []
    total = Decimal(0)
    try:
        for line in order["items"]:
            qty = int(line["qty"])
            res = inventory.update_item(
                Key={"sku": line["sku"]},
                UpdateExpression="SET qtyOnHand = qtyOnHand - :q",
                ConditionExpression="qtyOnHand >= :q",
                ExpressionAttributeValues={":q": qty},
                ReturnValues="ALL_NEW",
            )
            reserved.append({"sku": line["sku"], "qty": qty})
            total += res["Attributes"]["unitPrice"] * qty
    except ClientError as e:
        release_items(reserved)
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise OutOfStock("Insufficient stock")
        raise
    return {
        "orderId": order["orderId"],
        "customerId": order["customerId"],
        "reserved": reserved,
        "orderTotal": int(total),
    }


def charge(event, context):
    if event["customerId"] == "fail-payment":
        raise PaymentDeclined("Card declined (simulated)")
    return {**event, "paymentId": "pay_" + event["orderId"][:8]}


def confirm(event, context):
    orders.update_item(
        Key={"orderId": event["orderId"]},
        UpdateExpression="SET #s = :s, paymentId = :p, orderTotal = :t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "CONFIRMED",
            ":p": event["paymentId"],
            ":t": event["orderTotal"],
        },
    )
    return {"orderId": event["orderId"], "status": "CONFIRMED"}


def fail(event, context):
    release_items(event.get("reserved", []))
    orders.update_item(
        Key={"orderId": event["orderId"]},
        UpdateExpression="SET #s = :s, failureReason = :r",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "FAILED",
            ":r": str(event.get("error", {}).get("Error", "unknown")),
        },
    )
    return {"orderId": event["orderId"], "status": "FAILED"}
