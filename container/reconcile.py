import os
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

table = boto3.resource("dynamodb").Table(os.environ["ORDERS_TABLE"])
stale_minutes = int(os.environ.get("STALE_MINUTES", "60"))
cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()


def main():
    stale, kwargs = [], {"FilterExpression": Attr("status").eq("PENDING") & Attr("createdAt").lt(cutoff)}
    while True:
        page = table.scan(**kwargs)
        stale += page["Items"]
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    expired = 0
    for o in stale:
        try:
            table.update_item(
                Key={"orderId": o["orderId"]},
                UpdateExpression="SET #s = :e, reconciledAt = :t",
                ConditionExpression="#s = :p",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":e": "EXPIRED",
                    ":p": "PENDING",
                    ":t": datetime.now(timezone.utc).isoformat(),
                },
            )
            expired += 1
            print("Expired order " + o["orderId"])
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
    print("Reconciliation done. Scanned stale=" + str(len(stale)) + " expired=" + str(expired))


if __name__ == "__main__":
    main()
